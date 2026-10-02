"""vox: control client for voxd (stdlib only). Usage: vox start|stop|status|toggle."""

import argparse
import json
import shutil
import socket
import subprocess
import sys

from dictation import config as config_mod
from dictation import protocol as proto


TIMEOUTS = {"status": 10.0, "start": 30.0, "stop": 120.0, "toggle": 120.0}

# Hyprland overlay pill while recording: icon 1 (info), 60 s cap so a crashed
# client can never leave it up for long; stop dismisses it immediately.
_PILL_MESSAGE = "Listening…"
_PILL_TIMEOUT_MS = "60000"


def call(sock_path: str, req: dict, timeout: float = 60.0) -> dict:
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(timeout)  # wedged daemon must not hang the keybinding forever
    with s:
        s.connect(sock_path)
        f = s.makefile("rwb")
        proto.send_json(s, req)
        return proto.recv_json(f.readline())


def _overlay_active() -> bool:
    """True when the layer-shell pill service is running (it owns the UI then)."""
    try:
        r = subprocess.run(
            ["systemctl", "--user", "is-active", "voxd-pill.service"],
            capture_output=True,
            timeout=5,
        )
        return r.returncode == 0
    except Exception:
        return False


def _pill(show: bool) -> None:
    """Show/dismiss the Hyprland listening pill. Best-effort: never fails the command."""
    if shutil.which("hyprctl") is None or _overlay_active():
        return
    try:
        if show:
            subprocess.run(
                ["hyprctl", "notify", "1", _PILL_TIMEOUT_MS, "0", _PILL_MESSAGE],
                check=True,
                timeout=5,
            )
        else:
            subprocess.run(["hyprctl", "dismissnotify", "1"], check=True, timeout=5)
    except Exception:
        pass


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["start", "stop", "status", "toggle"])
    ap.add_argument("--socket", default=None)
    args = ap.parse_args(argv)
    cfg = config_mod.load()
    sock_path = args.socket or cfg["socket"]
    cmd = args.cmd
    if cmd == "toggle":
        # GNOME bindings fire on press only (no release event), so one shortcut
        # alternates: idle -> start, recording -> stop.
        try:
            state = call(sock_path, {"cmd": "status"}, timeout=TIMEOUTS["status"])
        except (OSError, ValueError) as e:
            print(f"vox: {e}", file=sys.stderr)
            return 1
        if not state.get("ok"):
            print(json.dumps(state))
            return 1
        cmd = "stop" if state.get("state") == "recording" else "start"
    try:
        resp = call(sock_path, {"cmd": cmd}, timeout=TIMEOUTS[cmd])
    except (OSError, ValueError) as e:
        print(f"vox: {e}", file=sys.stderr)
        return 1
    if cmd == "stop":
        _pill(False)  # pill down the moment the key releases, whatever follows
        if resp.get("ok"):
            print(resp.get("text", ""))
            return 0
    if cmd == "start" and resp.get("ok"):
        _pill(True)
    print(json.dumps(resp))
    return 0 if resp.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
