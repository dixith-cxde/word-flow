"""Wire protocols (pure helpers, no I/O side effects beyond the given socket).

Control protocol (daemon <-> client): newline-delimited JSON, one request per
connection, one JSON reply. Sample rate is fixed at 16 kHz mono float32.
"""

import json
import os
import socket
import struct
from typing import Any

SAMPLE_RATE = 16000
MAX_UTTERANCE_S = 120
MAX_PCM_BYTES = MAX_UTTERANCE_S * SAMPLE_RATE * 4  # f32le mono: 7_680_000

_LEN = struct.Struct(">Q")


def send_json(sock, obj: dict[str, Any]) -> None:
    sock.sendall((json.dumps(obj) + "\n").encode())


def recv_json(line: bytes) -> dict[str, Any]:
    return json.loads(line.decode())


def pack_pcm(samples: bytes) -> bytes:
    """Frame raw f32le PCM for the worker: u64 length + bytes."""
    return _LEN.pack(len(samples)) + samples


def pack_text(text: str) -> bytes:
    data = text.encode()
    return _LEN.pack(len(data)) + data


def read_exact(stream, n: int) -> bytes:
    buf = bytearray()
    while len(buf) < n:
        chunk = stream.read(n - len(buf))
        if not chunk:
            raise EOFError("short read")
        buf += chunk
    return bytes(buf)


def read_frame(stream) -> bytes:
    (n,) = _LEN.unpack(read_exact(stream, _LEN.size))
    if n == 0:
        return b""
    if n > MAX_PCM_BYTES:
        raise ValueError(f"frame too large: {n} bytes")
    return read_exact(stream, n)


def bind_unix_socket(path: str, backlog: int = 8) -> socket.socket:
    """Bind a listening unix socket safely: refuse to steal a live peer, restrict perms.

    Tries connecting first; only unlinks a stale socket (connection refused).
    Creates the socket under umask 077 so other local users cannot drive it.
    """
    probe = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        probe.connect(path)
    except OSError:
        if os.path.exists(path):
            os.unlink(path)
    else:
        probe.close()
        raise RuntimeError(f"already running (socket live): {path}")
    finally:
        probe.close()
    old = os.umask(0o077)
    try:
        srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        srv.bind(path)
        srv.listen(backlog)
    finally:
        os.umask(old)
    return srv
