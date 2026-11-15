"""Traduce al catalán problemas sintéticos verificados en inglés (mismas opciones, misma etiqueta, mismo programa) con un
modelo abierto ilimitado de Helmcode. El examen es eng/cat y en catalán acertamos ~6-8 puntos menos.
Salida: sintetico/generado/gen_cat_<n>.jsonl (los vuelve a comprobar verificar_sintetico.py).

python -X utf8 traducir_helmcode.py [--modelo qwen3.6] [--max 3000] [--paralelo 4]
"""
import argparse
import concurrent.futures as cf
import json
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from helmcode import chat  # noqa: E402

p = argparse.ArgumentParser()
p.add_argument("--modelo", default="qwen3.6")
p.add_argument("--max", type=int, default=3000)
p.add_argument("--paralelo", type=int, default=4)
args = p.parse_args()
rows = [json.loads(l) for l in open(os.path.join(HERE, "limpio.jsonl"), encoding="utf-8") if l.strip()]
rows = [r for r in rows if r.get("language") == "eng"]
random.Random(9).shuffle(rows)
rows = rows[:args.max]
SYS = ("Translate the math problem statement into Catalan (Central Catalan, correct accents and apostrophes). Keep every number, "
       "name and condition exactly; do not solve it; do not add anything. Reply with the translated statement only.")


def uno(r):
    text, _ = chat(args.modelo, [{"role": "system", "content": SYS}, {"role": "user", "content": r["text"]}], max_tokens=600,
                   temperature=0.2, reasoning_effort="none")
    text = text.strip().strip('"')
    if len(text.split()) < 8:
        return None
    return {"text": text, "options": r["options"], "label": r["label"], "level": r["level"], "type": r["type"],
            "language": "cat", "code": r["code"]}


n = 0
lote, k = [], 0
with cf.ThreadPoolExecutor(args.paralelo) as ex:
    for d in ex.map(uno, rows):
        if d:
            lote.append(d)
        if len(lote) >= 200:
            with open(os.path.join(HERE, "generado", f"gen_cat_{k:03d}.jsonl"), "w", encoding="utf-8") as f:
                f.write("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in lote))
            n += len(lote)
            print(f"  {n} traducidos", flush=True)
            lote, k = [], k + 1
if lote:
    with open(os.path.join(HERE, "generado", f"gen_cat_{k:03d}.jsonl"), "w", encoding="utf-8") as f:
        f.write("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in lote))
    n += len(lote)
print(f"hecho: {n} problemas traducidos al catalán con {args.modelo}")
