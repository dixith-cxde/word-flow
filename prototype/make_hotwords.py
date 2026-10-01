#!/usr/bin/env python3
"""Build a sherpa-onnx hotwords file from plain words + the model tokens.txt.

sherpa wants one hotword per line with BPE pieces separated by spaces, e.g.
a word the tokenizer splits as [\u2581pipe, wire] becomes a line "\u2581pipe wire".
Segmentation here is greedy longest-match against tokens.txt; terms that cannot
be fully covered are skipped with a warning (visible, not silent).
"""

import argparse
from pathlib import Path


def load_pieces(tokens_path: Path) -> set[str]:
    pieces = set()
    with open(tokens_path, encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\n")
            if not line:
                continue
            sym, _ = line.rsplit(" ", 1)
            pieces.add(sym)
    return pieces


def segment_word(word: str, pieces: set[str]) -> list[str] | None:
    """Greedy longest-match: first piece carries the \u2581 word-boundary marker."""
    out: list[str] = []
    i = 0
    s = "\u2581" + word.lower()
    while i < len(s):
        if s[i] == " ":
            i += 1
            continue
        match = None
        for j in range(len(s), i, -1):
            cand = s[i:j]
            if cand in pieces:
                match = cand
                break
        if match is None:
            return None
        out.append(match)
        i += len(match)
    # First piece must start a word; a bare continuation piece cannot lead.
    if out and not out[0].startswith("\u2581"):
        return None
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--vocab", type=Path, required=True)
    ap.add_argument("--tokens", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()

    pieces = load_pieces(args.tokens)
    kept, skipped = [], []
    for raw in args.vocab.read_text(encoding="utf-8").splitlines():
        term = raw.strip()
        if not term or term.startswith("#"):
            continue
        seg: list[str] = []
        ok = True
        for word in term.split():
            parts = segment_word(word, pieces)
            if parts is None:
                ok = False
                break
            seg.extend(parts)
        if ok:
            kept.append(" ".join(seg))
        else:
            skipped.append(term)
    args.out.write_text("\n".join(kept) + "\n", encoding="utf-8")
    print(f"kept {len(kept)}, skipped {len(skipped)}", flush=True)
    for term in skipped:
        print(f"  skipped (no BPE cover): {term}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
