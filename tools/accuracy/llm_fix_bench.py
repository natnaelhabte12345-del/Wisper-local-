"""Can the cleanup LLM repair misheard names without breaking legitimate words?

    .venv\\Scripts\\python.exe tools\\accuracy\\llm_fix_bench.py <set_dir> [variant ...]

Variants differ only in the system prompt:  base = production, gloss = + personal glossary
with a context-based swap rule.  Three test sets:
  precision  sentences where "cloud", "java", "tournament"... are CORRECT - must stay untouched
  recall     real misheard sentences from his archive - must be repaired
  synth      Whisper's actual output on the synthetic clips - repaired where wrong, untouched where right
"""
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import formatter as fm  # noqa: E402
import score  # noqa: E402

GLOSSARY = """\
PERSONAL GLOSSARY — words this speaker says often, and what the transcriber usually makes of them:
  Claude / Claude Code / Claude Desktop   heard as: cloud, cloud code, cloud desktop, clod, claud
  Stockfish (chess engine)                heard as: stock fish, stop fishing, StockBush
  Jarvis (his dashboard)                  heard as: java, service, driver
  terminal                                heard as: tournament
  Opera / Opera GX (browser)              heard as: paras, opera is fine
  Supabase                                heard as: superbase, sipabase
  Groq (the API, with a Q)                heard as: grog
  Wispr Flow                              heard as: swapflow, wisp flow, whisper flow
Apply the glossary ONLY when the surrounding sentence makes the glossary word clearly
the intended one (an AI tool, a chess game, a pop-up, startup apps...). If the heard
word fits its own sentence ("the cloud storage", "learn Java", "the opera singer",
"a chess tournament", "the airport terminal"), it is correct — leave it exactly as it is.
"""

NEW_RULE3 = """\
3. VOCABULARY FIX — replace a misheard word with a term from the KNOWN VOCABULARY or the
   PERSONAL GLOSSARY when it sounds nearly identical AND the sentence only makes sense with
   the glossary term (e.g. "tournament pop-up" -> "terminal pop-up", "tools to cloud code" ->
   "tools to Claude Code"). If the heard word makes sense in its own sentence, leave it.

"""


def build_gloss_system():
    s = fm._SYSTEM
    a, b = s.index("3. VOCABULARY FIX"), s.index("4. FILLERS")
    s = s[:a] + NEW_RULE3 + s[b:]
    s = s.replace("- NEVER swap one real word for another real word that merely fits better.\n"
                  "  An odd but real word is the speaker's; a smoother one would be yours.",
                  "- Swap a real word for another one ONLY under rule 3. Otherwise an odd but real\n"
                  "  word is the speaker's; a smoother one would be yours.")
    s = s.replace("CONTEXT: the user is usually", GLOSSARY + "\nCONTEXT: the user is usually", 1)
    return s


VARIANTS = {"prod": fm._SYSTEM, "gloss_old": build_gloss_system()}

PRECISION = [
    "I store the backup in the cloud, so I can reach it from my phone.",
    "Java is slower than Rust for this kind of thing.",
    "The chess tournament starts at five and I'm not ready.",
    "She sings at the opera on Friday and I got two tickets.",
    "The terminal at the airport was crowded and my flight got delayed.",
    "Cloud computing costs are going up, so we moved some servers back.",
    "The pop-up shows a cloud icon next to the file.",
    "Stockfish is the strongest engine, but I only play against bots.",
    "Jarvis is my dashboard, not the Marvel one.",
    "Claude became cloud in the transcript, which is wrong.",
    "We went fishing at the lake and the fish wouldn't stop biting.",
    "I use the Claude Code terminal to run the tests before I commit.",
    "Grok is the xAI model and Groq is the inference API.",
    "I put the files in the cloud and then deleted them from the laptop.",
    "She works with Java and Kotlin at the bank.",
    "The Opera browser feels slower than Brave on my laptop.",
    "He didn't win the tournament because he lost his queen early.",
    "Don't touch the terminal, I'm still running the build.",
    "I don't think the cloud is the problem, I think it's the router.",
    "We watched an opera and then walked home in the rain.",
]

