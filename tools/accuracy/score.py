"""Score STT output against the known text: content-word WER, key-term hits, and what each miss turned into.

    .venv\\Scripts\\python.exe tools\\accuracy\\score.py <set_dir> [config ...]
"""
import collections
import difflib
import json
import os
import re
import sys

FILLERS = {"um", "uh", "uhm", "umm", "er", "erm", "ah", "hm", "hmm", "mm", "äh", "ähm", "öhm", "eh"}
_ONES = "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen".split()
_TENS = "_ _ twenty thirty forty fifty sixty seventy eighty ninety".split()


def _num_words(n: int) -> str:
    if n < 20:
        return _ONES[n]
    if n < 100:
        return _TENS[n // 10] + ("" if n % 10 == 0 else " " + _ONES[n % 10])
    if n < 1000:
        return _ONES[n // 100] + " hundred" + ("" if n % 100 == 0 else " " + _num_words(n % 100))
    return str(n)


def normalize(text: str) -> list[str]:
    t = text.lower().replace("ß", "ss").replace("’", "'")
    t = t.replace("%", " percent ").replace("$", " dollars ")
    t = re.sub(r"(\d+)\.(\d+)", r"\1 \2", t)
    t = re.sub(r"\d+", lambda m: " " + _num_words(int(m.group())) + " ", t)
    t = re.sub(r"[^\w\säöü']", " ", t.replace("-", " "))
    t = t.replace("_", " ")
    return t.split()


def content(tokens):
    return [w for w in tokens if w not in FILLERS]


def wer(ref, hyp):
    ref, hyp = content(normalize(ref)), content(normalize(hyp))
    if not ref:
        return 0.0, 0, 0
    prev = list(range(len(hyp) + 1))
    for i, r in enumerate(ref, 1):
        cur = [i]
        for j, h in enumerate(hyp, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (r != h)))
        prev = cur
    return prev[-1] / len(ref), prev[-1], len(ref)


def _spaceless(tokens):
    return "".join(tokens)


def term_hit(term_alts: str, hyp: str) -> bool:
    h = normalize(hyp)
    hs = _spaceless(h)
    hj = " " + " ".join(h) + " "
    for alt in term_alts.split("|"):
        t = normalize(alt)
        if not t:
            continue
        if (" " + " ".join(t) + " ") in hj:
            return True
        if len(_spaceless(t)) >= 5 and _spaceless(t) in hs:
            return True
    return False


def what_it_became(term_alts: str, truth: str, hyp: str) -> str:
    """The words the recogniser produced where the term was spoken."""
    t_tok, h_tok = normalize(truth), normalize(hyp)
    best = normalize(term_alts.split("|")[0])
    n = len(best)
    start = next((i for i in range(len(t_tok) - n + 1) if t_tok[i:i + n] == best), None)
    if start is None:
        for alt in term_alts.split("|")[1:]:
            best = normalize(alt)
            n = len(best)
            start = next((i for i in range(len(t_tok) - n + 1) if t_tok[i:i + n] == best), None)
            if start is not None:
                break
    if start is None:
        return "?"
    sm = difflib.SequenceMatcher(None, t_tok, h_tok, autojunk=False)
    got = []
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if i2 > start and i1 < start + n and op != "equal":
            got.extend(h_tok[j1:j2] or ["∅"])
    return " ".join(got) or "?"


def load(set_dir, kind="synth"):
    man = {m["id"]: m for m in json.load(open(os.path.join(set_dir, "manifest.json"), encoding="utf-8"))}
    res = collections.defaultdict(dict)
    p = os.path.join(set_dir, f"results_{kind}.jsonl")
    for line in open(p, encoding="utf-8"):
        r = json.loads(line)
        if not r.get("error"):
            res[r["config"]][r["id"]] = r["text"]
    return man, res


def score_config(man, texts):
    rows = []
    for cid, hyp in texts.items():
        m = man[cid]
        w, errs, n = wer(m["text"], hyp)
        hits = [(t, term_hit(t, hyp)) for t in m["terms"]]
        rows.append({"id": cid, "cond": m["cond"], "lang": m["lang"], "wer": w, "errs": errs, "n": n,
                     "hits": hits, "hyp": hyp})
    return rows


def summarize(rows):
    n = sum(r["n"] for r in rows) or 1
    e = sum(r["errs"] for r in rows)
    th = sum(h for r in rows for _, h in r["hits"])
    tt = sum(len(r["hits"]) for r in rows) or 1
    allhit = sum(all(h for _, h in r["hits"]) for r in rows)
    return {"clips": len(rows), "wer": e / n, "term_hit": th / tt, "clips_all_terms": allhit}


if __name__ == "__main__":
    set_dir = sys.argv[1]
    man, res = load(set_dir)
    cfgs = sys.argv[2:] or list(res)
    print(f"{'config':<14}{'clips':>6}{'WER':>8}{'terms ok':>10}{'clips w/ all terms ok':>24}")
    for c in cfgs:
        s = summarize(score_config(man, res[c]))
        print(f"{c:<14}{s['clips']:>6}{s['wer']:>8.1%}{s['term_hit']:>10.1%}{s['clips_all_terms']:>12}/{s['clips']}")
