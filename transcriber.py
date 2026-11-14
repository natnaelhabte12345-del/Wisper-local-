"""
Speech-to-text via Groq API (whisper-large-v3).
No local fallback — keeps the pipeline simple and avoids the bad 'base' model.
"""
import io
import os
import time

import httpx
import numpy as np
import scipy.io.wavfile as wav_io

from config import GROQ_MODEL, ASSEMBLYAI_MIN_SECONDS

# ── Load API key from .env ─────────────────────────────────────────────────────
def _load_env():
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    try:
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if "=" in line and not line.startswith("#"):
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())
    except FileNotFoundError:
        pass

_load_env()
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
ASSEMBLYAI_KEY = os.environ.get("ASSEMBLYAI_API_KEY", "")
last_engine = "groq"   # which engine produced the latest transcript (saved with each clip)

# Names the recogniser keeps getting wrong. AssemblyAI takes up to 1000 such terms.
_GLOSSARY = ["Claude", "Claude Code", "Claude Desktop", "Claude Cowork", "Jarvis", "Stockfish",
             "Supabase", "Groq", "Grok", "Whisper", "Wispr Flow", "WisprWin", "Opus", "Sonnet",
             "Haiku", "Vercel", "Next.js", "PowerShell", "ADB", "MCP", "Telegram", "Speechmatics",
             "Opera", "Opera GX", "Brave", "Spotify", "Discord", "OneDrive", "Playwright",
             "Firecrawl", "Hyperframes"]

# Groq caps this at 896 characters — keep only terms Whisper struggles with.
# Common words (Python, Docker, API, React) are already in Whisper's vocab.
_INITIAL_PROMPT = (
    "Supabase, Prisma, Drizzle, Vercel, Vite, esbuild, SvelteKit, Nuxt, Bun, Deno, Astro, "
    "Groq, WisprWin, MCP, RAG, LLM, JWT, OAuth, CORS, GraphQL, WebSocket, webhook, "
    "pnpm, Kubernetes, Terraform, Cloudflare, Netlify, "
    "FastAPI, Fastify, Next.js, TypeScript, "
    "Ollama, Whisper, Claude, Anthropic, ChatGPT, transformer, tokenizer, "
    "Embedding, Vektordatenbank, Fine-Tuning, Guardrails, "
    "microservice, serverless, codebase, refactor, async, await, rebase, rollback, "
    # English terms that Whisper turns into German homophones mid-sentence:
    # Build->Bild, Audio->Auto, Cache->Käsche
    "der Build, das Audio, der Cache, die Logs, das Deployment, das Repository, "
    "Environment Variables, Middleware, Transkription, Commit, Branch, Rollback, "
    "Subagent, Claude Code, Sonnet, Opus, Haiku, Prompt, Token, Benchmark, Regex"
)


# Whisper was trained on subtitled video and hallucinates these canned phrases
# when it is given silence or near-silence. Compared lowercased, without punctuation.
#
# Only phrases a user would never actually dictate belong here. The RMS guard
# below already covers plain silence, so short polite phrases ("vielen dank",
# "tschüss", "bye") must NOT be listed — swallowing those would be worse than
# the occasional hallucination they'd catch.
_HALLUCINATIONS = {
    "thank you for watching", "thanks for watching",
    "vielen dank für's zuschauen", "vielen dank fürs zuschauen",
    "untertitel von stephanie geiges", "untertitelung des zdf",
    "untertitel im auftrag des zdf", "untertitel der amara.org community",
    "untertitel der amara.org-community", "amara.org", "copyright wdr",
}

# Below this RMS the clip carries no speech — sending it to Whisper only
# produces a hallucination. Measured on this machine (tools/mic_check.py):
# the Intel Smart Sound array delivers speech at ~0.010 with a noise gate that
# floors silence at ~0.000, so 0.005 left only a 2x margin and would have
# discarded genuinely quiet speech. 0.002 keeps the gap to real silence.
_MIN_RMS = 0.002


def level(audio: np.ndarray) -> tuple[float, float, float]:
    """(rms, dBFS, peak) — dBFS is the readable one: 0 = full scale, -60 = silence."""
    rms = float(np.sqrt(np.mean(np.square(audio)))) if audio.size else 0.0
    peak = float(np.max(np.abs(audio))) if audio.size else 0.0
    dbfs = 20 * np.log10(rms) if rms > 0 else -99.0
    return rms, float(dbfs), peak


