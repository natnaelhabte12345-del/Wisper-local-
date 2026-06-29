"""
Types text directly into the active field using keyboard.write().
No clipboard, no Ctrl+V — avoids URL bar focus jump in Chrome/Brave.
Falls back to clipboard paste only if text contains characters keyboard.write() can't send.
"""
import time
import keyboard
import pyperclip


def inject(text: str) -> None:
    text = text.replace("\n", " ").replace("\r", " ").strip()
    if not text:
        return
    try:
        # Direct typing — no clipboard involved, no modifier keys
        keyboard.write(text, delay=0)
    except Exception:
        # Fallback: clipboard paste (handles rare edge-case chars)
        try:
            old = pyperclip.paste()
        except Exception:
            old = ""
        pyperclip.copy(text)
        time.sleep(0.05)
        keyboard.send("ctrl+v")
        time.sleep(0.15)
        try:
            pyperclip.copy(old)
        except Exception:
            pass
