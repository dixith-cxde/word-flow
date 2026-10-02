"""Silence trimming via silero VAD (thin orchestration over a sherpa detector).

Feed audio in small windows: a single bulk accept_waveform() call starves the
detector (measured: 5k/106k samples kept), while 0.1 s streaming windows keep
the speech (100k/106k). The worker owns one detector and resets it per request;
serve() is single-threaded so no locking is needed.
"""

import numpy as np
import sherpa_onnx

from dictation import protocol as proto

_WINDOW_S = 0.1


def create_detector(model_path: str, num_threads: int = 1):
    """Load the VAD model once. Raises if the file is missing or invalid."""
    config = sherpa_onnx.VadModelConfig(
        silero_vad=sherpa_onnx.SileroVadModelConfig(model=model_path),
        sample_rate=proto.SAMPLE_RATE,
        num_threads=num_threads,
    )
    return sherpa_onnx.VoiceActivityDetector(config)


def trim_silence(pcm: bytes, detector) -> bytes:
    """Return only VAD speech segments. None detector or empty input passes through."""
    if detector is None or not pcm:
        return pcm
    samples = np.frombuffer(pcm, dtype=np.float32)
    step = int(proto.SAMPLE_RATE * _WINDOW_S)
    detector.reset()
    for i in range(0, len(samples), step):
        detector.accept_waveform(samples[i : i + step])
    detector.flush()
    parts = []
    while not detector.empty():
        parts.append(np.asarray(detector.front.samples, dtype=np.float32))
        detector.pop()
    if not parts:
        return b""
    return np.concatenate(parts).tobytes()
