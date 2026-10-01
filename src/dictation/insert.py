"""Text insertion backends (pure command builders + thin runner).

Primary: wtype via the virtual-keyboard protocol (no special permissions).
Fallback: wl-copy clipboard + Hyprland sendshortcut Ctrl+V (works in XWayland apps).
"""

import shutil
import subprocess

WTYPE = "wtype"
WL_COPY = "wl-copy"
HYPRCTL = "hyprctl"


def build_wtype_cmd(text: str) -> list[str]:
    # "-" reads the text from stdin (avoids argv length/escaping issues).
    # NOTE: no "-d 0" — the installed wtype rejects a zero delay as invalid
    # ("Invalid sleep time"); the default delay is already 0.
    return [WTYPE, "-"]


def build_clipboard_cmds() -> tuple[list[str], list[str]]:
    copy = [WL_COPY, "--trim-newline"]
    paste = [HYPRCTL, "dispatch", "sendshortcut", "CTRL,V,"]
    return copy, paste


def available() -> str:
    """Pick the first usable backend: 'wtype', 'clipboard', or 'none'."""
    if shutil.which(WTYPE):
        return "wtype"
    if shutil.which(WL_COPY) and shutil.which(HYPRCTL):
        return "clipboard"
    return "none"


def insert(text: str, backend: str = "auto") -> str:
    """Insert text into the focused app. Returns the backend used. No logging."""
    if backend == "auto":
        backend = available()
    if backend == "wtype":
        subprocess.run(build_wtype_cmd(text), input=text.encode(), check=True, timeout=10)
        return "wtype"
    if backend == "clipboard":
        copy, paste = build_clipboard_cmds()
        subprocess.run(copy, input=text.encode(), check=True, timeout=10)
        subprocess.run(paste, check=True, timeout=10)
        return "clipboard"
    raise RuntimeError("no insertion backend available (need wtype or wl-copy+hyprctl)")
