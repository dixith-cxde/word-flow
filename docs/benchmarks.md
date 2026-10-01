# Benchmarks

## Reference machine (2026-10-01, measured)

- Session: `wayland`, desktop `Hyprland` 0.56.2 (running compositor; `niri 26.04` is
  installed but not running — earlier "Reference environment: Niri" assumption corrected).
- OS: CachyOS (Arch-based). Kernel/CPU: 12th Gen Intel i5-1235U (10 cores / 12 threads,
  max 4.4 GHz). RAM: 15 GB (+ 15 GB swap).
- Audio: PipeWire 1.6.9 (Pulse compat server present). portaudio 1:19.7.0-4.1.
- Insertion/capture tools installed: `wtype`, `wl-copy`, `wl-paste`, `pw-record`,
  `parecord`, `ydotool`, `hyprctl`, `systemctl` (all in `/usr/bin`).
- Python 3.14.7 + pip 26.2.1. `sounddevice`: NOT installed (needs approval).
- Budgets under test (AGENTS.md): idle <30 MB RSS, 0% idle CPU, <150 ms key-to-record,
  <700 ms release-to-text for a 5 s utterance.

## Measurements (prototype, Option A — file-based, 2026-10-01)

Versions: `sherpa-onnx 1.13.8`, `sounddevice 0.5.6`, `numpy 2.5.3` (PyPI),
model `sherpa-onnx-nemo-parakeet-tdt-0.6b-v3-int8`, VAD `silero_vad.onnx`.
Dev: `pytest 9.1.1`, `ruff 0.16.9`, `pre-commit 4.6.2` (hooks: whitespace, private-key scan, ruff).
Decode: `OfflineRecognizer.from_transducer(..., model_type="nemo_transducer",
num_threads=4, decoding_method="greedy_search")`, i5-1235U.
Sample: bundled `test_wavs/en.wav` (3.85 s, resampled 24 kHz → 16 kHz in-runtime).

- Cold start (import + model load to ready): 1.8–2.3 s. (Budget has no cold-start number;
  key-down path will need a warm worker — see unload row.)
- RSS with runtime imported, model NOT loaded: 24–28 MB — inside the 30 MB idle budget,
  provided the listener process never loads weights (see below).
- RSS loaded idle: 728 MB. Peak during 3.85 s decode: ~777 MB.
- End-of-audio → text (3.85 s): 0.28–0.41 s (RTF ~10–14x). Warm second decode: same.
  10 s / 30 s utterances: pending mic test.
- Unload in-process (`del` + `gc.collect()`): RSS stays at peak (~777 MB) — memory does
  NOT return to the OS. Confirms the AGENTS.md design: the model worker must EXIT to
  release memory; in-process unload is not a thing with this runtime.
- Transcript of bundled sample: correct
  ("Ask not what your country can do for you, ...").
- Anomaly note: the first two runs reported ~554 MB pre-load RSS under high system memory
  pressure (9.3/15 GB used); all runs since (7.6/15 GB) report 24–28 MB stably via both
  `ru_maxrss` and `/proc` VmHWM. Treating 24–28 MB as the number; will re-check if pressure recurs.

## Pending (needs mic access + read-aloud script)

- End-of-audio → text for 10 s and 30 s utterances; WER on technical text;
  `sounddevice` host-API check on this PipeWire box; `wtype` end-to-end insertion check.

- RSS: model unloaded / loaded-idle / peak (5 s and 30 s utterances) / after unload.
- Latency: cold start request→ready, warm latency, end-of-audio→text (3/10/30 s).
- WER on a short technical script read aloud.
