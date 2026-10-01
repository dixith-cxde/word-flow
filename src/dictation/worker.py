"""Model worker: loads Parakeet once, serves PCM->text over a unix socket.

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


def create_recognizer(model_dir: str, num_threads: int):
    return sherpa_onnx.OfflineRecognizer.from_transducer(
        encoder=os.path.join(model_dir, "encoder.int8.onnx"),
        decoder=os.path.join(model_dir, "decoder.int8.onnx"),
        joiner=os.path.join(model_dir, "joiner.int8.onnx"),
        tokens=os.path.join(model_dir, "tokens.txt"),
        num_threads=num_threads,
        sample_rate=proto.SAMPLE_RATE,
        feature_dim=80,
        decoding_method="greedy_search",
        model_type="nemo_transducer",
        provider="cpu",
    )


def serve(sock_path: str, recognizer, idle_timeout: float) -> None:
    if os.path.exists(sock_path):
        os.unlink(sock_path)
    srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    srv.bind(sock_path)
    srv.listen(1)
    srv.settimeout(idle_timeout)
    while True:
        try:
            conn, _ = srv.accept()
        except socket.timeout:
            return  # idle timeout: exit, memory back to the OS
        with conn:
            f = conn.makefile("rwb")
            try:
                pcm = proto.read_frame(f)
            except EOFError:
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
    args = ap.parse_args()
    recognizer = create_recognizer(args.model_dir, args.threads)
    serve(args.socket, recognizer, args.idle_timeout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
