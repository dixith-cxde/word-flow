# Offline Dictation

Offline hold-to-talk voice dictation for Linux Wayland.

Hold a key, speak, release — transcribed text is inserted at the cursor in any application. Fully offline after model download.

V1: English only, Hyprland primary (GNOME toggle supported), no streaming, no GUI, no X11. Stack: Moonshine-tiny ASR (q8, ~34 MB, punctuates natively) + deterministic cleanup. See `docs/spec.md` and `docs/decisions/0002-tiny-stack.md` (amended by `0003-no-neural-punct.md`).

## Requirements

- Linux with systemd user services
- Python >= 3.12 (or `uv`)
- Hyprland (`hyprctl`) for hold-to-talk, or GNOME for press-to-toggle
- Text insertion: `wtype`, or `wl-copy` + `hyprctl`
- Mic via PortAudio (`sounddevice`)

## Install

```sh
./install.sh [--key KEY] [--with-models]
```

- Default key: `F9` (Hyprland hold, GNOME toggle).
- `--with-models` downloads Moonshine-tiny q8 (~34 MB) + punct model + silero-vad. Opt-in only.
- Installs venv to `~/.local/share/voxd`, shims to `~/.local/bin`, service to `~/.config/systemd/user/voxd.service`, config to `~/.config/voxd/config.toml`.

Verify: focus a text editor, hold `KEY`, speak, release.

Service logs:

```sh
journalctl --user -u voxd.service
```

## Usage

```sh
vox start | stop | status | toggle
voxd [--config PATH]
```

- Hyprland: `bind` press → `vox start`, `bindr` release → `vox stop`.
- GNOME (no release event): one shortcut → `vox toggle`.
- First run loads the model (~2 s); worker exits after 25 s idle.

## Develop

```sh
uv venv .venv && uv pip install -e ".[dev]"
.venv/bin/python -m pytest -q
.venv/bin/ruff check src tests prototype
.venv/bin/ruff format src tests prototype
.venv/bin/python prototype/mic_spike.py --file <wav>
```

## Privacy

No network use after model download. No audio/transcript logging by default.

## License

MIT — see `LICENSE`.
