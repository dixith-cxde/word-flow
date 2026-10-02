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
        text = re.sub(rf"\b{re.escape(wrong)}\b", lambda m: right, text, flags=re.IGNORECASE)
    return text


def expand_snippets(text: str, snippets: dict[str, str]) -> str:
    """Cue expansion, longest cue first so phrases win over single words.

    Cues may be multi-word ("gnome media keys" -> full schema path) and match
    case-insensitively, which is what makes dictated technical terms usable.
    """
    for cue in sorted(snippets, key=lambda c: (-len(c.split()), -len(c))):
        text = re.sub(rf"\b{re.escape(cue)}\b", lambda m: snippets[cue], text, flags=re.IGNORECASE)
    return text


SPOKEN_PUNCT = {
    "full stop": ".",
    "exclamation mark": "!",
    "exclamation point": "!",
    "question mark": "?",
    "semicolon": ";",
    "period": ".",
    "comma": ",",
    "colon": ":",
    "dot": ".",
}


def normalize_spoken(text: str) -> str:
    """Map dictated punctuation words to marks ("dot" -> "."), longest cue first.

    Known limitation: bare words always map, so "a period of time" becomes
    "a . of time". Mitigate with dictionary/snippet wording or a grammar
    post-pass (see docs/future.md); the mapping itself stays deterministic.
    """
    for cue in sorted(SPOKEN_PUNCT, key=lambda c: (-len(c.split()), -len(c))):
        mark = SPOKEN_PUNCT[cue]
        text = re.sub(rf"\b{re.escape(cue)}\b", lambda m: mark, text, flags=re.IGNORECASE)
    return text


def clean(
    text: str,
    dictionary: dict[str, str] | None = None,
    snippets: dict[str, str] | None = None,
) -> str:
    """Full pipeline: fillers -> repeats -> spoken punct -> dict -> snippets -> tidy -> case."""
    text = remove_fillers(text)
    text = collapse_repeats(text)
    text = normalize_spoken(text)
    text = apply_dictionary(text, dictionary or {})
    text = expand_snippets(text, snippets or {})
    text = tidy_spacing(text)
    return capitalize_first(text)
