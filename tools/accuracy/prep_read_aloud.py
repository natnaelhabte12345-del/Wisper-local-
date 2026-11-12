"""Turn Nati's read-aloud session into a scoreable set (his real voice, known text).

    .venv\\Scripts\\python.exe tools\\accuracy\\prep_read_aloud.py <out_dir> [YYYY-MM-DD]

Looks at the day's saved clips, matches each numbered sentence of tests/read_aloud.md to the
clip whose transcript is most similar (so a repeated or skipped sentence doesn't shift the rest),
and writes <out_dir>/manifest.json. Then:

    run_bench.py <out_dir> synth current speechmatics deepgram assemblyai ...   (uses the same wavs)
    score.py <out_dir>
"""
import difflib
import glob
import json
import os
import re
import sys
import datetime as dt

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

TERMS = {
    1: ["Claude Code", "Jarvis", "terminal", "pop-up|popup"],
    2: ["queen", "Stockfish", "knight"],
    3: ["don't touch", "Spotify", "Discord", "OneDrive", "Opera GX", "Opera"],
    4: ["Groq", "not Grok|not groq", "Whisper"],
    5: ["BitLocker", "forty eight digit|48 digit|48-digit|forty-eight digit", "recovery key"],
    6: ["PowerShell", "administrator", "scheduled task", "Jarvis"],
    7: ["Android", "ADB", "wirelessly", "MCP", "times out"],
    8: ["Sonnet", "Opus", "usage", "go back"],
    9: ["don't deploy", "production", "preview", "Vercel"],
    10: ["Supabase", "Clerk", "Stripe"],
    11: ["main goal", "not to build", "ten users|10 users"],
    12: ["Playwright", "screenshot", "landing page", "headline", "cut off"],
    13: ["nicht", "Terminal", "aufpoppt", "Jarvis", "Hintergrund"],
    14: ["Schlüsseldienst", "Fotos", "Öffnungszeiten", "Google Profil"],
    15: ["model", "not", "whole meaning", "different voices", "background noise"],
}


def items():
    txt = open(os.path.join(ROOT, "tests", "read_aloud.md"), encoding="utf-8").read().split("\n===", 1)[1]
    out = []
    for m in re.finditer(r"^(\d+)\.\s+(.*)$", txt, re.M):
        out.append((int(m.group(1)), m.group(2).strip()))
    return out


def main():
    out_dir = sys.argv[1]
    day = sys.argv[2] if len(sys.argv) > 2 else dt.date.today().isoformat()
    os.makedirs(out_dir, exist_ok=True)
    clips = []
    for j in sorted(glob.glob(os.path.join(ROOT, "recordings", day, "*.json"))):
        d = json.load(open(j, encoding="utf-8"))
        wav = j[:-5] + ".wav"
        if d.get("raw") and os.path.exists(wav):
            clips.append({"wav": wav, "raw": d["raw"], "stem": os.path.basename(j)[:-5]})
    manifest, used = [], set()
    for n, text in items():
        best, score = None, 0.0
        for c in clips:
            if c["stem"] in used:
                continue
            r = difflib.SequenceMatcher(None, text.lower(), c["raw"].lower()).ratio()
            if r > score:
                best, score = c, r
        if best and score >= 0.45:
            used.add(best["stem"])
            manifest.append({"id": f"r{n:02d}", "lang": "de" if n in (13, 14) else "en", "text": text,
                             "terms": TERMS[n], "cond": "real_voice", "voice": "Nati",
                             "wav": best["wav"], "seconds": 0, "match": round(score, 2)})
        else:
            print(f"item {n}: no matching clip (best {score:.2f}) — skipped")
    json.dump(manifest, open(os.path.join(out_dir, "manifest.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print(f"{len(manifest)} of {len(items())} sentences matched -> {out_dir}")


if __name__ == "__main__":
    main()
