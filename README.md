# WisprWin

Local voice dictation for Windows, built for people who say words like *Supabase*,
*Vercel* and *Next.js* out loud and are tired of seeing "Superbase", "Wechsel" and
"Index.js" appear on screen.

Hold **Right Ctrl**, speak, release. The text is typed wherever your cursor is —
browser, editor, chat, terminal. German, English, or both in the same sentence.

A free, open alternative to Wispr Flow.

---

## What is this, and what is it for?

WisprWin turns your voice into typed text, in any app, with one hotkey. It runs
on your own PC and only sends the audio to a speech-to-text service
(Groq, optionally AssemblyAI) to be transcribed. You need your own API key.

It is useful in three ways:

1. **Talk instead of type.** Messages, emails, prompts for an AI, notes. You
   speak about 3x faster than you type. Technical words and mixed German/English
   come out right (*Supabase*, not "Superbase").
2. **Understand how you really speak.** The *unfiltered* mode (below) keeps every
   "um" and "uh", stamps every word with its time, **volume**, **pitch** and **brightness**, and marks
   long pauses. Hand that text to an AI and it can see your rhythm, hesitations,
   filler words, where you got quiet or emphasised something. Good for language
   learning (English as a second language), speech or interview practice,
   presentations, or checking how clearly you come across.
