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
import archive
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
        # The bars follow the real mic level, so the overlay needs to read it live.
        _overlay = RecordingOverlay(level_source=_recorder.current_level)
    return _overlay


# ── Hotkey callbacks ───────────────────────────────────────────────────────────
def on_press():
    global _recording, _busy, _target_hwnd
    if _busy:
        return
    # Capture which window the user was typing in before overlay appears
    _target_hwnd = ctypes.windll.user32.GetForegroundWindow()
    _recording = True
    # Open the mic BEFORE drawing the overlay — the Tk redraw costs enough
    # milliseconds to clip the first syllable, which derails the whole sentence.
    _recorder.start(on_max_reached=on_release)
    _get_overlay().show_listening()


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
    ov = _get_overlay()
    try:
        ov.show_transcribing()
        audio = _recorder.stop()

        if audio.size < 16000 * 0.5:   # less than 0.5s — ignore
            ov.hide()
            return

        print()
        t0 = time.time()
        raw = transcriber.transcribe(audio)
        text = raw
        t_stt = time.time() - t0
        print(f"    Whisper   {t_stt:>6.2f}s")

        t_fmt = 0.0
        if text:
            t1 = time.time()
            # The regex layer runs either way — it is free and deterministic.
            # FORMAT_TEXT only decides whether the LLM pass follows.
            text = formatter.format_text(text) if FORMAT_TEXT \
                else formatter.quick_fix(text)
            t_fmt = time.time() - t1
            print(f"    Formatter {t_fmt:>6.2f}s{'' if FORMAT_TEXT else '   (nur Regex)'}")

        if raw:
            rms, dbfs, peak = transcriber.level(audio)
            # Pegel mitspeichern, damit sich später zeigen lässt, ob ein
            # schlechtes Transkript schlicht zu leise aufgenommen war.
            archive.save(audio, raw, text, {
                "dbfs": round(dbfs, 1), "peak": round(peak, 3),
                "stt_s": round(t_stt, 2), "format_s": round(t_fmt, 2),
            })

        total = time.time() - t0
        spoken = audio.size / 16000 / 60
        wc = len(text.split())
        print(f"    {'─' * 24}")
        print(f"    Gesamt    {total:>6.2f}s   {wc} Wörter"
              + (f" · {round(wc / spoken)} W/min" if spoken > 0.02 else ""))
        if raw and raw != text:
            print(f"    roh  › {raw}")
        print(f"    text › {text}")
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
    except Exception as e:
        print(f"[process] error: {e}")
    finally:
        ov.hide()   # always clear the overlay, even if transcription/injection failed
        _busy = False


# ── Entry point ────────────────────────────────────────────────────────────────
def main():
    archive.prune()
    s = archive.stats()
    rule = "─" * 58
    print()
    print(f"  WisprWin   ·   RIGHT CTRL halten zum Diktieren")
    print(f"  {rule}")
    print(f"  Heute       {s['words_today']:>7,} Wörter")
    print(f"  Insgesamt   {s['words']:>7,} Wörter   in {s['minutes']:.0f} min   "
          f"({s['wpm']} W/min)")
    print(f"  Archiv      {s['clips']:>7} Clips    {s['mb']:.0f} MB   "
          f"(Audio {archive.RETENTION_DAYS} Tage, Texte dauerhaft)")
    print(f"  {rule}")

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
