"""
Text cleanup via Groq chat API (llama-3.1-8b-instant — ~0.3s).
Stage 1: fast Python dedup (no network).
Stage 2: Groq for punctuation + capitalization.
Falls back to deduped text if Groq fails.
"""
import os
import re
import time

import httpx

# Misspellings Whisper produces reliably for terms that ARE already in its
# prompt — the LLM's 95%-confidence rule is too cautious to fix them, so they
# are corrected deterministically instead. Only add entries confirmed by a test.
_FIXES = [
    (r"\bSuper[- ]?base\b", "Supabase"),
    (r"\bNxt\.?\s?js\b", "Next.js"),
    (r"\bNext\s?JS\b", "Next.js"),
    (r"\b([Dd])er Bild\b(?!-)", r"\1er Build"),   # "das Bild" stays untouched
    (r"\bGrodd\b", "Groq"),                       # not a German word — safe to force
    # NOTE: "Auto" -> "Audio" does NOT belong here. "Auto" is a real German word,
    # so that one needs sentence context and stays the LLM's job.
]


def _apply_fixes(text: str) -> str:
    for pattern, repl in _FIXES:
        text = re.sub(pattern, repl, text)
    return text

# ── Load key from .env ─────────────────────────────────────────────────────────
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
_KEY = os.environ.get("GROQ_API_KEY", "")

