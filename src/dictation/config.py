"""Configuration: ~/.config/voxd/config.toml over baked-in defaults (pure merge)."""

import os
import sys
import tomllib
from pathlib import Path

DEFAULTS: dict = {
    "socket": "$XDG_RUNTIME_DIR/voxd.sock",
    "model_dir": "models/sherpa-onnx-moonshine-tiny-en-int8",
    "worker_idle_timeout": 25,  # seconds warm after last use, then worker exits
    "num_threads": 4,
    "insert_backend": "auto",  # auto | wtype | clipboard
    "dictionary": {},
    "snippets": {},
}

PATH_KEYS = {"socket", "model_dir"}

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
            if k not in DEFAULTS:
                print(f"voxd config: unknown key {k!r}, ignoring", file=sys.stderr)
                continue
            cfg[k] = _expand(v) if k in PATH_KEYS else v
    if not isinstance(cfg["num_threads"], int) or cfg["num_threads"] < 1:
        raise ValueError(
            f"voxd config: num_threads must be a positive int, got {cfg['num_threads']!r}"
        )
    timeout = cfg["worker_idle_timeout"]
    if not isinstance(timeout, (int, float)) or timeout <= 0:
        raise ValueError(f"voxd config: worker_idle_timeout must be positive, got {timeout!r}")
    if cfg["insert_backend"] not in ("auto", "wtype", "clipboard"):
        raise ValueError(f"voxd config: bad insert_backend {cfg['insert_backend']!r}")
    if "XDG_RUNTIME_DIR" not in os.environ and path == CONFIG_PATH:
        # Systemd user units always set XDG_RUNTIME_DIR, but bare contexts
        # (e.g. a compositor exec without the session env) may not. Prefer the
        # standard per-user runtime dir over /tmp so client and daemon agree.
        cfg["socket"] = "/run/user/%d/voxd.sock" % os.getuid()
    return cfg
