"""Compare cleanup models on real dictations, using Llama 3.3's saved output as reference."""
import difflib
import glob
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import formatter as fm  # noqa: E402

MODELS = {
    "gpt-oss-120b": {"model": "openai/gpt-oss-120b", "reasoning_effort": "low",
                     "include_reasoning": False},
    "gpt-oss-20b": {"model": "openai/gpt-oss-20b", "reasoning_effort": "low",
                    "include_reasoning": False},
    "qwen3.8-27b": {"model": "qwen/qwen3.8-27b", "reasoning_effort": "none",
                    "reasoning_format": "hidden"},
}

root = os.path.join(os.path.dirname(__file__), "..", "recordings")
refs = []
for f in sorted(glob.glob(os.path.join(root, "2026-07-3*", "*.json"))
                + glob.glob(os.path.join(root, "2026-08-0*", "*.json"))):
    d = json.load(open(f, encoding="utf-8"))
    if d.get("raw") and d["raw"] != d["formatted"] and 8 <= len(d["raw"].split()) <= 120:
        refs.append((d["raw"], d["formatted"]))
refs = refs[::max(1, len(refs) // 10)][:10]

specials = []
for f in glob.glob(os.path.join(root, "2026-09-27", "*.json")):
    d = json.load(open(f, encoding="utf-8"))
    if re.search(r"Sipabase|golf drugs", d.get("raw", "")):
        specials.append(d["raw"])


def run(cfg, raw):
    time.sleep(PAUSE)
    deduped = fm.quick_fix(raw)
    payload = {**cfg, "temperature": 0.1,
               "max_tokens": fm._output_budget(deduped) + 1500,
               "messages": [{"role": "system", "content": fm._SYSTEM},
                            {"role": "user", "content": f"<t>{deduped}</t>"}]}
    t = time.time()
    r = fm._post_with_retry(payload, timeout=40)
    dt = time.time() - t
    if r.status_code != 200:
        return None, dt, f"HTTP {r.status_code}: {r.text[:120]}"
    out = r.json()["choices"][0]["message"]["content"] or ""
    out = fm._apply_fixes(re.sub(r"</?t>", "", out).strip())
    in_wc, out_wc = len(deduped.split()), len(out.split())
    guard = in_wc * 0.7 <= out_wc <= in_wc * 1.3 + 5
    return out, dt, "" if guard else f"guard fail {in_wc}->{out_wc}"


PAUSE = float(os.environ.get("BENCH_PAUSE", "0"))
only = sys.argv[1:]
report = {}
for name, cfg in MODELS.items():
    if only and name not in only:
        continue
    sims, times, fails = [], [], 0
    samples = []
    for raw, ref in refs:
        out, dt, err = run(cfg, raw)
        times.append(dt)
        if err:
            fails += 1
            samples.append({"raw": raw, "err": err})
            continue
        sims.append(difflib.SequenceMatcher(None, out, ref).ratio())
    for raw in specials:
        out, dt, err = run(cfg, raw)
        samples.append({"raw": raw[:200], "out": out, "end": (out or "")[-160:], "err": err, "s": round(dt, 2)})
    report[name] = {"similarity_to_llama": round(sum(sims) / len(sims), 3) if sims else None,
                    "median_s": round(sorted(times)[len(times) // 2], 2),
                    "fails": f"{fails}/{len(refs)}", "specials": samples}
    print(name, report[name]["similarity_to_llama"], report[name]["median_s"],
          report[name]["fails"], flush=True)

base = sum(difflib.SequenceMatcher(None, fm.quick_fix(r), f).ratio() for r, f in refs) / len(refs)
print("baseline (regex only vs llama):", round(base, 3))
json.dump(report, open(os.path.join(os.path.dirname(__file__), "formatter_bench.json"), "w",
                       encoding="utf-8"), ensure_ascii=False, indent=1)
