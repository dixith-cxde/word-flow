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


def create_recognizer(model_dir: str, num_threads: int, args) -> object:
    return sherpa_onnx.OfflineRecognizer.from_transducer(
        encoder=os.path.join(model_dir, "encoder.int8.onnx"),
        decoder=os.path.join(model_dir, "decoder.int8.onnx"),
        joiner=os.path.join(model_dir, "joiner.int8.onnx"),
        tokens=os.path.join(model_dir, "tokens.txt"),
        num_threads=num_threads,
        sample_rate=proto.SAMPLE_RATE,
        feature_dim=80,
        decoding_method=args.decoding_method,
        max_active_paths=args.max_active_paths,
        hotwords_file=args.hotwords_file,
        hotwords_score=args.hotwords_score,
        modeling_unit=args.modeling_unit,
        bpe_vocab=args.bpe_vocab,
        model_type="nemo_transducer",
        provider="cpu",
    )


def serve(sock_path: str, recognizer, idle_timeout: float, conn_timeout: float = 30) -> None:
    srv = proto.bind_unix_socket(sock_path)
    srv.listen(1)
    srv.settimeout(idle_timeout)
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
    ap.add_argument("--decoding-method", default="greedy_search")
    ap.add_argument("--hotwords-file", default="")
    ap.add_argument("--hotwords-score", type=float, default=1.5)
    ap.add_argument("--max-active-paths", type=int, default=4)
    ap.add_argument("--modeling-unit", default="")
    ap.add_argument("--bpe-vocab", default="")
    args = ap.parse_args()
    recognizer = create_recognizer(args.model_dir, args.threads, args)
    serve(args.socket, recognizer, args.idle_timeout, args.conn_timeout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
