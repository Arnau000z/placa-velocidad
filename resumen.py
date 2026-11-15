#!/usr/bin/env python3
"""Resúmenes de las pruebas.

python3 resumen.py bench resultados/X/bench_modelo.csv   → una línea con lo que ha dado llama-bench
python3 resumen.py todo resultados/X                     → resultados/X/resumen.md con todo junto (y lo enseña)
"""
import csv
import glob
import json
import os
import re
import statistics
import sys

ENUNCIADO = 180   # tokens nuevos de un problema típico (el prompt de sistema va en caché)
LIMITE = 56       # segundos útiles por problema en predict.py (60 menos margen)
MARGEN = 4        # segundos que predict.py reserva para ejecutar el programa y casar la opción


def leer_bench(ruta):
    """{'modelo', 'mb', 'hilos', 'lee', 'lee_sd', 'escribe', 'escribe_sd'} de un CSV de llama-bench."""
    r = {"modelo": os.path.basename(ruta)[6:-4]}
    for fila in csv.DictReader(open(ruta, encoding="utf-8")):
        r["mb"] = int(fila.get("model_size") or 0) / 1e6
        r["hilos"] = fila.get("n_threads")
        if int(fila.get("n_gen") or 0) > 0:
            r["escribe"], r["escribe_sd"] = float(fila["avg_ts"]), float(fila["stddev_ts"])
        elif int(fila.get("n_prompt") or 0) > 0:
            r["lee"], r["lee_sd"] = float(fila["avg_ts"]), float(fila["stddev_ts"])
    return r


def cabe(lee, escribe):
    """Tokens de programa que caben en un problema con estas velocidades (la cuenta de predict.py)."""
    if not lee or not escribe:
        return None
    return max(0, (LIMITE - ENUNCIADO / lee - MARGEN) * escribe)


def linea_bench(r):
    c = cabe(r.get("lee"), r.get("escribe"))
    return (f"  {r['modelo']}: lee {r.get('lee', 0):.2f} ± {r.get('lee_sd', 0):.2f} t/s · escribe {r.get('escribe', 0):.2f} ± "
            f"{r.get('escribe_sd', 0):.2f} t/s · {r.get('mb', 0):.0f} MB · caben ~{c or 0:.0f} tokens de programa por problema")


