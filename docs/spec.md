# Offline Dictation for Linux

Goal: Hold a key, speak, release, and have the transcribed text inserted at the cursor in any application, fully offline.
User: Only me, single user, single machine first.
In scope for version 1: hold-to-talk dictation, English, text insertion, idle unload of the model, configuration file, a service that starts on login.
Out of scope for version 1: other languages, streaming partial text, local language model cleanup, graphical settings window, X11 support, other operating systems.

Acceptance criteria:

1. Holding the configured key records audio, and releasing it inserts the transcript into the focused application.
2. No network connection is used after the model is downloaded, verified by blocking the application's network access.
3. Memory and latency budgets in AGENTS.md are measured and reported.
4. The model unloads after the idle timeout and the memory returns to the system.
5. Text cleanup functions have unit tests.
6. No audio or transcripts are written to disk by default.
