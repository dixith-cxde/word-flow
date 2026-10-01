"""Configuration: ~/.config/voxd/config.toml over baked-in defaults (pure merge)."""

import os
import tomllib
from pathlib import Path

DEFAULTS: dict = {
    "socket": "$XDG_RUNTIME_DIR/voxd.sock",
    "model_dir": "models/sherpa-onnx-nemo-parakeet-tdt-0.6b-v3-int8",
    "vad_model": "models/silero_vad.onnx",
    "worker_idle_timeout": 60,
    "num_threads": 4,
    "insert_backend": "auto",  # auto | wtype | clipboard
    "dictionary": {},
    "snippets": {},
}

CONFIG_PATH = Path("~/.config/voxd/config.toml").expanduser()


def _expand(value):
    if isinstance(value, str):
        return os.path.expandvars(os.path.expanduser(value))
    return value


def load(path: Path | None = None) -> dict:
    cfg = {k: _expand(v) for k, v in DEFAULTS.items()}
    path = path or CONFIG_PATH
    if path.exists():
        with open(path, "rb") as f:
            user = tomllib.load(f)
        for k, v in user.items():
            cfg[k] = _expand(v)
    if "XDG_RUNTIME_DIR" not in os.environ and path == CONFIG_PATH:
        cfg["socket"] = "/tmp/voxd-%d.sock" % os.getuid()
    return cfg
