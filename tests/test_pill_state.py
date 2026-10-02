"""Unit tests for the pill state machine (pure, no GTK)."""

from dictation.pill_state import render


def test_recording_state():
    assert render({"event": "recording"}) == (True, "recording", "Listening…")


def test_transcribing_state():
    assert render({"event": "transcribing"}) == (True, "working", "Transcribing…")


def test_done_ok_hides():
    assert render({"event": "done", "ok": True, "text": "Hello world"}) == (False, "idle", "")


def test_done_ok_empty_text_hides():
    assert render({"event": "done", "ok": True, "text": "   "}) == (False, "idle", "")


def test_done_failed():
    assert render({"event": "done", "ok": False}) == (True, "error", "Failed")


def test_unknown_event_hides():
    assert render({"event": "bogus"}) == (False, "idle", "")
    assert render({}) == (False, "idle", "")
