"""Doble verificación con un modelo abierto: deepseek-v4-flash resuelve cada problema sintético SIN ver la respuesta.
Se quedan solo los que coinciden con la letra marcada → limpio_doble.jsonl (calidad alta para entrenar).

python -X utf8 control_helmcode.py [--modelo deepseek-v4-flash] [--paralelo 5]
"""
import argparse
import concurrent.futures as cf
import json
import os
import re
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from helmcode import chat  # noqa: E402

p = argparse.ArgumentParser()
p.add_argument("--modelo", default="deepseek-v4-flash")
p.add_argument("--paralelo", type=int, default=5)
p.add_argument("--esfuerzo", default="low")
args = p.parse_args()
rows = [json.loads(l) for l in open(os.path.join(HERE, "limpio.jsonl"), encoding="utf-8") if l.strip()]
cache_path = os.path.join(HERE, "control_cache.jsonl")
hechos = {}
if os.path.exists(cache_path):
    for l in open(cache_path, encoding="utf-8"):
        if l.strip():
            d = json.loads(l)
            hechos[d["h"]] = d["resp"]
SYS = ("Solve the multiple-choice math problem carefully. Think as needed, then end your reply with exactly 'Answer: X' "
       "where X is the letter A-E of the correct option.")


def clave(r):
    return str(abs(hash(r["text"] + json.dumps(r["options"], sort_keys=True))))


def uno(r):
    h = clave(r)
    if h in hechos:
        return r, hechos[h], False
    user = r["text"] + "\n" + "\n".join(f"{k}) {r['options'][k]}" for k in "ABCDE")
    text, _ = chat(args.modelo, [{"role": "system", "content": SYS}, {"role": "user", "content": user}], max_tokens=3000,
                   reasoning_effort=args.esfuerzo)
    m = re.findall(r"Answer:\s*\**\s*\(?([A-E])\b", text)
    return r, (m[-1] if m else None), True


t0 = time.time()
ok = n = 0
with cf.ThreadPoolExecutor(args.paralelo) as ex, open(cache_path, "a", encoding="utf-8") as fc, \
        open(os.path.join(HERE, "limpio_doble.jsonl"), "w", encoding="utf-8", newline="\n") as fo:
    for r, resp, nuevo in ex.map(uno, rows):
        n += 1
        if nuevo:
            fc.write(json.dumps({"h": clave(r), "resp": resp}) + "\n")
            fc.flush()
        if resp == r["label"]:
            ok += 1
            fo.write(json.dumps(r, ensure_ascii=False) + "\n")
        if n % 200 == 0:
            print(f"  {n}/{len(rows)}  coinciden {ok} ({100 * ok / n:.0f} %)  {time.time() - t0:.0f} s", flush=True)
print(f"doble verificación: {ok} de {n} coinciden con {args.modelo} → limpio_doble.jsonl")
