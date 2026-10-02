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

## Live service (Phase 2, 2026-10-01)

- Daemon (`voxd`, stdlib only) + warm worker: ~934 MB cgroup total
  (worker ~810 MB RSS, daemon the rest). Worker status `warm` within 25 s of use.
- After `worker_idle_timeout` (default 25 s) the worker exits; only the ~12–28 MB
  listener remains at 0% CPU (blocking socket read). Confirm with
  `systemctl --user show voxd.service -p MemoryCurrent` after a minute idle.
- Budget reading: the <30 MB idle budget is met in the unloaded state; the 25 s warm
  window trades ~800 MB for zero cold-load latency on the next utterance. Lower
  `worker_idle_timeout` in `~/.config/voxd/config.toml` to shrink the window at the
  cost of more 2 s cold loads.

## Hotwords experiment (2026-10-01, Option A + beam search)

Goal: bias through decoding toward technical terms (general vocab, not per-user).
Method: `modified_beam_search` + plain-word hotwords file + `modeling_unit=bpe` +
`bpe.vocab` derived from the published `tokenizer.json` merge ranks
(`prototype/make_bpe_vocab.py`; regenerate with the command in `docs/future.md`
if the model changes). Test speech: `espeak-ng` technical sentences (robotic —
weak proxy for human speech, good for A/B mechanics, not for absolute WER).

Findings on i5-1235U, threads=4, 4–5 s utterances:

- Without `modeling_unit=bpe` + `bpe.vocab`, hotwords are silently ignored at any
  score (1.5–4.0) and in any file format (BPE pieces or plain words). The sherpa
  docs bury this: BPE models need the unit set or the hotwords path is dead.
- With unit+vocab, the mechanism engages: `pipe wire` → `pipewire` at score 1.5.
- Effect size is narrow on synthetic speech: `systemd`→`system D`, `hyprland`→
  `hyperland`, `hyprctl`→`Hypercutal`, `onnx`→`on's` survive at 1.5 and 2.5.
  Score 4.0 over-biases and distorts neighbors (`system v`, `hyper cattle`,
  dropped `with`). Sweet spot on this data: 1.5–2.5, fixing only close calls.
- Latency cost is modest: beam+hotwords 0.5–0.6 s vs greedy 0.4–0.5 s for the same
  clips — inside the 700 ms budget for short utterances. Cold load 3.1 s vs 2.3 s.
- Verdict: keep the plumbing (config-flagged, default greedy/off). Do NOT enable by
  default yet. Next: re-test on human speech, where formant variation may give the
  beam more to work with; espeak's canonical pronunciation likely understates the win.

## Covered live (Phase 2 service on reference machine)

- End-to-end hold-key dictation works: trigger, capture, decode, cleanup, insertion.
- Warm RSS ~934 MB cgroup total; unloaded listener 12–28 MB (confirm post-idle drop live).
- Transcription WER ~14% on jargon-dense read speech; conversational speech scores better.

## Moonshine-tiny service (Phase 3, 2026-10-02 — current stack, see `decisions/0003`)

Stack: Moonshine tiny q8 ASR (English-only, no neural punct stage — ASR punctuates
natively; spoken-punct/ITN are deterministic rules in `cleanup.py`).

Versions: `sherpa-onnx 1.13.8`, `sounddevice 0.5.6`, `numpy 2.5.3`,
model `sherpa-onnx-moonshine-tiny-en-int8` (27M params, ~119 MB shipped files).
Dev: `pytest 9.1.1`, `ruff 0.16.9`. One-shot quant tools (punct eval only, not shipped):
`onnx 1.23.1`, `onnxruntime 1.30.0`.

Measured on i5-1235U, threads=4:

- Cold start (import + model load to ready): 0.79 s (vs 1.8–2.3 s Parakeet).
- Worker peak RSS (`/proc` VmHWM, load + 16.7 s decode): 286 MB (vs ~810 MB Parakeet).
- Decode: bundled `0.wav` (6.6 s): 0.19 s; `1.wav` (16.7 s): 0.68 s roundtrip.
  5 s utterance scales to ~0.2–0.3 s — inside the 700 ms budget with wide margin.