3. **Learn from your own recordings and improve the tool.** An optional local
   archive keeps your recordings so you can measure which engine understands
   *you* best and fix what fails. See
   [Optional: keep your recordings](#optional-keep-your-recordings-and-learn-from-them).

It is a personal tool, not a polished product. It works well for its author on
Windows; expect rough edges and please report them.

> **Installing this with an AI assistant?** Point it at [`AGENTS.md`](AGENTS.md).
> It lists the choices to put to you (privacy, accuracy, cost) so nothing is
> switched on without you knowing.

| Hotkey | What happens |
|---|---|
| **Right Ctrl** (hold) | Normal dictation: cleaned-up text is typed at your cursor. |
| **Right Ctrl + Right Shift** | *Unfiltered* take (see below). Needs an AssemblyAI key. Shift can be pressed while holding, or up to ~2 s after letting go. |

### The unfiltered take

Nothing is cleaned up. Every word gets a time stamp, a volume, a pitch and a brightness value, `um`/`uh` stay in,
and pauses of 3 s or more are marked:

```
(Je Wort: Zeit, Lautstärke in dBFS (0 = Maximum, Ø -31 dB), Tonhöhe in Hz (↗ steigend, ↘ fallend; ...))
[0:00.0 -28dB 118Hz] So [0:00.4 -24dB 124Hz] I [0:00.6 -33dB 110Hz↘] think
[0:00.9 -38dB] um [0:01.3 -22dB 131Hz↗] actually? (Pause 4 s) [0:06.1 -30dB 112Hz↘] yes
```

- **Time** is `minutes:seconds.tenths` from the start of the take.
- **Volume** is the level of just that word in dBFS: 0 is the maximum, so `-22dB` is
  louder than `-38dB`. The first line gives the median of the take. Compare words
  *within one take*; absolute values depend on your microphone.
- **Pitch** is the median fundamental frequency of the word in Hz. `↗` means the pitch
  rises by more than ~2 semitones within the word (typical for questions), `↘` means it
  falls (typical for the end of a statement). Whispered, very short or unvoiced words
  (*s*, *f*) have no pitch and show none. Pitch comes from [Praat](https://www.fon.hum.uva.nl/praat/) (via `praat-parselmouth`,
  the standard tool in speech research, ~0.1 s per take). Without it a simpler built-in
  estimator is used, which is less exact. Treat the values as a hint, not a measurement.
- **Brightness** (`B650`) is the spectral centroid of the word in Hz: how much of the
  sound sits in higher frequencies. A smiling or laughing voice is brighter than a flat
  one. Only shown for voiced words. It is a rough proxy for timbre: compare takes of
  *your own voice* with the *same microphone*; the number is not an emotion detector.
- **Held words** (`~0.5s`) mark a word held unusually long (prolongation or block, as in
  stuttering). Pauses from 1 s are marked. **Repeated sounds** ("t-t-to") are *not*
  visible: the speech engine merges them into one word.
- Texts over 1,500 characters are pasted automatically (no manual Ctrl+V).

Paste the result into an AI chat and ask, for example: *"Where do I hesitate, which
filler words do I use most, where do I trail off quietly, how would a native speaker
phrase this?"*

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
   │                     (speech ≥ 12 s → AssemblyAI instead, if you set its key)
   ├─ 4  formatter.py    regex fixes → Groq llama-3.3-70b → regex again
   ├─ 5  archive.py      OPTIONAL, off by default: audio + texts stored locally
   └─ 6  injector.py     Win32 SendInput; texts over 1,500 characters are pasted
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

### Stage 3b — which engine

Speech under 12 s goes to Groq (about 0.7 s). Longer speech goes to
AssemblyAI (about 5 s slower) **if** `ASSEMBLYAI_API_KEY` is set; on any failure
it falls back to Groq. Without the key everything stays on Groq. Threshold:
`ASSEMBLYAI_MIN_SECONDS` in [`config.py`](config.py). In a test on 60 clips,
Groq started missing key words from about 12 s on.

### Stage 6 — injection

Win32 `SendInput` with `KEYEVENTF_UNICODE`, one character at a time.
Texts over 1,500 characters are put on the clipboard and pasted with Ctrl+V
instead, then your previous clipboard text is restored: typing ~10,000
characters in one burst garbled the output in real apps (measured).

Not `keyboard.write()`. That library tracks modifier state internally, and a
stuck Ctrl turned a typed `l` into Ctrl+L — which is why text used to land in
the browser address bar. Unicode events carry no virtual key code and cannot be
interpreted as a shortcut.

---

## Throw a take away (Delete)

Said something badly? Press **Delete** at any time from pressing Right Ctrl until the
text appears: nothing is typed and nothing is archived. [`cancel.py`](cancel.py) swallows
that Delete (low-level keyboard hook) so it does not also delete a character in your
text box. Outside a dictation, Delete works as usual.

---

## Scrolling while you hold the key

Holding Right Ctrl normally turns the mouse wheel into "zoom" (browsers) or nothing, so
scrolling seems frozen while you dictate. [`wheel.py`](wheel.py) installs a low-level
mouse hook that, during recording, re-sends wheel events with Ctrl briefly released, so
the wheel scrolls normally. Left Ctrl + wheel (zoom) is untouched. Other keys held
together with Right Ctrl still act as Ctrl shortcuts (that cannot be hidden safely).

---

## The overlay

While you hold the key, a small dark pill shows a live "thermal" waveform: each
bar glows from cold blue (quiet) through red and orange to white-hot (loud).
The lower edge is a level meter. It is warm orange at a good level, cold blue
when you are too quiet, white-hot when you clip. On release it cools to grey
while the text is transcribed, then fades out. It is drawn as a per-pixel-alpha
window (anti-aliased, soft shadow), see [`overlay.py`](overlay.py).

---

## Two modes

Set `FORMAT_TEXT` in [`config.py`](config.py).

| | `FORMAT_TEXT = True` | `FORMAT_TEXT = False` |
|---|---|---|
| Text quality | best | good |
| Latency | ~2.5 s | ~2.0 s |
| API cost | transcription + LLM tokens | transcription only |
| Vocabulary fixes (`Superbase` → `Supabase`) | yes | **yes** — regex runs either way |
| Repeated-phrase removal | yes | **yes** |
| Dictated punctuation (`Doppelpunkt` → `:`) | yes | no |
| German noun capitalization | yes | no |
| Filler removal | yes | no |

`FORMAT_TEXT` only controls the **LLM** pass. The regex layer is free,
deterministic and needs no network, so it always runs — including the
misspellings you add yourself.

Dictated punctuation cannot work without the LLM: `Doppelpunkt` must become `:`
in *"Ergebnis Doppelpunkt"* but stay a word in *"der Doppelpunkt gehört da nicht
hin"*. That needs the sentence to be understood, which is not something a regex
can do.

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

Everything else in `.env.example` is optional: `ASSEMBLYAI_API_KEY` (better
long dictations) and `WISPRWIN_KEEP_AUDIO_DAYS` (local archive, see above).

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
| `tools/accuracy/` | Engine comparison on test clips and, if you use the archive, on your own recordings (`real_bench.py`; `make_rating_page.py` builds a page to judge disagreements by ear). |
| `tests/bench_text.md` | The 60-second reference text, dense with the vocabulary that usually fails. |
| `tests/dictation-tests.md` | Six graded test texts, each probing a different failure mode. |

---

## Optional: keep your recordings and learn from them

**Off by default. Out of the box WisprWin stores nothing.** Your voice goes to
the transcription provider and nowhere else.

You can switch on a local archive. It exists for one purpose: **learning about
your own speech.** Every dictation is saved as audio plus a JSON file (raw
transcript, final text, level, timings, engine). Then you or an AI can:

- build a benchmark from *your* voice and see which engine mishears *your* words,
- find recurring mistakes (German homophones like *eher/mehr*, names, accent),
- review how you speak (filler words, pace) with the unfiltered mode,
- count how much and how long you dictate (each entry stores the length of the take),
- **improve WisprWin itself.** It is open source and far from perfect. Your own
  recordings show exactly where it fails for *your* voice, language and
  vocabulary, and an AI can turn that into fixes (better regex entries, prompt
  changes, engine settings).

Turn it on in `.env`:

```
WISPRWIN_KEEP_AUDIO_DAYS=30
```

The number is how many days the **audio** is kept. Transcript JSON files are tiny
and stay. `0` or unset means nothing is stored.

**Why this is not for everybody:**

- Recordings of your voice are personal data, and often include other people,
  passwords or client names you said out loud. A plain folder on disk is not
  protected from anyone with access to your PC, a backup, or a synced cloud folder.
- Audio is large (about 2 MB per minute), so 30 days of heavy use is gigabytes.
- It only pays off if you actually *use* the data. If you just want to dictate,
  leave it off.
- Shared or work machines: usually a bad idea, check your employer's rules.

If you turn it on: keep `recordings/` out of Git and cloud sync (it is in
`.gitignore`), and choose the shortest retention that still serves your purpose.
WisprWin never uploads the archive. The data leaves your machine only if *you*
hand it to an AI or benchmark tool.

---

## Found something that is not good?

Please tell me. Open an [issue](https://github.com/natnaelhabte12345-del/Wisper-local-/issues)
with what you said, what appeared, and what you expected. Pull requests are welcome.
Do not paste recordings or private text into a public issue.

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
