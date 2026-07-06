"""
Types text via the Win32 SendInput API using KEYEVENTF_UNICODE events.

Why not keyboard.write(): the keyboard library keeps its own key-state table
and re-presses modifiers it wrongly believes are held. A stuck synthetic Ctrl
turns typed "l" into Ctrl+L (browser URL bar) and eats text in other apps.
Unicode events carry no virtual-key code, so they can never be interpreted
as a shortcut — and they are layout-independent (German umlauts just work).
"""
import time
import ctypes
from ctypes import wintypes

_user32 = ctypes.windll.user32

_INPUT_KEYBOARD = 1
_KEYEVENTF_KEYUP = 0x0002
_KEYEVENTF_UNICODE = 0x0004

_ULONG_PTR = wintypes.WPARAM  # pointer-sized unsigned


class _KEYBDINPUT(ctypes.Structure):
    _fields_ = (
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", _ULONG_PTR),
    )


class _MOUSEINPUT(ctypes.Structure):
    # Needed only so the INPUT union has the correct (larger) size
    _fields_ = (
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", _ULONG_PTR),
    )


class _INPUTUNION(ctypes.Union):
    _fields_ = (("ki", _KEYBDINPUT), ("mi", _MOUSEINPUT))


class _INPUT(ctypes.Structure):
    _fields_ = (("type", wintypes.DWORD), ("union", _INPUTUNION))


def _key_event(vk=0, scan=0, flags=0) -> _INPUT:
    inp = _INPUT()
    inp.type = _INPUT_KEYBOARD
    inp.union.ki = _KEYBDINPUT(vk, scan, flags, 0, 0)
    return inp


def _send(events: list) -> None:
    n = len(events)
    arr = (_INPUT * n)(*events)
    _user32.SendInput(n, arr, ctypes.sizeof(_INPUT))


# All modifier virtual-key codes: L/R Ctrl, Shift, Alt, Win
_MODIFIER_VKS = (0xA2, 0xA3, 0xA0, 0xA1, 0xA4, 0xA5, 0x5B, 0x5C)


def _release_modifiers() -> None:
    """Force key-up for every modifier so no stuck Ctrl/Shift/Alt/Win
    turns the typed text into shortcuts."""
    _send([_key_event(vk=vk, flags=_KEYEVENTF_KEYUP) for vk in _MODIFIER_VKS])


def inject(text: str) -> None:
    text = text.replace("\n", " ").replace("\r", " ").strip()
    if not text:
        return

    _release_modifiers()
    time.sleep(0.02)

    # Each char as a unicode key-down + key-up pair (UTF-16 code units,
    # so emoji/surrogate pairs work too). Sent in chunks so slow apps keep up.
    units = text.encode("utf-16-le")
    events = []
    for i in range(0, len(units), 2):
        code = units[i] | (units[i + 1] << 8)
        events.append(_key_event(scan=code, flags=_KEYEVENTF_UNICODE))
        events.append(_key_event(scan=code, flags=_KEYEVENTF_UNICODE | _KEYEVENTF_KEYUP))

    _CHUNK = 100  # 50 chars per SendInput call
    for i in range(0, len(events), _CHUNK):
        _send(events[i : i + _CHUNK])
        time.sleep(0.005)
