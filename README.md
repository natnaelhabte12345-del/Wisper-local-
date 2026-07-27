# WisprWin

Local voice dictation for Windows, built for people who say words like *Supabase*,
*Vercel* and *Next.js* out loud and are tired of seeing "Superbase", "Wechsel" and
"Index.js" appear on screen.

Hold **Right Ctrl**, speak, release. The text is typed wherever your cursor is —
browser, editor, chat, terminal. German, English, or both in the same sentence.

A free, open alternative to Wispr Flow.

---

## Why another dictation tool

General speech recognition is already good. Where it falls apart is vocabulary:
product names, frameworks, and English terms dropped into German sentences.
These are exactly the words that carry the meaning, and exactly the words a
general model has never heard often enough.

WisprWin's answer is a three-stage pipeline where each stage does only what it
is actually good at.

---

## How it works

```
Right Ctrl held
   │
   ├─ 1  hotkey.py      GetAsyncKeyState(VK_RCONTROL), polled every 50 ms
   ├─ 2  recorder.py    microphone → 16 kHz mono buffer
   │
Right Ctrl released  (+0.85 s trailing buffer so word endings survive)
   │
   ├─ 3  transcriber.py  silence check → trim dead air → Groq whisper-large-v3
   ├─ 4  formatter.py    regex fixes → Groq llama-3.3-70b → regex again
   ├─ 5  archive.py      audio + both texts stored locally
   └─ 6  injector.py     Win32 SendInput, character by character
```

### Stage 3 — transcription

Audio goes to Groq's `whisper-large-v3`. Two things happen before the request:

**Silence is rejected.** Below −54 dBFS the clip never leaves the machine.
Whisper was trained on subtitled video and, given silence, invents the phrases
it saw most often there — *"Thank you for watching"*, *"Untertitel von …"*.

**Dead air is trimmed.** The 0.85 s trailing buffer that protects word endings
is mostly silence once you have stopped talking, and Whisper fills silence with
the same subtitle filler. Trimming it at the audio level removes the problem at
its source; no text rule can, because *"und mehr"* is a legitimate thing to say.

