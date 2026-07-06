# WisprWin — configuration
# Flip LOOP_TRAINING_MODE = True to pause after each step and wait for approval.
LOOP_TRAINING_MODE = False

# ── Groq API (preferred — faster, higher quality) ─────────────────────────────
# Key is loaded from .env — set USE_GROQ = False to force local Whisper instead.
USE_GROQ = True
GROQ_MODEL = "whisper-large-v3"   # $0.111/hr, better accuracy especially for German

# ── Local Whisper fallback ────────────────────────────────────────────────────
# faster-whisper model size: tiny, base, small, medium, large-v3
MODEL_SIZE = "base"

# Language: None = auto-detect (German + English), or "de", "en"
LANGUAGE = None

# Device: "auto" picks CUDA if available, else CPU
DEVICE = "auto"
COMPUTE_TYPE = "int8"

# Text formatting — send transcript through local qwen2.5:7b to clean up
# repetitions and fix punctuation. Requires Ollama running locally.
# Set to False to skip formatting and inject raw transcript immediately.
FORMAT_TEXT = False

# Hotkey: both Ctrl AND the Windows key must be held simultaneously
# Hold to record, release to transcribe and inject.
HOTKEY_POLL_MS = 50  # ms between hotkey state checks

# UI
OVERLAY_BOTTOM_MARGIN = 100  # px from bottom of screen
