"""
Vergleicht mehrere Speech-to-Text-Anbieter auf DEINER Stimme.

    .venv\\Scripts\\python.exe tools\\stt_bench.py tests\\bench_text.md <clip.wav>

Referenz ist der Text, den du vorgelesen hast — damit steht die Wahrheit fest
und niemand muss raten. Gemessen wird WER (Word Error Rate): Anteil der Wörter,
die geändert, eingefügt oder gelöscht werden müssten. Niedriger ist besser.

Anbieter werden übersprungen, wenn ihr Key nicht in .env steht.
"""
import os
import re
import sys
import time

import httpx

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import transcriber  # lädt .env und bringt _INITIAL_PROMPT mit

_KEYS = {
    "groq": "GROQ_API_KEY",
    "openai": "OPENAI_API_KEY",
    "deepgram": "DEEPGRAM_API_KEY",
    "assemblyai": "ASSEMBLYAI_API_KEY",
    "speechmatics": "SPEECHMATICS_API_KEY",
}


# ── WER ───────────────────────────────────────────────────────────────────────
def normalize(text: str) -> list[str]:
    """Kleinschreibung, Satzzeichen weg — wir messen Wörter, nicht Kommas."""
    text = text.lower().replace("ß", "ss")
    text = re.sub(r"[^\wäöü\s]", " ", text)
    return text.split()


def wer(reference: str, hypothesis: str) -> tuple[float, int]:
    ref, hyp = normalize(reference), normalize(hypothesis)
    if not ref:
        return 0.0, 0
    # Levenshtein auf Wortebene
    prev = list(range(len(hyp) + 1))
    for i, r in enumerate(ref, 1):
        cur = [i]
        for j, h in enumerate(hyp, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (r != h)))
        prev = cur
    return prev[-1] / len(ref), prev[-1]


def diff_words(reference: str, hypothesis: str, limit: int = 12) -> list[str]:
    """Grobe Liste der Wörter, die in der Referenz stehen, aber nicht im Ergebnis."""
    ref, hyp = normalize(reference), set(normalize(hypothesis))
    return [w for w in dict.fromkeys(ref) if w not in hyp][:limit]


# ── Anbieter ──────────────────────────────────────────────────────────────────
def via_groq(wav: bytes, key: str) -> str:
    r = httpx.post(
        "https://api.groq.com/openai/v1/audio/transcriptions",
        headers={"Authorization": f"Bearer {key}"},
        files={"file": ("a.wav", wav, "audio/wav")},
        data={"model": "whisper-large-v3", "response_format": "json",
              "prompt": transcriber._INITIAL_PROMPT},
        timeout=120,
    )
    r.raise_for_status()
    return r.json()["text"]


def via_groq_noprompt(wav: bytes, key: str) -> str:
    r = httpx.post(
        "https://api.groq.com/openai/v1/audio/transcriptions",
        headers={"Authorization": f"Bearer {key}"},
        files={"file": ("a.wav", wav, "audio/wav")},
        data={"model": "whisper-large-v3", "response_format": "json"},
        timeout=120,
    )
    r.raise_for_status()
    return r.json()["text"]


# Obergrenze: nur die schweren Woerter aus bench_text.md, sonst nichts. Ein
# echter Prompt kann nie besser sein als dieser hier. Damit laesst sich
# "Prompts bringen generell wenig" von "unser Prompt ist schlecht" trennen:
# gewinnt dieser Lauf deutlich, liegt es an unserem Prompt — sonst am Mechanismus.
_FOCUSED_PROMPT = (
    "Vercel, Supabase, Prisma, JWT, Next.js, Middleware, Build, Cache, "
    "Deployment, Environment Variables, Refresh, Genauigkeit, Testtexte"
)


def via_groq_focused(wav: bytes, key: str) -> str:
    r = httpx.post(
        "https://api.groq.com/openai/v1/audio/transcriptions",
        headers={"Authorization": f"Bearer {key}"},
        files={"file": ("a.wav", wav, "audio/wav")},
        data={"model": "whisper-large-v3", "response_format": "json",
              "prompt": _FOCUSED_PROMPT},
        timeout=120,
    )
    r.raise_for_status()
    return r.json()["text"]


def via_openai(wav: bytes, key: str) -> str:
    r = httpx.post(
        "https://api.openai.com/v1/audio/transcriptions",
        headers={"Authorization": f"Bearer {key}"},
        files={"file": ("a.wav", wav, "audio/wav")},
        data={"model": "gpt-4o-transcribe", "response_format": "json"},
        timeout=120,
    )
    r.raise_for_status()
    return r.json()["text"]


def via_deepgram(wav: bytes, key: str) -> str:
    r = httpx.post(
        "https://api.deepgram.com/v1/listen",
        params={"model": "nova-3", "language": "multi", "punctuate": "true", "smart_format": "true"},
        headers={"Authorization": f"Token {key}", "Content-Type": "audio/wav"},
        content=wav,
        timeout=120,
    )
    r.raise_for_status()
    return r.json()["results"]["channels"][0]["alternatives"][0]["transcript"]


