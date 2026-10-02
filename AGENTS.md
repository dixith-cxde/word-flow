# Scope

Offline hold-to-talk dictation for Linux Wayland (Hyprland on CachyOS primary, X11 deferred). Fully offline after model download. Spec: `docs/spec.md`; V1 is English only, no streaming, GUI, or X11 (Hyprland notify pill is a status indicator, not GUI). Stack (see `docs/decisions/0002-tiny-stack.md`, amended by `0003-no-neural-punct.md`): Moonshine-tiny ASR (English-only, int8, punctuates natively) + silero-VAD silence trim + deterministic text rules in `cleanup.py` (spoken-punct, fillers, tidy). Models on disk ~120 MB (budget ≤200 MB). Grammar-correction SLM deferred to next iteration, gated on measured error rate.

# Repo state

V1 service live (daemon + worker + recorder + client, 53 tests passing). ASR pivoted from Parakeet v3 int8 (~487 MB) to Moonshine-tiny q8; neural punct evaluated and rejected; transducer backend retired (0005). Research → `docs/research.md`, measurements → `docs/benchmarks.md`.

# Constraints

- Owner knows Go/TS/Python; any other language needs written justification in `docs/decisions`.
- Event-driven, 0% idle CPU. Mic open only while key held. Compositor keybinding signals the service (no global hotkey capture). Models load on key-down, unload after idle timeout with memory returned to OS (worker exit OK). Pipeline: transcribe (ASR punctuates natively) → spoken-punct normalize → `cleanup.clean()` → insert. Text cleanup + spoken-punct pre-pass are pure functions with unit tests.
- Budgets (confirm by measurement): idle <30MB RSS, <150ms key-to-record, <700ms release-to-text for 5s utterance. Warm-peak measured ~286MB RSS (Moonshine-tiny q8, i5-1235U).
- Keep OS interaction (trigger / capture / insert / autostart) behind narrow interfaces so other platforms need only new backends.

# Rules

- Never invent SDK/CLI APIs; verify against installed docs. Ask before installing, downloading, or recording.
- No audio/transcript logging by default (may contain secrets); never print `.env`.
- Pin versions; one-line justification per dependency. Small changes, checkpoint commit per step. Choices → `docs/decisions/NNNN-title.md`. Never edit tests to pass.
# Commands

- Setup: `uv venv .venv && uv pip install -e ".[dev]"`
- Install (home dir + service + keybind): `./setup.sh [--key KEY] [--with-models]`
- Test: `.venv/bin/python -m pytest -q`
- Lint: `.venv/bin/ruff check src tests prototype ui`
- Format: `.venv/bin/ruff format src tests prototype ui` (CI checks `--check`)
- Hooks: `.venv/bin/pre-commit run --all-files` (whitespace, private-key scan, ruff)
- Spike: `.venv/bin/python prototype/mic_spike.py --file <wav>` |
  `--mic` (interactive Enter start/stop) | `--mic-secs N`
- Service: `.venv/bin/voxd [--config PATH]` + `.venv/bin/vox start|stop|status`
  (Hyprland `bind`/`bindr` exec `vox start`/`vox stop`; user unit in `systemd/`)
- Done = build/lint/tests pass, diff scoped, new behavior tested, benchmarks re-run if perf-relevant.
