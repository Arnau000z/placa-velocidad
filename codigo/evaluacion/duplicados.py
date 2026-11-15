"""¿Cuántos problemas de val son (casi) el mismo que uno de train? Si el test se parece a val, un detector de
duplicados contesta en 1 s copiando la etiqueta del vecino. Mide precisión y cobertura según el umbral.

python -X utf8 duplicados.py <repo>   (necesita el servidor de embeddings bge-m3 en :8084 y data/index_m3.db)
Solo CPU (numpy) salvo embeber los 789 de val una vez.
"""
import json
import os
import sqlite3
import sys
from array import array
from collections import Counter

import numpy as np

repo = sys.argv[1]
sys.path.insert(0, repo)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from copilot.embed import embed  # noqa: E402
from copilot.llm import format_problem  # noqa: E402
from util_opciones import parse_value  # noqa: E402

db = sqlite3.connect(os.path.join(repo, "data", "index_m3.db"))
keys, probs, vecs = [], [], []
for key, problem, blob in db.execute("SELECT key, problem, vec FROM problems"):
    v = array("f")
    v.frombytes(blob)
    keys.append(key)
    probs.append(json.loads(problem))
    vecs.append(v)
T = np.array(vecs, dtype=np.float32)
T /= np.linalg.norm(T, axis=1, keepdims=True)
val = [json.loads(l) for l in open(os.path.join(repo, "data", "val.jsonl"), encoding="utf-8") if l.strip()]
train_ids = {p["id"] for p in probs}
print(f"train en índice: {len(probs)}; val: {len(val)}; ids de val que también están en train: {sum(1 for r in val if r['id'] in train_ids)}")

cache = os.path.join(os.path.dirname(os.path.abspath(__file__)), "resultados", "val_bge-m3.npy")
if os.path.exists(cache):
    V = np.load(cache)
else:
    V = []
    for i in range(0, len(val), 16):
        V += embed([format_problem(r) for r in val[i:i + 16]], query=True)
    V = np.array(V, dtype=np.float32)
    np.save(cache, V)
V /= np.linalg.norm(V, axis=1, keepdims=True)


def opciones_norm(o):
    if not o or len(o) != 5:
        return None
    vals = []
    for k in "ABCDE":
        v = parse_value(o.get(k, ""))
        vals.append(round(v, 6) if v is not None else str(o.get(k, "")).strip().lower())
    return tuple(vals)


S = V @ T.T  # 789 × N
best = S.argmax(axis=1)
filas = []
for i, r in enumerate(val):
    j = int(best[i])
    n = probs[j]
    mismas_opts = opciones_norm(r.get("options")) is not None and opciones_norm(r.get("options")) == opciones_norm(n.get("options"))
    filas.append({"id": r["id"], "language": r["language"], "sim": float(S[i, j]), "vecino": n["id"], "vecino_lang": n["language"],
                  "mismo_id": n["id"] == r["id"], "mismas_opciones": mismas_opts, "label": r["label"], "label_vecino": n["label"],
                  "acierta": n["label"] == r["label"], "text_only": r["text_only"]})
with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "resultados", "duplicados_val.jsonl"), "w", encoding="utf-8") as f:
    for d in filas:
        f.write(json.dumps(d, ensure_ascii=False) + "\n")

print("\numbral de parecido → cuántos de val lo superan y qué % acierta copiando la etiqueta del vecino:")
for th in (0.98, 0.95, 0.92, 0.90, 0.88, 0.85, 0.80, 0.75, 0.70):
    sel = [d for d in filas if d["sim"] >= th]
    if sel:
        print(f"  sim ≥ {th:.2f}: {len(sel):3d} ({100 * len(sel) / len(val):4.1f} %)  acierto {100 * sum(d['acierta'] for d in sel) / len(sel):5.1f} %"
              f"   con mismas opciones: {sum(d['mismas_opciones'] for d in sel):3d}, acierto {100 * sum(d['acierta'] for d in sel if d['mismas_opciones']) / max(1, sum(d['mismas_opciones'] for d in sel)):5.1f} %")
mo = [d for d in filas if d["mismas_opciones"]]
print(f"\nmismas 5 opciones que el vecino (cualquier parecido): {len(mo)}, acierto {100 * sum(d['acierta'] for d in mo) / max(1, len(mo)):.1f} %")
print("azar de referencia: 20 %")
print("\nlos 12 más parecidos:")
for d in sorted(filas, key=lambda d: -d["sim"])[:12]:
    print(f"  {d['sim']:.3f} {d['id']}/{d['language']} ↔ {d['vecino']}/{d['vecino_lang']}  mismas_opts={d['mismas_opciones']} acierta={d['acierta']}")
print("\nvecinos por nivel (val → train):", Counter((d["id"].split("_")[0], d["vecino"].split("_")[0]) for d in filas if d["sim"] >= 0.9).most_common(8))
