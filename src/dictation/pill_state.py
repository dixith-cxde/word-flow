"""Pill state machine: daemon event -> (visible, style class, label).

Pure function with no GTK dependency so the mapping is unit-testable; ui/pill.py
renders whatever this returns.
"""


def render(event: dict) -> tuple:
    """Return (visible, style, label) for a daemon event dict."""
    name = event.get("event") if isinstance(event, dict) else None
    if name == "recording":
        return True, "recording", "Listening…"
    if name == "transcribing":
        return True, "working", "Transcribing…"
    if name == "done":
        # Done never displays: the pill vanishes the moment transcription lands.
        # Only failure surfaces (monochrome, auto-hidden by the pill).
        if event.get("ok"):
            return False, "idle", ""
        return True, "error", "Failed"
    return False, "idle", ""
