# WisprWin — configuration

# ── Transcription ─────────────────────────────────────────────────────────────
# Groq speech-to-text model. whisper-large-v3 is more accurate than -turbo,
# noticeably so for German and for technical vocabulary.
GROQ_MODEL = "whisper-large-v3"

# Dictations at least this long (seconds of speech) go to AssemblyAI instead of Groq: ~2x fewer
# errors on names/accents, ~5 s slower. Shorter ones stay on Groq (0.7 s). 0 = always Groq.
# Measured on 60 test clips (tools/accuracy); 12 s is where Groq starts missing key words.
ASSEMBLYAI_MIN_SECONDS = 12

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
