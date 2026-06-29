"""
Minimal waveform overlay — thin white bars on black, no pill, no clock.
Each bar has its own frequency so it looks like a real audio visualizer.
"""
import ctypes
import math
import random
import threading
import tkinter as tk

_TRANSPARENT = "#010203"
_BG = "#080808"
_BAR_LISTEN = "#ffffff"
_BAR_TRANSCRIBE = "#888888"

_W = 220
_H = 46
_N_BARS = 28
_BAR_W = 2
_BAR_GAP = 2
_FPS = 30

_GWL_EXSTYLE = -20
_WS_EX_NOACTIVATE = 0x08000000
_WS_EX_TOOLWINDOW = 0x00000080

# Each bar gets its own speed + phase + amplitude so motion looks organic
random.seed(42)
_freqs  = [0.6 + random.random() * 1.8 for _ in range(_N_BARS)]
_phases = [random.random() * math.pi * 2 for _ in range(_N_BARS)]
_amps   = [5 + random.random() * 14 for _ in range(_N_BARS)]
_bases  = [1 + random.random() * 2 for _ in range(_N_BARS)]


class RecordingOverlay:
    def __init__(self):
        self._state = "hidden"
        self._phase = 0.0
        self._root = None
        self._canvas = None
        self._ready = threading.Event()
        threading.Thread(target=self._run, daemon=True).start()
        self._ready.wait(timeout=5)

    def show_listening(self):
        self._state = "listening"
        if self._root:
            self._root.after(0, self._root.deiconify)

    def show_transcribing(self):
        self._state = "transcribing"

    def hide(self):
        self._state = "hidden"
        if self._root:
            self._root.after(0, self._root.withdraw)

    def _run(self):
        self._root = tk.Tk()
        self._root.overrideredirect(True)
        self._root.wm_attributes("-topmost", True)
        self._root.wm_attributes("-transparentcolor", _TRANSPARENT)
        self._root.configure(bg=_TRANSPARENT)

        sw = self._root.winfo_screenwidth()
        sh = self._root.winfo_screenheight()
        x = (sw - _W) // 2
        y = sh - _H - 70
        self._root.geometry(f"{_W}x{_H}+{x}+{y}")
        self._root.withdraw()

        self._canvas = tk.Canvas(
            self._root, width=_W, height=_H,
            bg=_TRANSPARENT, highlightthickness=0,
        )
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
                s | _WS_EX_NOACTIVATE | _WS_EX_TOOLWINDOW)
        except Exception:
            pass

    def _tick(self):
        state = self._state
        self._phase += 0.12
        c = self._canvas
        c.delete("all")

        if state == "hidden":
            self._root.after(1000 // _FPS, self._tick)
            return

        # Dark background rectangle
        pad = 6
        c.create_rectangle(pad, pad, _W - pad, _H - pad,
                            fill=_BG, outline="", width=0)

        cy = _H // 2
        total_w = _N_BARS * _BAR_W + (_N_BARS - 1) * _BAR_GAP
        sx = (_W - total_w) // 2
        clr = _BAR_LISTEN if state == "listening" else _BAR_TRANSCRIBE

        for i in range(_N_BARS):
            x0 = sx + i * (_BAR_W + _BAR_GAP)
            x1 = x0 + _BAR_W
            if state == "listening":
                amp = _bases[i] + _amps[i] * abs(math.sin(
                    self._phase * _freqs[i] + _phases[i]))
            else:
                amp = _bases[i] + 2 * abs(math.sin(
                    self._phase * 0.3 * _freqs[i] + _phases[i]))
            amp = max(1, amp)
            c.create_rectangle(x0, cy - amp, x1, cy + amp, fill=clr, outline="")

        self._root.after(1000 // _FPS, self._tick)
