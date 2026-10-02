# 0004: Stay with Moonshine tiny (A/B verdict)

Date: 2026-10-02. Evidence: A/B table in `docs/benchmarks.md` (tiny vs base vs
SenseVoice-Small on user fixture + tech clips + literary sample, i5-1235U).

## Decision

Keep Moonshine tiny q8 as the ASR. Do not adopt base or SenseVoice now.

- Base (~2x params) wins isolated words but loses others ("transusa" vs tiny's
  "transducer") and peaks at 499 MB on 19 s audio — over the 300–400 MB cap.
  Inconsistent gains, certain budget breach: rejected.
- SenseVoice-Small (229 MB, ITN punctuation is genuinely nice) is worst on
  jargon: run-together words ("waylandcomp"), stutters ("Checkck"). Rejected.
- Tiny matches or beats both on tech terms and stays in budget on every clip.

## Consequences

- The remaining gap is vocabulary, not capacity: user-owned `dictionary`/`snippets`
  config for personal jargon (never hardcoded repo defaults), plus delivery and mic.
- Revisit only with new evidence: a base-size model that stays <400 MB peak on
  20 s audio, or a fixture-measured WER win that justifies the RAM.
- `prototype/mic_spike.py` keeps all three backends (`--asr-backend`,
  `--model-dir`) so any future A/B replays the same fixtures.
