"""Tests for wire protocol framing, insertion command builders, config merge."""

import io
import os
import signal
import socket
import threading
import time

import pytest

from dictation import config as config_mod
from dictation import insert as insert_mod
from dictation import protocol as proto
from dictation.daemon import _drain_to_chunks


def test_control_round_trip():
    a, b = socket.socketpair()
    with a, b:
        proto.send_json(a, {"cmd": "stop"})
        f = b.makefile("rb")
        assert proto.recv_json(f.readline()) == {"cmd": "stop"}


def test_binary_framing():
    pcm = b"\x00" * 160
    stream = io.BytesIO(proto.pack_pcm(pcm))
    assert proto.read_frame(stream) == pcm
    stream = io.BytesIO(proto.pack_text("héllo"))
    assert proto.read_frame(stream) == "héllo".encode()


def test_short_read_raises():
    with pytest.raises(EOFError):
        proto.read_frame(io.BytesIO(b"\x00\x01"))


def test_zero_length_frame_is_empty():
    stream = io.BytesIO(proto.pack_text(""))
    assert proto.read_frame(stream) == b""


def test_oversize_frame_rejected():
    big = proto._LEN.pack(proto.MAX_PCM_BYTES + 1)
    with pytest.raises(ValueError):
        proto.read_frame(io.BytesIO(big))


def test_bind_refuses_live_socket(tmp_path):
    from dictation import protocol as proto2

    sock_path = str(tmp_path / "live.sock")
    srv = proto2.bind_unix_socket(sock_path)
    try:
        with pytest.raises(RuntimeError):
            proto2.bind_unix_socket(sock_path)
    finally:
        srv.close()
    # Stale file (no listener) is replaced.
    srv2 = proto2.bind_unix_socket(sock_path)
    srv2.close()


def test_bind_restricts_permissions(tmp_path):
    import stat

    sock_path = str(tmp_path / "perm.sock")
    srv = proto.bind_unix_socket(sock_path)
    try:
        mode = stat.S_IMODE(os.stat(sock_path).st_mode)
        assert mode & 0o077 == 0, oct(mode)
    finally:
        srv.close()


def test_builders_do_not_contain_text_in_argv():
    # Text travels via stdin so argv stays clean (no secrets in ps output).
    assert "secret" not in " ".join(insert_mod.build_wtype_cmd("secret"))
    copy, paste = insert_mod.build_clipboard_cmds()
    assert "secret" not in " ".join(copy + paste)


def test_available_returns_known_backend():
    assert insert_mod.available() in ("wtype", "clipboard", "none")


def test_drain_keeps_up_with_producer():
    # The recorder writes continuously; the daemon must drain concurrently or
    # the 64 KB pipe stalls and mic audio is dropped (truncated transcripts).
    r, w = os.pipe()
    chunks: list = []
    t = threading.Thread(target=_drain_to_chunks, args=(os.fdopen(r, "rb"), chunks))
    t.start()
    with os.fdopen(w, "wb") as f:
        for _ in range(100):
            f.write(b"\x00" * 8192)  # 800 KB total, far past the pipe buffer
    t.join(timeout=10)
    assert not t.is_alive()
    assert b"".join(chunks) == b"\x00" * (100 * 8192)


def test_toggle_starts_when_idle(monkeypatch, capsys):
    from dictation import client as client_mod

    calls = []

    def fake_toggle_call(sock, req, timeout=60):
        calls.append(req)
        return {"ok": True, "state": "idle"}

    monkeypatch.setattr(client_mod, "call", fake_toggle_call)
    assert client_mod.main(["toggle", "--socket", "/nonexistent"]) == 0
    assert [r["cmd"] for r in calls] == ["status", "start"]


def test_toggle_stops_when_recording(monkeypatch, capsys):
    from dictation import client as client_mod

    calls = []

    def fake_call(sock, req, timeout=60):
        calls.append(req)
        if req["cmd"] == "status":
            return {"ok": True, "state": "recording"}
        return {"ok": True, "text": "hello"}

    monkeypatch.setattr(client_mod, "call", fake_call)
    assert client_mod.main(["toggle", "--socket", "/nonexistent"]) == 0
    assert [r["cmd"] for r in calls] == ["status", "stop"]
    assert capsys.readouterr().out == "hello\n"


