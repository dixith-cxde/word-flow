"""Tests for wire protocol framing, insertion command builders, config merge."""

import io
import os
import socket
import threading

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


def test_builders_do_not_contain_text_in_argv():
    # Text travels via stdin so argv stays clean (no secrets in ps output).
    assert "secret" not in " ".join(insert_mod.build_wtype_cmd("secret"))
    copy, paste = insert_mod.build_clipboard_cmds("secret")
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


def test_config_defaults_and_override(tmp_path):
    cfg = config_mod.load(path=tmp_path / "missing.toml")
    assert cfg["num_threads"] == 4
    assert cfg["dictionary"] == {}
    p = tmp_path / "config.toml"
    p.write_text('num_threads = 2\n[snippets]\nmyemail = "me@example.com"\n')
    cfg = config_mod.load(path=p)
    assert cfg["num_threads"] == 2
    assert cfg["snippets"] == {"myemail": "me@example.com"}
    assert cfg["worker_idle_timeout"] == 60  # default preserved