- Sample transcript (verbatim, includes native `, .`):
  `After early nightfall, the yellow lamps would light up here and there ... brothels.`
- Shipped model footprint: ~119 MB (moonshine int8 files minus test wavs) —
  inside the ≤200 MB combined budget with room for the future grammar SLM.
- Rejected: `sherpa-onnx-punct-ct-transformer-zh-en` (FunASR zh-common conversion).
  Emits fullwidth `。，？` and duplicates Moonshine's native marks (`,，`, ` .。`).
  int8 quant of it verified parity 3/3 at 3 ms (294→75 MB) — method kept, model dropped.

## Still pending

- End-to-end hold-key run against the moonshine worker (service wiring unchanged,
  daemon-tested with mocks; live mic check pending).
- `wtype` insertion into XWayland/Electron apps (native Wayland verified).
- Exact 10 s / 30 s utterance brackets on the new stack.
- Grammar SLM iteration gated on punct/grammar error rate (see `future.md` §1).

## ASR A/B (2026-10-02 — verdict: stay with tiny, see `decisions/0004-stay-with-tiny.md`)

Contenders (threads=4, i5-1235U, separate process per run, peak = `ru_maxrss`):

- A: Moonshine tiny q8 (control, ~119 MB shipped)
- B: Moonshine base-en int8 (~275 MB shipped)
- C: SenseVoice-Small int8 + `use_itn=True` (~229 MB shipped)

Fixtures: `/tmp/para-take1.wav` (user mic, 19.0 s — since moved to `audio/`),
`audio/tech1-3.wav` (resampled 22.05→16 kHz), moonshine `0.wav` (6.6 s, literary).

| clip | A tiny: decode / peak / key terms | B base: decode / peak / key terms | C sensevoice: decode / peak / key terms |
|---|---|---|---|
| para (19 s, "PipeWire graph", "Mike/mic", "example dot com") | 0.67 s / 324 MB. "pipeline graph"; "So, enter according to my example.com"; mic✓ | 0.94 s / **499 MB**. "pipe wire graph"; "Send that according to mike@example.com"; "mike" for mic✗ | 0.66 s / 367 MB. "paragraph"; "send there according to mic at example. co"; mic✓, ITN punct✓ |
| tech1 ("systemd unit … PipeWire … Hyprland startup") | 0.16 s / 201 MB. "system the unit … pipeline graph … hyperland" | 0.20 s / 331 MB. "pipe while a graph" (worse) | 0.21 s / 330 MB. "reunit … pipeline wire … hyperland target" (worse) |
| tech2 ("unix socket … wayland compositor") | 0.14 s / 204 MB. "unique socket … composite" | 0.50 s / 336 MB. "unique socket … **compositor**✓" | 0.24 s / 334 MB. "Checkck sockets … waylandcomp" (stutter + run-on) |
| tech3 ("quantized transducer … real time") | 0.14 s / 200 MB. "**transducer**✓ … cereal time" | 0.31 s / 332 MB. "transusa … run-scene" (worse) | 0.20 s / 330 MB. "one time trans … synferum" (worst) |
| 0.wav (literary 6.6 s) | 0.19 s / 215 MB, near-verbatim | 0.41 s / 350 MB, near-verbatim | 0.28 s / 337 MB, near-verbatim + better sentence split |

Load times: A 0.6–0.8 s, B 1.3–1.5 s, C ~1.0 s. No ground-truth transcripts for
tech1-3, so comparison is qualitative on key terms, not WER.

Reading: no model dominates. B wins isolated words ("compositor", "pipe wire"
split, email merge) but loses others ("transusa", "pipe while a") and peaks at
**499 MB on 19 s audio — over the 300–400 MB cap**. C has the nicest punctuation
(ITN) but the worst jargon (run-ons, stutters). A matches or beats both on tech
terms while staying in budget on every clip. Conclusion: the gap is vocabulary,
not capacity — address via user-owned config vocabulary, delivery, and mic.
