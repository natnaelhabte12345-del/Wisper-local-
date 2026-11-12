"""Speech-to-text back ends under one signature: fn(audio_f32_16k) -> text."""
import os
import sys
import time

import httpx
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import transcriber  # noqa: E402  (loads .env, owns the production code path)

KEYS = {k: os.environ.get(k, "") for k in
        ("GROQ_API_KEY", "DEEPGRAM_API_KEY", "ASSEMBLYAI_API_KEY", "SPEECHMATICS_API_KEY")}

PERSONAL_PROMPT = ("Claude, Claude Code, Jarvis, Stockfish, Supabase, Groq, Grok, Whisper, "
                   "Opus, Sonnet, PowerShell, terminal, Opera, Brave, Spotify, Discord, "
                   "OneDrive, ADB, MCP, Vercel, Playwright")


class RateLimited(Exception):
    pass


def _level_to(audio, db):
    rms = float(np.sqrt(np.mean(audio ** 2))) or 1e-9
    return np.clip(audio * (10 ** (db / 20) / rms), -1, 1).astype(np.float32)


def _groq(audio, model="whisper-large-v3", language=None, prompt=None, normalize=False):
    if normalize:
        audio = _level_to(audio, -20)
    wav = transcriber._to_wav_bytes(transcriber._trim_silence(audio))
    data = {"model": model, "response_format": "json"}
    if language:
        data["language"] = language
    if prompt:
        data["prompt"] = prompt
    for attempt in range(4):
        r = httpx.post("https://api.groq.com/openai/v1/audio/transcriptions",
                       headers={"Authorization": f"Bearer {KEYS['GROQ_API_KEY']}"},
                       files={"file": ("a.wav", wav, "audio/wav")}, data=data, timeout=60)
        if r.status_code == 429:
            wait = float(r.headers.get("retry-after", "10"))
            if wait > 150:
                raise RateLimited(f"retry-after {wait:.0f}s")
            time.sleep(wait + 1)
            continue
        r.raise_for_status()
        return r.json().get("text", "").strip()
    raise RateLimited("429 after retries")


def current(audio):
    """The exact production function (silence guard, trim, model, no prompt)."""
    return transcriber.transcribe(audio)


def groq_plain(audio): return _groq(audio)
def groq_norm(audio): return _groq(audio, normalize=True)
def groq_turbo(audio): return _groq(audio, model="whisper-large-v3-turbo")
def groq_en(audio): return _groq(audio, language="en")
def groq_prompt(audio): return _groq(audio, prompt=PERSONAL_PROMPT)


def _wav(audio):
    return transcriber._to_wav_bytes(audio)


def deepgram(audio):
    r = httpx.post("https://api.deepgram.com/v1/listen",
                   params={"model": "nova-3", "language": "multi", "punctuate": "true",
                           "smart_format": "true"},
                   headers={"Authorization": f"Token {KEYS['DEEPGRAM_API_KEY']}",
                            "Content-Type": "audio/wav"}, content=_wav(audio), timeout=120)
    r.raise_for_status()
    return r.json()["results"]["channels"][0]["alternatives"][0]["transcript"]


GLOSSARY = ["Claude", "Claude Code", "Claude Desktop", "Claude Cowork", "Jarvis", "Stockfish",
            "Supabase", "Groq", "Grok", "Whisper", "Wispr Flow", "WisprWin", "Opus", "Sonnet",
            "Haiku", "Vercel", "Next.js", "PowerShell", "ADB", "MCP", "Telegram", "Speechmatics",
            "Opera", "Opera GX", "Brave", "Spotify", "Discord", "OneDrive", "Playwright",
            "Firecrawl", "Hyperframes"]


def assemblyai(audio, keyterms=None, poll=0.4):
    h = {"authorization": KEYS["ASSEMBLYAI_API_KEY"]}
    up = httpx.post("https://api.assemblyai.com/v2/upload", headers=h, content=_wav(audio), timeout=120)
    up.raise_for_status()
    body = {"audio_url": up.json()["upload_url"],
            "speech_models": ["universal-3-5-pro", "universal-2"]}
    if keyterms:
        body["keyterms_prompt"] = keyterms
    job = httpx.post("https://api.assemblyai.com/v2/transcript", headers=h, timeout=60, json=body)
    job.raise_for_status()
    jid = job.json()["id"]
    for _ in range(int(300 / poll)):
        s = httpx.get(f"https://api.assemblyai.com/v2/transcript/{jid}", headers=h, timeout=60).json()
        if s["status"] == "completed":
            return s["text"] or ""
        if s["status"] == "error":
            raise RuntimeError(s.get("error", "unknown"))
        time.sleep(poll)
    raise TimeoutError("assemblyai")


def assemblyai_kt(audio): return assemblyai(audio, keyterms=GLOSSARY)
def assemblyai_fast(audio): return assemblyai(audio)


def speechmatics(audio, language="en"):
    h = {"Authorization": f"Bearer {KEYS['SPEECHMATICS_API_KEY']}"}
    base = "https://asr.api.speechmatics.com/v2/jobs"
    cfg = ('{"type":"transcription","transcription_config":'
           f'{{"language":"{language}","operating_point":"enhanced"}}}}')
    job = httpx.post(base + "/", headers=h, timeout=120,
                     files={"data_file": ("a.wav", _wav(audio), "audio/wav"), "config": (None, cfg)})
    job.raise_for_status()
    jid = job.json()["id"]
    for _ in range(150):
        s = httpx.get(f"{base}/{jid}", headers=h, timeout=60).json()["job"]["status"]
        if s == "done":
            r = httpx.get(f"{base}/{jid}/transcript", headers=h, params={"format": "txt"}, timeout=60)
            r.raise_for_status()
            return r.text.strip()
        if s in ("rejected", "expired", "deleted"):
            raise RuntimeError(f"job {s}")
        time.sleep(2)
    raise TimeoutError("speechmatics")


def speechmatics_de(audio): return speechmatics(audio, "de")


# name -> (fn, provider group). Groq runs one at a time, the rest in parallel.
CONFIGS = {
    "current":      (current, "groq"),
    "groq_plain":   (groq_plain, "groq"),
    "norm":         (groq_norm, "groq"),
    "turbo":        (groq_turbo, "groq"),
    "en":           (groq_en, "groq"),
    "prompt":       (groq_prompt, "groq"),
    "deepgram":     (deepgram, "deepgram"),
    "assemblyai":   (assemblyai, "assemblyai"),
    "aai_kt":       (assemblyai_kt, "assemblyai"),
    "aai_fast":     (assemblyai_fast, "aai_seq"),
    "speechmatics": (speechmatics, "speechmatics"),
}