def todo(res):
    md = []
    info = open(os.path.join(res, "info.txt"), encoding="utf-8", errors="replace").read() if os.path.exists(os.path.join(res, "info.txt")) else ""
    cpu = re.search(r"Model name:\s*(.+)", info)
    feats = re.search(r"(?im)^features\s*:\s*(.+)$", info)
    mem = re.search(r"(?m)^Mem:\s+(\d+)", info)
    md.append(f"# Velocidad en la placa · {os.path.basename(res)}\n")
    if cpu:
        md.append(f"- CPU: {cpu.group(1).strip()}")
    if feats:
        f = feats.group(1).split()
        md.append(f"- dotprod (asimddp): **{'sí' if 'asimddp' in f else 'no'}** · i8mm: **{'sí' if 'i8mm' in f else 'no'}**")
    if mem:
        md.append(f"- Memoria total: {mem.group(1)} MB")
    commit = re.search(r"## llama.cpp\n([0-9a-f]{40})", info)
    if commit:
        md.append(f"- llama.cpp: {commit.group(1)[:9]}")

    bench = [leer_bench(p) for p in sorted(glob.glob(os.path.join(res, "bench_*.csv"))) if os.path.getsize(p) > 0]
    if bench:
        md.append(f"\n## llama-bench (velocidad pura, {bench[0].get('hilos')} hilos)\n")
        md.append(f"| Modelo | MB | Lee t/s | Escribe t/s | Programa que cabe* |")
        md.append("|---|---:|---:|---:|---:|")
        for r in sorted(bench, key=lambda r: -(cabe(r.get("lee"), r.get("escribe")) or 0)):
            md.append(f"| {r['modelo']} | {r.get('mb', 0):.0f} | {r.get('lee', 0):.2f} ± {r.get('lee_sd', 0):.2f} | "
                      f"{r.get('escribe', 0):.2f} ± {r.get('escribe_sd', 0):.2f} | {cabe(r.get('lee'), r.get('escribe')) or 0:.0f} |")
        md.append(f"\n*Tokens de programa en {LIMITE} s con un enunciado de {ENUNCIADO} tokens y el sistema en caché, "
                  f"dejando {MARGEN} s para ejecutar y casar (la cuenta de predict.py, que corta en 220).")

    ruta = os.path.join(res, "servidor.jsonl")
    if os.path.exists(ruta):
        filas = [json.loads(l) for l in open(ruta, encoding="utf-8") if l.strip()]
        md.append("\n## Servidor en las condiciones de predict.py\n")
        md.append("| Modelo | Carga s | RAM MB | Libres MB | Lee frío t/s | Lee con caché t/s | Tokens nuevos | Escribe t/s |")
        md.append("|---|---:|---:|---:|---:|---:|---:|---:|")
        for m in dict.fromkeys(f["modelo"] for f in filas):
            fm = [f for f in filas if f["modelo"] == m]
            frio = [f for f in fm if f["frio"]]
            cal = [f for f in fm if not f["frio"]] or fm
            md.append(f"| {m} | {fm[0]['carga_s']:.0f} | {fm[0]['rss_mb']} | {fm[0]['mem_libre_mb']} | "
                      f"{(frio[0]['lee_tps'] or 0) if frio else 0:.2f} | {statistics.mean(f['lee_tps'] or 0 for f in cal):.2f} | "
                      f"{statistics.mean(f['leidos'] or 0 for f in cal):.0f} | {statistics.mean(f['escribe_tps'] or 0 for f in cal):.2f} |")
        si = next((f["system_info"] for f in filas if f.get("system_info")), "")
        if si:
            md.append(f"\n`{si[:300]}`")

    ruta = os.path.join(res, "cadena.json")
    if os.path.exists(ruta):
        c = json.load(open(ruta, encoding="utf-8"))
        md.append("\n## Cadena completa (predict.py en la placa)\n")
        md.append(f"- {c['modelo']} sobre {c['problemas']} problemas ({c['origen']})")
        md.append(f"- Aciertos: **{c['aciertos']}/{c['con_etiqueta']}**")
        md.append(f"- Segundos por problema: media {c['seg_media'] or 0:.1f}, mediana {c['seg_mediana'] or 0:.1f}, máximo {c['seg_max'] or 0:.1f}; "
                  f"**{c['pasados_60s']} pasados de 60 s**")
        md.append(f"- Vías: {c['vias']}")
        md.append(f"- Memoria libre al acabar: {c['mem_libre_mb_fin']} MB · {c['total_s'] / 60:.1f} min en total")

    ruta = os.path.join(res, "temperatura.csv")
    if os.path.exists(ruta):
        filas = list(csv.DictReader(open(ruta, encoding="utf-8")))
        carga = [f for f in filas if float(f["carga_1min"] or 0) >= 2]
        if filas:
            tmax = max(int(f["temp_max_c"]) for f in filas)
            md.append("\n## Calor\n")
            md.append(f"- Temperatura máxima: **{tmax} °C** ({len(filas)} lecturas, {len(filas) * 5 / 60:.0f} min)")
            if carga:
                mhz = [int(f["mhz_cpu0"]) for f in carga]
                frenada = min(mhz) < 0.9 * max(mhz)
                md.append(f"- CPU0 con carga: {min(mhz)}-{max(mhz)} MHz → {'**se frena por calor**' if frenada else 'no se frena'}")
            md.append(f"- Memoria libre mínima: {min(int(f['mem_libre_mb'] or 0) for f in filas)} MB")

    texto = "\n".join(md) + "\n"
    open(os.path.join(res, "resumen.md"), "w", encoding="utf-8").write(texto)
    print(texto)


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "bench":
        print(linea_bench(leer_bench(sys.argv[2])))
    elif len(sys.argv) == 3 and sys.argv[1] == "todo":
        todo(sys.argv[2])
    else:
        sys.exit(__doc__)
