"""
Global hotkey monitor — hold RIGHT CTRL to record.
A bare modifier never triggers app shortcuts and never leaks characters
into the focused window (unlike Ctrl+Space, which browsers act on).

Uses the Win32 GetAsyncKeyState API with VK_RCONTROL (0xA3) instead of the
`keyboard` library's "right ctrl" name — that name is not reliably
distinguished from left ctrl on all keyboard layouts, which made left-ctrl
copy/paste (Ctrl+C / Ctrl+V) accidentally trigger recording too.
"""
import time
import threading
import ctypes

_VK_RCONTROL = 0xA3
_VK_RSHIFT = 0xA1
verbatim = False   # Right Shift added while Right Ctrl is held - or right after letting go
watch_shift = False  # main.py keeps this on until it has the text, so a late Shift still counts
_user32 = ctypes.windll.user32


def _right_ctrl_pressed() -> bool:
    return bool(_user32.GetAsyncKeyState(_VK_RCONTROL) & 0x8000)


def _right_shift_pressed() -> bool:
    return bool(_user32.GetAsyncKeyState(_VK_RSHIFT) & 0x8000)


def monitor(on_press, on_release, poll_ms: int = 50):
    """Start hotkey monitor in a daemon thread."""
    t = threading.Thread(
        target=_loop, args=(on_press, on_release, poll_ms / 1000), daemon=True
    )
    t.start()


def _loop(on_press, on_release, poll_s: float):
    global verbatim
    active = False
    while True:
        combo = _right_ctrl_pressed()

        if (combo and active or watch_shift) and _right_shift_pressed():
            verbatim = True

        if combo and not active:
            active = True
            verbatim = False
            try:
                on_press()
            except Exception as e:
                print(f"[hotkey] on_press error: {e}")

        elif not combo and active:
            active = False
            try:
                on_release()
            except Exception as e:
                print(f"[hotkey] on_release error: {e}")

        time.sleep(poll_s)
