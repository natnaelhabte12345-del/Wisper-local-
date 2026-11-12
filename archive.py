"""
Local recording archive — keeps audio + transcript so a slower, better model
can label them later (see tools/review.py).

Layout, one folder per day so pruning is a single rmtree:

    recordings/2026-07-24/143052_812.wav
    recordings/2026-07-24/143052_812.json

Nothing leaves the machine here. Clips older than RETENTION_DAYS are deleted
on every start and after every save.
"""
import datetime as _dt
import json
import os
import shutil

import numpy as np
import scipy.io.wavfile as wav_io

SAMPLE_RATE = 16000
RETENTION_DAYS = 30

_ROOT = os.path.join(os.path.dirname(__file__), "recordings")


def _day_dir(when: _dt.datetime) -> str:
    return os.path.join(_ROOT, when.strftime("%Y-%m-%d"))


def save(audio: np.ndarray, raw: str, formatted: str, meta: dict | None = None) -> str | None:
    """Store one dictation. Returns the clip path, or None if nothing was saved."""
    if audio.size == 0:
        return None
    try:
        now = _dt.datetime.now()
        folder = _day_dir(now)
        os.makedirs(folder, exist_ok=True)
        stem = now.strftime("%H%M%S_") + f"{now.microsecond // 1000:03d}"

        pcm = (audio * 32767).clip(-32768, 32767).astype(np.int16)
        wav_io.write(os.path.join(folder, stem + ".wav"), SAMPLE_RATE, pcm)

        record = {
            "recorded_at": now.isoformat(timespec="seconds"),
            "duration_s": round(audio.size / SAMPLE_RATE, 2),
            "raw": raw,          # what Whisper returned
            "formatted": formatted,   # what was actually typed
            "reference": None,   # filled in later by the review pass
        }
        if meta:
            record.update(meta)
        with open(os.path.join(folder, stem + ".json"), "w", encoding="utf-8") as f:
            json.dump(record, f, ensure_ascii=False, indent=2)

        prune()
        return os.path.join(folder, stem + ".wav")
    except Exception as e:
        # Archiving must never break dictation itself.
        print(f"[archive] save failed: {e}")
        return None


def prune() -> int:
    """Free disk without losing benchmark data.

    Audio is the only large part; a labelled clip needs nothing but its JSON,
    so its .wav goes as soon as a reference exists. Unlabelled audio is kept
    for RETENTION_DAYS so a skipped review evening doesn't lose the clip.
    The .json files stay forever — that IS the benchmark set.

    Returns the number of .wav files deleted.
    """
    if not os.path.isdir(_ROOT):
        return 0
    cutoff = _dt.date.today() - _dt.timedelta(days=RETENTION_DAYS - 1)
    deleted = 0
    for folder, _, files in os.walk(_ROOT):
        try:
            day = _dt.date.fromisoformat(os.path.basename(folder))
        except ValueError:
            continue   # not a day folder — leave it alone
        expired = day < cutoff
        for name in files:
            if not name.endswith(".wav"):
                continue
            meta_path = os.path.join(folder, name[:-4] + ".json")
            labelled = False
            try:
                with open(meta_path, encoding="utf-8") as f:
                    labelled = bool(json.load(f).get("reference"))
            except Exception:
                pass
            if labelled or expired:
                try:
                    os.remove(os.path.join(folder, name))
                    deleted += 1
                except OSError:
                    pass
    return deleted


def stats() -> dict:
    """How much was dictated, how fast, and what it costs on disk.

    Counted from the .json files, so it survives the audio being pruned.
    """
    clips = 0
    total_bytes = 0
    seconds = 0.0
    words = 0
    today = _dt.date.today().isoformat()
    words_today = 0
    for folder, _, files in os.walk(_ROOT):
        for name in files:
            path = os.path.join(folder, name)
            total_bytes += os.path.getsize(path)
            if not name.endswith(".json"):
                continue
            clips += 1
            try:
                with open(path, encoding="utf-8") as f:
                    rec = json.load(f)
            except Exception:
                continue
            seconds += rec.get("duration_s", 0)
            n = len((rec.get("formatted") or rec.get("raw") or "").split())
            words += n
            if os.path.basename(folder) == today:
                words_today += n
    minutes = seconds / 60
    return {
        "clips": clips,
        "minutes": round(minutes, 1),
        "words": words,
        "words_today": words_today,
        "wpm": round(words / minutes) if minutes > 0.1 else 0,
        "mb": round(total_bytes / 1024 / 1024, 1),
    }
