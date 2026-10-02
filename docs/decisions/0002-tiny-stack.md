# 0002: Tiny two-stage stack (Moonshine-tiny ASR + punct + rules)

Date: 2026-10-02. Supersedes the ASR choice in `0001-stack.md` (Voz rejection rationale
stands; only the sherpa-side model changes). Owner-approved direction: two small models,
combined ≤200 MB on disk, English-only.

## Decision

- ASR: Moonshine tiny q8 (`OpenASR/moonshine-tiny`, 27M params, 34 MB q8 / 109 MB fp16,
  MIT, upstream `UsefulSensors/moonshine-tiny`) — smallest credible offline English ASR;
  variable-length (no 30 s padding tax on short utterances), RTF ~0.03x ref.
  Justification: only verified sub-50 MB model beating Whisper-tiny-class WER.
- Punctuation: sherpa-onnx punct CT-Transformer
  (`sherpa-onnx-punct-ct-transformer-zh-en-vocab272727-2024-04-12`, same runtime as ASR,
  MBs, CPU ms) — restores `, . ?` the ASR omits.
  Justification: reuses the installed runtime, no new dependency.
- Rules (no model): spoken-punct whitelist ("dot"→`.`, "comma"→`,`, …) + NeMo-WFST-style
  ITN ("one hundred twenty three"→`123`) + existing filler/strip/tidy in `cleanup.py`.
  Justification: deterministic, KBs, zero inference — ML cannot beat explicit dictation.
- Deferred: grammar-correction SLM (GECToR-style tagger, not generative rewrite),
  gated on measured punct/grammar error rate; must fit the ≤200 MB combined budget
  (see `docs/future.md` §1). The 3B-LM option is rejected (2–3 GB RAM).

## Pipeline

`mic → ASR (frozen) → spoken-punct normalize → punct model → cleanup.clean() → insert`.
Worker-exit unload design unchanged; models load on key-down, exit after idle timeout.

## Budgets (to confirm by measurement on i5-1235U)

- Idle (unloaded): <30 MB RSS (unchanged).
- Warm-peak target: ~350–500 MB (ASR q8 ~306 MB peak ref + punct + runtime), vs ~810 MB now.
- Release-to-text 5 s: <700 ms total; punct stage must add <~100 ms.
- Eval gates before grammar iteration: WER on jargon script, punct-F1, 5 s decode latency.

## Migration

`worker.py` recognizer swap (framing unchanged) → punct stage in daemon/worker →
`cleanup.py` spoken-punct/ITN pre-pass (pure + tested) → `config.py` keys
(`asr_model`, `punct_model`, `punct_enabled`) → re-run `docs/benchmarks.md` matrix.
Parakeet v3 int8 stays as accuracy reference until the tiny stack proves out.
