"""voxd: hold-to-talk dictation daemon. Stdlib only — stays small while idle.

START (key down) spawns the recorder (mic -> pipe). STOP (key up) terminates it,
pipes the utterance to the model worker, cleans the text, and inserts it into the
focused app. The worker exits after its idle timeout, returning memory to the OS.
Audio and transcripts live in pipes/memory only; only sizes and timings are logged.
"""

import argparse
import json
import os
import signal
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

from dictation import cleanup, config as config_mod
from dictation import insert as insert_mod
from dictation import protocol as proto

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent.parent  # src/dictation -> repo root


def _drain_to_chunks(stream, chunks: list) -> None:
    """Copy a pipe to chunks until EOF. Runs in a thread while recording, so a
    full 64 KB pipe can never stall the recorder and drop mic audio."""
    while True:
        data = stream.read(65536)
        if not data:
            break
        chunks.append(data)


def _spawn_recorder() -> tuple:
    proc = subprocess.Popen(
        [sys.executable, str(HERE / "recorder.py"), "--sample-rate", str(proto.SAMPLE_RATE)],
        stdout=subprocess.PIPE,
        stdin=subprocess.DEVNULL,
    )
    chunks: list = []
    thread = threading.Thread(target=_drain_to_chunks, args=(proc.stdout, chunks))
    thread.start()
    return proc, chunks, thread


def _worker_sock_path(cfg: dict) -> str:
    return cfg["socket"] + ".worker"


def _reap(proc, thread, timeout: float = 10) -> None:
    """Wait out a terminated child and its drain thread: no zombies, no leaked fds."""
    try:
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        try:
            proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            pass
    if thread is not None:
        thread.join(timeout=timeout)


def _resolve(path: str) -> str:
    if path and not os.path.isabs(path):
        return str(REPO_ROOT / path)
    return path


def _ensure_worker(cfg: dict, state: dict) -> None:
    proc = state.get("worker_proc")
    if proc is not None and proc.poll() is None and os.path.exists(_worker_sock_path(cfg)):
        return
    model_dir = _resolve(cfg["model_dir"])
    state["worker_proc"] = subprocess.Popen(
        [
            sys.executable,
            str(HERE / "worker.py"),
            "--socket",
            _worker_sock_path(cfg),
            "--model-dir",
            model_dir,
            "--threads",
            str(cfg["num_threads"]),
            "--idle-timeout",
            str(cfg["worker_idle_timeout"]),
        ],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
    )
    deadline = time.time() + 180
    while not os.path.exists(_worker_sock_path(cfg)):
        if state["worker_proc"].poll() is not None:
            raise RuntimeError("worker exited during load")
        if time.time() > deadline:
            raise RuntimeError("worker did not come up in time")
        time.sleep(0.1)
    # Brief pause: socket file appears at bind(), connect retries below cover listen().
    for _ in range(50):
        try:
            s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            s.connect(_worker_sock_path(cfg))
            s.close()
            return
        except OSError:
            time.sleep(0.1)
    raise RuntimeError("worker socket not accepting connections")


def _transcribe(cfg: dict, state: dict, pcm: bytes) -> tuple[str, float]:
    """Decode via the worker, with one reconnect-and-retry on transport errors.

    The worker can die between the liveness check and connect(); retry once
    against a freshly spawned worker before giving up loudly (never silently).
    """
    last: Exception | None = None
    for _ in range(2):
        try:
            _ensure_worker(cfg, state)
            t0 = time.perf_counter()
            s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            with s:
                s.connect(_worker_sock_path(cfg))
                f = s.makefile("rwb")
                f.write(proto.pack_pcm(pcm))
                f.flush()
                text = proto.read_frame(f).decode()
            return text, time.perf_counter() - t0
        except OSError as e:
            last = e
            wproc = state.pop("worker_proc", None)
            if wproc is not None and wproc.poll() is None:
                wproc.terminate()
    raise RuntimeError(f"transcribe-failed: {last}")


