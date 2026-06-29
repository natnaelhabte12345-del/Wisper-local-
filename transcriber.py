"""
Speech-to-text via Groq API (whisper-large-v3).
No local fallback — keeps the pipeline simple and avoids the bad 'base' model.
"""
import io
import os

import httpx
import numpy as np
import scipy.io.wavfile as wav_io

from config import GROQ_MODEL

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

# Groq caps this at 896 characters — keep only terms Whisper struggles with.
# Common words (Python, Docker, API, React) are already in Whisper's vocab.
_INITIAL_PROMPT = (
    "Supabase, Prisma, Drizzle, Vercel, Vite, esbuild, SvelteKit, Nuxt, Bun, Deno, Astro, "
    "Groq, WisprWin, MCP, RAG, LLM, JWT, OAuth, CORS, GraphQL, WebSocket, webhook, "
    "pnpm, Kubernetes, Terraform, Cloudflare, Netlify, "
    "FastAPI, Fastify, Next.js, TypeScript, "
    "Ollama, Whisper, Claude, Anthropic, ChatGPT, transformer, tokenizer, "
    "Embedding, Vektordatenbank, Fine-Tuning, Hallucination, Guardrails, Alignment, "
    "microservice, serverless, codebase, refactor, async, await, rebase, rollback, "
    "Utilitarismus, Determinismus, Existenzialismus, Erkenntnistheorie, "
    "Opportunitätskosten, Rückkopplungsschleife, Skalierbarkeit, Validierung"
)


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
    wav_bytes = _to_wav_bytes(audio)
    resp = httpx.post(
        "https://api.groq.com/openai/v1/audio/transcriptions",
        headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
        files={"file": ("audio.wav", wav_bytes, "audio/wav")},
        data={
            "model": GROQ_MODEL,
            "response_format": "json",
            "prompt": _INITIAL_PROMPT,
        },
        timeout=20,
    )
    if not resp.is_success:
        print(f"[Groq] {resp.status_code} error: {resp.text}")
        resp.raise_for_status()
    text = resp.json().get("text", "").strip()
    print(f"[Groq] {text!r}")
    return text


def _get_model():
    """No-op — kept so main.py background pre-warm call doesn't crash."""
    pass
