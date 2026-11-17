"""
Keep the mouse wheel scrolling while Right Ctrl is held for dictation.

Held Ctrl turns the wheel into "zoom" (browsers) or nothing (many apps), so scrolling
seems frozen while you talk. A low-level mouse hook catches wheel events during
recording and re-sends them with Ctrl briefly released. hotkey.py is told to treat
that blink as "still held", so the recording is not cut off.

Only Right Ctrl is touched; Left Ctrl + wheel (zoom) works as usual.
"""
import ctypes
import queue
import threading
import time
from ctypes import wintypes

import hotkey

_user32 = ctypes.windll.user32
_WH_MOUSE_LL = 14
_WM_MOUSEWHEEL = 0x020A
_WM_MOUSEHWHEEL = 0x020E
_MARK = 0x57495350          # our own events carry this, so the hook lets them through
_VK_RCONTROL, _VK_LCONTROL = 0xA3, 0xA2
_ULONG_PTR = wintypes.WPARAM

_q: "queue.Queue[tuple[int, int]]" = queue.Queue()


class _MSLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = (("pt", wintypes.POINT), ("mouseData", wintypes.DWORD), ("flags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", _ULONG_PTR))


class _KEYBDINPUT(ctypes.Structure):
    _fields_ = (("wVk", wintypes.WORD), ("wScan", wintypes.WORD), ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", _ULONG_PTR))


class _MOUSEINPUT(ctypes.Structure):
    _fields_ = (("dx", wintypes.LONG), ("dy", wintypes.LONG), ("mouseData", wintypes.DWORD),
                ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD), ("dwExtraInfo", _ULONG_PTR))


class _UNION(ctypes.Union):
    _fields_ = (("ki", _KEYBDINPUT), ("mi", _MOUSEINPUT))


class _INPUT(ctypes.Structure):
    _fields_ = (("type", wintypes.DWORD), ("u", _UNION))


def _key(down: bool) -> _INPUT:
    i = _INPUT(type=1)
    i.u.ki = _KEYBDINPUT(_VK_RCONTROL, 0, 0x0001 | (0 if down else 0x0002), 0, _MARK)  # extended
    return i


def _wheel(delta: int, horizontal: bool) -> _INPUT:
    i = _INPUT(type=0)
    i.u.mi = _MOUSEINPUT(0, 0, delta & 0xFFFFFFFF, 0x1000 if horizontal else 0x0800, 0, _MARK)
    return i


def _pressed(vk: int) -> bool:
    return bool(_user32.GetAsyncKeyState(vk) & 0x8000)


def _worker():
    while True:
        delta, horiz = _q.get()
        batch = [(delta, horiz)]
        time.sleep(0.01)                      # collect a burst of wheel ticks into one blink
        while not _q.empty():
            batch.append(_q.get())
        ev = [_key(False)] + [_wheel(d, h) for d, h in batch] + [_key(True)]
        hotkey.ignore_until = time.time() + 0.3   # the blink must not end the recording
        arr = (_INPUT * len(ev))(*ev)
        _user32.SendInput(len(ev), arr, ctypes.sizeof(_INPUT))


_HOOKPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)


def _proc(n, wparam, lparam):
    if n >= 0 and wparam in (_WM_MOUSEWHEEL, _WM_MOUSEHWHEEL):
        info = ctypes.cast(lparam, ctypes.POINTER(_MSLLHOOKSTRUCT)).contents
        if info.dwExtraInfo != _MARK and _pressed(_VK_RCONTROL) and not _pressed(_VK_LCONTROL):
            delta = ctypes.c_short(info.mouseData >> 16).value
            _q.put((delta, wparam == _WM_MOUSEHWHEEL))
            return 1                          # swallow the Ctrl-flavoured original
    return _user32.CallNextHookEx(None, n, wparam, lparam)


_keep = _HOOKPROC(_proc)   # must stay referenced or the callback is garbage-collected


def _run():
    _user32.SetWindowsHookExW.argtypes = (ctypes.c_int, _HOOKPROC, wintypes.HINSTANCE, wintypes.DWORD)
    _user32.SetWindowsHookExW.restype = wintypes.HHOOK
    _user32.CallNextHookEx.argtypes = (wintypes.HHOOK, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)
    _user32.CallNextHookEx.restype = ctypes.c_ssize_t
    hook = _user32.SetWindowsHookExW(_WH_MOUSE_LL, _keep, None, 0)
    if not hook:
        print("[wheel] mouse hook failed - wheel stays Ctrl-flavoured while recording")
        return
    msg = wintypes.MSG()
    while _user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
        pass


def start():
    threading.Thread(target=_worker, daemon=True).start()
    threading.Thread(target=_run, daemon=True).start()