def _is_silence(audio: np.ndarray) -> bool:
    rms, dbfs, peak = level(audio)
    warn = "  ← leise" if dbfs < -40 else ("  ← übersteuert" if peak > 0.99 else "")
    print(f"    Aufnahme  {audio.size / 16000:>6.1f}s   {dbfs:>5.1f} dBFS"
          f"   Spitze {peak:.2f}{warn}")
    return rms < _MIN_RMS


def _trim_silence(audio: np.ndarray) -> np.ndarray:
    """Cut dead air off both ends.

    The recorder's 0.85s trailing buffer is mostly silence once the speaker has
    stopped, and Whisper fills silence with subtitle filler ("und so weiter",
    "und mehr", "Thank you for watching"). Removing it removes the hallucination.
    The threshold is relative to the loudest part, so it adapts to a quiet mic.
    """
    frame = 320                      # 20 ms at 16 kHz
    n = audio.size // frame
    if n < 2:
        return audio
    frames = audio[: n * frame].reshape(n, frame)
    rms = np.sqrt(np.mean(np.square(frames), axis=1))
    thresh = max(0.002, float(rms.max()) * 0.05)
    loud = np.flatnonzero(rms > thresh)
    if loud.size == 0:
        return audio
    margin = 10                      # keep 200 ms around the speech
    start = max(0, int(loud[0]) - margin) * frame
    end = min(n, int(loud[-1]) + 1 + margin) * frame
    if start > 0 or end < audio.size:
        print(f"    Stille    {(audio.size - (end - start)) / 16000:>6.1f}s   entfernt")
    return audio[start:end]


def _to_wav_bytes(audio: np.ndarray) -> bytes:
    buf = io.BytesIO()
    pcm = (audio * 32767).clip(-32768, 32767).astype(np.int16)
    wav_io.write(buf, 16000, pcm)
    buf.seek(0)
    return buf.read()


def transcribe(audio: np.ndarray) -> str:
    if audio.size == 0:
        return ""
    if not GROQ_API_KEY:
        print("[transcribe] No GROQ_API_KEY — set it in .env")
        return ""
    if _is_silence(audio):
        print("    ! zu leise — übersprungen")
        return ""
    trimmed = _trim_silence(audio)
    text = None
    global last_engine
    last_engine = "groq"
    if ASSEMBLYAI_KEY and ASSEMBLYAI_MIN_SECONDS and trimmed.size / 16000 >= ASSEMBLYAI_MIN_SECONDS:
        try:
            text = _assemblyai(trimmed)
            last_engine = "assemblyai"
        except Exception as e:
            print(f"    ! AssemblyAI fehlgeschlagen ({str(e)[:60]}) — Groq als Ersatz")
    if text is None:
        text = _groq(trimmed)
    if text.lower().strip(" .,!?…") in _HALLUCINATIONS:
        print("    ! bekannte Halluzination bei Stille — verworfen")
        return ""
    return text


def _assemblyai(audio: np.ndarray, verbatim: bool = False):
    """Longer dictations: ~2x fewer errors than Whisper, mostly on names and accents,
    but ~5 s slower (tools/accuracy). The glossary is what fixes Claude/Stockfish/Jarvis.
    verbatim=True keeps "uh/um" and returns (text, words-with-timings) instead of text."""
    h = {"authorization": ASSEMBLYAI_KEY}
    up = httpx.post("https://api.assemblyai.com/v2/upload", headers=h,
                    content=_to_wav_bytes(audio), timeout=30)
    up.raise_for_status()
    body = {"audio_url": up.json()["upload_url"],
            "speech_models": ["universal-3-5-pro", "universal-2"],
            "keyterms_prompt": _GLOSSARY}
    if verbatim:
        body["disfluencies"] = True
    job = httpx.post("https://api.assemblyai.com/v2/transcript", headers=h, timeout=30, json=body)
    job.raise_for_status()
    url = f"https://api.assemblyai.com/v2/transcript/{job.json()['id']}"
    deadline = time.time() + 45
    while time.time() < deadline:
        s = httpx.get(url, headers=h, timeout=30).json()
        if s["status"] == "completed":
            text = (s.get("text") or "").strip()
            return (text, s.get("words") or []) if verbatim else text
        if s["status"] == "error":
            raise RuntimeError(s.get("error", "unknown"))
        time.sleep(0.4)
    raise TimeoutError("keine Antwort in 45 s")


