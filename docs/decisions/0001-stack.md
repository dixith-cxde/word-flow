# 0001: Technology stack (proposal — STOP: needs owner approval)

Date: 2026-10-01. Evidence: `docs/research.md`. No installs, downloads, or code yet.

## Shared shape (both options)

- Trigger: Hyprland `bind` (press) + `bindr` (release) `exec` a tiny client that signals
  the service over a unix socket. Service: systemd user unit; persistent listener
  (blocking read, 0% idle CPU) + worker process for the model (exit = memory back to OS).
- Capture: `sounddevice` (PortAudio) while key held; `pw-record` fallback.
- VAD: silero-vad (MIT) to trim silence. Insertion: `wtype`, clipboard+`sendshortcut` fallback.
- Text cleanup: pure functions + unit tests. OS seam (trigger/capture/insert/autostart)
  behind narrow interfaces per AGENTS.md.
- The options below differ only in the **model runtime**.

## Option A — Python + sherpa-onnx (Parakeet v3 int8). RECOMMENDED for prototype.

- Runtime: `sherpa-onnx` (Apache-2.0, CPU pip wheel) + `sherpa-onnx-nemo-parakeet-tdt-0.6b-v3-int8`
  (~487 MB, original NVIDIA weights, CC-BY-4.0) + silero-vad (MIT). One Python process tree.
- Idle memory: interpreter + listener only while model unloaded; expected ~15–25 MB RSS,
  inside the 30 MB budget. MUST MEASURE.
- Startup: pip wheels, no build, no native-addon surgery. Cold model load latency unknown —
  the prototype's first measurement.
- Ecosystem: audio (sounddevice), Wayland (subprocess `wtype`/`wl-copy`), and runtime
  (sherpa Python API incl. VAD + mic examples) all cover the design. Windows later:
  sherpa ships Windows prebuilts, sounddevice covers WASAPI — only trigger/insert/autostart
  need new backends.
- Distribution: venv + pinned pip requirements + systemd unit; model + VAD files excluded
  from git, fetched once with pinned revisions.
- Dev speed / review: single language you know; sherpa Python API is small
  (`from_transducer`, `create_stream`, `decode_stream`). Fastest to prototype and review.
- License stack fully open: Apache-2.0 + CC-BY-4.0 + MIT. No telemetry, no attribution UI,
  no device ceiling — fits "no network after download" by construction.

## Option B — Python + Voz via Node sidecar. FALLBACK.

- Runtime: `@desert-ant-labs/voz` + caller-supplied `onnxruntime-node` (CPU) in a Node
  worker; Python keeps trigger/capture/insert/service. Verified API
  (`Voz.load({ort})`, `transcribe()`, `{text, words, realtimeFactor}`), 467 MB, 25 langs.
- Idle memory: Node baseline (~30–60 MB RSS before inference) threatens the 30 MB budget
  on its own; two runtimes to keep alive/unload. MUST MEASURE, likely over budget.
- Startup: npm + native addon (`onnxruntime-node`, ~100 MB+) — heavier install, slower cold start.
- Ecosystem: same OS seam as A, but logic splits across Python + JS and the Voz Linux path
  (Node CPU) is the vendor's least-documented tier — no published Linux numbers at all.
- Distribution: venv + node_modules + pinned npm/pip versions; more moving parts.
- Dev speed / review: you know TS, but two processes + IPC schema slow the prototype.
- License: source-available (free <100k MAD/platform, attribution, MAD telemetry).
  Telemetry conflicts with the offline acceptance criterion until proven otherwise;
  scale ceiling and attribution UI are fine for personal use but add risk for zero gain
  unless B measurably beats A on latency/accuracy.

## Considered and deferred

- **Go service**: you know Go and the idle RSS would be smallest, but the audio (PortAudio
  bindings) and model-runtime (sherpa Go API) ecosystem for this niche is thinner than
  Python's, slowing the prototype and review. Revisit only if Python misses idle budgets.
- **faster-whisper (MIT) as runtime**: viable fallback model (Whisper `small.en`) if both
  Parakeet paths miss latency; not a separate stack since it slots into Option A's shape.

## Comparison

| Criterion | A: sherpa-onnx | B: Voz-Node sidecar |
|---|---|---|
| Idle RSS vs 30 MB | likely fits (~15–25 MB) | likely over (Node baseline) |
| Cold/warm latency | unknown, measure first | unknown, vendor silent on Linux CPU |
| Audio/Wayland/runtime ecosystem | tested paths (sherpa mic+VAD examples) | Voz Linux path least documented |
| Binary size / distribution | pip venv + unit | pip venv + node_modules + unit |
| Dev speed | fastest (one language) | slower (two processes, IPC) |
| Reviewability | Python only | Python + JS |
| Licensing/offline fit | clean (no telemetry) | telemetry + attribution to verify |

## Recommendation

Prototype **Option A**. If its measured cold-start or 5 s-utterance latency misses budget,
fall back to measuring B before changing budgets. Go stays deferred; faster-whisper stays
as a model-swap fallback inside A's shape.

**STOP — do not install, download, or write code until the owner approves an option.**
Prototype entry (after approval): CLI spike — Enter-to-start/stop recording, transcribe,
print text; then the full benchmark matrix in `docs/benchmarks.md`. Version pins for
`sherpa-onnx`, `sounddevice`, model revision, and VAD file are fixed at install time,
not in this doc.
