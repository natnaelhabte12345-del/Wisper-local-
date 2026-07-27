"""
Recording overlay — a small rounded pill with a live waveform.

The bars show the microphone level as it actually is: flat when you stop
talking, tall when you speak. (The earlier version animated constantly, which
looked busy and told you nothing.) A colour bar on each side reads the level
at a glance — green good, orange borderline, red too quiet or clipping.
"""
import ctypes
import math
import threading
import tkinter as tk
from collections import deque

_TRANSPARENT = "#010203"
_BG = "#e9e9eb"                   # hell, wie die Referenz
_BAR_LISTEN = "#1c1c1e"           # dunkle Balken auf hellem Grund
_BAR_TRANSCRIBE = "#9a9aa0"

# Auf hellem Grund brauchen die Signalfarben mehr Tiefe, sonst leuchten sie aus.
_GOOD = "#1faa5a"
_OK = "#d18700"
_BAD = "#d13438"

_W = 178              # 3.7:1 — die Referenz ist gedrungen, nicht schlank
_H = 48
_RADIUS = 24          # voll gerundete Enden = halbe Höhe
_N_BARS = 24
_BAR_W = 3            # dicker als vorher, sonst wirkt es blass
_BAR_MIN = 1.5        # Ruhehöhe: saubere Punktreihe statt leerer Pille

# Kein Kreis, kein Symbol — nur die Wellenform über die ganze Breite.
_BARS_X0 = 18
_BARS_X1 = _W - 18
_FPS = 30
_PEAK_HOLD_FRAMES = 60   # ~2s at 30 fps

# dBFS mapping: below this is silence, above this is full height.
_DB_FLOOR = -55.0
_DB_CEIL = -12.0

_GWL_EXSTYLE = -20
_WS_EX_NOACTIVATE = 0x08000000
_WS_EX_TOOLWINDOW = 0x00000080
_WS_EX_TRANSPARENT = 0x00000020   # click-through — overlay never intercepts input


def _db(rms: float) -> float:
    return 20 * math.log10(rms) if rms > 1e-9 else -99.0


def _norm(rms: float) -> float:
    """RMS -> 0..1 on a dB scale, which matches how loudness is perceived."""
    d = _db(rms)
    if d <= _DB_FLOOR:
        return 0.0
    return min(1.0, (d - _DB_FLOOR) / (_DB_CEIL - _DB_FLOOR))


def _level_colour(rms: float, peak_clipping: bool = False) -> str:
    d = _db(rms)
    if peak_clipping or d > -6:
        return _BAD          # übersteuert
    if d < -42:
        return _BAD          # zu leise
    if d < -33 or d > -10:
        return _OK
    return _GOOD


def _round_rect(canvas, x1, y1, x2, y2, r, **kw):
    """Tk has no rounded rectangle — a smoothed polygon is the usual stand-in."""
    pts = [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r,
           x2, y2, x2 - r, y2, x1 + r, y2, x1, y2, x1, y2 - r,
           x1, y1 + r, x1, y1]
    return canvas.create_polygon(pts, smooth=True, **kw)


class RecordingOverlay:
    def __init__(self, level_source=None):
        self._state = "hidden"
        self._level_source = level_source or (lambda: 0.0)
        self._history = deque([0.0] * _N_BARS, maxlen=_N_BARS)
        # Peak hold: the meter judges the loudest moment of the last ~2s, so
        # breathing pauses and quiet syllables don't flash it red.
        self._recent = deque(maxlen=_PEAK_HOLD_FRAMES)
        self._smoothed = 0.0
        self._phase = 0.0
        self._root = None
        self._canvas = None
        self._ready = threading.Event()
        threading.Thread(target=self._run, daemon=True).start()
        self._ready.wait(timeout=5)

    def show_listening(self):
        # No deiconify — the window stays permanently mapped so it never
        # steals focus. Only the drawn content changes (empty = transparent).
        self._state = "listening"

    def show_transcribing(self):
        self._state = "transcribing"

    def hide(self):
        self._state = "hidden"
        self._history = deque([0.0] * _N_BARS, maxlen=_N_BARS)
        self._recent.clear()

    def _run(self):
        self._root = tk.Tk()
        self._root.overrideredirect(True)
        self._root.wm_attributes("-topmost", True)
        self._root.wm_attributes("-transparentcolor", _TRANSPARENT)
        self._root.configure(bg=_TRANSPARENT)

        sw = self._root.winfo_screenwidth()
        sh = self._root.winfo_screenheight()
        self._root.geometry(f"{_W}x{_H}+{(sw - _W) // 2}+{sh - _H - 70}")

        self._canvas = tk.Canvas(self._root, width=_W, height=_H,
                                 bg=_TRANSPARENT, highlightthickness=0)
        self._canvas.pack()
        self._root.update_idletasks()
        self._no_activate()
        self._ready.set()
        self._tick()
        self._root.mainloop()

    def _no_activate(self):
        try:
            hwnd = ctypes.windll.user32.GetParent(self._root.winfo_id()) or self._root.winfo_id()
            s = ctypes.windll.user32.GetWindowLongW(hwnd, _GWL_EXSTYLE)
            ctypes.windll.user32.SetWindowLongW(hwnd, _GWL_EXSTYLE,
                s | _WS_EX_NOACTIVATE | _WS_EX_TOOLWINDOW | _WS_EX_TRANSPARENT)
        except Exception:
            pass

    def _tick(self):
        state = self._state
        c = self._canvas
        c.delete("all")

        if state == "hidden":
            self._root.after(1000 // _FPS, self._tick)
            return

        # Der Pegel steckt jetzt im Rand der Pille selbst — kein Extra-Element,
        # das den ruhigen Look kaputt macht.
        edge = ""
        if self._state == "listening" and self._recent:
            edge = _level_colour(max(self._recent))
        _round_rect(c, 1, 1, _W - 2, _H - 2, _RADIUS, fill=_BG,
                    outline=edge, width=2 if edge else 0)

        rms = 0.0
        if state == "listening":
            try:
                rms = float(self._level_source())
            except Exception:
                rms = 0.0
            # Bars show the moment — that IS the waveform.
            target = _norm(rms)
            self._smoothed += (target - self._smoothed) * 0.35
            self._history.append(self._smoothed)
            self._recent.append(rms)
        else:
            # Transcribing: nothing is being recorded, so show a slow pulse
            # rather than a fake waveform.
            self._phase += 0.1
            self._history.append(0.18 + 0.12 * abs(math.sin(self._phase)))

        cy = _H / 2
        max_amp = _H / 2 - 9
        colour = _BAR_LISTEN if state == "listening" else _BAR_TRANSCRIBE

        # Runde Enden über capstyle — deutlich weicher als eckige Rechtecke.
        span = _BARS_X1 - _BARS_X0 - _BAR_W
        step = span / max(_N_BARS - 1, 1)
        for i, v in enumerate(self._history):
            x = _BARS_X0 + _BAR_W / 2 + i * step
            amp = max(_BAR_MIN, v * max_amp)
            c.create_line(x, cy - amp, x, cy + amp, fill=colour,
                          width=_BAR_W, capstyle=tk.ROUND)

        self._root.after(1000 // _FPS, self._tick)

