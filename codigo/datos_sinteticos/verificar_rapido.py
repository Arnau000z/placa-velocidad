"""Igual que verificar_sintetico.py (mismos filtros, mismas salidas) pero ejecuta los programas en paralelo antes de la
pasada secuencial, y luego arma la mezcla con nube/mezclar_sft.py sin volver a verificar al importarlo.

python -X utf8 verificar_rapido.py [nombre_mezcla=sft_codigo_v3]
"""
import concurrent.futures
import glob
import hashlib
import json
import os
import runpy
import sys
import types
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
src = open(os.path.join(HERE, "verificar_sintetico.py"), encoding="utf-8").read()
corte = src.index("buenos, vistos = [], set()")
mod = types.ModuleType("verificar_sintetico")
mod.__file__ = os.path.join(HERE, "verificar_sintetico.py")
exec(compile(src[:corte], mod.__file__, "exec"), mod.__dict__)
sys.modules["verificar_sintetico"] = mod
LETTERS, match_option, run, limpiar_codigo, formato, SYSTEM = (mod.LETTERS, mod.match_option, mod.run, mod.limpiar_codigo,
                                                              mod.formato, mod.SYSTEM)
import re  # noqa: E402

filas, stats = [], Counter()
for p in sorted(glob.glob(os.path.join(HERE, "generado", "*.jsonl"))):
    for l in open(p, encoding="utf-8"):
        if not l.strip():
            continue
        try:
            filas.append(json.loads(l))
        except json.JSONDecodeError:
            stats["json_malo"] += 1
codigos = {limpiar_codigo(r["code"]) for r in filas if isinstance(r, dict) and r.get("code")}
codigos = [c for c in codigos if c.count("\n") <= 14 and len(c) <= 700]
print(len(filas), "filas,", len(codigos), "programas distintos a ejecutar", flush=True)
with concurrent.futures.ThreadPoolExecutor(12) as ex:
    salidas = dict(zip(codigos, ex.map(run, codigos)))

buenos, vistos = [], set()
for r in filas:
    if not isinstance(r, dict):
        continue
    stats["leidos"] += 1
    o = r.get("options") or {}
    if not isinstance(o, dict) or len(o) != 5 or r.get("label") not in LETTERS or not r.get("text") or not r.get("code"):
        stats["incompleto"] += 1
        continue
    o = {k: str(v).strip() for k, v in o.items()}
    if len(set(o.values())) < 5:
        stats["opciones_repetidas"] += 1
        continue
    h = hashlib.sha1(re.sub(r"\W+", "", r["text"].lower()).encode()).hexdigest()
    if h in vistos:
        stats["duplicado"] += 1
        continue
    code = limpiar_codigo(r["code"])
    if code not in salidas:
        stats["codigo_largo"] += 1
        continue
    out, err = salidas[code]
    letra, _ = (None, "") if not out.strip() else match_option(out, o)
    if letra != r["label"]:
        stats["no_casa_o_distinta"] += 1
        continue
    vistos.add(h)
    buenos.append({"id": f"sint_{len(buenos):05d}", "language": r.get("language", "eng"), "level": int(r.get("level", 4) or 4),
                   "type": r.get("type", "other"), "text": r["text"].strip(), "options": o, "label": r["label"], "code": code, "text_only": True})
    stats["ok"] += 1
with open(os.path.join(HERE, "limpio.jsonl"), "w", encoding="utf-8", newline="\n") as f:
    for b in buenos:
        f.write(json.dumps(b, ensure_ascii=False) + "\n")
print(dict(stats), flush=True)
print(f"{len(buenos)} sintéticos verificados → limpio.jsonl; idiomas {dict(Counter(b['language'] for b in buenos))}", flush=True)
sys.argv = ["mezclar_sft.py", sys.argv[1] if len(sys.argv) > 1 else "sft_codigo_v3"]
runpy.run_path(r"D:\Datathon_A\nube\mezclar_sft.py", run_name="__main__")
