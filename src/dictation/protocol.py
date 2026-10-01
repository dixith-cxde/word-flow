"""Wire protocols (pure helpers, no I/O side effects beyond the given socket).

Control protocol (daemon <-> client): newline-delimited JSON, one request per
connection, one JSON reply. Sample rate is fixed at 16 kHz mono float32.
"""

import json
import struct
from typing import Any

SAMPLE_RATE = 16000

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
    return read_exact(stream, n)
