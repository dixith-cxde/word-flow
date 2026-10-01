"""Deterministic transcript cleanup: pure functions, no I/O, no model calls.

Covers the mechanical tier (Wispr "Light" equivalent): filler stripping, repeated-word
collapse, spacing tidy, sentence-case enforcement, dictionary replacements, snippet
expansion. Genuine grammar rewriting is out of scope (see docs/future.md).
"""

import re

FILLERS = frozenset({"uh", "um", "uhm", "er", "ah", "hmm", "hmmm", "mm", "mhm"})

_WORD_RE = re.compile(r"[A-Za-z']+|[0-9]+(?:[.,][0-9]+)?|[^\w\s]", re.UNICODE)
_WS_BEFORE_PUNCT_RE = re.compile(r"\s+([,.!?;:])")
_DUP_PUNCT_RE = re.compile(r"([,!?;:])\1+")  # ",," left behind by a removed filler
_APOS_RE = re.compile(r"(\w)\s+'\s+(\w)")
_MULTI_WS_RE = re.compile(r"\s{2,}")


def _tokens(text: str) -> list[str]:
    return _WORD_RE.findall(text)


def remove_fillers(text: str) -> str:
    """Drop filler words (uh, um, ...) wherever they appear."""
    return " ".join(t for t in _tokens(text) if t.lower().strip("'") not in FILLERS)


def collapse_repeats(text: str) -> str:
    """Collapse adjacent duplicate words: "the the" -> "the" (case-insensitive)."""
    out: list[str] = []
    for t in _tokens(text):
        if out and out[-1].lower() == t.lower() and re.fullmatch(r"[A-Za-z']+", t or ""):
            continue
        out.append(t)
    return " ".join(out)


def tidy_spacing(text: str) -> str:
    """Remove spaces before punctuation, rejoin apostrophes, collapse whitespace."""
    text = _WS_BEFORE_PUNCT_RE.sub(r"\1", text)
    text = _DUP_PUNCT_RE.sub(r"\1", text)
    text = _APOS_RE.sub(r"\1'\2", text)
    return _MULTI_WS_RE.sub(" ", text).strip()


def capitalize_first(text: str) -> str:
    """Uppercase the first alphabetic character (model usually does; enforce)."""
    for i, ch in enumerate(text):
        if ch.isalpha():
            return text[:i] + ch.upper() + text[i + 1 :]
    return text


def apply_dictionary(text: str, mapping: dict[str, str]) -> str:
    """Whole-word replacements, case-insensitive (e.g. {"pipewire": "PipeWire"})."""
    for wrong, right in mapping.items():
        text = re.sub(rf"\b{re.escape(wrong)}\b", right, text, flags=re.IGNORECASE)
    return text


def expand_snippets(text: str, snippets: dict[str, str]) -> str:
    """Whole-word cue expansion (e.g. {"myemail": "me@example.com"})."""
    for cue, expansion in snippets.items():
        text = re.sub(rf"\b{re.escape(cue)}\b", expansion, text)
    return text


def clean(
    text: str,
    dictionary: dict[str, str] | None = None,
    snippets: dict[str, str] | None = None,
) -> str:
    """Full pipeline: fillers -> repeats -> dictionary -> snippets -> tidy -> case."""
    text = remove_fillers(text)
    text = collapse_repeats(text)
    text = apply_dictionary(text, dictionary or {})
    text = expand_snippets(text, snippets or {})
    text = tidy_spacing(text)
    return capitalize_first(text)
