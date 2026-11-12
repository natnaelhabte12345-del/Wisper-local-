"""Run STT configs over a clip set. Results are cached, so a rate limit just means "run again".

    .venv\\Scripts\\python.exe tools\\accuracy\\run_bench.py <set_dir> <set: synth|real> <config> [<config> ...]
"""
import glob
import json
import os
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import scipy.io.wavfile as wavio

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import engines  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_lock = threading.Lock()


_DE = {"ich", "und", "nicht", "das", "ist", "mit", "auch", "dass", "eher", "mehr", "ein", "es",
       "ja", "aber", "wir", "du", "so", "dann", "wenn", "noch", "mal", "doch", "die", "der"}


def guess_lang(text):
    w = re.findall(r"[a-zäöüß]+", text.lower())
    return "de" if w and sum(x in _DE for x in w) / len(w) > 0.18 else "en"


def load_clips(set_dir, kind):
    if kind == "synth":
        return json.load(open(os.path.join(set_dir, "manifest.json"), encoding="utf-8"))
    clips = []
    for j in sorted(glob.glob(os.path.join(ROOT, "recordings", "*", "*.json"))):
        wav = j[:-5] + ".wav"
        d = json.load(open(j, encoding="utf-8"))
        if os.path.exists(wav) and d.get("raw"):
            day = os.path.basename(os.path.dirname(j))
            clips.append({"id": f"{day}/{os.path.basename(j)[:-5]}", "wav": wav, "lang": guess_lang(d["raw"]),
                          "seconds": d.get("duration_s", 0), "prod_raw": d["raw"]})
    return clips


def load_audio(path):
    sr, x = wavio.read(path)
    assert sr == 16000
    return x.astype(np.float32) / 32768


def main():
    set_dir, kind, configs = sys.argv[1], sys.argv[2], sys.argv[3:]
    out_path = os.path.join(set_dir, f"results_{kind}.jsonl")
    done = set()
    if os.path.exists(out_path):
        for line in open(out_path, encoding="utf-8"):
            r = json.loads(line)
            if not r.get("error"):
                done.add((r["config"], r["id"]))
    clips = load_clips(set_dir, kind)
    only = os.environ.get("ONLY")           # comma list of clip ids
    maxsec = float(os.environ.get("MAXSEC", "1e9"))
    if only:
        clips = [c for c in clips if c["id"] in only.split(",")]
    clips = [c for c in clips if (c.get("seconds") or 0) <= maxsec]
    sample = int(os.environ.get("SAMPLE", "0"))
    if sample:
        clips = clips[::max(1, len(clips) // sample)][:sample]

    def work(cfg, clip):
        fn, _ = engines.CONFIGS[cfg]
        if cfg == "speechmatics" and clip["lang"] == "de":
            fn = engines.speechmatics_de
        if cfg == "en" and clip["lang"] == "de":
            return None
        audio = load_audio(clip["wav"])
        t = time.time()
        try:
            text = fn(audio)
            rec = {"config": cfg, "id": clip["id"], "text": text, "s": round(time.time() - t, 2)}
        except engines.RateLimited as e:
            rec = {"config": cfg, "id": clip["id"], "error": f"ratelimit {e}"}
        except Exception as e:
            rec = {"config": cfg, "id": clip["id"], "error": repr(e)[:200]}
        with _lock:
            with open(out_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        return rec

    for cfg in configs:
        todo = [c for c in clips if (cfg, c["id"]) not in done]
        group = engines.CONFIGS[cfg][1]
        t0 = time.time()
        print(f"[{cfg}] {len(todo)} clips ({len(clips) - len(todo)} cached)", flush=True)
        if group == "groq":
            errs = 0
            for i, c in enumerate(todo):
                r = work(cfg, c)
                if r and r.get("error"):
                    errs += 1
                    print("  ", c["id"], r["error"][:90], flush=True)
                    if "ratelimit" in r["error"] or errs >= 4:
                        print("  stopping this config — rerun later to resume", flush=True)
                        break
                time.sleep(3.2)   # 20 requests/minute
        else:
            with ThreadPoolExecutor(3) as ex:
                for r in ex.map(lambda c: work(cfg, c), todo):
                    if r and r.get("error"):
                        print("  ", r["id"], r["error"][:90], flush=True)
        print(f"[{cfg}] done in {time.time() - t0:.0f}s", flush=True)


if __name__ == "__main__":
    main()
