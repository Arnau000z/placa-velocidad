"""Mezcla los datasets de código en el formato exacto de la placa (SYSTEM_CODE corto → ```python ... ```):
sintético verificado (generado por un LLM), autodestilado (programas correctos del propio 1.7B) y los programas verificados de M3Kang
(cortos y sin comentarios). Escribe nube/datos/sft_codigo_total.jsonl (+ _val, 3 % por id).

python -X utf8 mezclar_sft.py"""
import hashlib
import json
import os
import re
import sys

sys.path.insert(0, r"D:\Datathon_A\sintetico")
from verificar_sintetico import SYSTEM, formato, limpiar_codigo  # noqa: E402

DATOS = r"D:\Datathon_A\nube\datos"
repo = r"D:\Datathon_A\datathon-UPC-maths-qualcomm-arduino-unoq"
filas, fuentes = [], {}


def add(fuente, pid, user, code):
    code = limpiar_codigo(code)
    if not code or code.count("\n") > 14 or len(code) > 700 or "print(" not in code:
        return
    filas.append((pid, {"messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user},
                                     {"role": "assistant", "content": f"```python\n{code}\n```"}]}))
    fuentes[fuente] = fuentes.get(fuente, 0) + 1


# 1) sintético verificado
for l in open(r"D:\Datathon_A\sintetico\limpio.jsonl", encoding="utf-8"):
    r = json.loads(l)
    add("sintetico", r["id"], formato(r), r["code"])
# 2) autodestilado (ya en formato messages; el system es el mismo texto)
for nombre in ("sft_autodestilado3.jsonl", "sft_autodestilado2.jsonl", "sft_autodestilado.jsonl", "sft_profesor.jsonl", "sft_publicos_star.jsonl"):
    p = os.path.join(DATOS, nombre)
    if os.path.exists(p):
        for l in open(p, encoding="utf-8"):
            m = json.loads(l)["messages"]
            code = re.sub(r"^```(?:python)?\s*|\s*```$", "", m[2]["content"].strip(), flags=re.M)
            add("autodestilado", hashlib.sha1(m[1]["content"].encode()).hexdigest(), m[1]["content"], code)
# 3) programas verificados de M3Kang (ok), en los tres idiomas del problema
train = {}
for l in open(os.path.join(repo, "data", "train.jsonl"), encoding="utf-8"):
    r = json.loads(l)
    train.setdefault(r["id"], []).append(r)
for l in open(r"D:\Datathon_A\experimentos\codigo\verificado.jsonl", encoding="utf-8"):
    c = json.loads(l)
    if c["status"] != "ok":
        continue
    for r in train.get(c["id"], []):
        if len(r.get("options") or {}) == 5 and r["text_only"]:
            add("m3kang", f"{c['id']}|{r['language']}", formato({"text": r["text"], "options": r["options"]}), c["code"])

vistos = set()
tr = va = 0
SAL = sys.argv[1] if len(sys.argv) > 1 else "sft_codigo_total"
with open(os.path.join(DATOS, f"{SAL}.jsonl"), "w", encoding="utf-8", newline="\n") as ft, \
        open(os.path.join(DATOS, f"{SAL}_val.jsonl"), "w", encoding="utf-8", newline="\n") as fv:
    for pid, row in filas:
        h = hashlib.sha1(row["messages"][1]["content"].encode()).hexdigest()
        if h in vistos:
            continue
        vistos.add(h)
        if int(hashlib.sha256(str(pid).encode()).hexdigest(), 16) % 100 < 3:
            fv.write(json.dumps(row, ensure_ascii=False) + "\n")
            va += 1
        else:
            ft.write(json.dumps(row, ensure_ascii=False) + "\n")
            tr += 1
print(f"{SAL}: {tr} train, {va} val; fuentes: {fuentes}")
