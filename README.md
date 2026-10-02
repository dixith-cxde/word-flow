# voxd — Offline Hold-to-Talk Dictation

Hold a key, speak, release — transcribed text is inserted at the cursor in any
application. Fully offline after the model download. English only, Wayland
(Hyprland primary, GNOME toggle supported), no streaming, no GUI, no X11.

Stack: **Moonshine-tiny ASR** (q8, English-only, punctuates natively) +
**silero-VAD** silence trim + deterministic text rules (`cleanup.py`:
spoken-punctuation, filler stripping, tidy). Models on disk ~120 MB
(budget ≤200 MB). Details: `docs/spec.md`, `docs/decisions/0002-tiny-stack.md`
(as amended by `0003-no-neural-punct.md`).

## How it works

```text
Hyprland bind press ──► vox start ──► daemon opens mic (recorder lives only
                                      while the key is held) ──► pill shows
                                      "Listening…" (bottom-center overlay)
Hyprland bind release ─► vox stop ──► worker transcribes ──► cleanup ──► text
                                      inserted at cursor via wtype
                                      (wl-copy + hyprctl fallback)
```

- **Daemon** (`voxd`, stdlib only): persistent listener on a unix socket, 0% idle
  CPU. Owns the recorder, the worker lifecycle, and the event feed the pill
  subscribes to (`recording` / `transcribing` / `done`).
- **Worker**: loads the model on first use, exits after `worker_idle_timeout`
  (default 25 s) so memory returns to the OS. Cold load ~0.8 s, warm
  release-to-text ~0.2 s for a 5 s utterance.
- **Recorder**: short-lived `sounddevice` capture streaming raw PCM to the
  daemon — never touches disk, alive only while the key is held.
- **Pill** (`voxd-pill.service`): GTK4 layer-shell overlay, bottom-center, with
  animated voice bars. Shows `Listening…` / `Transcribing…`; hides the moment
  transcription lands, auto-hides errors after 2 s. If the overlay service
  isn't running, `vox` falls back to a best-effort `hyprctl notify` that can
  never break dictation. GNOME uses press-to-toggle (`vox toggle`).

## Requirements

- Linux with systemd user services; Python ≥ 3.12 (or `uv`)
- Hyprland (`hyprctl`) for hold-to-talk, or GNOME for press-to-toggle
- Text insertion: `wtype`, or `wl-copy` + `hyprctl`
- Mic via PortAudio (`sounddevice`)
- Pill overlay only: system `python3-gi` + `gtk4` + `gtk-layer-shell`
  (`setup.sh` offers to install them on pacman systems)

## Install

```sh
./setup.sh [--key KEY] [--with-models] [--clean-models] [--uninstall]
```

- Default key `F9` (Hyprland hold, GNOME toggle). Model download is opt-in only.
- Installs: venv to `~/.local/share/voxd`, `vox`/`voxd`/`voxd-pill` shims to
  `~/.local/bin`, units to `~/.config/systemd/user/`, config to
  `~/.config/voxd/config.toml`, Hyprland binds to `~/.config/voxd/hypr-binds.conf`.
- Verify: focus a text editor, hold `KEY`, speak, release.
- Logs: `journalctl --user -u voxd.service` (daemon),
  `journalctl --user -u voxd-pill.service` (overlay).

## Usage

```sh
vox start | stop | status | toggle
voxd [--config PATH]
```

- First run loads the model (~1 s); the worker exits after 25 s idle and memory
  drops back. Lower `worker_idle_timeout` in `~/.config/voxd/config.toml` for a
  smaller warm window at the cost of more cold loads.
- Silence-only utterances insert nothing (`note: silence`). Set `vad_model = ""`
  to disable VAD trimming.

## Measured budgets (i5-1235U, Hyprland/CachyOS)

| Budget | Measured |
|---|---|
| Idle < 30 MB RSS, 0% CPU | Daemon ~5–20 MB, 0 jiffies over 5 s |
| Key-to-record < 150 ms | `vox start` roundtrip 68 ms |
| Release-to-text < 700 ms (5 s utterance) | ~0.2 s warm (cold +0.8 s model load) |
| Warm-peak RSS | 189–286 MB (Moonshine-tiny q8) |
| Models on disk ≤ 200 MB | ~120 MB |

Full numbers and method: `docs/benchmarks.md`.

## Develop

```sh
uv venv .venv && uv pip install -e ".[dev]"
.venv/bin/python -m pytest -q
.venv/bin/ruff check src tests prototype ui
.venv/bin/ruff format src tests prototype ui
.venv/bin/pre-commit run --all-files
.venv/bin/python prototype/mic_spike.py --file <wav>   # or --mic / --mic-secs N
.venv/bin/voxd [--config PATH]                          # daemon directly
```

Conventions (`AGENTS.md`): event-driven, 0% idle CPU; OS interaction
(trigger/capture/insert/autostart) behind narrow interfaces; text cleanup stays
pure with unit tests — never edit tests to pass; pin versions with a one-line
justification; checkpoint commit per step; record choices in
`docs/decisions/NNNN-title.md`.

Layout: `src/dictation/` (daemon, worker, recorder, client, cleanup, vad,
insert, config, protocol, pill_state) · `ui/pill.py` (overlay) ·
`systemd/` (units) · `prototype/` (mic spike) · `tests/` (61 tests) ·
`docs/` (spec, research, benchmarks, decisions, future) · `audio/` (fixtures).

## Privacy

No network use after model download. No audio/transcript logging by default
(mic audio is piped in memory, never written to disk).

## License

MIT — see `LICENSE`.
