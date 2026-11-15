"""Puntúa todas las simulaciones con las MISMAS reglas (las de predict.py de ahora), para comparar modelos aunque se
simularan con versiones distintas: vía letra → E, sin duplicados (no salen en el examen final).
python -X utf8 puntuar.py   → tabla demo / val / suma por modelo, ordenada."""
import glob
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
DATOS = {"demo": r"D:\Datathon_A\demo\train.jsonl", "val": r"D:\Datathon_A\demo\val_ec_texto.jsonl"}
lab = {k: {(r["id"], r["language"]): r["label"] for r in map(json.loads, open(p, encoding="utf-8"))} for k, p in DATOS.items()}


def puntos(log, conjunto):
    ok = n = 0
    for t in map(json.loads, open(log, encoding="utf-8")):
        if t["via"] == "duplicado":
            continue
        n += 1
        resp = "E" if t["via"] in ("letra", "letra_figura") else t["respuesta"]
        ok += resp == lab[conjunto][(t["id"], t["language"])]
    return ok, n


tabla = {}
for log in glob.glob(os.path.join(HERE, "sim_*_mediana.csv.log.jsonl")):
    nombre = os.path.basename(log)[4:-len("_mediana.csv.log.jsonl")]
    conjunto = "val" if nombre.startswith("val_") else "demo"
    nombre = nombre[4:] if conjunto == "val" else nombre
    try:
        tabla.setdefault(nombre, {})[conjunto] = puntos(log, conjunto)
    except (KeyError, json.JSONDecodeError):
        continue
filas = [(n, d.get("demo"), d.get("val")) for n, d in tabla.items() if d.get("demo") and d.get("val") and d["demo"][1] == 100]
filas.sort(key=lambda f: -(f[1][0] + f[2][0]))
print(f"{'modelo':28s} {'demo':>8s} {'val':>9s} {'suma':>5s}")
for n, d, v in filas:
    print(f"{n:28s} {d[0]:>4d}/{d[1]:<3d} {v[0]:>4d}/{v[1]:<3d} {d[0] + v[0]:>5d}")
