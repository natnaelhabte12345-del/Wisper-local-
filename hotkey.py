"""
Global hotkey monitor — detects Ctrl + Win held simultaneously.
Uses a polling loop so we can track press AND release reliably on Windows.
Calls on_press() when the combo activates, on_release() when it breaks.
"""
import time
import threading
import keyboard   # pip install keyboard


def monitor(on_press, on_release, poll_ms: int = 50):
    """Start hotkey monitor in a daemon thread."""
    t = threading.Thread(
        target=_loop, args=(on_press, on_release, poll_ms / 1000), daemon=True
    )
    t.start()


def _loop(on_press, on_release, poll_s: float):
    active = False
    while True:
        ctrl = keyboard.is_pressed("ctrl")
        space = keyboard.is_pressed("space")
        combo = ctrl and space

        if combo and not active:
            active = True
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