RECALL = [  # (heard, must contain)
    ("I only want Brave and Cloud.", "Claude"),
    ("I activated um cloud to start at the beginning of the laptop start.", "Claude"),
    ("I have cloud code installed on my PC and that's also where I work.", "Claude Code"),
    ("Maybe connecting tools to cloud code works with a custom CLI.", "Claude Code"),
    ("I like stop fishing because I think it's too good of a playing style to copy.", "Stockfish"),
    ("Maybe you could see what StockBush would have done in that position.", "Stockfish"),
    ("There's like a tournament pop-up coming every 15 minutes and it's annoying.", "terminal"),
    ("I don't want Spotify, Discord, OneDrive and two of Paras to start.", "Opera"),
    ("Can you fix java so it's not loading and the pop-up disappears?", "Jarvis"),
    ("Superbase stores the users and Grog cleans the text.", "Supabase"),
    ("He told me to use the new feature in cloud desktop instead.", "Claude Desktop"),
    ("We built it with swapflow and I cloned it by myself.", "Wispr Flow"),
]


def run_variant(name, system, text):
    payload = {"model": "openai/gpt-oss-120b", "reasoning_effort": "low", "include_reasoning": False,
               "messages": [{"role": "system", "content": system},
                            {"role": "user", "content": f"<t>{fm.quick_fix(text)}</t>"}],
               "temperature": 0.1, "max_tokens": fm._output_budget(text) + 600}
    for _ in range(3):
        r = fm._post_with_retry(payload, timeout=40)
        if r.status_code == 200:
            out = (r.json()["choices"][0]["message"]["content"] or "").strip()
            return fm._apply_fixes(re.sub(r"</?t>", "", out).strip())
        time.sleep(8)
    return None


def same(a, b):
    return score.normalize(a) == score.normalize(b)


def main():
    set_dir = sys.argv[1]
    names = sys.argv[2:] or list(VARIANTS)
    man, res = score.load(set_dir)
    synth = []
    for r in score.score_config(man, res["current"]):
        synth.append(r)
    report = {}
    for v in names:
        sysmsg = VARIANTS[v]
        rep = {"precision_kept": 0, "precision_broken": [], "recall_fixed": 0, "recall_missed": [],
               "synth_fixed": 0, "synth_missed": 0, "synth_broken": [], "synth_wer_before": 0,
               "synth_wer_after": 0, "n_synth": 0}
        for s in PRECISION:
            out = run_variant(v, sysmsg, s)
            if out is not None and same(out, s):
                rep["precision_kept"] += 1
            else:
                rep["precision_broken"].append([s, out])
            time.sleep(6)
        for heard, must in RECALL:
            out = run_variant(v, sysmsg, heard)
            if out and must.lower() in out.lower():
                rep["recall_fixed"] += 1
            else:
                rep["recall_missed"].append([heard, out])
            time.sleep(6)
        # synthetic: every clip that had a miss, plus an equal number that had none
        bad = [r for r in synth if not all(h for _, h in r["hits"])]
        good = [r for r in synth if all(h for _, h in r["hits"]) and r["lang"] == "en"][:len(bad)]
        for r in bad + good:
            out = run_variant(v, sysmsg, r["hyp"])
            time.sleep(6)
            if out is None:
                continue
            m = man[r["id"]]
            hits_after = [(t, score.term_hit(t, out)) for t in m["terms"]]
            rep["n_synth"] += 1
            rep["synth_wer_before"] += score.wer(m["text"], r["hyp"])[1]
            rep["synth_wer_after"] += score.wer(m["text"], out)[1]
            for (t, b), (_, a) in zip(r["hits"], hits_after):
                if not b and a:
                    rep["synth_fixed"] += 1
                elif not b and not a:
                    rep["synth_missed"] += 1
                elif b and not a:
                    rep["synth_broken"].append([r["id"], t, out[:160]])
        report[v] = rep
        json.dump(report, open(os.path.join(set_dir, "llm_fix_report.json"), "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1)
        print(v, {k: (len(x) if isinstance(x, list) else x) for k, x in rep.items()}, flush=True)


if __name__ == "__main__":
    main()
