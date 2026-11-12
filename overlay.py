"""
Recording overlay — a small dark pill with a live "thermal" waveform.

Each bar is rendered like a heat-camera blob: cool blue when quiet, burning
through red/orange/yellow to a white core when loud, with film grain and a
light ordered dither on top.

The pill is lit like an earthrise: a faint blue sky haze along the top edge,
a glowing horizon along the bottom. The horizon IS the level meter — warm
orange when you speak at a good level, cold blue when you're too quiet,
white-hot when you're clipping. On release the heat cools to grey ash while
transcribing, then the pill fades out.

The window is a per-pixel-alpha layered window (UpdateLayeredWindow), not a
Tk colour-key: that is what allows anti-aliased edges, a soft shadow and glow
that spills onto whatever is behind it.
"""
import ctypes
import math
import threading
import tkinter as tk
from collections import deque
from ctypes import wintypes

import numpy as np

# Thermal ramp, cold → hot. The hard blue→red step is what gives the heat-camera edge.
_STOPS = [
    (0.00, (14, 14, 18)),
    (0.20, (10, 20, 78)),
    (0.36, (28, 104, 255)),
    (0.47, (70, 150, 255)),
    (0.55, (240, 62, 44)),
    (0.69, (255, 122, 30)),
    (0.84, (255, 208, 64)),
    (1.00, (255, 249, 232)),
]

_BODY = (22, 20, 19)
_SKY = (60, 110, 220)

# Horizon colour per level zone — the meter speaks the same thermal language as the bars.
# Traffic-light order so it reads without thinking: green good, amber a bit off,
# red fix it. The green is the one from the thermal side-streaks, so it still fits.
_H_COLD = ((240, 58, 48), 0.9)       # too quiet
_H_COOL = ((255, 168, 40), 0.8)      # a bit quiet
_H_WARM = ((64, 214, 118), 0.85)     # good
_H_HOT = ((255, 168, 40), 0.85)      # a bit loud
_H_FLARE = ((240, 58, 48), 1.0)      # clipping (flickers)
_H_IDLE = ((200, 200, 205), 0.25)

_W = 178
_H = 48
_M = 18                  # margin around the pill for shadow + spill glow
_CW = _W + 2 * _M
_CH = _H + 2 * _M
_N_BARS = 16
_FPS = 30
_PEAK_HOLD_FRAMES = 60   # ~2s at 30 fps
_JUDGE_AFTER = 12        # don't judge the level in the first ~0.4s
_COOL_FRAMES = 9         # heat → grey ash on release
_FADE_FRAMES = 7         # fade-out after transcription

# dBFS mapping: below this is silence, above this is full height.
_DB_FLOOR = -55.0
_DB_CEIL = -12.0

_GWL_EXSTYLE = -20
_WS_EX_LAYERED = 0x00080000
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


def _horizon_target(peak_rms: float):
    d = _db(peak_rms)
    if d > -6:
        return _H_FLARE
    if d > -10:
        return _H_HOT
    if d < -42:
        return _H_COLD
    if d < -33:
        return _H_COOL
    return _H_WARM


def _build_lut():
    xs = np.linspace(0, 1, 256)
    pos = [s[0] for s in _STOPS]
    return np.stack([np.interp(xs, pos, [s[1][c] for s in _STOPS]) for c in range(3)], axis=1)


def _over(dst_rgb, dst_a, src_rgb, src_a):
    """Premultiplied 'over'. rgb arrays are premultiplied, alphas are (H, W, 1)."""
    return src_rgb * src_a + dst_rgb * (1 - src_a), src_a + dst_a * (1 - src_a)


