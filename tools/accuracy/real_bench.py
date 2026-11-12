"""Nati's own benchmark from his saved clips: estimate each engine's error rate by
voting between engines (no ground truth exists), and list the contested spots for him to rule on.

    .venv\Scripts\python.exe tools\accuracy\real_bench.py <set_dir>
"""
import collections, difflib, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import score
import run_bench

ENG = ["groq_plain", "assemblyai", "deepgram", "speechmatics"]


def toks(t):
    return score.content(score.normalize(t))


def main():
    d = sys.argv[1]
    res = collections.defaultdict(dict)
    for l in open(os.path.join(d, "results_real.jsonl"), encoding="utf-8"):
        r = json.loads(l)
        if not r.get("error"):
            res[r["config"]][r["id"]] = r["text"]
    clips = {c["id"]: c for c in run_bench.load_clips(d, "real")}
    ids = [i for i in clips if all(i in res[e] for e in ENG)]
    out = {"errors": collections.defaultdict(lambda: collections.defaultdict(lambda: [0, 0])), "contested": []}
    for i in ids:
        lang = clips[i]["lang"]
        T = {e: toks(res[e][i]) for e in ENG}
        for e in ENG:
            others = [o for o in ENG if o != e]
            # words of e judged against each other engine; a word is "contested" when
            # at least 2 of the 3 others disagree with it
            bad = [0] * len(T[e])
            alts = [collections.defaultdict(list) for _ in T[e]]
            for o in others:
                sm = difflib.SequenceMatcher(None, T[e], T[o], autojunk=False)
                for op, i1, i2, j1, j2 in sm.get_opcodes():
                    if op != "replace":     # a word one engine dropped/added is mostly disfluency taste
                        continue
                    for k in range(i1, i2):
                        kk = min(k, len(T[e]) - 1)
                        if kk >= 0:
                            bad[kk] += 1
                            alts[kk][o].append(" ".join(T[o][j1:j2]))
            n = len(T[e])
            flagged = sum(1 for b in bad if b >= 2)
            st = out["errors"][lang][e]
            st[0] += flagged
            st[1] += n
            if e == "assemblyai":
                for k, b in enumerate(bad):
                    if b >= 2 or (b == 1 and False):
                        ctx = " ".join(T[e][max(0, k - 4):k]) + " [[" + T[e][k] + "]] " + " ".join(T[e][k + 1:k + 5])
                        out["contested"].append({"id": i, "lang": lang, "ctx": ctx,
                                                 "aai": T[e][k], "others": {o: v[0] for o, v in alts[k].items()}})
    print(f"{len(ids)} clips scored")
    print("\nestimated error rate = words the engine wrote that >=2 of the other 3 engines wrote differently")
    for lang in ("en", "de"):
        print(f"\n[{lang}]")
        for e in ENG:
            f, n = out["errors"][lang][e]
            print(f"  {e:<13} {f / max(n, 1):6.1%}   ({f}/{n} words)")
    # production question: where AssemblyAI and Groq differ, who is right?
    vs = []
    for i in ids:
        a, g = toks(res["assemblyai"][i]), toks(res["groq_plain"][i])
        for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, g, autojunk=False).get_opcodes():
            if op == "replace" and i2 - i1 <= 2 and j2 - j1 <= 2:
                vs.append({"id": i, "lang": clips[i]["lang"],
                           "ctx": " ".join(a[max(0, i1 - 4):i1]) + " [[" + " ".join(a[i1:i2]) + "]] " + " ".join(a[i2:i2 + 4]),
                           "aai": " ".join(a[i1:i2]), "others": {"groq_plain": " ".join(g[j1:j2])}})
    json.dump(vs, open(os.path.join(d, "aai_vs_groq.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("AssemblyAI vs Groq differing spots:", len(vs), {l: sum(v["lang"] == l for v in vs) for l in ("en", "de")})
    json.dump(out["contested"], open(os.path.join(d, "contested.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    c = collections.Counter((x["lang"], x["aai"]) for x in out["contested"])
    print("\ncontested spans (AssemblyAI view):", len(out["contested"]))
    print("most repeated words:", c.most_common(25))


if __name__ == "__main__":
    main()
