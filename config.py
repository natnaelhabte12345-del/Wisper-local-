# WisprWin — configuration

# ── Transcription ─────────────────────────────────────────────────────────────
# Groq speech-to-text model. whisper-large-v3 is more accurate than -turbo,
# noticeably so for German and for technical vocabulary.
GROQ_MODEL = "whisper-large-v3"

# ── Cleanup ───────────────────────────────────────────────────────────────────
# Stage 2+3 of the pipeline: deterministic regex fixes for known Whisper
# misspellings, then a Groq LLM call for punctuation, German noun
# capitalization, dictated punctuation ("Doppelpunkt" -> ":") and fillers.
#
# True  — best text quality, roughly +0.5s per dictation, uses LLM tokens.
# False — raw Whisper output, injected immediately, transcription tokens only.
#         Whisper already punctuates reasonably, so this is a usable mode.
FORMAT_TEXT = True

# ── Hotkey ────────────────────────────────────────────────────────────────────
# Hold RIGHT CTRL alone. See hotkey.py — left ctrl stays free for copy/paste.
HOTKEY_POLL_MS = 50   # ms between hotkey state checks
