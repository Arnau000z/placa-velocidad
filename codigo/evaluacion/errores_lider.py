"""Mapa de errores del modelo líder en la simulación de placa (demo + val texto eng+cat), sin modelos: por vía y por tipo.
python -X utf8 errores_lider.py <log_demo.jsonl> <log_val.jsonl> <salida_fallos.jsonl>"""
import collections
import json
import sys

sys.path.insert(0, r"D:\Datathon_A\entrega")
import predict  # noqa: E402

DATOS = {"demo": r"D:\Datathon_A\demo\train.jsonl", "val": r"D:\Datathon_A\demo\val_ec_texto.jsonl"}
fallos = []
for nombre, log in zip(("demo", "val"), sys.argv[1:3]):
    prs = {(r["id"], r["language"]): r for r in map(json.loads, open(DATOS[nombre], encoding="utf-8"))}
    cuenta = collections.Counter()
    for t in map(json.loads, open(log, encoding="utf-8")):
        pr = prs[(t["id"], t["language"])]
        ok = t["respuesta"] == pr["label"]
        progs, sals = t.get("programas") or [], t.get("salidas") or []
        if not pr["text_only"]:
            tipo = "figura"
        elif t["via"] == "duplicado":
            tipo = "duplicado"
        elif t["via"].startswith("python"):
            tipo = "programa casa y acierta" if ok else "programa casa con OTRA opción"
        elif not progs:
            tipo = "sin programa (sin tiempo)"
        else:
            ultimas = [s.strip().splitlines()[-1].strip() if s.strip() else "" for s in sals]
            if any("Traceback" in s or "Error" in s for s in sals):
                tipo = "programa con error"
            elif all(not u for u in ultimas):
                tipo = "programa sin salida (cortado o sin print)"
            elif any(predict.parse_value(u) is not None for u in ultimas):
                tipo = "programa da un número que no es ninguna opción"
            else:
                tipo = "programa da texto que no casa"
        cuenta[(tipo, ok)] += 1
        if not ok and pr["text_only"]:
            fallos.append({"conjunto": nombre, "tipo": tipo, "id": t["id"], "language": t["language"], "level": pr.get("level"),
                           "text": pr["text"], "options": pr["options"], "label": pr["label"], "via": t["via"],
                           "respuesta": t["respuesta"], "programas": progs, "salidas": sals, "segundos": t.get("segundos")})
    print(f"\n== {nombre}")
    for tipo in sorted({k[0] for k in cuenta}):
        print(f"  {tipo:48s} aciertos {cuenta[(tipo, True)]:3d}  fallos {cuenta[(tipo, False)]:3d}")
with open(sys.argv[3], "w", encoding="utf-8", newline="\n") as f:
    for x in fallos:
        f.write(json.dumps(x, ensure_ascii=False) + "\n")
print(f"\n{len(fallos)} fallos de texto guardados en {sys.argv[3]}")
c = collections.Counter(x["level"] for x in fallos)
print("fallos de texto por nivel:", dict(sorted(c.items())))
