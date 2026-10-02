#!/usr/bin/env python3
"""voxd listening pill: layer-shell top-center overlay driven by daemon events.

System Python (gi/GTK4 from distro packages, not the voxd venv). Holds one
`subscribe` connection; reconnects with backoff across daemon restarts.
Memory-only: the done-snippet is displayed, never written anywhere.
"""

import argparse
import json
import os
import socket
import sys
import threading
import time

try:
    from dictation.pill_state import render
except ImportError:  # repo-direct run: fall back to src/ next to ui/
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
    from dictation.pill_state import render

try:
    import gi

    gi.require_version("Gtk", "4.0")
    gi.require_version("Gtk4LayerShell", "1.0")
    from gi.repository import GLib, Gtk, Gtk4LayerShell as LayerShell
except (ImportError, ValueError) as e:
    print(f"voxd-pill: GTK4 + gtk4-layer-shell required: {e}", file=sys.stderr)
    raise SystemExit(1)

CSS = b"""
window { background: transparent; }
.pill {
  background: linear-gradient(to bottom, rgba(26, 28, 36, 0.96), rgba(15, 17, 23, 0.96));
  border-radius: 999px;
  padding: 10px 22px;
  border: 1px solid rgba(255, 255, 255, 0.10);
}
.pill label { color: #e8eaed; font-size: 14px; font-weight: 500; letter-spacing: 0.2px; }
.pill .dot { font-size: 11px; }
.pill.recording { border-color: rgba(255, 95, 87, 0.55); }
.pill.recording .dot { color: #ff5f57; animation: pulse 1.1s ease-in-out infinite; }
.pill.working { border-color: rgba(88, 166, 255, 0.45); }
.pill.working .dot { color: #58a6ff; animation: breathe 1.6s ease-in-out infinite; }
.pill.done { border-color: rgba(63, 185, 80, 0.55); }
.pill.done .dot { color: #3fb950; }
.pill.error { border-color: rgba(255, 95, 87, 0.55); }
.pill.error .dot { color: #ff5f57; }
@keyframes pulse { 0% { opacity: 1; } 50% { opacity: 0.35; } 100% { opacity: 1; } }
@keyframes breathe { 0% { opacity: 1; } 50% { opacity: 0.55; } 100% { opacity: 1; } }
"""

_HIDE_AFTER_S = 2


class Pill:
    def __init__(self):
        self.win = Gtk.Window()
        self.win.set_decorated(False)
        self.win.set_resizable(False)
        LayerShell.init_for_window(self.win)
        LayerShell.set_layer(self.win, LayerShell.Layer.TOP)
        # Anchor left+right with a centered child: the window spans the output
        # width (transparent) while the pill itself stays top-center. Anchoring
        # top-only leaves the window an arbitrary size and the pill off-center.
        LayerShell.set_anchor(self.win, LayerShell.Edge.TOP, True)
        LayerShell.set_anchor(self.win, LayerShell.Edge.LEFT, True)
        LayerShell.set_anchor(self.win, LayerShell.Edge.RIGHT, True)
        LayerShell.set_margin(self.win, LayerShell.Edge.TOP, 12)
        LayerShell.set_exclusive_zone(self.win, 0)
        LayerShell.set_keyboard_mode(self.win, LayerShell.KeyboardMode.NONE)
        css = Gtk.CssProvider()
        css.load_from_data(CSS)
        Gtk.StyleContext.add_provider_for_display(
            self.win.get_display(), css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )
        self.box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        self.box.add_css_class("pill")
        self.box.set_halign(Gtk.Align.CENTER)
        self.box.set_valign(Gtk.Align.START)
        self.dot = Gtk.Label(label="●")
        self.dot.add_css_class("dot")
        self.label = Gtk.Label(label="")
        self.label.set_ellipsize(True)
        self.label.set_max_width_chars(60)
        self.box.append(self.dot)
        self.box.append(self.label)
        self.win.set_child(self.box)
        self._hide_timer = None

    def apply(self, visible: bool, style: str, label: str) -> None:
        for cls in ("recording", "working", "done", "error"):
            self.box.remove_css_class(cls)
        if self._hide_timer is not None:
            GLib.source_remove(self._hide_timer)
            self._hide_timer = None
        if not visible:
            self.win.set_visible(False)
            return
        self.box.add_css_class(style)
        self.label.set_text(label)
        self.win.set_visible(True)
        self.win.present()
        if style in ("done", "error"):
            self._hide_timer = GLib.timeout_add_seconds(_HIDE_AFTER_S, self._auto_hide)

    def _auto_hide(self) -> bool:
        self._hide_timer = None
        self.win.set_visible(False)
        return False


def event_loop(sock_path: str, pill: Pill) -> None:
    backoff = 0.5
    while True:
        try:
            s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            s.connect(sock_path)
            f = s.makefile("rwb")
            f.write((json.dumps({"cmd": "subscribe"}) + "\n").encode())
            f.flush()
            if json.loads(f.readline().decode()).get("ok") is not True:
                raise OSError("subscribe refused")
            backoff = 0.5
            while True:
                line = f.readline()
                if not line:
                    break
                visible, style, label = render(json.loads(line.decode()))
                GLib.idle_add(pill.apply, visible, style, label)
        except (OSError, ValueError):
            pass
        try:
            s.close()
        except (OSError, NameError):
            pass
        GLib.idle_add(pill.apply, False, "idle", "")
        time.sleep(backoff)
        backoff = min(backoff * 2, 10.0)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--socket", default=None)
    args = ap.parse_args()
    sock = args.socket or os.path.join(
        os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}"), "voxd.sock"
    )
    pill = Pill()
    t = threading.Thread(target=event_loop, args=(sock, pill), daemon=True)
    t.start()
    loop = GLib.MainLoop()
    try:
        loop.run()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
