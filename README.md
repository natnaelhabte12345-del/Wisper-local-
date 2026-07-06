# WisprWin

A local voice-dictation tool for Windows — hold a hotkey, speak, release, and the
transcribed text is typed wherever your cursor is. Built as a free, open alternative
to Wispr Flow.

- Hold **Right Ctrl** → speak → release → text appears
- Works in any app (browser, editor, chat, terminal)
- German + English, including code-switching mid-sentence
- Transcription via Groq's `whisper-large-v3`, cleanup via `llama-3.3-70b-versatile`
- Animated waveform overlay while recording/transcribing
- Runs in the system tray, optional autostart on boot

## How it works

1. `hotkey.py` polls for the Right Ctrl key being held. A bare modifier never
   triggers app shortcuts and never leaks keystrokes into the focused window.
2. On press: `recorder.py` starts capturing microphone audio (16kHz mono).
3. On release: the audio is sent to Groq's Whisper API for transcription.
4. The raw transcript is cleaned up by a Groq LLM call — punctuation,
   capitalization, and correction of known technical terms only (no rephrasing).
5. The final text is typed into the active window via `keyboard.write()`.

No local STT model, no GPU required — everything runs through the Groq API.

## Setup

**Requirements:** Python 3.11+, Windows, a [Groq API key](https://console.groq.com/keys) (free tier available).

```bash
git clone https://github.com/<your-username>/WisprWin.git
cd WisprWin
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
```

Copy `.env.example` to `.env` and add your key:

```
GROQ_API_KEY=your_groq_api_key_here
```

Run it:

```bash
run.bat
```

Hold **Right Ctrl**, speak, release.

## Autostart on boot

```bash
.venv\Scripts\python.exe -c "import startup; startup.enable()"
```

To disable:

```bash
.venv\Scripts\python.exe -c "import startup; startup.disable()"
```

## Configuration

All settings live in [`config.py`](config.py):

| Setting | Description |
|---|---|
| `GROQ_MODEL` | Whisper model used for transcription (`whisper-large-v3` recommended over `-turbo` for accuracy) |
| `FORMAT_TEXT` | Whether to run the cleanup LLM pass after transcription |
| `HOTKEY_POLL_MS` | Hotkey polling interval in ms |
| `OVERLAY_BOTTOM_MARGIN` | Overlay distance from bottom of screen |

To add your own technical vocabulary (so Whisper recognizes domain-specific terms),
edit `_INITIAL_PROMPT` in [`transcriber.py`](transcriber.py) — note Groq caps this at
896 characters — and the vocabulary list in the system prompt in [`formatter.py`](formatter.py).

## Known limitations

- Max ~10 minutes per recording (Groq's file size limit)
- Windows only (uses Win32 APIs for focus handling and global hotkeys)
- Requires an internet connection (no offline mode)

## License

MIT
