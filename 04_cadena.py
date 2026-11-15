#!/usr/bin/env python3
"""La cadena entera en la placa: llama-server con el modelo de la entrega + el predict.py del equipo sobre N problemas,
con el límite de tiempo de verdad. Da aciertos, segundos por problema, cuántos se pasan de 60 s y por qué vía sale cada letra.

python3 04_cadena.py [--n 15] [--modelo X.gguf] [--problemas ruta.jsonl] [--predict ruta/predict.py]
"""
import argparse
import csv
import json
import os
import statistics
import subprocess
import sys
import time
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib_servidor as L  # noqa: E402

p = argparse.ArgumentParser()
p.add_argument("--n", type=int, default=15)
p.add_argument("--modelo", default=L.PRINCIPAL)
p.add_argument("--problemas", default=os.path.join(L.DATOS, "val.jsonl"))
p.add_argument("--predict", default=os.environ.get("PREDICT") or os.path.join(L.REPO, "equipo", "predict.py"))
p.add_argument("--extra", nargs=argparse.REMAINDER, default=[], help="opciones que se pasan tal cual a predict.py")
args = p.parse_args()

if not os.path.exists(args.predict):
    sys.exit(f"  FALTA {args.predict} (cópialo o di dónde está con --predict)")
modelo = L.ruta_modelo(args.modelo)
if not os.path.exists(modelo):
    sys.exit(f"  FALTA {modelo}")
base = os.path.basename(modelo).removesuffix(".gguf")

problemas, origen = L.cargar_problemas(args.problemas, args.n)
entrada = os.path.join(L.RES, "cadena_problemas.jsonl")
with open(entrada, "w", encoding="utf-8") as f:
    for pr in problemas:
        f.write(json.dumps(pr, ensure_ascii=False) + "\n")
salida = os.path.join(L.RES, "cadena_respuestas.csv")
log = os.path.join(L.RES, "cadena_predict.log")

print(f"==> {base} + {args.predict} sobre {len(problemas)} problemas ({origen})")
with L.Servidor(modelo, os.path.join(L.RES, f"cadena_servidor_{base}.log")) as s:
    print(f"  servidor listo en {s.carga_s:.0f} s · ocupa {s.rss_mb} MB · quedan {s.mem_libre_mb} MB libres")
    cmd = [sys.executable, args.predict, "--input", entrada, "--output", salida, "--url", s.url,
           "--train", os.path.join(L.DATOS, "train.jsonl")] + args.extra
    t0 = time.time()
    with open(log, "w", encoding="utf-8") as lg:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace")
        for linea in proc.stdout:
            print("  " + linea.rstrip(), flush=True)
            lg.write(linea)
        proc.wait()
    total = time.time() - t0
    mem_fin = L.mem_libre_mb()

etiquetas = {pr.get("id"): pr.get("label") for pr in problemas}
filas = list(csv.DictReader(open(salida, encoding="utf-8"))) if os.path.exists(salida) else []
segs = [float(r["seconds"]) for r in filas if r.get("seconds")]
con_etiqueta = [r for r in filas if etiquetas.get(r["id"])]
aciertos = sum(r["answer"] == etiquetas[r["id"]] for r in con_etiqueta)
vias = Counter(r.get("status", "?").split(":")[0] for r in filas)
res = {
    "modelo": base, "predict": args.predict, "problemas": len(problemas), "origen": origen, "respondidos": len(filas),
    "aciertos": aciertos, "con_etiqueta": len(con_etiqueta),
    "seg_media": statistics.mean(segs) if segs else None, "seg_mediana": statistics.median(segs) if segs else None,
    "seg_max": max(segs) if segs else None, "pasados_60s": sum(x > 60 for x in segs), "total_s": total,
    "vias": dict(vias), "rss_mb": s.rss_mb, "mem_libre_mb_fin": mem_fin, "codigo_salida": proc.returncode,
}
json.dump(res, open(os.path.join(L.RES, "cadena.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(f"  ==> {aciertos}/{len(con_etiqueta)} aciertos · media {res['seg_media'] or 0:.1f} s, máx {res['seg_max'] or 0:.1f} s, "
      f"{res['pasados_60s']} pasados de 60 s · vías {dict(vias)} · {total / 60:.1f} min en total")
