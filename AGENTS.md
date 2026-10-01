# Scope

Offline hold-to-talk dictation for Linux Wayland (Hyprland on CachyOS primary, X11 deferred). Fully offline after model download. Spec: `docs/spec.md`; V1 is English only, no streaming, LM cleanup, GUI, or X11.

# Repo state

Pre-scaffold: no stack, code, or commands. No installs, downloads, recording, or prototype code until `docs/decisions/0001-stack.md` is approved. Research → `docs/research.md`, measurements → `docs/benchmarks.md`.

# Constraints

- Owner knows Go/TS/Python; any other language needs written justification in `docs/decisions`.
- Event-driven, 0% idle CPU. Mic open only while key held. Compositor keybinding signals the service (no global hotkey capture). Model loads on key-down, unloads after idle timeout with memory returned to OS (worker exit OK). Text cleanup is pure functions with unit tests.
- Budgets (confirm by measurement): idle <30MB RSS, <150ms key-to-record, <700ms release-to-text for 5s utterance.
- Keep OS interaction (trigger / capture / insert / autostart) behind narrow interfaces so other platforms need only new backends.

# Rules

- Never invent SDK/CLI APIs; verify against installed docs. Ask before installing, downloading, or recording.
- No audio/transcript logging by default (may contain secrets); never print `.env`.
- Pin versions; one-line justification per dependency. Small changes, checkpoint commit per step. Choices → `docs/decisions/NNNN-title.md`. Never edit tests to pass.
- No commands exist yet; do not invent them. Fill in after scaffold. Done = build/lint/tests pass, diff scoped, new behavior tested, benchmarks re-run if perf-relevant.
