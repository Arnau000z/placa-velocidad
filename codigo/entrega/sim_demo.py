"""Simula la placa desde la torre: ejecuta predict.py sobre la demo con la velocidad medida y cuenta aciertos por vía.
python -X utf8 sim_demo.py <url> <nombre> [--reserva descarte|letra] [--tps 4.6,2.7] [--extra "ENV=valor"]"""
import argparse
import collections
import csv
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
p = argparse.ArgumentParser()
p.add_argument("url")
p.add_argument("nombre")
p.add_argument("--reserva", default="descarte")
p.add_argument("--tps", default="4.6,2.7")
p.add_argument("--demo", default=r"D:\Datathon_A\demo\train.jsonl")
args = p.parse_args()
out = os.path.join(HERE, f"sim_{args.nombre}_{args.reserva}.csv")
for f in (out, out + ".log.jsonl"):
    if os.path.exists(f):
        os.remove(f)
subprocess.run([sys.executable, "-X", "utf8", os.path.join(HERE, "predict.py"), "--input", args.demo, "--output", out, "--url", args.url,
                "--train", r"D:\Datathon_A\datathon-UPC-maths-qualcomm-arduino-unoq\data\train.jsonl", "--tps-forzado", args.tps,
                "--reserva", args.reserva], stderr=subprocess.DEVNULL, check=False)
lab = {(r["id"], r["language"]): r for r in (json.loads(l) for l in open(args.demo, encoding="utf-8"))}
rows = list(csv.DictReader(open(out, encoding="utf-8")))
ok = [lab[(r["id"], r["language"])]["label"] == r["answer"] for r in rows]
seg = [float(r["seconds"]) for r in rows]
tx = [o for o, r in zip(ok, rows) if lab[(r["id"], r["language"])]["text_only"]]
fg = [o for o, r in zip(ok, rows) if not lab[(r["id"], r["language"])]["text_only"]]
vias = collections.Counter(r["status"] for r in rows)
detalle = {v: f"{sum(1 for o, r in zip(ok, rows) if r['status'] == v and o)}/{c}" for v, c in vias.items()}
print(f"{args.nombre} reserva={args.reserva} tps={args.tps}: TOTAL {sum(ok)}/{len(rows)}  texto {sum(tx)}/{len(tx)}  figura {sum(fg)}/{len(fg)}"
      f"  seg media {sum(seg) / len(seg):.0f} máx {max(seg):.0f} (>56 s: {sum(1 for s in seg if s > 56)})  vías {detalle}")
