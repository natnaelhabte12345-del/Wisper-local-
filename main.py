"""
WisprWin — local Wispr Flow alternative for Windows.

Hold Right Ctrl (+ Right Shift for an unfiltered take with fillers and timestamps)  →  speak  →  release  →  text is typed where your cursor is.
Transcription and formatting run via the Groq API.
"""
import sys
import threading
import ctypes
import time

from config import HOTKEY_POLL_MS, FORMAT_TEXT
import archive
import wheel
import hotkey
import recorder as rec_module
import transcriber
import formatter
import injector
import tray


class _Tee:
    """Console runs hidden, so everything printed also goes to wisprwin.log."""
    def __init__(self, stream, f):
        self.stream, self.f = stream, f

    def write(self, data):
        for out in (self.stream, self.f):
            try:
                out.write(data)
                out.flush()
            except Exception:
                pass

    def flush(self):
        pass


_log = open(__import__("os").path.join(__import__("os").path.dirname(__file__), "wisprwin.log"),
            "a", encoding="utf-8")
sys.stdout = _Tee(sys.stdout, _log)
sys.stderr = _Tee(sys.stderr, _log)
print()
print(f"=== start {time.strftime('%Y-%m-%d %H:%M:%S')} ===")

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
    hotkey.watch_shift = True
    threading.Thread(target=_process, daemon=True).start()


def _process():
    global _busy
    ov = _get_overlay()
    audio = None
    try:
        ov.show_transcribing()
        audio = _recorder.stop()

        if audio.size < 16000 * 0.5:   # less than 0.5s — ignore
            ov.hide()
            return

        print()
        t0 = time.time()
        verbatim = hotkey.verbatim
        raw = transcriber.transcribe_verbatim(audio) if verbatim else transcriber.transcribe(audio)
        text = raw
        t_stt = time.time() - t0
        print(f"    Whisper   {t_stt:>6.2f}s")

        t_fmt = 0.0
        if text and not verbatim:   # verbatim stays untouched: fillers and timings are the point
            t1 = time.time()
            # The regex layer runs either way — it is free and deterministic.
            # FORMAT_TEXT only decides whether the LLM pass follows.
            text = formatter.format_text(text) if FORMAT_TEXT \
                else formatter.quick_fix(text)
            t_fmt = time.time() - t1
            print(f"    Formatter {t_fmt:>6.2f}s{'' if FORMAT_TEXT else '   (nur Regex)'}")

        hotkey.watch_shift = False
        if hotkey.verbatim and not verbatim:   # Shift came after letting go of Ctrl
            verbatim = True
            raw = text = transcriber.transcribe_verbatim(audio)
            print("    Shift danach gedrückt -> unveränderte Fassung")

        if True:   # save even when transcription came back empty — never lose a take
            rms, dbfs, peak = transcriber.level(audio)
            # Pegel mitspeichern, damit sich später zeigen lässt, ob ein
            # schlechtes Transkript schlicht zu leise aufgenommen war.
            archive.save(audio, raw, text, {
                "dbfs": round(dbfs, 1), "peak": round(peak, 3),
                "stt_s": round(t_stt, 2), "format_s": round(t_fmt, 2),
                "engine": transcriber.last_engine,
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
        print(f"[process] error {time.strftime('%H:%M:%S')}: {e!r}")
        if audio is not None and audio.size:
            archive.save(audio, "", "", {"error": repr(e)})
            print("    Audio trotzdem gespeichert in recordings/")
    finally:
        hotkey.watch_shift = False
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
          f"({'Audio ' + str(archive.RETENTION_DAYS) + ' Tage, Texte dauerhaft' if archive.ENABLED else 'AUS - nichts wird gespeichert'})")
    print(f"  {rule}")

    # Pre-initialize overlay so Tk window exists before first keypress
    _get_overlay()

    # Pre-load the Whisper model in background so first use feels instant
    threading.Thread(target=transcriber._get_model, daemon=True).start()

    # Start hotkey monitor
    hotkey.monitor(on_press, on_release, poll_ms=HOTKEY_POLL_MS)
    wheel.start()   # mouse wheel keeps scrolling while Right Ctrl is held

    # Block main thread on tray icon (blocks until Quit)
    tray.run_tray(on_quit=lambda: sys.exit(0))


if __name__ == "__main__":
    main()
