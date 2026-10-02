"""Unit tests for VAD silence trimming (needs silero model file)."""

import os

import numpy as np
import pytest

from dictation import vad as vad_mod

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VAD_MODEL = os.path.join(REPO_ROOT, "models", "silero_vad.onnx")
WAV = os.path.join(REPO_ROOT, "models", "sherpa-onnx-moonshine-tiny-en-int8", "test_wavs", "0.wav")

needs_vad = pytest.mark.skipif(
    not os.path.isfile(VAD_MODEL),
    reason="silero vad model not downloaded (see install.sh --with-models)",
)


def _pcm(seconds: float, value: float = 0.0) -> bytes:
    return np.full(int(16000 * seconds), value, dtype=np.float32).tobytes()


@needs_vad
def test_silence_trims_to_empty():
    detector = vad_mod.create_detector(VAD_MODEL)
    assert vad_mod.trim_silence(_pcm(1.0), detector) == b""


@needs_vad
def test_speech_survives_trim():
    import wave

    with wave.open(WAV, "rb") as w:
        raw = w.readframes(w.getnframes())
    pcm = (np.frombuffer(raw, dtype=np.int16).astype("float32") / 32768.0).tobytes()
    detector = vad_mod.create_detector(VAD_MODEL)
    trimmed = vad_mod.trim_silence(pcm, detector)
    assert trimmed  # speech must survive
    assert len(trimmed) <= len(pcm)


def test_none_detector_passes_through():
    pcm = _pcm(0.5)
    assert vad_mod.trim_silence(pcm, None) == pcm
    assert vad_mod.trim_silence(b"", None) == b""
