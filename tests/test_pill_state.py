"""Unit tests for the pill state machine (pure, no GTK)."""

from dictation.pill_state import render


def test_recording_state():
    assert render({"event": "recording"}) == (True, "recording", "Listening…")


def test_transcribing_state():
    assert render({"event": "transcribing"}) == (True, "working", "Transcribing…")


def test_done_ok_with_text_snippet():
    visible, style, label = render({"event": "done", "ok": True, "text": "Hello world"})
    assert (visible, style) == (True, "done")
    assert label == "Hello world"


def test_done_ok_truncates_long_text():
    visible, style, label = render({"event": "done", "ok": True, "text": "x" * 100})
    assert (visible, style) == (True, "done")
    assert len(label) == 61 and label.endswith("…")


def test_done_ok_empty_text():
    assert render({"event": "done", "ok": True, "text": "   "}) == (True, "done", "Done")


def test_done_failed():
    assert render({"event": "done", "ok": False}) == (True, "error", "Failed")


def test_unknown_event_hides():
    assert render({"event": "bogus"}) == (False, "idle", "")
    assert render({}) == (False, "idle", "")
