#!/usr/bin/env python3
"""Spike: transcribe mic (Enter to start/stop) or a wav file.

Usage:
    uv run --with ... (see below) / .venv/bin/python prototype/mic_spike.py --file <wav>
    .venv/bin/python prototype/mic_spike.py --mic   # asks before touching the mic
    Backend defaults to moonshine (--asr-backend sensevoice + --model-dir for A/B).
"""

import argparse
import os
import resource
import sys
import time
import wave
from pathlib import Path

import sherpa_onnx

ROOT = Path(__file__).resolve().parent.parent
MODEL_DIRS = {
    "moonshine": ROOT / "models" / "sherpa-onnx-moonshine-tiny-en-int8",
    "sensevoice": ROOT / "models" / "sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17",
}
MODEL_FILES = {
    "moonshine": (
        "preprocess.onnx",
        "encode.int8.onnx",
        "uncached_decode.int8.onnx",
        "cached_decode.int8.onnx",
        "tokens.txt",
    ),
    "sensevoice": ("model.int8.onnx", "tokens.txt"),
}
NUM_THREADS = 4


def rss_mb() -> float:
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024


def create_recognizer(
    backend="moonshine",
    model_dir=None,
    threads=NUM_THREADS,
) -> tuple:
    t0 = time.perf_counter()
    model_dir = Path(model_dir) if model_dir else MODEL_DIRS[backend]
    if backend == "sensevoice":
        recognizer = sherpa_onnx.OfflineRecognizer.from_sense_voice(
            model=str(model_dir / "model.int8.onnx"),
            tokens=str(model_dir / "tokens.txt"),
            num_threads=threads,
            language="en",
            use_itn=True,
        )
        return recognizer, time.perf_counter() - t0
    if backend != "moonshine":
        raise ValueError(f"unknown asr_backend: {backend!r}")
    recognizer = sherpa_onnx.OfflineRecognizer.from_moonshine(
        preprocessor=str(model_dir / "preprocess.onnx"),
        encoder=str(model_dir / "encode.int8.onnx"),
        uncached_decoder=str(model_dir / "uncached_decode.int8.onnx"),
        cached_decoder=str(model_dir / "cached_decode.int8.onnx"),
        tokens=str(model_dir / "tokens.txt"),
        num_threads=threads,
    )
    return recognizer, time.perf_counter() - t0


def read_wav(path: Path) -> tuple:
    with wave.open(str(path), "rb") as w:
        assert w.getnchannels() == 1, "need mono wav"
        assert w.getsampwidth() == 2, "need 16-bit wav"
        sr = w.getframerate()
        n = w.getnframes()
        raw = w.readframes(n)
    import numpy as np

    samples = np.frombuffer(raw, dtype=np.int16).astype("float32") / 32768.0
    return samples, sr


def decode(recognizer, samples, sample_rate: int) -> tuple:
    import numpy as np

    samples = np.asarray(samples, dtype=np.float32)
    stream = recognizer.create_stream()
    stream.accept_waveform(sample_rate, samples)
    t0 = time.perf_counter()
    recognizer.decode_stream(stream)
    dt = time.perf_counter() - t0
    return stream.result.text, dt


def record_until_enter() -> tuple:
    import threading

    import numpy as np
    import sounddevice as sd

    sr = 16000
    chunks: list = []
    stop = False

    def reader(stream) -> None:
        # Continuous blocking reads: an unread PortAudio input overflows and
        # drops data, so the mic must be drained in real time.
        while not stop:
            data, _ = stream.read(int(0.1 * sr))
            if data.size:
                chunks.append(np.asarray(data).reshape(-1))

    print("Press Enter to START recording ...", flush=True)
    input()
    print("Recording ... press Enter to STOP.", flush=True)
    with sd.InputStream(channels=1, dtype="float32", samplerate=sr) as s:
        t = threading.Thread(target=reader, args=(s,), daemon=True)
        t.start()
        input()
        stop = True
        t.join()
    samples = np.concatenate(chunks) if chunks else np.zeros(0, dtype=np.float32)
    return samples, sr


def record_fixed(secs: float) -> tuple:
    import numpy as np
    import sounddevice as sd

    sr = 16000
    print(f"Recording {secs:.0f}s ... speak now!", flush=True)
    data = sd.rec(int(secs * sr), samplerate=sr, channels=1, dtype="float32", blocking=True)
    return np.asarray(data).reshape(-1), sr


def main() -> int:
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--file", type=Path)
    g.add_argument("--mic", action="store_true")
    g.add_argument("--mic-secs", type=float, metavar="SECONDS")
    ap.add_argument("--asr-backend", default="moonshine", choices=("moonshine", "sensevoice"))
    ap.add_argument("--model-dir", type=Path, default=None)
    args = ap.parse_args()

    model_dir = args.model_dir or MODEL_DIRS[args.asr_backend]
    for f in MODEL_FILES[args.asr_backend]:
        if not (model_dir / f).exists():
            print(f"missing model file: {model_dir / f}", file=sys.stderr)
            return 1

    print(f"RSS before load: {rss_mb():.0f} MB", flush=True)
    recognizer, t_load = create_recognizer(
        backend=args.asr_backend,
        model_dir=args.model_dir,
    )
    print(f"model loaded in {t_load:.2f}s (threads={NUM_THREADS}, pid={os.getpid()})", flush=True)
    print(f"RSS loaded idle: {rss_mb():.0f} MB", flush=True)

    if args.mic:
        samples, sr = record_until_enter()
    elif args.mic_secs:
        samples, sr = record_fixed(args.mic_secs)
    else:
        samples, sr = read_wav(args.file)
    dur = len(samples) / sr
    print(f"audio: {dur:.2f}s @ {sr} Hz", flush=True)

    text, t_dec = decode(recognizer, samples, sr)
    rtf = f"{dur / t_dec:.1f}x" if t_dec > 0 else "empty"
    print(f"decode took {t_dec:.2f}s (RTF {rtf})", flush=True)
    text2, t_warm = decode(recognizer, samples, sr)
    print(f"warm decode took {t_warm:.2f}s (RTF {dur / t_warm:.1f}x)", flush=True)
    assert text2 == text, "warm decode mismatch"
    print(f"RSS peak: {rss_mb():.0f} MB", flush=True)
    print("TEXT:", text)

    del recognizer
    import gc

    gc.collect()
    print(f"RSS after unload+gc: {rss_mb():.0f} MB", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
