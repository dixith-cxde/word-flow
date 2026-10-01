"""Tests for wire protocol framing, insertion command builders, config merge."""

import io
import os
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
    monkeypatch.setattr(
        client_mod, "call", lambda sock, req: calls.append(req) or {"ok": True, "state": "idle"}
    )
    assert client_mod.main(["toggle", "--socket", "/nonexistent"]) == 0
    assert [r["cmd"] for r in calls] == ["status", "start"]


def test_toggle_stops_when_recording(monkeypatch, capsys):
    from dictation import client as client_mod

    calls = []

    def fake_call(sock, req):
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
    def __init__(self, chunks: list):
        self._chunks = chunks

    def poll(self):
        return None

    def terminate(self):
        pass

    def kill(self):
        pass

    def wait(self, timeout=None):
        return 0


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
