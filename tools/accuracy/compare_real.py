"""Where do other engines disagree with the production transcript on Nati's real clips?

    .venv\\Scripts\\python.exe tools\\accuracy\\compare_real.py <set_dir>

A span the production engine wrote that at least two other engines wrote differently
(and whose spelling doesn't merely differ in format) is a suspect error.
"""
import collections
import difflib
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import score  # noqa: E402

ALTS = ["speechmatics", "deepgram", "assemblyai"]


def toks(t):
    return score.content(score.normalize(t))


def spans(a, b):
    sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
    return [(i1, i2, b[j1:j2]) for op, i1, i2, j1, j2 in sm.get_opcodes() if op != "equal"]


def main():
    set_dir = sys.argv[1]
    prod, alt = {}, collections.defaultdict(dict)
    for line in open(os.path.join(set_dir, "results_real.jsonl"), encoding="utf-8"):
        r = json.loads(line)
        if not r.get("error"):
            alt[r["config"]][r["id"]] = r["text"]
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    import glob
    for j in glob.glob(os.path.join(root, "recordings", "*", "*.json")):
        d = json.load(open(j, encoding="utf-8"))
        prod[f"{os.path.basename(os.path.dirname(j))}/{os.path.basename(j)[:-5]}"] = d.get("raw", "")
    ids = [i for i in prod if all(i in alt[a] for a in ALTS) and prod[i]]
    print(f"{len(ids)} clips with all engines")

    # engine-vs-engine distance (content words), production included
    names = ["prod"] + ALTS
    texts = {"prod": prod, **{a: alt[a] for a in ALTS}}
    print("\npairwise word difference (content words, % of production words):")
    for a in names:
        row = []
        for b in names:
            if a == b:
                row.append("   -  ")
                continue
            e = n = 0
            for i in ids:
                ra, hb = toks(texts[a][i]), toks(texts[b][i])
                n += len(ra)
                e += int(score.wer(texts[a][i], texts[b][i])[1])
            row.append(f"{e / max(n, 1):6.1%}")
        print(f"  {a:<13}" + " ".join(row))

    suspects = collections.defaultdict(list)
    for i in ids:
        p = toks(prod[i])
        votes = collections.defaultdict(list)
        for a in ALTS:
            for i1, i2, rep in spans(p, toks(alt[a][i])):
                votes[(i1, i2)].append((a, " ".join(rep)))
        for (i1, i2), vs in votes.items():
            if len(vs) >= 2 and i2 > i1 and (i2 - i1) <= 3:
                key = " ".join(p[i1:i2])
                ctx = " ".join(p[max(0, i1 - 4):i1]) + " [[" + key + "]] " + " ".join(p[i2:i2 + 4])
                suspects[key].append((i, ctx, [v for _, v in vs]))
    print(f"\n{sum(len(v) for v in suspects.values())} suspect spans; most repeated:")
    for key, lst in sorted(suspects.items(), key=lambda kv: -len(kv[1]))[:60]:
        print(f"\n[{key}] x{len(lst)}")
        for i, ctx, alts in lst[:2]:
            print(f"   {i[5:]} | {ctx}")
            print(f"        others say: {alts}")


if __name__ == "__main__":
    main()