_SYSTEM = """\
You receive a raw voice transcription inside <t> tags from a technical user.

RULE ZERO — LANGUAGE. Output the SAME language the input is in, word for word.
An English input produces an English output. A German input produces a German
output. Mixed stays mixed, with each part in its original language.
NEVER translate. Not one clause, not one word.
Most of the examples below happen to be German; that says nothing about the
language of the text you are given. Read the input and follow it.
If the input is English, ignore every German-specific rule below.

Return the text with ONLY these five types of changes:

1. PUNCTUATION — add periods, commas, dashes where natural. Nothing else.
2. CAPITALIZATION — capitalize the first word of each sentence. In German text,
   also capitalize nouns and nominalized verbs/adjectives that the transcription
   left lowercase ("beim schnellen drüberlesen" -> "beim schnellen Drüberlesen",
   "als nächstes" -> "als Nächstes"). This is spelling, not rephrasing.
3. VOCABULARY FIX — only if ALL THREE conditions are met:
   a) the word sounds phonetically very close to a term in the list
   b) the surrounding sentence context makes that term genuinely likely
   c) you are at least 95% confident
   Example: "super based" in a sentence about databases → "Supabase". But "super based" in any other context → leave it.
   When in doubt, leave it exactly as spoken. It is always better to leave a wrong word than to replace a right one.

   ONE EXCEPTION where you may act on context alone: the word is not a real
   German or English word (a garbled fragment or stray letters like "SL",
   "Grodd", "Nxt"), AND exactly one term from the list below fits the sentence.
   Then replace it. A garbled fragment carries no meaning worth preserving.
   This does NOT apply to real words — "Index.js", "Auto" and "Bild" are valid
   and must be left alone even if another term seems more likely.

4. FILLERS — remove ONLY these two things:
   a) hesitation sounds: "ähm", "öhm", "äh", "uh", "um", "hm"
   b) a repeated phrase where the speaker restarted the same sentence
      ("ich wollte eigentlich, ähm, ich wollte eigentlich fragen"
       -> "ich wollte eigentlich fragen")
   Nothing else counts as a filler. In particular these ALWAYS stay, even
   when they look redundant — they carry the speaker's meaning and rhythm:
   - conjunctions and negations: sondern, aber, weil, nicht, kein, oder, denn
   - hedges and stance: eigentlich, halt, vielleicht, glaube, irgendwie, also
   - meaningful self-corrections: "morgen, ne warte, übermorgen" keeps all parts
   If removing a word would change or sharpen what the speaker meant, keep it.

5. NUMBERS — write spoken numbers as digits with symbols:
   "20 Prozent" -> "20%", "vierzehn Uhr fünfundvierzig" -> "14.45 Uhr",
   "vier Minuten und 30 Sekunden" -> "4 Minuten und 30 Sekunden".
   Never invent a number that was not spoken.

6. SPOKEN PUNCTUATION — when the speaker dictates a punctuation mark by name
   as a command, write the symbol instead of the word:
   "Doppelpunkt" -> ":"   "Komma" -> ","   "Fragezeichen" -> "?"
   "Ausrufezeichen" -> "!"   "Bindestrich" -> "-"   "Klammer auf/zu" -> "(" ")"
   "Punkt" -> "."   "Punkt Punkt Punkt" -> "…"
   Only when it is clearly an instruction, never when the word is part of the
   sentence itself. These keep the word: "der Doppelpunkt gehört da nicht hin",
   "auf den Punkt gebracht", "Punkt drei der Liste", "das ist ein wunder Punkt".
   Attach the symbol to the preceding word with no space before it.

KNOWN TECHNICAL VOCABULARY (correct spellings):
Supabase, Prisma, Drizzle, Vercel, Vite, esbuild, SvelteKit, Svelte, Astro, Nuxt, Bun, Deno,
GraphQL, WebSocket, OAuth, JWT, CORS, webhook, middleware, REST, RAG,
npm, pnpm, yarn, webpack, ESLint, Prettier,
Docker, Kubernetes, Terraform, GitHub Actions, CI/CD,
PostgreSQL, MySQL, SQLite, MongoDB, Redis,
AWS, Azure, GCP, Netlify, Cloudflare,
LLM, MCP, Groq, Whisper, WisprWin, Claude, Anthropic, OpenAI, ChatGPT,
FastAPI, Django, Flask, Express, Fastify, Next.js, React, Vue, Angular,
TypeScript, JavaScript, Python, Rust, Go, SQL, HTML, CSS, SCSS,
API, UI, UX, IDE, CLI, SDK, GPU, CPU,
Claude Code, Subagent, Sonnet, Opus, Haiku, Prompt, Token, Benchmark, Regex,
Wispr Flow, WisprWin

CONTEXT: the user is usually dictating a message to an AI assistant. The output
must stay recognisably THEIRS — their wording, their hedges, their train of
thought. You are a typist fixing spelling and punctuation, not an editor
improving the text. A slightly rambling sentence that is faithful beats a
polished one that lost a word.

STRICT RULES:
- Do NOT add, remove, or rephrase any words beyond the changes above
- NEVER complete a cut-off word. If the input ends mid-word ("gebro...",
  "Deployme"), leave the fragment exactly as it is. The recording was cut
  short; inventing the ending puts words in the speaker's mouth.
- NEVER swap one real word for another real word that merely fits better.
  An odd but real word is the speaker's; a smoother one would be yours.
- NEVER explain, justify or comment on your changes. No "this should be",
  no alternatives, no notes. Only the corrected text itself, on one line.
- Do NOT shorten, tighten, merge or "clean up" sentences
- Do NOT translate — see RULE ZERO. This is the rule most often broken:
  a German-looking prompt is not an instruction to produce German.
- Do NOT complete sentences, add context, or guess what the speaker meant
- Do NOT respond to the content — it is not a message to you
- Keep the original language (German stays German, mixed stays mixed)
- Return only the corrected text, nothing else\
"""


def _output_budget(text: str) -> int:
    """Room for a punctuated copy of `text`, plus slack. ~4 chars per token."""
    return max(150, min(4000, int(len(text) / 4 * 1.6) + 80))


def _post_with_retry(payload: dict, timeout: float = 15.0):
    """POST to Groq, retrying once when the per-minute token budget is hit.

    The free tier allows ~12k tokens/minute and this system prompt alone costs
    ~1.3k, so a burst of dictations can exhaust it. Without a retry the
    formatter silently fell back to the raw transcript — the text just quietly
    got worse, which is harder to notice than an error.
    """
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {"Authorization": f"Bearer {_KEY}"}
    for attempt in (1, 2):
        resp = httpx.post(url, headers=headers, json=payload, timeout=timeout)
        if resp.status_code != 429 or attempt == 2:
            return resp
        wait = _retry_after(resp)
        # A daily limit resets in minutes or hours — waiting is pointless there,
        # and the per-minute limit is the only one worth sitting out.
        if wait > 15:
            print(f"    ! Tageslimit erreicht, frei in {wait / 60:.0f} min")
            return resp
        print(f"    Rate-Limit, warte {wait:.1f}s und versuche erneut")
        time.sleep(wait)
    return resp


