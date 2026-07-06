"""
WisprWin — local Wispr Flow alternative for Windows.

Hold Right Ctrl  →  speak  →  release  →  text is typed where your cursor is.
Transcription and formatting run via the Groq API.
"""
import sys
import threading
import ctypes
import time

from config import HOTKEY_POLL_MS, FORMAT_TEXT
import hotkey
import recorder as rec_module
import transcriber
import formatter
import injector
import tray

# ── State ─────────────────────────────────────────────────────────────────────
_recorder = rec_module.Recorder()
_overlay = None
_recording = False
_busy = False
_target_hwnd = None
_release_lock = threading.Lock()   # prevents double-fire from timer + manual release


def _get_overlay():
    global _overlay
    if _overlay is None:
        from overlay import RecordingOverlay
        _overlay = RecordingOverlay()
    return _overlay


# ── Hotkey callbacks ───────────────────────────────────────────────────────────
def on_press():
    global _recording, _busy, _target_hwnd
    if _busy:
        return
    # Capture which window the user was typing in before overlay appears
    _target_hwnd = ctypes.windll.user32.GetForegroundWindow()
    _recording = True
    _get_overlay().show_listening()
    _recorder.start(on_max_reached=on_release)


def on_release():
    global _recording, _busy
    with _release_lock:
        if not _recording:
            return
        _recording = False
        _busy = True
    threading.Thread(target=_process, daemon=True).start()


def _process():
    global _busy
    try:
        ov = _get_overlay()
        ov.show_transcribing()
        audio = _recorder.stop()

        if audio.size < 16000 * 0.5:   # less than 0.5s — ignore
            ov.hide()
            return

        t0 = time.time()
        text = transcriber.transcribe(audio)
        print(f"[timing] transcribe: {time.time()-t0:.2f}s")

        if text and FORMAT_TEXT:
            t1 = time.time()
            text = formatter.format_text(text)
            print(f"[timing] format:     {time.time()-t1:.2f}s")

        print(f"[timing] total:      {time.time()-t0:.2f}s  →  {text!r}")
        ov.hide()
        if text:
            # Only restore focus if the target window is NOT already in front.
            # The overlay uses WS_EX_NOACTIVATE and never steals focus, so in the
            # normal case the target is still frontmost — and calling
            # SetForegroundWindow anyway makes Chromium refocus its URL bar.
            if _target_hwnd and ctypes.windll.user32.GetForegroundWindow() != _target_hwnd:
                ctypes.windll.user32.SetForegroundWindow(_target_hwnd)
                time.sleep(0.15)
            injector.inject(text)
        time.sleep(0.3)
    finally:
        _busy = False


# ── Entry point ────────────────────────────────────────────────────────────────
def main():
    print("WisprWin started. Hold RIGHT CTRL to dictate.")

    # Pre-initialize overlay so Tk window exists before first keypress
    _get_overlay()

    # Pre-load the Whisper model in background so first use feels instant
    threading.Thread(target=transcriber._get_model, daemon=True).start()

    # Start hotkey monitor
    hotkey.monitor(on_press, on_release, poll_ms=HOTKEY_POLL_MS)

    # Block main thread on tray icon (blocks until Quit)
    tray.run_tray(on_quit=lambda: sys.exit(0))


if __name__ == "__main__":
    main()
