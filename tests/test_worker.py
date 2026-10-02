"""Worker integration test: bundled moonshine wav PCM -> text (no mic, no daemon)."""

import os
import socket
import subprocess
import sys
import tempfile
import wave

import numpy as np
import pytest

from dictation import protocol as proto

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODEL_DIR = os.path.join(REPO_ROOT, "models", "sherpa-onnx-moonshine-tiny-en-int8")
WAV = os.path.join(MODEL_DIR, "test_wavs", "0.wav")

needs_models = pytest.mark.skipif(
    not (os.path.isdir(MODEL_DIR) and os.path.isfile(WAV)),
    reason="model files not downloaded (see install.sh --with-models)",
)


def _wav_pcm_16k(path: str) -> bytes:
    with wave.open(path, "rb") as w:
        assert w.getnchannels() == 1 and w.getsampwidth() == 2
        sr = w.getframerate()
        raw = w.readframes(w.getnframes())
    assert sr == 16000  # moonshine test wavs are native 16 kHz
    samples = np.frombuffer(raw, dtype=np.int16).astype("float32") / 32768.0
    return samples.tobytes()


@needs_models
def test_worker_transcribes_bundled_sample():
    pcm = _wav_pcm_16k(WAV)
    with tempfile.TemporaryDirectory() as d:
        sock = os.path.join(d, "w.sock")
        proc = subprocess.Popen(
            [
                sys.executable,
                os.path.join(REPO_ROOT, "src", "dictation", "worker.py"),
                "--socket",
                sock,
                "--model-dir",
                MODEL_DIR,
                "--threads",
                "2",
                "--idle-timeout",
                "60",
                "--asr-backend",
                "moonshine",
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
        )
        try:
            for _ in range(600):  # wait for cold load (~1 s)
                if os.path.exists(sock):
                    break
                if proc.poll() is not None:
                    raise RuntimeError("worker exited during load")
                __import__("time").sleep(0.1)
            s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            with s:
                s.connect(sock)
                f = s.makefile("rwb")
                f.write(proto.pack_pcm(pcm))
                f.flush()
                text = proto.read_frame(f).decode()
            assert "yellow lamps" in text
        finally:
            proc.terminate()
            proc.wait(timeout=30)


def test_create_recognizer_rejects_unknown_backend():
    from types import SimpleNamespace

    from dictation import worker as worker_mod

    with pytest.raises(ValueError, match="unknown asr_backend"):
        worker_mod.create_recognizer("/nonexistent", 1, SimpleNamespace(asr_backend="whisper"))