class _Renderer:
    """Precomputes everything that doesn't change per frame. Returns BGRA, premultiplied."""

    def __init__(self):
        self.lut = _build_lut()
        yy, xx = np.mgrid[0:_CH, 0:_CW].astype(np.float32)
        self.xx, self.yy = xx + 0.5, yy + 0.5
        self.cy = _CH / 2
        self.ys = self.yy[:, 0]
        self.bar_x = np.linspace(_M + 22, _M + _W - 22, _N_BARS)
        dx = self.xx[0][None, :] - self.bar_x[:, None]
        self.ex_core = np.exp(-(dx / 2.6) ** 2)
        self.ex_aura = np.exp(-(dx / 5) ** 2)

        # Capsule signed distance: negative inside the pill.
        r = _H / 2 - 1
        seg_x = np.clip(self.xx, _M + 1 + r, _M + _W - 1 - r)
        sdf = np.hypot(self.xx - seg_x, self.yy - self.cy) - r
        self.pill = np.clip(0.5 - sdf, 0, 1)[..., None]

        # Horizon: a glowing line hugging the lower edge, brightest at the bottom
        # centre and dying out towards the ends — the curve of a planet at sunrise.
        v = (self.yy - self.cy) / r                              # -1 top … +1 bottom
        centre = np.exp(-((self.xx - _CW / 2) / (_W * 0.42)) ** 2)
        lower = np.clip((v - 0.05) / 0.8, 0, 1) ** 1.5 * centre
        line = np.exp(-((sdf + 1.6) / 1.7) ** 2)
        haze = np.exp(-np.abs(sdf + 3) / 5) * 0.5
        spill = np.exp(-np.maximum(sdf, 0) / 4) * (sdf > 0) * 0.45
        self.horizon = np.clip((line + haze) * lower * (sdf < 0.5) + spill * lower, 0, 1)[..., None]

        upper = np.clip((-v - 0.2) / 0.8, 0, 1) * centre
        self.sky = (np.exp(-((sdf + 1.2) / 1.6) ** 2) * upper * 0.28)[..., None]

        sh = np.hypot(self.xx - seg_x, self.yy - self.cy - 3) - r
        self.shadow = (0.55 * np.exp(-np.maximum(sh + 2, 0) / 5.5))[..., None]

        b = np.array([[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]]) / 16 - 0.5
        self.bayer = np.tile(b, (_CH // 4 + 1, _CW // 4 + 1))[:_CH, :_CW]

        # A few pre-rolled grain frames, cycled — live random noise costs CPU for nothing.
        rng = np.random.default_rng(7)
        self.grain = [rng.normal(0, 1, (_CH, _CW)).astype(np.float32) for _ in range(6)]
        self.frame = 0
        self.empty = np.zeros((_CH, _CW, 4), np.uint8)

    def render(self, levels, heat_scale, horizon_rgb, horizon_a, cool=0.0, fade=1.0):
        g = self.grain[self.frame % len(self.grain)]
        self.frame += 1
        gg = g[..., None]

        # Each blob is separable (x-falloff × y-falloff), so the whole field is two
        # small matrix products instead of 16 full-canvas exp() passes.
        levels = np.asarray(levels, dtype=np.float32)
        half = np.maximum(1.2, levels * (_H / 2 - 11))
        dy = np.maximum(0, np.abs(self.ys[:, None] - self.cy) - half[None, :])
        peak = (0.42 + 0.58 * levels) * heat_scale
        core = (np.exp(-(dy / 2.3) ** 2) * peak) @ self.ex_core
        aura = (np.exp(-(dy / 5) ** 2) * (0.3 * levels)) @ self.ex_aura
        field = np.clip(core + np.minimum(aura, 0.42) + g * 0.03, 0, 1)
        field = np.clip(np.floor(field * 14 + 0.5 + self.bayer * 0.9) / 14, 0, 1)

        heat_rgb = self.lut[(field * 255).astype(np.uint8)]
        horizon_rgb = np.array(horizon_rgb, np.float32)
        if cool > 0:
            # Cooling to ash: heat drains into a warm grey, keeping its brightness.
            ash = heat_rgb @ np.array([0.3, 0.55, 0.15], np.float32)
            ash = ash[..., None] * np.array([0.82, 0.8, 0.78], np.float32)
            heat_rgb = heat_rgb * (1 - cool) + ash * cool
            h_ash = horizon_rgb @ np.array([0.3, 0.55, 0.15], np.float32) * 0.8
            horizon_rgb = horizon_rgb * (1 - cool) + h_ash * cool
            horizon_a *= 1 - 0.55 * cool
        heat_rgb = heat_rgb + gg * 7
        heat_a = np.clip((field - 0.10) / 0.28, 0, 1)[..., None]
        heat_a = heat_a * (self.pill + (1 - self.pill) * 0.55)

        rgb = np.zeros((_CH, _CW, 3), np.float32)
        a = self.shadow.copy()
        rgb, a = _over(rgb, a, np.array(_BODY, np.float32) + gg * 7, self.pill)
        rgb, a = _over(rgb, a, np.array(_SKY, np.float32) + gg * 12, self.sky * (1 - cool))
        rgb, a = _over(rgb, a, np.clip(horizon_rgb + gg * 14, 0, 255), self.horizon * horizon_a)
        rgb, a = _over(rgb, a, np.clip(heat_rgb, 0, 255), heat_a)

        if fade < 1:
            rgb, a = rgb * fade, a * fade
        out = np.empty((_CH, _CW, 4), np.uint8)
        out[..., 2::-1] = np.clip(rgb, 0, 255)      # RGB → BGR
        out[..., 3] = np.clip(a[..., 0] * 255, 0, 255)
        return out


class _LayeredWindow:
    """Pushes a premultiplied BGRA frame to a WS_EX_LAYERED window."""

    def __init__(self, hwnd):
        u, g = ctypes.windll.user32, ctypes.windll.gdi32
        vp = ctypes.c_void_p
        u.GetDC.restype = vp
        u.GetDC.argtypes = [vp]
        g.CreateCompatibleDC.restype = vp
        g.CreateCompatibleDC.argtypes = [vp]
        g.CreateDIBSection.restype = vp
        g.CreateDIBSection.argtypes = [vp, vp, wintypes.UINT, ctypes.POINTER(vp), vp, wintypes.DWORD]
        g.SelectObject.restype = vp
        g.SelectObject.argtypes = [vp, vp]
        u.UpdateLayeredWindow.argtypes = [vp, vp, vp, vp, vp, vp, wintypes.DWORD, vp, wintypes.DWORD]

        class BMIH(ctypes.Structure):
            _fields_ = [("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG),
                        ("biHeight", wintypes.LONG), ("biPlanes", wintypes.WORD),
                        ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                        ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", wintypes.LONG),
                        ("biYPelsPerMeter", wintypes.LONG), ("biClrUsed", wintypes.DWORD),
                        ("biClrImportant", wintypes.DWORD)]

        class Blend(ctypes.Structure):
            _fields_ = [("op", ctypes.c_ubyte), ("flags", ctypes.c_ubyte),
                        ("alpha", ctypes.c_ubyte), ("fmt", ctypes.c_ubyte)]

        bmi = BMIH(ctypes.sizeof(BMIH), _CW, -_CH, 1, 32, 0, 0, 0, 0, 0, 0)  # top-down
        self.u = u
        self.hwnd = hwnd
        self.screen = u.GetDC(None)
        self.mem = g.CreateCompatibleDC(self.screen)
        self.bits = vp()
        hbmp = g.CreateDIBSection(self.mem, ctypes.byref(bmi), 0, ctypes.byref(self.bits), None, 0)
        g.SelectObject(self.mem, hbmp)
        self.size = wintypes.SIZE(_CW, _CH)
        self.src = wintypes.POINT(0, 0)
        self.blend = Blend(0, 0, 255, 1)   # AC_SRC_OVER, AC_SRC_ALPHA

    def push(self, bgra):
        ctypes.memmove(self.bits, bgra.ctypes.data, bgra.nbytes)
        self.u.UpdateLayeredWindow(self.hwnd, self.screen, None, ctypes.byref(self.size),
                                   self.mem, ctypes.byref(self.src), 0,
                                   ctypes.byref(self.blend), 2)   # ULW_ALPHA


class RecordingOverlay:
    def __init__(self, level_source=None):
        self._state = "hidden"
        self._level_source = level_source or (lambda: 0.0)
        self._history = deque([0.0] * _N_BARS, maxlen=_N_BARS)
        # Peak hold: the meter judges the loudest moment of the last ~2s, so
        # breathing pauses and quiet syllables don't flash it cold.
        self._recent = deque(maxlen=_PEAK_HOLD_FRAMES)
        self._smoothed = 0.0
        self._phase = 0.0
        self._cool = 0.0
        self._fade = 1.0
        self._h_rgb = np.array(_H_IDLE[0], np.float32)
        self._h_a = _H_IDLE[1]
        self._frames_listening = 0
        self._root = None
        self._win = None
        self._drawn_hidden = False
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
        # Fade out first; the reset happens in _tick once the fade is done.
        if self._state != "hidden":
            self._state = "fading"

    def _reset(self):
        self._history = deque([0.0] * _N_BARS, maxlen=_N_BARS)
        self._recent.clear()
        self._smoothed = 0.0
        self._cool = 0.0
        self._fade = 1.0
        self._frames_listening = 0
        self._h_rgb = np.array(_H_IDLE[0], np.float32)
        self._h_a = _H_IDLE[1]

    def _run(self):
        self._root = tk.Tk()
        self._root.overrideredirect(True)
        self._root.wm_attributes("-topmost", True)

        sw = self._root.winfo_screenwidth()
        sh = self._root.winfo_screenheight()
        self._root.geometry(f"{_CW}x{_CH}+{(sw - _CW) // 2}+{sh - _CH - 70 + _M}")
        self._root.update_idletasks()

        u = ctypes.windll.user32
        hwnd = u.GetParent(self._root.winfo_id()) or self._root.winfo_id()
        s = u.GetWindowLongW(hwnd, _GWL_EXSTYLE)
        u.SetWindowLongW(hwnd, _GWL_EXSTYLE, s | _WS_EX_LAYERED | _WS_EX_NOACTIVATE
                         | _WS_EX_TOOLWINDOW | _WS_EX_TRANSPARENT)

        self._renderer = _Renderer()
        self._win = _LayeredWindow(hwnd)
        self._win.push(self._renderer.empty)
        self._ready.set()
        self._tick()
        self._root.mainloop()

    def _tick(self):
        state = self._state

        if state == "hidden":
            if not self._drawn_hidden:
                self._win.push(self._renderer.empty)
                self._drawn_hidden = True
            self._root.after(1000 // _FPS, self._tick)
            return
        self._drawn_hidden = False

        if state == "listening":
            self._cool = 0.0
            self._fade = 1.0
            try:
                rms = float(self._level_source())
            except Exception:
                rms = 0.0
            target = _norm(rms)
            self._smoothed += (target - self._smoothed) * 0.35
            self._history.append(self._smoothed)
            self._recent.append(rms)
            self._frames_listening += 1
            levels = list(self._history)
            h_rgb, h_a = (_horizon_target(max(self._recent))
                          if self._frames_listening > _JUDGE_AFTER else _H_IDLE)
            if h_rgb is _H_FLARE[0]:
                h_a *= 0.8 + 0.2 * math.sin(self._frames_listening * 0.9)
            self._h_rgb += (np.array(h_rgb, np.float32) - self._h_rgb) * 0.14
            self._h_a += (h_a - self._h_a) * 0.14
            heat = 1.0
        else:
            # Released: the heat cools to grey ash and a slow wave sweeps across
            # while the text is being transcribed.
            self._cool = min(1.0, self._cool + 1 / _COOL_FRAMES)
            self._phase += 0.16
            wave = [0.12 + 0.3 * max(0.0, math.sin(self._phase - i * 0.32)) ** 4
                    for i in range(_N_BARS)]
            # Blend from the last spoken shape into the wave instead of jumping.
            k = self._cool
            levels = [h * (1 - k) + w * k for h, w in zip(self._history, wave)]
            heat = 1.0 - 0.15 * self._cool
            if state == "fading":
                self._fade -= 1 / _FADE_FRAMES
                if self._fade <= 0:
                    self._state = "hidden"
                    self._reset()
                    self._root.after(1000 // _FPS, self._tick)
                    return

        self._win.push(self._renderer.render(levels, heat, self._h_rgb, self._h_a,
                                             self._cool, max(self._fade, 0.0)))
        self._root.after(1000 // _FPS, self._tick)
