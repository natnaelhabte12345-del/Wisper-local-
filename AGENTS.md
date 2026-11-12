# For AI assistants installing WisprWin

WisprWin is local push-to-talk dictation for Windows (hold Right Ctrl, speak,
text is typed at the cursor). If a user asked you to set it up, follow this.
Do not skip the questions: some options store personal data.

## Install
1. Windows only, Python 3.11+. In the repo: `python -m venv .venv`, then
   `.venv\Scripts\pip install -r requirements.txt`.
2. Copy `.env.example` to `.env`. The user needs a free Groq key
   (https://console.groq.com/keys) as `GROQ_API_KEY`. Never print or commit keys.
3. Start with `run.bat`. (PowerShell 5.1: no `&&`, use `;`.)

## Ask the user before configuring (one short question each)
1. **Keep recordings?** Default is NO: nothing is stored. Only set
   `WISPRWIN_KEEP_AUDIO_DAYS=<days>` in `.env` if the user wants to analyse their
   own speech later. Explain: it saves audio of their voice (maybe other people,
   passwords, client names) in `recordings/`, about 2 MB per minute. Suggest the
   smallest number of days that fits (e.g. 7). Shared or work PC: advise against.
2. **Better accuracy on long dictations?** Optional `ASSEMBLYAI_API_KEY` (paid
   after free credit). Without it everything uses Groq. Fine for most people.
3. **Cleanup by an AI model?** `FORMAT_TEXT` in `config.py`. True: punctuation,
   German noun capitalization, spoken punctuation, filler removal (+0.5 s, uses
   tokens). False: raw Whisper plus regex fixes only, no LLM touches the words.
4. **Autostart on boot?** `.venv\Scripts\python.exe -c "import startup; startup.enable()"`.
5. **Own vocabulary?** Confirmed misspellings go in `_FIXES` in `formatter.py`.
   Do NOT add a Whisper `prompt`: measured worse.

## Facts worth knowing
- Hotkeys: Right Ctrl = dictate. Right Ctrl + Right Shift = unfiltered take with
  per-word timestamps (needs `ASSEMBLYAI_API_KEY`), nothing cleaned up.
- Audio goes to Groq (and AssemblyAI if configured) for transcription. Nothing
  else leaves the machine; the archive never uploads.
- `recordings/`, `.env`, and logs are git-ignored. Keep it that way.
- The microphone matters more than any setting: run `tools/mic_check.py`. A
  laptop mic array is often too quiet; a headset boom or USB mic helps most.
