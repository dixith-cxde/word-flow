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
  background: rgba(0, 0, 0, 0.88);
  border-radius: 999px;
  padding: 10px 22px;
  border: 1px solid rgba(255, 255, 255, 0.12);
}
.pill label { color: #ffffff; font-size: 14px; font-weight: 500; letter-spacing: 0.2px; }
"""

_HIDE_AFTER_S = 2


class Wave(Gtk.DrawingArea):
    """Animated voice bars, drawn with cairo — no image assets, monochrome."""

    def __init__(self):
        super().__init__()
        self.set_content_width(64)
        self.set_content_height(24)
        self._phase = 0.0
        self._tick_id = None
        self.set_draw_func(self._draw, None)

    def start(self) -> None:
        if self._tick_id is None:
            self._tick_id = self.add_tick_callback(self._on_tick)

    def stop(self) -> None:
        if self._tick_id is not None:
            self.remove_tick_callback(self._tick_id)
            self._tick_id = None

    def _on_tick(self, _widget, _frame_clock) -> bool:
        self._phase += 0.35
        self.queue_draw()
        return True

    def _draw(self, _area, cr, width, height, _data) -> None:
        import math

        bars = 5
        bar_w = 3.5
        gap = (width - 12 - bar_w * bars) / (bars - 1)
        cr.set_source_rgba(1, 1, 1, 0.95)
        for i in range(bars):
            level = abs(math.sin(self._phase + i * 0.9))
            bar_h = 4 + level * (height - 8)
            cr.rectangle(6 + i * (bar_w + gap), (height - bar_h) / 2, bar_w, bar_h)
        cr.fill()


class Pill:
    def __init__(self):
        self.win = Gtk.Window()
        self.win.set_decorated(False)
        self.win.set_resizable(False)
        LayerShell.init_for_window(self.win)
        LayerShell.set_layer(self.win, LayerShell.Layer.TOP)
        # Anchor left+right with a centered child: the window spans the output
        # width (transparent) while the pill itself stays bottom-center.
        LayerShell.set_anchor(self.win, LayerShell.Edge.BOTTOM, True)
        LayerShell.set_anchor(self.win, LayerShell.Edge.LEFT, True)
        LayerShell.set_anchor(self.win, LayerShell.Edge.RIGHT, True)
        LayerShell.set_margin(self.win, LayerShell.Edge.BOTTOM, 28)
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
        self.box.set_valign(Gtk.Align.END)
        self.wave = Wave()
        self.label = Gtk.Label(label="")
        self.label.set_ellipsize(True)
        self.label.set_max_width_chars(60)
        self.box.append(self.wave)
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
            self.wave.stop()
            self.win.set_visible(False)
            return
        self.box.add_css_class(style)
        self.label.set_text(label)
        self.win.set_visible(True)
        self.win.present()
        self.wave.start()
        if style == "error":
            self._hide_timer = GLib.timeout_add_seconds(_HIDE_AFTER_S, self._auto_hide)

    def _auto_hide(self) -> bool:
        self._hide_timer = None
        self.wave.stop()
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
