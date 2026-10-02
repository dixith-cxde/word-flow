"""Pill state machine: daemon event -> (visible, style class, label).

Pure function with no GTK dependency so the mapping is unit-testable; ui/pill.py
renders whatever this returns.
"""

_SNIPPET_LEN = 60


def render(event: dict) -> tuple:
    """Return (visible, style, label) for a daemon event dict."""
    name = event.get("event") if isinstance(event, dict) else None
    if name == "recording":
        return True, "recording", "Listening…"
    if name == "transcribing":
        return True, "working", "Transcribing…"
    if name == "done":
        if event.get("ok"):
            text = (event.get("text") or "").strip()
            label = text[:_SNIPPET_LEN] + ("…" if len(text) > _SNIPPET_LEN else "")
            return True, "done", label or "Done"
        return True, "error", "Failed"
    return False, "idle", ""
