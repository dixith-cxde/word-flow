# voxd — Project Report (2026-10-02)

## 1. Summary

`voxd` (package `offline-dictation` 0.1.0) is offline hold-to-talk voice
dictation for Linux Wayland: hold a key, speak, release, and the transcript is
inserted at the cursor in any application. V1 is English-only, Hyprland
primary with GNOME press-to-toggle supported, fully offline after a one-time
opt-in model download (~120 MB on disk). The service is live: daemon + worker
+ recorder + client plus a layer-shell listening pill, with 61 tests passing
and every performance budget confirmed by measurement.

## 2. Scope status (V1 per `docs/spec.md`)

| Acceptance criterion | Status |
|---|---|
| Key hold records, release inserts transcript | Done (service wiring live; daemon-tested with mocks) |
| No network after model download | Done by design (no network code paths; no audio/transcript logging) |
| Memory/latency budgets measured and reported | Done (`docs/benchmarks.md`; summary §5) |
| Models unload after idle, memory returns to OS | Done (worker exits after `worker_idle_timeout`, default 25 s) |
| Cleanup functions have unit tests | Done (20 tests in `test_cleanup.py`) |
| No audio/transcripts on disk by default | Done (PCM piped in memory via stdout) |

Out of V1 scope (parked): other languages, streaming partials, grammar SLM
(gated on measured error rate, `docs/future.md` §1), settings GUI, X11.

## 3. Architecture

- **Daemon** (`src/dictation/daemon.py`, stdlib only): persistent unix-socket
  listener, blocking read at 0% idle CPU. Owns recorder + worker lifecycle and
  broadcasts `recording` / `transcribing` / `done{ok,text}` to subscribers.
- **Worker** (`worker.py`, `sherpa-onnx==1.13.8`): loads Moonshine-tiny q8 on
  demand; in-process unload cannot return memory to the OS (measured), so the
  worker *exits* after idle timeout instead.
- **Recorder** (`recorder.py`, `sounddevice==0.5.6` PortAudio): short-lived,
  streams raw f32le 16 kHz mono PCM to stdout; alive only while the key is held.
- **Client** (`client.py`, `vox start|stop|status|toggle`): Hyprland
  `bind`/`bindr` drive start/stop; GNOME uses `toggle`. Yields to the overlay
  when `voxd-pill.service` is active, else best-effort `hyprctl notify`.
- **Text pipeline**: ASR (punctuates natively) → spoken-punct normalize →
  `cleanup.clean()` (pure, tested) → `insert.py` (`wtype`, `wl-copy`+`hyprctl`
  fallback). Silence → empty reply, `note: silence`, nothing inserted.
- **Overlay** (`ui/pill.py`, system Python + GTK4 layer-shell): bottom-center
  pill with cairo voice bars, event-driven via `subscribe`. States from pure
  `pill_state.render()` (6 unit tests): visible for recording/transcribing,
  hidden on done, 2 s auto-hide on error.

## 4. Decision log (`docs/decisions/`)

- `0001` — stack shape: event-driven service, unix socket, systemd units.
- `0002` — Moonshine-tiny q8 + deterministic rules (≤200 MB combined).
- `0003` — neural punct rejected: Moonshine punctuates natively; the
  FunASR-derived model emitted fullwidth marks and duplicates.
- `0004` — A/B verdict (tiny vs base vs SenseVoice-Small): stay with tiny —
  no rival dominates jargon, base peaks at 499 MB (over cap).
- `0005` — transducer backend + hotwords plumbing retired (1.1 GB reclaimed).
- `0006` — UI phase 1: event bus + listening pill (status surface, not GUI).

## 5. Measured results vs budgets (i5-1235U, Hyprland/CachyOS — `docs/benchmarks.md`)

| Budget (AGENTS.md) | Measured |
|---|---|
| Idle < 30 MB RSS, 0% CPU | Daemon ~5 MB fresh / ~20 MB serving, 0 jiffies over 5 s |
| Key-to-record < 150 ms | `vox start` roundtrip 68 ms |
| Release-to-text < 700 ms (5 s) | ~0.2 s warm; cold adds ~0.8 s model load |
| Warm-peak RSS | 189 MB (2.8 s) – 286 MB (16.7 s decode) |
| Models ≤ 200 MB | ~119 MB shipped (Moonshine-tiny int8 + silero VAD) |

Decode: 6.6 s clip in 0.19 s; 16.7 s in 0.68 s. VAD trim adds ~0.03 s;
pure silence → empty reply in 0.01 s. Transcription WER ~14% on jargon-dense
read speech, better on conversational speech.

## 6. Tests (61 passing)

`test_cleanup.py` 20 · `test_service.py` 31 · `test_pill_state.py` 6 ·
`test_vad.py` 3 · `test_worker.py` 1. Hooks: whitespace, private-key scan,
ruff; CI checks `ruff format --check`. Lint/format cover
`src tests prototype ui`.

## 7. Recent UI work (this session)

1. Pill moved from screen-center to **bottom-center**: anchoring left+right did
   not stretch on Hyprland (299 px surface hugging the left edge, measured via
   `hyprctl layers`), so the pill now anchors the bottom edge only — a
   single-edge layer surface is compositor-centered — with a 48 px layer margin.
   Verified geometry: x=811 on 1920 px (centered), ~58 px above the bottom edge
   (remainder is compositor gap).
2. Pill background made fully opaque black (`#000000`); the window surface was
   already transparent.

## 8. Pending and risks

- Live-mic end-to-end run on the Moonshine worker; 10 s / 30 s utterance brackets.
- `wtype` insertion into XWayland/Electron apps (native Wayland verified).
- Grammar-correction SLM stays gated on measured error rate from daily use.
- `~/.config/voxd/config.toml` from older installs may carry retired keys
  (harmless "unknown key" warning; reinstall refreshes it).

## 9. How to run it

`./setup.sh --with-models` (opt-in download) → hold `F9` in any editor, speak,
release. Develop: `uv venv .venv && uv pip install -e ".[dev]"`,
`.venv/bin/python -m pytest -q`. Full contributor guide: `README.md`,
`AGENTS.md`.
