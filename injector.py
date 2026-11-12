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


_kernel32 = ctypes.windll.kernel32
_CF_UNICODETEXT = 13
_GMEM_MOVEABLE = 0x0002
_PASTE_OVER = 1500   # typing this many characters in one burst garbles in real apps (measured)

_user32.OpenClipboard.argtypes = (wintypes.HWND,)
_user32.GetClipboardData.restype = wintypes.HANDLE
_user32.GetClipboardData.argtypes = (wintypes.UINT,)
_user32.SetClipboardData.argtypes = (wintypes.UINT, wintypes.HANDLE)
_kernel32.GlobalAlloc.restype = wintypes.HANDLE
_kernel32.GlobalAlloc.argtypes = (wintypes.UINT, ctypes.c_size_t)
_kernel32.GlobalLock.restype = ctypes.c_void_p
_kernel32.GlobalLock.argtypes = (wintypes.HANDLE,)
_kernel32.GlobalUnlock.argtypes = (wintypes.HANDLE,)


def _clipboard_get():
    """Current clipboard text, or None if it holds something else / is busy."""
    if not _user32.OpenClipboard(None):
        return None
    try:
        h = _user32.GetClipboardData(_CF_UNICODETEXT)
        if not h:
            return None
        p = _kernel32.GlobalLock(h)
        try:
            return ctypes.wstring_at(p)
        finally:
            _kernel32.GlobalUnlock(h)
    finally:
        _user32.CloseClipboard()


def _clipboard_set(text: str) -> bool:
    data = (text + "\0").encode("utf-16-le")
    if not _user32.OpenClipboard(None):
        return False
    try:
        _user32.EmptyClipboard()
        h = _kernel32.GlobalAlloc(_GMEM_MOVEABLE, len(data))
        p = _kernel32.GlobalLock(h)
        ctypes.memmove(p, data, len(data))
        _kernel32.GlobalUnlock(h)
        return bool(_user32.SetClipboardData(_CF_UNICODETEXT, h))
    finally:
        _user32.CloseClipboard()


def _paste(text: str) -> bool:
    """Long text goes in with Ctrl+V; the previous clipboard text is put back afterwards."""
    old = _clipboard_get()
    if not _clipboard_set(text):
        return False
    _send([_key_event(vk=0x11), _key_event(vk=0x56),
           _key_event(vk=0x56, flags=_KEYEVENTF_KEYUP), _key_event(vk=0x11, flags=_KEYEVENTF_KEYUP)])
    time.sleep(0.6)   # let the target read the clipboard before it is replaced
    if old is not None:
        _clipboard_set(old)
    return True


def inject(text: str) -> None:
    text = text.replace("\n", " ").replace("\r", " ").strip()
    if not text:
        return

    _release_modifiers()
    time.sleep(0.02)
    if len(text) > _PASTE_OVER and _paste(text):
        return

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