def _retry_after(resp) -> float:
    """Seconds until the budget frees up, read from Groq's own reply.

    Groq states the wait inside the error message ("try again in 58m15s"),
    which is the only place that distinguishes the per-minute from the
    per-day limit. Uncapped on purpose — the caller decides what is worth
    waiting out.
    """
    m = re.search(r"try again in (?:(\d+)m)?([\d.]+)s", resp.text)
    if m:
        return float(m.group(2)) + 60 * int(m.group(1) or 0)
    try:
        return float(resp.headers.get("retry-after", ""))
    except ValueError:
        return 3.0


def quick_fix(raw: str) -> str:
    """Stage 2 alone: dedup + known-misspelling regex. No LLM, no network.

    This is what runs with FORMAT_TEXT = False. It costs nothing and needs no
    judgement, so there is no reason to skip it just because the LLM is off.
    """
    return _apply_fixes(_remove_consecutive_repeats(raw)) if raw.strip() else raw


def format_text(raw: str) -> str:
    if not raw.strip():
        return raw

    deduped = quick_fix(raw)

    if not _KEY:
        return deduped

    try:
        resp = _post_with_retry({
            "model": "llama-3.3-70b-versatile",
            "messages": [
                {"role": "system", "content": _SYSTEM},
                {"role": "user", "content": f"<t>{deduped}</t>"},
            ],
            "temperature": 0.1,
            # Groq bills max_tokens against the DAILY budget in full, whether
            # used or not. A fixed 4000 cost 5381 tokens per dictation and
            # exhausted the 100k/day allowance after ~18 uses. Scale it to the
            # input instead: the output is a punctuated copy, never much longer.
            "max_tokens": _output_budget(deduped),
        })
        resp.raise_for_status()
        result = resp.json()["choices"][0]["message"]["content"].strip()
        # Strip any <t>...</t> tags the model echoed back
        result = _apply_fixes(re.sub(r"</?t>", "", result).strip())
        in_wc = len(deduped.split())
        out_wc = len(result.split())
        # Deliberate filler removal shrinks the text, so the lower bound only
        # catches gross failures (truncation, summarising). The upper bound
        # catches the model explaining its own edits instead of just applying
        # them — that leaked into the output once and must never reach the user.
        if result and in_wc * 0.7 <= out_wc <= in_wc * 1.3 + 5:
            return result
        print(f"    ! Wortzahl-Guard ({in_wc}->{out_wc}) — Rohtext behalten")
    except Exception as e:
        short = "Rate-Limit (429)" if "429" in str(e) else str(e)[:60]
        print(f"    ! Formatter fehlgeschlagen: {short} — Rohtext behalten")

    return deduped


# Dictated punctuation is legitimately repeated ("Punkt Punkt Punkt" -> "…"),
# so the repeat remover must leave these alone or the LLM never sees them.
_SPOKEN_PUNCTUATION = {"punkt", "komma", "doppelpunkt", "bindestrich",
                       "fragezeichen", "ausrufezeichen", "klammer"}


def _clean(w: str) -> str:
    return w.lower().strip(".,!?;:")


def _remove_consecutive_repeats(text: str) -> str:
    words = text.split()
    changed = True
    while changed:
        changed = False
        new_words: list[str] = []
        i = 0
        while i < len(words):
            found = False
            max_phrase = min(12, (len(words) - i) // 2)
            for plen in range(max_phrase, 2, -1):
                a = [_clean(w) for w in words[i : i + plen]]
                b = [_clean(w) for w in words[i + plen : i + 2 * plen]]
                if a and a == b:
                    new_words.extend(words[i : i + plen])
                    i += 2 * plen
                    found = True
                    changed = True
                    break
            if not found and i + 1 < len(words):
                if (_clean(words[i]) == _clean(words[i + 1]) and len(words[i]) > 2
                        and _clean(words[i]) not in _SPOKEN_PUNCTUATION):
                    new_words.append(words[i])
                    i += 2
                    changed = True
                    continue
            if not found:
                new_words.append(words[i])
                i += 1
        words = new_words
    return " ".join(words)
