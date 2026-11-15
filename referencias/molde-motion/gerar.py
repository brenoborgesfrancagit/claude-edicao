import json, os, shutil, sys
aqui = os.path.dirname(os.path.abspath(__file__))
molde = open(os.path.join(aqui, "molde.html"), encoding="utf-8").read()
studio = os.path.expanduser("~/.claude/skills/claude-video/modelos/motion/studio.js")
for c in json.load(open(sys.argv[1] if len(sys.argv) > 1 else os.path.join(aqui, "cenas.json"), encoding="utf-8")):
    d = os.path.join(aqui, "proj", c["id"]); os.makedirs(d, exist_ok=True)
    html = molde.replace("__DUR__", str(c["dur"])).replace("__CENA__", json.dumps(c["cena"], ensure_ascii=False))
    open(os.path.join(d, "index.html"), "w", encoding="utf-8").write(html)
    shutil.copy(studio, d)
    for f in ("hyperframes.json", "meta.json"):
        shutil.copy(os.path.join(os.path.dirname(studio), f), d)
print("ok")
