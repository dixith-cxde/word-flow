"""Unit tests for deterministic transcript cleanup (fixtures: real spike outputs)."""

from dictation.cleanup import (
    apply_dictionary,
    capitalize_first,
    clean,
    collapse_repeats,
    expand_snippets,
    remove_fillers,
    tidy_spacing,
)


def test_live_take_fillers_stripped():
    # Real mic take: "Uh um Uh is it working uh"
    assert clean("Uh um Uh is it working uh") == "Is it working"


def test_live_take_clean_passes_through():
    # Real mic take, no fillers: punctuation/case preserved, spacing tidied.
    text = "Speak for 10 seconds between two editors two work so far"
    assert clean(text) == "Speak for 10 seconds between two editors two work so far"


def test_filler_with_punctuation():
    assert clean("Well, uh, let's go") == "Well, let's go"


def test_collapse_repeats_case_insensitive():
    assert collapse_repeats("the The worker decodes") == "the worker decodes"


def test_collapse_repeats_keeps_distinct_words():
    assert collapse_repeats("to be or not to be") == "to be or not to be"


def test_tidy_spacing():
    assert tidy_spacing("hello , world .  Next") == "hello, world. Next"


def test_capitalize_first():
    assert capitalize_first("is it working ?") == "Is it working ?"
    assert capitalize_first("") == ""


def test_dictionary_replacement():
    out = clean("route the pipewire graph", dictionary={"pipewire": "PipeWire"})
    assert out == "Route the PipeWire graph"


def test_snippet_expansion():
    out = clean("contact myemail today", snippets={"myemail": "me@example.com"})
    assert out == "Contact me@example.com today"


def test_empty_and_filler_only():
    assert clean("") == ""
    assert clean("uh um") == ""


def test_remove_fillers_direct():
    assert remove_fillers("I uh went") == "I went"


def test_apply_dictionary_direct():
    assert apply_dictionary("pipewire graph", {"pipewire": "PipeWire"}) == "PipeWire graph"


def test_expand_snippets_direct():
    assert expand_snippets("see myemail", {"myemail": "me@example.com"}) == "see me@example.com"


def test_snippet_phrase_longest_first():
    snippets = {
        "media keys": "MEDIA-KEYS",
        "gnome media keys": "org.gnome.settings-daemon.plugins.media-keys",
    }
    out = expand_snippets("open gnome media keys now", snippets)
    assert out == "open org.gnome.settings-daemon.plugins.media-keys now"


def test_snippet_cue_case_insensitive():
    out = expand_snippets("see MyEmail", {"myemail": "me@example.com"})
    assert out == "see me@example.com"
