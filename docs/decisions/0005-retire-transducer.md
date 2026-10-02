# 0005: Retire transducer backend and hotwords plumbing

Date: 2026-10-02. Follows `0004-stay-with-tiny.md`.

## Decision

With the Parakeet model files deleted (1.1 GB reclaimed), the transducer backend
has no runnable model left, so its code goes too: `worker.py` is Moonshine-only,
`asr_backend`/`decoding_method`/`hotwords_*`/`max_active_paths`/`modeling_unit`/
`bpe_vocab` config keys are removed (old configs carrying them get the standard
"unknown key" warning, not an error), `install.sh` no longer writes `asr_backend`,
and `prototype/make_bpe_vocab.py` (hotwords BPE builder, zero live references) is
deleted. `mic_spike.py` keeps moonshine + sensevoice for future A/B.

## Consequences

- Re-adding a transducer later means re-adding the branch, keys, and model
  download together — use git history (`1f372d7` and ancestors) as the template.
- Hotwords experiment docs in `benchmarks.md` stay as history of a dropped path.