def _run_daemon_thread(sock_path: str, cfg: dict) -> threading.Thread:
    from dictation import daemon as daemon_mod

    t = threading.Thread(target=daemon_mod.run, args=(sock_path, cfg))
    t.daemon = True  # accept loop would otherwise hang the test session
    t.start()
    for _ in range(100):
        if os.path.exists(sock_path):
            return t
        time.sleep(0.05)
    raise RuntimeError("daemon did not bind")


def _daemon_cfg(sock_path: str, tmp_path) -> dict:
    return {
        "socket": sock_path,
        "model_dir": str(tmp_path),
        "worker_idle_timeout": 5,
        "num_threads": 1,
        "insert_backend": "none",
        "dictionary": {},
        "snippets": {},
    }


class _FakeProc:
    def __init__(self, _chunks=None, crashed=False):
        self.returncode = 2 if crashed else None

    def poll(self):
        return self.returncode

    def terminate(self):
        if self.returncode is None:
            self.returncode = -signal.SIGTERM

    def kill(self):
        self.returncode = -signal.SIGKILL

    def wait(self, timeout=None):
        return self.returncode


class _DoneThread:
    def join(self, timeout=None):
        pass


def test_status_answers_during_slow_stop(monkeypatch, tmp_path):
    # Finding #1: transcription must not wedge the accept loop.
    from dictation import client as client_mod
    from dictation import daemon as daemon_mod

    sock_path = str(tmp_path / "d.sock")
    pcm = b"\x00" * 16000  # 0.25 s of silence
    monkeypatch.setattr(
        daemon_mod,
        "_spawn_recorder",
        lambda: (_FakeProc([]), [pcm], _DoneThread()),
    )

    def slow_transcribe(cfg, state, pcm_bytes):
        time.sleep(2)
        return "hello", 2.0

    monkeypatch.setattr(daemon_mod, "_transcribe", slow_transcribe)
    monkeypatch.setattr(daemon_mod.insert_mod, "insert", lambda text, backend="auto": "wtype")
    _run_daemon_thread(sock_path, _daemon_cfg(sock_path, tmp_path))

    results = {}
    assert client_mod.call(sock_path, {"cmd": "start"}) == {"ok": True}
    t = threading.Thread(
        target=lambda: results.setdefault("stop", client_mod.call(sock_path, {"cmd": "stop"}))
    )
    t.start()
    time.sleep(0.3)  # let stop enter the slow transcribe
    t0 = time.monotonic()
    status = client_mod.call(sock_path, {"cmd": "status"})
    status_latency = time.monotonic() - t0
    t.join(timeout=15)
    assert status == {"ok": True, "state": "idle", "worker": "cold"}
    assert status_latency < 1.5, status_latency
    assert results["stop"]["text"] == "Hello"  # cleanup capitalizes


def test_stop_rejects_overlong_utterance(monkeypatch, tmp_path):
    from dictation import client as client_mod
    from dictation import daemon as daemon_mod
    from dictation import protocol as proto2

    sock_path = str(tmp_path / "d2.sock")
    huge = [b"\x00" * (proto2.MAX_PCM_BYTES + 4)]
    monkeypatch.setattr(daemon_mod, "_spawn_recorder", lambda: (_FakeProc([]), huge, _DoneThread()))
    _run_daemon_thread(sock_path, _daemon_cfg(sock_path, tmp_path))
    assert client_mod.call(sock_path, {"cmd": "start"}) == {"ok": True}
    resp = client_mod.call(sock_path, {"cmd": "stop"})
    assert resp["ok"] is False
    assert "too long" in resp["error"]


def test_config_defaults_and_override(tmp_path):
    cfg = config_mod.load(path=tmp_path / "missing.toml")
    assert cfg["num_threads"] == 4
    assert cfg["dictionary"] == {}
    p = tmp_path / "config.toml"
    p.write_text('num_threads = 2\n[snippets]\nmyemail = "me@example.com"\n')
    cfg = config_mod.load(path=p)
    assert cfg["num_threads"] == 2
    assert cfg["snippets"] == {"myemail": "me@example.com"}
    assert cfg["worker_idle_timeout"] == 25  # default preserved


def test_config_unknown_key_warns(tmp_path, capsys):
    p = tmp_path / "config.toml"
    p.write_text("num_thread = 2\n")  # typo, not a real key
    cfg = config_mod.load(path=p)
    assert cfg["num_threads"] == 4
    assert "unknown key" in capsys.readouterr().err


