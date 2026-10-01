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

## Measurements (pending prototype approval)

- RSS: model unloaded / loaded-idle / peak (5 s and 30 s utterances) / after unload.
- Latency: cold start request→ready, warm latency, end-of-audio→text (3/10/30 s).
- WER on a short technical script read aloud.