> **No vocabulary prompt.** Whisper's `prompt` parameter accepts a word list, and
> using it made results measurably **worse** — see [Benchmark](#benchmark). The
> parameter is not an instruction; it is pretended prior context, and priming the
> decoder pulled it away from correct words as often as toward them.

### Stage 4 — cleanup

Two mechanisms in one file, deliberately separate:

| | What it is | What it does |
|---|---|---|
| `_FIXES` | Plain regex. No AI, no network. | Misspellings confirmed by a test: `Superbase` → `Supabase`, `Nxt.js` → `Next.js` |
| `llama-3.3-70b` | The LLM | Punctuation, German noun capitalization, dictated punctuation, filler removal |

The split exists because the LLM proved unreliable at exactly the task that
needs no judgement. It left `Superbase` untouched even with *Supabase* in its
own vocabulary list — its "only correct at 95% confidence" rule is too cautious
for facts. So proven facts go to the regex, and anything needing context goes to
the model.

The regex runs again after the LLM, so the deterministic layer has the last word.

**The LLM is held back, not encouraged.** Instruction-following models are
trained to be helpful, and "change nothing" reads to them as failure. Left
loose, this one rewrote `gegeben` into `gearbeitet`, completed the cut-off
`gebro...` into `gebrochen`, and once emitted 2,235 words explaining its own
edits instead of applying them. The prompt is therefore mostly prohibitions,
and a word-count guard discards any response that grew or shrank too much.

Dictated punctuation is supported: say *"Doppelpunkt"* and you get `:`, while
*"der Doppelpunkt gehört da nicht hin"* keeps the word.

### Stage 6 — injection

Win32 `SendInput` with `KEYEVENTF_UNICODE`, one character at a time.

Not `keyboard.write()`. That library tracks modifier state internally, and a
stuck Ctrl turned a typed `l` into Ctrl+L — which is why text used to land in
the browser address bar. Unicode events carry no virtual key code and cannot be
interpreted as a shortcut.

---

## Two modes

Set `FORMAT_TEXT` in [`config.py`](config.py).

| | `FORMAT_TEXT = True` | `FORMAT_TEXT = False` |
|---|---|---|
| Text quality | best | good |
| Latency | ~2.5 s | ~2.0 s |
| API cost | transcription + LLM tokens | transcription only |
| Dictated punctuation | yes | no |
| German noun capitalization | yes | no |
| Filler removal | yes | no |
| Vocabulary fixes | regex **and** LLM | regex only |

**`False` is a real option, not a degraded fallback.** Whisper punctuates
sentences on its own, and the regex layer still corrects known misspellings.
The benchmark below measured raw Whisper output at **2.9 % word error rate**.
Use it if you want to stay inside a free tier, keep latency minimal, or simply
prefer that no LLM touches your words.

The app also falls back to this mode automatically whenever the LLM call fails,
and says so in the terminal rather than silently handing you worse text.

---

## Benchmark

`tools/stt_bench.py` compares providers on **your own voice** against a text you
read aloud, so the reference is exact and free. Published leaderboards say
nothing about your microphone, your accent or your vocabulary.

Measured 2026-07-25, one 66-second German clip with English technical terms,
136 reference words. Lower is better.

| Run | WER | Time |
|---|---|---|
| **Groq whisper-large-v3, no prompt** | **2.9 %** | 1.8 s |
| AssemblyAI universal-3-5-pro | 3.7 % | 7.4 s |
| Groq whisper-large-v3, ideal prompt | 4.4 % | 1.9 s |
| Groq whisper-large-v3, vocabulary prompt | 5.1 % | 2.4 s |
| Deepgram nova-3 | 6.6 % | 2.9 s |
| Speechmatics enhanced | 7.4 % | 4.2 s |

The "ideal prompt" run contained only the difficult words from that exact text —
an upper bound on what prompting can do. It still lost to no prompt at all, and
turned `Vercel` into `Vessel`. That single result is why the vocabulary prompt
was removed from the code.

This is one clip from one speaker. Run it on your own voice:

```bash
.venv\Scripts\python.exe tools\stt_bench.py tests\bench_text.md <recording.wav>
```

Providers whose key is missing from `.env` are skipped.

---

## Setup

**Requirements:** Windows, Python 3.11+, a
[Groq API key](https://console.groq.com/keys) (the free tier is enough).

```bash
git clone https://github.com/natnaelhabte12345-del/Wisper-local-.git
cd Wisper-local-
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
```

Copy `.env.example` to `.env` and add your key:

```
GROQ_API_KEY=gsk_...
```

Run:

```bash
run.bat
```

Hold **Right Ctrl**, speak, release.

> PowerShell note: these are separate commands. PowerShell 5.1 does not support
> `&&` — use `;` between them.

### Autostart on boot

```bash
.venv\Scripts\python.exe -c "import startup; startup.enable()"
```

`startup.disable()` removes it again. Autostart runs through `run.vbs`, which
launches the app without a console window.

---

## Adding your own vocabulary

Two places, matching the two mechanisms:

**1. Confirmed misspellings** → `_FIXES` in [`formatter.py`](formatter.py):

```python
_FIXES = [
    (r"\bSuper[- ]?base\b", "Supabase"),
    (r"\bNxt\.?\s?js\b", "Next.js"),
]
```

Only add entries you have actually seen in a transcript. And only where the
wrong spelling is not itself a real word — `Index.js` stays untouched, because
replacing it would break correct text.

**2. Terms needing context** → the vocabulary list in the system prompt in
[`formatter.py`](formatter.py). The LLM uses it when the sentence makes the term
plausible.

Do **not** add words to a Whisper prompt. That path was measured and it hurts.

---

## Tools

| | |
|---|---|
| `tools/mic_check.py` | Measures your microphone: level in dBFS, signal-to-noise ratio, clipping. Says plainly whether the mic is a problem. |
| `tools/stt_bench.py` | Compares STT providers on your own voice, scored by word error rate. |
| `tests/bench_text.md` | The 60-second reference text, dense with the vocabulary that usually fails. |
| `tests/dictation-tests.md` | Six graded test texts, each probing a different failure mode. |

---

## Your recordings stay local

Every dictation is written to `recordings/<date>/`, audio plus a JSON file with
the raw transcript, the final text, level and timings. Nothing is uploaded
beyond the transcription request itself, and `recordings/` is in `.gitignore`.

Audio is deleted after 3 days. The JSON files stay — they are small, and they
are what a benchmark needs.

To turn the archive off, remove the `archive.save(...)` call in
[`main.py`](main.py).

---

## Known limitations

- **Windows only.** Win32 APIs for hotkeys, focus handling and injection.
- **Needs an internet connection.** No offline mode.
- **~10 minutes per recording**, then it stops automatically.
- **Groq free tier has a daily token budget.** When the LLM budget runs out,
  transcription keeps working and cleanup is skipped, with a note in the
  terminal. The two models have separate limits.
- **Acoustic errors remain.** `Vercel` heard as `SL` cannot be fixed by any
  rule; the sentence has to be understood. Rare, but real.

---

## License

MIT
