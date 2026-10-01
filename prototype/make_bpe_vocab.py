#!/usr/bin/env python3
"""Build a sherpa bpe.vocab from the HF tokenizer.json merge list.

sherpa wants "token score" lines to segment hotwords. True sentencepiece scores
are not published for this model, so merge rank stands in (rank 0 first =
highest priority); base characters sink below all merges. If hotwords still do
not engage, suspect this approximation first (see docs/benchmarks.md).
"""

import argparse
import json
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tokenizer", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()

    model = json.loads(args.tokenizer.read_text(encoding="utf-8"))["model"]
    assert model["type"] == "BPE", model["type"]
    merges: list[list[str]] = model["merges"]

    scored: dict[str, float] = {}
    chars: set[str] = set()
    for rank, (a, b) in enumerate(merges):
        chars.add(a)
        chars.add(b)
        merged = a + b
        if merged not in scored:
            scored[merged] = -float(rank)
    floor = -float(len(merges) + 256)
    for ch in chars:
        scored.setdefault(ch, floor - ord(ch[0]) if ch else floor)

    with open(args.out, "w", encoding="utf-8") as f:
        for tok, score in sorted(scored.items(), key=lambda kv: kv[1], reverse=True):
            f.write(f"{tok} {score}\n")
    print(f"wrote {len(scored)} pieces", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
