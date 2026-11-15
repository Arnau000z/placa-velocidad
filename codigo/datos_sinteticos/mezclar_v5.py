"""v5 = v4b (otra sesión, ya sin constantes) + problemas dirigidos 2 (gen_dir2_*, lecciones de los fallos de sopa_z10)
verificados aquí: el programa se ejecuta e imprime la opción marcada, opciones distintas, programa corto (≤ 8 líneas),
sin print(constante) ni «x = 48 / print(x)», y sin repetir enunciados de v4b.
python -X utf8 mezclar_v5.py   → nube/datos/sft_codigo_v5.jsonl (+ _val con el val de v4b)"""
import concurrent.futures
import glob
import hashlib
import json
import os
import re
import sys
import types

HERE = os.path.dirname(os.path.abspath(__file__))
src = open(os.path.join(HERE, "verificar_sintetico.py"), encoding="utf-8").read()
mod = types.ModuleType("verificar_sintetico")
mod.__file__ = os.path.join(HERE, "verificar_sintetico.py")
exec(compile(src[:src.index("buenos, vistos = [], set()")], "verificar_sintetico.py", "exec"), mod.__dict__)
LETTERS, match_option, run, limpiar_codigo, formato, SYSTEM = (mod.LETTERS, mod.match_option, mod.run, mod.limpiar_codigo, mod.formato,
                                                              mod.SYSTEM)
DATOS = r"D:\Datathon_A\nube\datos"
CONST = re.compile(r"print\(\s*(-?\d+(\.\d+)?|\"[^\"]*\"|'[^']*')\s*\)")


def es_constante(code):
    lineas = [x.strip() for x in code.splitlines() if x.strip()]
    if not lineas:
        return True
    if CONST.fullmatch(lineas[-1]):
        return True
    m = re.fullmatch(r"print\(\s*(\w+)\s*\)", lineas[-1])
    if m and len(lineas) == 2 and re.fullmatch(rf"{m.group(1)}\s*=\s*[-\d./\"' ]+", lineas[0]):
        return True
    return False


def huella(texto):
    return hashlib.sha1(re.sub(r"\W+", "", texto.lower()).encode()).hexdigest()


v4b = [json.loads(l) for l in open(os.path.join(DATOS, "sft_codigo_v4b.jsonl"), encoding="utf-8")]
vistos = {huella(r["messages"][1]["content"].split("\nA) ")[0]) for r in v4b}
filas = []
for p in sorted(glob.glob(os.path.join(HERE, "generado", "gen_dir2_*.jsonl"))):
    for l in open(p, encoding="utf-8"):
        try:
            r = json.loads(l)
        except json.JSONDecodeError:
            continue
        if isinstance(r, dict):
            filas.append(r)
cands = []
for r in filas:
    o = r.get("options") or {}
    if not isinstance(o, dict) or len(o) != 5 or r.get("label") not in LETTERS or not r.get("text") or not r.get("code"):
        continue
    o = {k: str(v).strip() for k, v in o.items()}
    if len(set(o.values())) < 5:
        continue
    code = limpiar_codigo(r["code"])
    if code.count("\n") > 7 or len(code) > 500 or es_constante(code):
        continue
    cands.append((r, o, code))
with concurrent.futures.ThreadPoolExecutor(12) as ex:
    salidas = list(ex.map(lambda c: run(c[2]), cands))
nuevas = []
for (r, o, code), (out, _) in zip(cands, salidas):
    letra, _ = (None, "") if not out.strip() else match_option(out, o)
    if letra != r["label"]:
        continue
    h = huella(r["text"].strip())
    if h in vistos:
        continue
    vistos.add(h)
    nuevas.append({"messages": [{"role": "system", "content": SYSTEM},
                                {"role": "user", "content": formato({"text": r["text"].strip(), "options": o})},
                                {"role": "assistant", "content": f"```python\n{code}\n```"}]})
with open(os.path.join(DATOS, "sft_codigo_v5.jsonl"), "w", encoding="utf-8", newline="\n") as f:
    for r in v4b + nuevas:
        f.write(json.dumps(r, ensure_ascii=False) + "\n")
with open(os.path.join(DATOS, "sft_codigo_v5_val.jsonl"), "w", encoding="utf-8", newline="\n") as f:
    f.write(open(os.path.join(DATOS, "sft_codigo_v4b_val.jsonl"), encoding="utf-8").read())
print(f"{len(filas)} generados, {len(cands)} candidatos, {len(nuevas)} nuevos verificados → v5 = {len(v4b) + len(nuevas)}")