def test_config_bad_values_rejected(tmp_path):
    bodies = (
        "num_threads = 0\n",
        "worker_idle_timeout = -5\n",
        'insert_backend = "x"\n',
    )
    for body in bodies:
        p = tmp_path / "bad.toml"
        p.write_text(body)
        with pytest.raises(ValueError):
            config_mod.load(path=p)


def test_config_removed_keys_warn_as_unknown(tmp_path, capsys):
    # Transducer-era keys were retired with the backend; configs still
    # carrying them warn instead of failing.
    p = tmp_path / "old.toml"
    p.write_text('hotwords_file = "words.txt"\n')
    cfg = config_mod.load(path=p)
    assert "unknown key" in capsys.readouterr().err
    assert "hotwords_file" not in cfg


def test_config_snippet_dollar_preserved(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text('[snippets]\n"show home" = "echo $HOME"\n')
    cfg = config_mod.load(path=p)
    assert cfg["snippets"] == {"show home": "echo $HOME"}


def test_call_times_out(tmp_path):
    from dictation import client as client_mod

    srv = proto.bind_unix_socket(str(tmp_path / "blackhole.sock"))
    threading.Thread(target=srv.accept, daemon=True).start()
    with pytest.raises(OSError):
        client_mod.call(str(tmp_path / "blackhole.sock"), {"cmd": "status"}, timeout=0.3)
    srv.close()


def test_worker_drops_half_open_connection(tmp_path):
    import struct

    from dictation import worker as worker_mod

    sock_path = str(tmp_path / "halfopen.sock")
    t = threading.Thread(target=worker_mod.serve, args=(sock_path, None, 30, 1))
    t.daemon = True
    t.start()
    for _ in range(100):
        if os.path.exists(sock_path):
            break
        time.sleep(0.05)
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    with s:
        s.connect(sock_path)
        f = s.makefile("rwb")
        f.write(struct.pack(">Q", 100))  # length prefix, then silence forever
        f.flush()
        time.sleep(2)
        assert f.read() == b""  # worker closed the connection


def _fake_worker_once(sock_path: str, text: str = "hi") -> None:
    srv = proto.bind_unix_socket(sock_path)

    def _run():
        conn, _ = srv.accept()
        with conn:
            f = conn.makefile("rwb")
            try:
                proto.read_frame(f)
            except Exception:
                return
            f.write(proto.pack_text(text))
            f.flush()
        srv.close()

    threading.Thread(target=_run, daemon=True).start()


def _transcribe_cfg(sock_path: str) -> dict:
    return {
        "socket": sock_path,
        "model_dir": "",
        "worker_idle_timeout": 5,
        "num_threads": 1,
        "insert_backend": "none",
        "dictionary": {},
        "snippets": {},
    }


def test_transcribe_retries_dead_worker(monkeypatch, tmp_path):
    from dictation import daemon as daemon_mod

    sock_path = str(tmp_path / "r.sock")
    calls = []

    def flaky_ensure(cfg, state):
        calls.append(1)
        if len(calls) == 1:
            raise OSError("worker gone")
        _fake_worker_once(cfg["socket"] + ".worker")

    monkeypatch.setattr(daemon_mod, "_ensure_worker", flaky_ensure)
    text, _ = daemon_mod._transcribe(_transcribe_cfg(sock_path), {}, b"\x00" * 16000)
    assert text == "hi"
    assert len(calls) == 2


def test_stop_reports_crashed_recorder(monkeypatch, tmp_path):
    # Finding #12: a mic failure must surface its reason, not read as silence.
    from dictation import client as client_mod
    from dictation import daemon as daemon_mod

    sock_path = str(tmp_path / "d3.sock")
    monkeypatch.setattr(
        daemon_mod, "_spawn_recorder", lambda: (_FakeProc(crashed=True), [], _DoneThread())
    )
    _run_daemon_thread(sock_path, _daemon_cfg(sock_path, tmp_path))
    assert client_mod.call(sock_path, {"cmd": "start"}) == {"ok": True}
    resp = client_mod.call(sock_path, {"cmd": "stop"})
    assert resp["ok"] is False
    assert "recorder failed" in resp["error"]


def test_transcribe_gives_up_loudly(monkeypatch, tmp_path):
    from dictation import daemon as daemon_mod

    def dead_ensure(cfg, state):
        raise OSError("no worker")

    monkeypatch.setattr(daemon_mod, "_ensure_worker", dead_ensure)
    with pytest.raises(RuntimeError, match="transcribe-failed"):
        daemon_mod._transcribe(_transcribe_cfg(str(tmp_path / "r2.sock")), {}, b"")
