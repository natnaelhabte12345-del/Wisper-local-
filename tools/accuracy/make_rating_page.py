"""Builds rate.html: contested spots from his own clips, with audio, for him to rule on by ear.
    .venv\Scripts\python.exe tools\accuracy\make_rating_page.py <set_dir>"""
import json, os, random, sys, html
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import run_bench
d = sys.argv[1]
clips = {c["id"]: c for c in run_bench.load_clips(d, "real")}
cont = [x for x in json.load(open(os.path.join(d, "aai_vs_groq_big.json"), encoding="utf-8"))
        if 3 <= clips[x["id"]]["seconds"] <= 15 and len(x["aai"]) >= 4 and len(list(x["others"].values())[0]) >= 4]
random.seed(7)
de = [x for x in cont if x["lang"] == "de"]; en = [x for x in cont if x["lang"] == "en"]
pick = random.sample(de, min(25, len(de))) + random.sample(en, min(15, len(en)))
random.shuffle(pick)
items = []
for n, x in enumerate(pick):
    opts = [x["aai"]] + [v for v in dict.fromkeys(x["others"].values()) if v != x["aai"]]
    items.append({"n": n, "id": x["id"], "lang": x["lang"], "ctx": x["ctx"], "opts": opts,
                  "wav": "file:///" + clips[x["id"]]["wav"].replace("\\", "/")})
rows = ""
for it in items:
    ctx = html.escape(it["ctx"]).replace("[[", "<b>▶ ").replace("]]", " ◀</b>")
    radios = "".join(f'<label><input type=radio name=q{it["n"]} value="{html.escape(o)}">{html.escape(o)}</label>' for o in it["opts"])
    radios += f'<label><input type=radio name=q{it["n"]} value="__none">beide gleich gut / keins davon</label>'
    rows += (f'<div class=c><div class=h>{it["n"]+1}/{len(items)} · {it["lang"]}</div><div class=t>{ctx}</div>'
             f'<audio controls preload=none src="{it["wav"]}"></audio><div class=o>{radios}</div></div>')
page = f"""<!doctype html><meta charset=utf-8><title>WisprWin Test</title>
<style>body{{font:16px system-ui;max-width:760px;margin:20px auto;padding:0 16px;background:#111;color:#eee}}
.c{{border:1px solid #333;border-radius:10px;padding:12px;margin:12px 0}}.h{{color:#888;font-size:13px}}
.t{{margin:6px 0;font-size:18px}}b{{color:#ffb84d}}.o label{{display:block;padding:4px 0}}
button{{font:16px system-ui;padding:12px 20px;border-radius:8px;border:0;background:#3fd676;color:#000}}
audio{{width:100%;margin:6px 0}}</style>
<h2>Welches Wort wurde wirklich gesagt?</h2>
<p>Clip abspielen (kurz), das markierte Wort <b>▶ ◀</b> hören, die richtige Variante wählen. Unsichere einfach überspringen. Am Ende „Fertig“ drücken.</p>
{rows}<button onclick=done()>Fertig – Ergebnis kopieren</button><pre id=out></pre>
<script>const items={json.dumps(items, ensure_ascii=False)};
function done(){{const r=items.map(i=>{{const c=document.querySelector('input[name=q'+i.n+']:checked');return {{id:i.id,lang:i.lang,ctx:i.ctx,opts:i.opts,answer:c?c.value:null}}}});
const s=JSON.stringify(r);navigator.clipboard.writeText(s).then(()=>out.textContent='Kopiert! Jetzt hier im Chat einfügen.',()=>out.textContent=s);}}</script>"""
open(os.path.join(d, "rate2.html"), "w", encoding="utf-8").write(page)
print(len(items), "items ->", os.path.join(d, "rate2.html"))
