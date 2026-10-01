# Research (Step 1, read-only, 2026-10-01)

Target: Hyprland 0.56.2 on CachyOS, PipeWire 1.6.9, i5-1235U, 15 GB RAM.
Every claim cites its source. Items marked UNVERIFIED need measurement or a prototype check.

## a. Hold-to-talk trigger from a compositor keybinding

Viable: two Hyprland binds on one key — `bind` fires on press, `bindr` (release flag) fires
on release, each `exec`ing a tiny client that signals the service (e.g. writes to a unix socket).

- Bind syntax `bind = MODS, key, dispatcher, params`; flags append letters (`r` = release):
  `bindr = SUPER, SUPER_L, exec, pkill wofi || wofi`.
  Source: Hyprland wiki Binds, versioned 0.54.0 page (legacy `bind`/`bindr` syntax) and
  current `wiki.hypr.land` Binds/Flags pages (`release` flag).
- Release binds on multi-key combos fire when only part of the combo is released
  (hyprwm/Hyprland issue #7675) — so use a **single-key bind** for the talk key, not a chord.
- Release binds misbehave inside submaps (issues #5292, #3058) — avoid submaps for this key.
- No global key capture by the app is needed or possible on Wayland; the compositor owns
  the keybinding. This matches the architecture in AGENTS.md.

## b. Audio capture while the key is held

Viable options, in order of preference:

1. **Python `sounddevice`** (MIT; Linux/macOS/Windows — supports the cross-platform seam):
   PortAudio bindings with blocking `InputStream.read()`.
   Source: python-sounddevice docs (`python-sounddevice.readthedocs.io`).
   Caveat: on Linux it needs a system PortAudio whose build exposes a usable host API.
   Debian/Ubuntu ship old 19.6.0 builds without Pulse/PipeWire support; Arch-family ships
   19.7.0 (this box: `portaudio 1:19.7.0-4.1`). PipeWire also offers Pulse/JACK/ALSA
   compatibility shims. UNVERIFIED: which host API `python3 -m sounddevice` lists on this
   box (check at prototype time; `sounddevice` is not installed yet).
   Source for the distro caveat: spatialaudio/python-sounddevice issue #609.
2. **Subprocess capture**: `pw-record` (PipeWire native) or `parecord` (Pulse compat) —
   both installed (`/usr/bin/pw-record`, `/usr/bin/parecord`). Heavier per-activation
   spawn cost; fallback if PortAudio misbehaves. UNVERIFIED: spawn-to-first-sample latency.
3. sherpa-onnx's own mic examples also use `sounddevice` + PortAudio, so option 1 shares
   the runtime's tested path. Source: `python-api-examples/speech-recognition-from-microphone.py`.

## c. Voice activity detection to trim silence

- **silero-vad: MIT** — recommended. sherpa-onnx ships `silero_vad.onnx` (629 KB) and an
  int8 variant (208 KB), 16 kHz only, with a Python `VadModelConfig` API.
  Sources: sherpa VAD docs (`k2-fsa.github.io/sherpa/onnx/vad/`), PR #2377 size/license
  table, snakers4/silero-vad (GitHub license field: MIT). Minor note: the repo README
  also carries a "CC BY-NC 4.0 downloads" badge whose scope is unclear — the code/weight
  license per GitHub metadata and sherpa docs is MIT.
- **ten-vad: Apache-2.0 with additional conditions** — smaller (324 KB / 126 KB int8) and
  lower compute per its authors, but the sherpa docs explicitly say to read its license
  before commercial use. Avoid unless silero-vad misses a budget.
  Sources: sherpa ten-vad docs, TEN-framework/ten-vad LICENSE.

## d. Text insertion into the focused app on Wayland/Hyprland

Primary: **`wtype`** (MIT, `/usr/bin/wtype` installed). It types via the
`virtual-keyboard-unstable-v1` protocol — no special permissions, just a same-user
Wayland client; fails cleanly if the compositor lacks the protocol.
Sources: atx/wtype (GitHub license field: MIT), `wtype(1)` man page, wayland.app
protocol table (Hyprland 0.52.1 supports v1; this box runs 0.56.2).

Known quirks (all documented, none blocking for V1):

- XWayland/Electron targets are flaky with `wtype` (dropped/garbled chars):
  atx/wtype issue #62, hyprwm/Hyprland issue #6647.
- Fallback that works even in XWayland apps: `wl-copy <text>` then
  `hyprctl dispatch sendshortcut "CTRL,V,"` (both installed). Source: Arch forums
  thread "[SOLVED] Hyprland unable to wl-paste/wtype from key bind".
- Typing while the trigger modifier is still held injects that modifier into the output
  (Hyprland issue #3165) — release-then-type ordering matters; the release bind gives us
  that for free if insertion waits for key-up.

Fallback: **`ydotool`** (installed) drives a kernel-level virtual device via `ydotoold`,
but needs `/dev/uinput` access (input-group udev rule or root daemon) plus socket-path
coordination — heavier setup, keep as fallback only.
Sources: ReimuNotMoe/ydotool README + issues #36/#73/#210/#241, PR #315.

## e. Idle service (systemd user + socket activation)

Viable: a systemd **user** service (`~/.config/systemd/user/`, `systemctl --user enable`),
with optional **socket activation** (`.socket` unit; service inherits the fd via
`LISTEN_PID`/`LISTEN_FDS`, fds start at 3).
Sources: ArchWiki `systemd/User`, ArchWiki `systemd` socket-activation section,
`systemd.socket(5)` (Accept=no vs Accept=yes semantics), gfxmonk socket-activation-in-Python.

Design note for the stack proposal: socket activation starts the service on first client
connect (i.e. on key-down), which conflicts with the <150 ms key-to-record budget if the
interpreter + audio stack must cold-start in that window. Likely shape: a persistent tiny
listener (blocking socket read = 0% idle CPU) plus a worker process that loads/unloads the
model. UNVERIFIED until prototyped.

## f. Speech model on Linux

### Option F1 — Voz (Desert Ant Labs, the candidate)

- What it is: converted/compressed NVIDIA Parakeet TDT 0.6B v3, 467 MB, 25 languages,
  word timestamps (80 ms), WER 7.40% vs Whisper large-v3-turbo 7.00%.
  Source: `docs/models/voz.md` in desert-ant-core (raw GitHub fetch).
- **Linux runs only via Node**: `npm i @desert-ant-labs/voz`, `Voz.load({ ort })` with a
  caller-supplied `onnxruntime-node` (CPU). There is no `/native` subpath for Voz (unlike
  sibling models) and no Linux Swift support. Verified JS API:
  `Voz.load()` → `voz.transcribe(file|samples)` → `{ text, words[], realtimeFactor }`.
  Source: desert-ant-core README (JS section) + `docs/models/voz.md`.
- **No published Linux CPU speed.** Published figures are Apple Neural Engine (e.g. 10 min
  in 2.4 s on M1 mini) and Chromium WebGPU/WebNN; the docs only say Node CPU is "slower
  than a browser on the same machine". UNVERIFIED:-omitted, must be measured.
- Voz has **no language detection** (wrong-language audio returns fluent wrong text, no
  error) — V1 fixes English in config. Source: voz.md Limits.
- License: **Desert Ant Labs Source-Available License 1.0 — not open source.**
  Free below 100,000 monthly-active-devices per platform per model; attribution
  ("Powered by Desert Ant Labs") required; no training competing models on outputs;
  no standalone redistribution. Full terms fetched from `license.desertant.com` (v1.0,
  3 July 2026). Two V1-relevant frictions:
  1. The SDK sends MAD-counting telemetry (minimal, no content — but it is network
     traffic from the app; acceptance criterion "no network after download" must be
     tested with the network blocked).
  2. Fully-offline Node use (`directory`-style pre-seeding, cf. `Redact.load({directory})`)
     is documented per-model for siblings; Voz parity UNVERIFIED until prototype.

### Option F2 — original Parakeet v3 weights via sherpa-onnx (alternative, same model family)

- sherpa-onnx runs `nvidia/parakeet-tdt-0.6b-v3` (CC-BY-4.0 — verified on the HF model
  card, `license: cc-by-4.0`) as `model_type="nemo_transducer"`, including an int8 build
  (`sherpa-onnx-nemo-parakeet-tdt-0.6b-v3-int8`, ~487 MB download) with the same usage as v2.
  Sources: sherpa NeMo-transducer docs page, PR #2500 (v3 export), PR review noting the
  int8 tarball size 487,170,055 bytes.
- **sherpa-onnx: Apache-2.0**, `pip install sherpa-onnx` (CPU wheel), Python ≥ 3.7,
  Linux x64/arm64 + Windows + macOS prebuilts. Python API verified:
  `OfflineRecognizer.from_transducer(encoder, decoder, joiner, tokens, num_threads,
  decoding_method="greedy_search", model_type=...)`, `create_stream()` /
  `accept_waveform()` / `decode_stream()`.
  Sources: sherpa install page, `offline_recognizer.py`, `offline-decode-files.py`,
  PyPI/GitHub metadata (Apache-2.0).
- Bundles VAD (silero/ten-vad) and mic examples in the same runtime. UNVERIFIED: Linux
  CPU latency/memory for the v3-int8 build on the i5-1235U — must be measured.
- License stack is fully open (Apache-2.0 + CC-BY-4.0 weights + MIT VAD): no telemetry,
  no attribution UI, no device-count ceiling. Fits the offline criterion by construction.

### Option F3 — faster-whisper (second alternative, different model family)

- `faster-whisper` (SYSTRAN, **MIT**, `pip install faster-whisper`) runs Whisper-family
  weights via CTranslate2 on CPU. Different accuracy/size tradeoff (e.g. `small.en`
  ~500 MB) and a useful fallback if Parakeet-class models miss the latency budget.
  Sources: PyPI faster-whisper page, GitHub LICENSE (MIT, © 2023 SYSTRAN).

## License table

| Component | License | Commercial / offline friction |
|---|---|---|
| NVIDIA Parakeet TDT 0.6B v3 weights | CC-BY-4.0 (needs attribution in docs) | none |
| sherpa-onnx runtime | Apache-2.0 | none |
| silero-vad | MIT | none |
| faster-whisper | MIT | none |
| sounddevice / PortAudio | MIT (both) | none |
| wtype | MIT | none |
| Voz SDK + weights | Source-Available 1.0, free <100k MAD/platform | telemetry, attribution, scale ceiling |
| ten-vad | Apache-2.0 + extra conditions | read license before commercial use |

## What was NOT verified (prototype must check)

1. Linux CPU latency + RSS for Voz-Node and sherpa-Parakeet-int8 on this box.
2. Voz-Node fully-offline behavior (pre-seeded model, blocked network).
3. `sounddevice` host-API list on this PipeWire box.
4. `pw-record`/`parecord` spawn-to-first-sample latency (only if sounddevice fails).
5. `wtype` end-to-end into Wayland + XWayland apps on Hyprland 0.56.2.