def _handle(cfg: dict, state: dict, req: dict) -> dict:
    cmd = req.get("cmd")
    if cmd == "status":
        with state["lock"]:
            rec = state.get("recorder")
            alive = rec is not None and rec.poll() is None
            wproc = state.get("worker_proc")
            warm = wproc is not None and wproc.poll() is None
        return {
            "ok": True,
            "state": "recording" if alive else "idle",
            "worker": "warm" if warm else "cold",
        }
    if cmd == "start":
        with state["lock"]:
            rec = state.get("recorder")
            if rec is not None and rec.poll() is None:
                return {"ok": False, "error": "already recording"}
            proc, chunks, thread = _spawn_recorder()
            state["recorder"] = proc
            state["rec_chunks"] = chunks
            state["rec_thread"] = thread
        return {"ok": True}
    if cmd == "stop":
        with state["lock"]:
            proc = state.pop("recorder", None)
            chunks = state.pop("rec_chunks", [])
            thread = state.pop("rec_thread", None)
        if proc is None:
            return {"ok": False, "error": "not recording"}
        if proc.poll() is None:
            proc.terminate()
        _reap(proc, thread)
        if proc.returncode not in (-signal.SIGTERM, -signal.SIGINT):
            return {
                "ok": False,
                "error": f"recorder failed (exit {proc.returncode}); "
                "see journal for RECORDER_ERROR",
            }
        pcm = b"".join(chunks)
        dur_s = len(pcm) / 4 / proto.SAMPLE_RATE
        if len(pcm) > proto.MAX_PCM_BYTES:
            return {
                "ok": False,
                "error": f"utterance too long ({dur_s:.0f}s > {proto.MAX_UTTERANCE_S}s), discarded",
            }
        if not pcm:
            return {"ok": False, "error": "no audio captured"}
        text, decode_s = _transcribe(cfg, state, pcm)
        cleaned = cleanup.clean(text, cfg.get("dictionary"), cfg.get("snippets"))
        try:
            backend = insert_mod.insert(cleaned, cfg.get("insert_backend", "auto"))
        except Exception as e:  # keep the text even if insertion fails
            return {
                "ok": True,
                "text": cleaned,
                "backend": "failed",
                "warning": str(e),
                "decode_s": round(decode_s, 2),
            }
        print(json.dumps({"decode_s": round(decode_s, 2), "pcm_bytes": len(pcm)}), flush=True)
        return {"ok": True, "text": cleaned, "backend": backend, "decode_s": round(decode_s, 2)}
    return {"ok": False, "error": f"unknown cmd: {cmd}"}


def _serve_conn(conn, cfg: dict, state: dict) -> None:
    # One thread per connection: slow work (transcribe/insert) here never blocks
    # the accept loop, so status/start stay responsive mid-transcription.
    # Recorder control inside _handle takes state["lock"]; the slow tail runs free.
    with conn:
        f = conn.makefile("rwb")
        line = f.readline()
        if not line:
            return
        try:
            req = proto.recv_json(line)
        except ValueError:
            resp = {"ok": False, "error": "bad json"}
        else:
            try:
                resp = _handle(cfg, state, req)
            except Exception as e:
                resp = {"ok": False, "error": str(e)}
        f.write((json.dumps(resp) + "\n").encode())
        f.flush()


def run(sock_path: str, cfg: dict) -> int:
    try:
        srv = proto.bind_unix_socket(sock_path)
    except RuntimeError as e:
        print(f"voxd: {e}", flush=True)
        return 1
    srv.listen(8)
    state: dict = {"lock": threading.Lock()}
    print(f"voxd listening on {sock_path}", flush=True)
    try:
        while True:
            conn, _ = srv.accept()
            t = threading.Thread(target=_serve_conn, args=(conn, cfg, state))
            t.daemon = True
            t.start()
    except KeyboardInterrupt:
        pass
    finally:
        with state["lock"]:
            rec = state.pop("recorder", None)
            thread = state.pop("rec_thread", None)
            wproc = state.pop("worker_proc", None)
        if rec is not None:
            if rec.poll() is None:
                rec.terminate()
            _reap(rec, thread)
        if wproc is not None:
            if wproc.poll() is None:
                wproc.terminate()
            _reap(wproc, None)
        srv.close()
        for p in (sock_path, sock_path + ".worker"):
            if os.path.exists(p):
                os.unlink(p)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=None)
    args = ap.parse_args()
    cfg = config_mod.load(Path(args.config).expanduser() if args.config else None)

    def _stop(signum, frame):
        raise KeyboardInterrupt

    # Process-global signal state belongs in the entry point, not run(), so run()
    # stays callable from any thread (tests run it in a background thread).
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    return run(cfg["socket"], cfg)


if __name__ == "__main__":
    raise SystemExit(main())
