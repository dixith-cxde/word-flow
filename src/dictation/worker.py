"""Model worker: loads Moonshine-tiny once, serves PCM->text over a unix socket.

Exits after --idle-timeout seconds without a request, so memory returns to the OS.
One request per connection: u64 PCM byte length + f32le mono 16 kHz samples;
reply: u64 length + UTF-8 text. Never logs audio or transcripts.
"""

import argparse
import os
import socket

import numpy as np
import sherpa_onnx

from dictation import protocol as proto
from dictation import vad as vad_mod


def create_recognizer(model_dir: str, num_threads: int) -> object:
    return sherpa_onnx.OfflineRecognizer.from_moonshine(
        preprocessor=os.path.join(model_dir, "preprocess.onnx"),
        encoder=os.path.join(model_dir, "encode.int8.onnx"),
        uncached_decoder=os.path.join(model_dir, "uncached_decode.int8.onnx"),
        cached_decoder=os.path.join(model_dir, "cached_decode.int8.onnx"),
        tokens=os.path.join(model_dir, "tokens.txt"),
        num_threads=num_threads,
    )


def serve(
    sock_path: str,
    recognizer,
    idle_timeout: float,
    conn_timeout: float = 30,
    vad_model: str = "",
) -> None:
    srv = proto.bind_unix_socket(sock_path)
    srv.listen(1)
    srv.settimeout(idle_timeout)
    detector = vad_mod.create_detector(vad_model) if vad_model else None
    while True:
        try:
            conn, _ = srv.accept()
        except socket.timeout:
            return  # idle timeout: exit, memory back to the OS
        conn.settimeout(conn_timeout)  # a half-open peer must not pin ~800 MB
        with conn:
            f = conn.makefile("rwb")
            try:
                pcm = proto.read_frame(f)
            except (EOFError, ValueError, socket.timeout):
                continue
            pcm = vad_mod.trim_silence(pcm, detector)
            if not pcm:  # silence only: reply empty, daemon reports it, nothing inserted
                f.write(proto.pack_text(""))
                f.flush()
                continue
            samples = np.frombuffer(pcm, dtype=np.float32)
            stream = recognizer.create_stream()
            stream.accept_waveform(proto.SAMPLE_RATE, samples)
            recognizer.decode_stream(stream)
            f.write(proto.pack_text(stream.result.text))
            f.flush()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--socket", required=True)
    ap.add_argument("--model-dir", required=True)
    ap.add_argument("--threads", type=int, default=4)
    ap.add_argument("--idle-timeout", type=float, default=60)
    ap.add_argument("--conn-timeout", type=float, default=30)
    ap.add_argument("--vad-model", default="")
    args = ap.parse_args()
    recognizer = create_recognizer(args.model_dir, args.threads)
    serve(args.socket, recognizer, args.idle_timeout, args.conn_timeout, args.vad_model)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
