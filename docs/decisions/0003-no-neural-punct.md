# 0003: Drop neural punct model — Moonshine punctuates natively

Date: 2026-10-02. Amends `0002-tiny-stack.md` (punct-model leg rejected; ASR + rules stand).

## Evidence (measured, i5-1235U, sherpa-onnx 1.13.8)

- Moonshine tiny q8 (`sherpa-onnx-moonshine-tiny-en-int8`) emits ASCII `, .` itself:
  `After early nightfall, the yellow lamps would light up here and there ... brothels.`
  Decode 0.19 s (short) / 0.98 s (long literary clip); ASR load 0.79 s (vs 1.8–2.3 s Parakeet).
- `sherpa-onnx-punct-ct-transformer-zh-en` (FunASR `punc_ct-transformer_zh-cn-common`
  conversion — a Chinese punctuation model) emits **fullwidth** `。，？` and, run after
  Moonshine, **duplicates** marks: `there，`, `,，`, ` .。`. It expects unpunctuated input;
  Moonshine output is already punctuated. Net effect: corruption, not cleanup.
- int8 quantization of the punct model verified parity 3/3 + 3 ms latency
  (onnx 1.23.1 + onnxruntime 1.30.0, one-shot dev tools, dynamic QInt8, 294→75 MB) —
  method recorded in case a future unpunctuated ASR needs it. Technique is sound;
  this model is simply the wrong stage for this pipeline.

## Decision

Pipeline is now `mic → Moonshine ASR → normalize_spoken() → cleanup.clean() → insert`.
No neural punct stage. Spoken punctuation ("dot"→`.`) and fillers stay deterministic
rules in `cleanup.py` (pure + tested). Both shipped models fit in ~119 MB
(moonshine int8 files minus test wavs) — well under the ≤200 MB budget in 0002.

## Consequences

- `punct_model`/`punct_enabled` config keys from the 0002 plan are NOT added.
- Removed `model.onnx` (294 MB fp32) locally; kept `model.int8.onnx` (75 MB) for
  future A/B only if an unpunctuated ASR is ever adopted. Neither is referenced by code.
- Grammar SLM gating (0002 / `docs/future.md` §1) unchanged.
