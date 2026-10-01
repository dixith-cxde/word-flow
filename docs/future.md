# Possible development plans (parked, not scheduled)

Trigger-gated experiments only. Nothing below starts until V1 dictation (cleanup + service
wiring) is proven in daily use. Each needs its own measurement before adoption.

## 1. Uhm-ONNX filler spans

- What: `uhm-web-fp16.onnx` (51 MB, documented I/O: 16 kHz mono in, per-20 ms softmax
  over `not_filler, uh, um, hmm, and, other`) run under the already-installed onnxruntime;
  map filler spans to transcript words.
- Trigger: text-based filler stripping disappoints on real usage — specifically fillers
  the ASR *mis*-transcribes (e.g. "um" → "arm"), which text rules cannot catch.
- Cost: 51 MB download, one extra inference step (tiny model; measure CPU latency),
  second source-available license component (telemetry/attribution regime as Voz).
- Note: Uhm SDK itself is Apple-only; only the raw ONNX weights are usable on Linux.

## 2. Clear-ONNX speech enhancement (denoise/dereverb/normalize)

- What: `clear-natural.onnx` or `clear-studio.onnx` (24 MB each — the "9 MB" figure is the
  Apple Core ML file) as a mic → Clear → Parakeet preprocessing pass. Audio in/out;
  does not transcribe. Linux-viable (LiteRT/ONNX builds, Node `/native` exists, raw ONNX
  documented for uncovered runtimes). No published Linux timings.
- Trigger: WER degrades in real noisy conditions (fan, keyboard, untreated room).
  Keep criterion: A/B the same noisy sample with/without Clear, adopt only on a measured win.
- Cost: 24 MB download, extra pipeline latency (measure), third source-available component.

## 3. Local-LM grammar rewrite (Wispr Medium/High equivalent)

- What: 3B-class instruct model as an optional transcript post-pass for genuine grammar
  correction, restatement resolution, tone adaptation.
- Trigger: deterministic rules prove insufficient AND owner amends the spec (local LM
  cleanup is currently out of V1 scope).
- Cost: ~2–3 GB extra resident RAM, latency hit against the 700 ms budget — both must be
  measured before any commitment. Cloud LLM is not an option (offline requirement).

## License watch

Uhm and Clear both fall under the Desert Ant Labs Source-Available License 1.0
(free <100k MAD/platform/model, attribution, MAD-counting telemetry). Any adoption must
re-verify fully-offline behavior with the network blocked, per the acceptance criteria.