def via_assemblyai(wav: bytes, key: str) -> str:
    # Header ist der rohe Key, KEIN "Bearer".
    h = {"authorization": key}
    up = httpx.post("https://api.assemblyai.com/v2/upload", headers=h, content=wav, timeout=120)
    up.raise_for_status()
    job = httpx.post(
        "https://api.assemblyai.com/v2/transcript",
        headers=h,
        # Ohne speech_models nimmt die API ein aelteres Default-Modell. Die Liste
        # ist eine Fallback-Kette, keine Parallelausfuehrung. U3.5 Pro wechselt
        # zwischen Deutsch und Englisch von sich aus — kein language_code noetig.
        json={
            "audio_url": up.json()["upload_url"],
            "speech_models": ["universal-3-5-pro", "universal-2"],
        },
        timeout=60,
    )
    job.raise_for_status()
    jid = job.json()["id"]
    for _ in range(120):
        s = httpx.get(f"https://api.assemblyai.com/v2/transcript/{jid}", headers=h, timeout=60).json()
        if s["status"] == "completed":
            return s["text"] or ""
        if s["status"] == "error":
            raise RuntimeError(s.get("error", "unknown"))
        time.sleep(2)
    raise TimeoutError("AssemblyAI antwortet nicht")


def via_speechmatics(wav: bytes, key: str) -> str:
    h = {"Authorization": f"Bearer {key}"}
    base = "https://asr.api.speechmatics.com/v2/jobs"
    cfg = '{"type":"transcription","transcription_config":' \
          '{"language":"de","operating_point":"enhanced"}}'
    job = httpx.post(
        base + "/",
        headers=h,
        files={"data_file": ("a.wav", wav, "audio/wav"), "config": (None, cfg)},
        timeout=120,
    )
    job.raise_for_status()
    jid = job.json()["id"]
    for _ in range(120):
        s = httpx.get(f"{base}/{jid}", headers=h, timeout=60).json()["job"]["status"]
        if s == "done":
            r = httpx.get(f"{base}/{jid}/transcript", headers=h,
                          params={"format": "txt"}, timeout=60)
            r.raise_for_status()
            return r.text.strip()
        if s in ("rejected", "expired", "deleted"):
            raise RuntimeError(f"Job {s}")
        time.sleep(2)
    raise TimeoutError("Speechmatics antwortet nicht")


PROVIDERS = [
    ("Groq whisper-large-v3 (mit Prompt)", "groq", via_groq),
    ("Groq whisper-large-v3 (ohne Prompt)", "groq", via_groq_noprompt),
    ("Groq whisper-large-v3 (Idealprompt)", "groq", via_groq_focused),
    ("OpenAI gpt-4o-transcribe", "openai", via_openai),
    ("Deepgram nova-3", "deepgram", via_deepgram),
    ("AssemblyAI universal-3-5-pro", "assemblyai", via_assemblyai),
    ("Speechmatics enhanced", "speechmatics", via_speechmatics),
]


def main() -> None:
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    ref_path, wav_path = sys.argv[1], sys.argv[2]

    raw_ref = open(ref_path, encoding="utf-8").read()
    # Alles vor der ===-Zeile ist Anleitung, nicht gesprochener Text. Ein
    # Praefix-Filter reichte hier nicht: die Anleitungssaetze beginnen mit
    # normalen Woertern und wurden als Referenz mitgezaehlt, was jedem
    # Anbieter ~27 erfundene Fehler aufgeschlagen hat.
    if "\n===" not in raw_ref:
        print(f"FEHLER: {ref_path} hat keine ===-Trennzeile.")
        sys.exit(1)
    reference = raw_ref.split("\n===", 1)[1].strip()
    wav = open(wav_path, "rb").read()

    print(f"Referenz: {len(normalize(reference))} Wörter aus {os.path.basename(ref_path)}")
    print(f"Audio:    {os.path.basename(wav_path)}  ({len(wav)/32000:.1f}s)\n")

    results = []
    for label, keyname, fn in PROVIDERS:
        key = os.environ.get(_KEYS[keyname], "")
        if not key:
            print(f"{'übersprungen':>12}  {label}  (kein {_KEYS[keyname]} in .env)")
            continue
        try:
            t0 = time.time()
            text = fn(wav, key)
            elapsed = time.time() - t0
            rate, errors = wer(reference, text)
            results.append((rate, label, elapsed, errors, text))
            print(f"{rate:>11.1%}  {label}  ({elapsed:.1f}s, {errors} Fehler)")
        except Exception as e:
            print(f"{'FEHLER':>12}  {label}: {str(e)[:80]}")

    if not results:
        print("\nKein Anbieter gelaufen. Keys in .env eintragen.")
        return

    results.sort()
    print("\n" + "─" * 60)
    print(f"Gewinner: {results[0][1]}  —  WER {results[0][0]:.1%}\n")
    for rate, label, _, _, text in results:
        missed = diff_words(reference, text)
        print(f"{label}  ({rate:.1%})")
        print(f"  nicht getroffen: {', '.join(missed) if missed else '—'}")
        print(f"  Ausgabe: {text[:160]}{'...' if len(text) > 160 else ''}\n")


if __name__ == "__main__":
    main()
