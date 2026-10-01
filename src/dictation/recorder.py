"""Mic recorder: streams raw f32le mono 16 kHz PCM to stdout until SIGTERM.

Short-lived by design (only alive while the talk key is held). Audio never touches
disk; the daemon pipes stdout straight to the worker. Prints nothing to stdout
except PCM bytes (status goes to stderr).
"""

import argparse
import signal
import sys

import numpy as np
import sounddevice as sd


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample-rate", type=int, default=16000)
    ap.add_argument("--block-ms", type=int, default=100)
    args = ap.parse_args()

    stop = False

    def on_term(signum, frame):
        nonlocal stop
        stop = True

    signal.signal(signal.SIGTERM, on_term)
    signal.signal(signal.SIGINT, on_term)

    out = sys.stdout.buffer
    block = int(args.sample_rate * args.block_ms / 1000)
    try:
        with sd.InputStream(channels=1, dtype="float32", samplerate=args.sample_rate) as s:
            while not stop:
                data, overflow = s.read(block)
                if overflow:
                    print("recorder: input overflow, dropping", file=sys.stderr)
                out.write(np.asarray(data).reshape(-1).tobytes())
    except Exception as e:  # mic missing/unplugged: say so, don't emit silence
        print(f"RECORDER_ERROR: {e}", file=sys.stderr)
        return 2
    finally:
        out.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