def _stamp(ms: int) -> str:
    return f"{ms // 60000}:{ms // 1000 % 60:02d}.{ms // 100 % 10}"


def _pitch(seg: np.ndarray):
    """(median Hz, trend) of the voiced part of one word, or (None, "") if it has none.
    Autocorrelation per 40 ms frame (70-400 Hz). trend is "↗"/"↘" when the pitch moves by
    more than ~2 semitones between the first and last third (rising = question, falling = end)."""
    sr, n, hop = 16000, 640, 160
    lo, hi = sr // 400, sr // 70
    f0 = []
    for i in range(0, len(seg) - n, hop):
        fr = seg[i:i + n] - np.mean(seg[i:i + n])
        if np.sqrt(np.mean(fr ** 2)) < 0.004:
            continue
        ac = np.correlate(fr, fr, "full")[n - 1:]
        if ac[0] <= 0:
            continue
        lag = lo + int(np.argmax(ac[lo:hi]))
        if ac[lag] / ac[0] > 0.4:
            f0.append(sr / lag)
    if len(f0) < 3:
        return None, ""
    k = max(1, len(f0) // 3)
    a, b = float(np.median(f0[:k])), float(np.median(f0[-k:]))
    st = 12 * np.log2(b / a)
    return round(float(np.median(f0))), ("↗" if st > 2 else "↘" if st < -2 else "")


def transcribe_verbatim(audio: np.ndarray) -> str:
    """Unfiltered take for analysing one's own speech: keeps fillers, timestamps every
    word (m:ss.d) and notes pauses of 3 s or more. Single line - a newline would press
    Enter in a chat box. Whisper (Groq) drops fillers, so there is no equal fallback."""
    global last_engine
    last_engine = "assemblyai-verbatim"
    if audio.size == 0 or not ASSEMBLYAI_KEY or _is_silence(audio):
        return ""
    text, words = _assemblyai(audio, verbatim=True)
    if not words:
        return text
    # Volume per word: RMS of exactly that word's samples (16 kHz -> 16 samples/ms), in dBFS.
    # 0 = full scale; closer to 0 = louder. Compare words within one take, not across mics.
    def _db(w):
        seg = audio[int(w["start"] * 16):int(w["end"] * 16)]
        return level(seg)[1] if seg.size else -99.0
    dbs = [_db(w) for w in words]
    pit = [_pitch(audio[int(w["start"] * 16):int(w["end"] * 16)]) for w in words]
    out = [f"(Je Wort: Zeit, Lautstärke in dBFS (0 = Maximum, Ø {round(float(np.median(dbs)))} dB), "
           f"Tonhöhe in Hz (↗ steigend, ↘ fallend; fehlt bei stimmlosen/zu kurzen Wörtern))"]
    prev_end = 0
    for i, w in enumerate(words):
        gap = w["start"] - prev_end
        if i and gap >= 3000:
            out.append(f"(Pause {round(gap / 1000)} s)")
        hz, tr = pit[i]
        out.append(f"[{_stamp(w['start'])} {round(dbs[i])}dB{f' {hz}Hz{tr}' if hz else ''}] {w['text']}")
        prev_end = w["end"]
    return " ".join(out)


def _groq(audio: np.ndarray) -> str:
    wav_bytes = _to_wav_bytes(audio)
    resp = httpx.post(
        "https://api.groq.com/openai/v1/audio/transcriptions",
        headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
        files={"file": ("audio.wav", wav_bytes, "audio/wav")},
        # KEIN prompt. Gemessen am 2026-07-25 (tools/stt_bench.py, 136 Wörter):
        #   ohne Prompt   2.9% WER
        #   mit Prompt    5.1% WER
        #   Idealprompt   4.4% WER  (nur die Wörter aus genau diesem Text)
        # Selbst der Idealprompt verlor und machte aus "Vercel" ein "Vessel" —
        # das Vorkontext-Priming zieht die Erkennung eher weg als hin.
        # _INITIAL_PROMPT bleibt definiert, stt_bench.py vergleicht damit weiter.
        data={"model": GROQ_MODEL, "response_format": "json"},
        timeout=20,
    )
    if not resp.is_success:
        print(f"[Groq] {resp.status_code} error: {resp.text}")
        resp.raise_for_status()
    return resp.json().get("text", "").strip()


def _get_model():
    """No-op — kept so main.py background pre-warm call doesn't crash."""
    pass
