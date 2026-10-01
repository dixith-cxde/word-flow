"""vox: tiny control client for voxd (stdlib only). Usage: vox start|stop|status."""

import argparse
import json
import socket
import sys

from dictation import config as config_mod
from dictation import protocol as proto


def call(sock_path: str, req: dict) -> dict:
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    with s:
        s.connect(sock_path)
        f = s.makefile("rwb")
        proto.send_json(s, req)
        return proto.recv_json(f.readline())


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["start", "stop", "status"])
    ap.add_argument("--socket", default=None)
    args = ap.parse_args(argv)
    cfg = config_mod.load()
    sock_path = args.socket or cfg["socket"]
    try:
        resp = call(sock_path, {"cmd": args.cmd})
    except (OSError, ValueError) as e:
        print(f"vox: {e}", file=sys.stderr)
        return 1
    if args.cmd == "stop" and resp.get("ok"):
        print(resp.get("text", ""))
        return 0
    print(json.dumps(resp))
    return 0 if resp.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
