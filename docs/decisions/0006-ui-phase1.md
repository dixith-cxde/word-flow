# 0006: UI phase 1 — event bus + listening pill

Date: 2026-10-02.

## Decision

- Daemon publishes `recording` / `transcribing` / `done{ok,text}` on a `subscribe`
  command held over the main socket (best-effort broadcast, dead subs dropped).
  V1 GUI ban amended: pill and tray are status surfaces, not a settings GUI
  (settings window stays Phase 2).
- Pill: GTK4 layer-shell top-center overlay on system Python (zero new pip deps),
  driven by a pure tested state machine (`pill_state.render`). Shows "Listening…"
  (pulsing) → "Transcribing…" → snippet flash → auto-hide. Memory-only display.
- Verified live: event sequence asserted in tests; pill runs clean on Hyprland
  only with `LD_PRELOAD=libgtk4-layer-shell.so` (without it the window is not a
  layer surface — distro link-order quirk, workaround baked into the installed
  wrapper with fallback lib).
- `install.sh` installs `voxd-pill.service` (graphical-session target) + wrapper,
  gated on Hyprland + gi/GTK4/layer-shell presence; otherwise warns and skips.
  Phase 2 (tray + settings + opt-in memory-only history) not started.
