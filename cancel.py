"""
Press Delete to throw a dictation away.

From pressing Right Ctrl until the text has been typed, a Delete key press cancels the
take: nothing is typed and nothing is archived. A low-level keyboard hook swallows that
Delete, so it does not also delete a character in the text box you are in. When no
dictation is running, Delete behaves normally.
"""
import ctypes
import threading
from ctypes import wintypes

_user32 = ctypes.windll.user32
_WH_KEYBOARD_LL = 13
_VK_DELETE = 0x2E
_WM_KEYDOWN, _WM_KEYUP, _WM_SYSKEYDOWN, _WM_SYSKEYUP = 0x100, 0x101, 0x104, 0x105
_ULONG_PTR = wintypes.WPARAM

requested = False        # main.py clears it on a new take and checks it before typing
armed = lambda: False    # main.py sets this: True while recording or processing
_swallowing = False      # a Delete key-down was swallowed, so swallow its key-up too


class _KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = (("vkCode", wintypes.DWORD), ("scanCode", wintypes.DWORD), ("flags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", _ULONG_PTR))


_HOOKPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)


def _proc(n, wparam, lparam):
    global requested, _swallowing
    if n >= 0:
        vk = ctypes.cast(lparam, ctypes.POINTER(_KBDLLHOOKSTRUCT)).contents.vkCode
        if vk == _VK_DELETE:
            if wparam in (_WM_KEYDOWN, _WM_SYSKEYDOWN) and armed():
                requested = True
                _swallowing = True
                return 1
            if wparam in (_WM_KEYUP, _WM_SYSKEYUP) and _swallowing:
                _swallowing = False
                return 1
    return _user32.CallNextHookEx(None, n, wparam, lparam)


_keep = _HOOKPROC(_proc)   # keep a reference or the callback gets garbage-collected


def _run():
    _user32.SetWindowsHookExW.argtypes = (ctypes.c_int, _HOOKPROC, wintypes.HINSTANCE, wintypes.DWORD)
    _user32.SetWindowsHookExW.restype = wintypes.HHOOK
    _user32.CallNextHookEx.argtypes = (wintypes.HHOOK, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)
    _user32.CallNextHookEx.restype = ctypes.c_ssize_t
    if not _user32.SetWindowsHookExW(_WH_KEYBOARD_LL, _keep, None, 0):
        print("[cancel] keyboard hook failed - Delete will not cancel a dictation")
        return
    msg = wintypes.MSG()
    while _user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
        pass


def start():
    threading.Thread(target=_run, daemon=True).start()
