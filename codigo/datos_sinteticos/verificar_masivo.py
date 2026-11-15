"""Verifica la generación masiva (generado_masivo/) en dos filtros y deja el dataset listo para entrenar.

  1. Ejecución: el programa del generador imprime la opción marcada (no la letra), con el preludio de la placa.
  2. A ciegas (--ciegas): OTRO modelo abierto resuelve el problema como el alumno (programa corto, sin ver la letra);
     solo quedan los problemas en los que su programa también imprime la opción marcada. Cuando los dos programas
     aciertan, se entrena con el más corto.

Quita repetidos entre sí y frente a sintetico/limpio.jsonl. Escribe:
  sintetico/limpio_masivo.jsonl                (problemas que pasan, con foco, generador y si pasaron a ciegas)
  nube/datos/sft_masivo.jsonl (+ _val, 3 %)    (formato exacto de la placa)
  nube/datos/sft_codigo_v4.jsonl (+ _val)      (sft_codigo_v3 + sft_masivo sin duplicados), con --v4

python -X utf8 verificar_masivo.py [--ciegas] [--v4]
"""
import argparse
import ast
import concurrent.futures as cf
import glob
import hashlib
import json
import os
import random
import re
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
DATOS = r"D:\Datathon_A\nube\datos"
sys.path.insert(0, r"D:\Datathon_A\experimentos")
from util_opciones import LETTERS, match_option  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--ciegas", action="store_true")
ap.add_argument("--v4", action="store_true")
ap.add_argument("--paralelo-api", type=int, default=5)
ap.add_argument("--sufijo", default="", help="sufijo de salida (p. ej. b → sft_masivo_b, sft_codigo_v4b) para no pisar la v4 entregada")
ap.add_argument("--solo-cache", action="store_true", help="a ciegas solo con lo ya resuelto, sin peticiones nuevas")
args = ap.parse_args()
SUF = f"_{args.sufijo}" if args.sufijo else ""

def calcula(code):
    """Un programa que entrena: no imprime una constante pura (print(48), o x = 48 y print(x) sin ninguna operación).
    Los de una línea que sí calculan, como print(36 // 3 - 36 // 4), valen: en la placa lo corto es oro."""
    lineas = [ln for ln in str(code).splitlines() if ln.strip()]
    if not lineas:
        return False
    literal = re.compile(r"""^\s*print\(\s*(-?\d+(\.\d+)?|"[^"]*"|'[^']*')\s*\)\s*$""")
    resto = " ".join(ln for ln in lineas if not literal.match(ln)).replace("print(", "(")
    return bool(re.search(r"[-+*/%<>]|\bfor\b|\bwhile\b|\bif\b|\w\(|\[", resto))


# SYSTEM y PRELUDIO idénticos a los del entrenamiento (sin importar verificar_sintetico.py, que se ejecuta al importarlo)
_arbol = ast.parse(open(os.path.join(HERE, "verificar_sintetico.py"), encoding="utf-8").read())
_c = {n.targets[0].id: ast.literal_eval(n.value) for n in _arbol.body
      if isinstance(n, ast.Assign) and isinstance(n.targets[0], ast.Name) and n.targets[0].id in ("SYSTEM", "PRELUDIO")}
SYSTEM, PRELUDIO = _c["SYSTEM"], _c["PRELUDIO"]


def formato(pr):
    return "\n".join([pr["text"].strip()] + [f"{k}) {pr['options'][k]}" for k in LETTERS])


def limpiar_codigo(code):
    code = re.sub(r"^```(?:python)?\s*|\s*```$", "", str(code).strip(), flags=re.M).strip()
    lines = [re.sub(r"(?<!['\"])\s+#.*$", "", ln) for ln in code.splitlines() if not ln.strip().startswith("#")]
    return "\n".join(ln for ln in lines if ln.strip())


def run(code):
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8") as f:
        f.write(PRELUDIO + code)
        p = f.name
    try:
        r = subprocess.run([sys.executable, "-I", "-S", p], capture_output=True, text=True, timeout=3, encoding="utf-8", errors="replace")
        return r.stdout
    except subprocess.TimeoutExpired:
        return ""
    finally:
        os.unlink(p)


def letra_de(code, opts):
    out = run(code)
    if not out.strip():
        return None
    ultima = out.strip().splitlines()[-1].strip()
    if len(ultima) == 1 and ultima.upper() in LETTERS:  # imprimir la letra no vale
        return None
    return match_option(out, opts)[0]


def huella(t):
    return hashlib.sha1(re.sub(r"\W+", "", t.lower()).encode()).hexdigest()


# --- 1. ejecución -----------------------------------------------------------------------------------------------
vistos = set()
if os.path.exists(os.path.join(HERE, "limpio.jsonl")):
    for l in open(os.path.join(HERE, "limpio.jsonl"), encoding="utf-8"):
        if l.strip():
            vistos.add(huella(json.loads(l)["text"]))
previos = len(vistos)
stats = Counter()
cand = []
for p in sorted(glob.glob(os.path.join(HERE, "generado_masivo", "*.jsonl"))):
    for l in open(p, encoding="utf-8"):
        if not l.strip():
            continue
        try:
            r = json.loads(l)
        except json.JSONDecodeError:
            stats["json_malo"] += 1
            continue
        stats["leidos"] += 1
        o = r.get("options") or {}
        if not isinstance(o, dict) or sorted(o) != list(LETTERS) or r.get("label") not in LETTERS or not r.get("text") or not r.get("code"):
            stats["incompleto"] += 1
            continue
        o = {k: str(v).strip() for k, v in o.items()}
        if len(set(o.values())) < 5:
            stats["opciones_repetidas"] += 1
            continue
        h = huella(r["text"])
        if h in vistos:
            stats["repetido"] += 1
            continue
        vistos.add(h)
        code = limpiar_codigo(r["code"])
        if code.count("\n") > 11 or len(code) > 600 or "print(" not in code:
            stats["codigo_largo_o_sin_print"] += 1
            continue
        if not calcula(code):
            stats["constante"] += 1
            continue
        r.update(options=o, code=code)
        cand.append(r)

with cf.ThreadPoolExecutor(12) as ex:
    letras = list(ex.map(lambda r: letra_de(r["code"], r["options"]), cand))
buenos = []
for r, le in zip(cand, letras):
    if le != r["label"]:
        stats["no_casa"] += 1
        continue
    stats["ok_ejecucion"] += 1
    buenos.append(r)
print(f"1) ejecución: {dict(stats)} (repetidos frente a limpio.jsonl: {previos} ya vistos)", flush=True)

# --- 2. a ciegas ------------------------------------------------------------------------------------------------
if args.ciegas:
    KEY = open(r"D:\Datathon_A\.helmcode_key", encoding="utf-8").read().strip()
    URL = "https://api.helmcode.com/v1/chat/completions"
    RESOLVER = {"qwen3.6": "gemma4", "gemma4": "qwen3.6", "glm5.3-flash": "qwen3.6", "deepseek-v4-flash": "gemma4"}
    PROMPT = (SYSTEM + "\n\nYou will get several problems, numbered. Answer with ONLY a JSON array with one string per problem, in the "
              "same order, each string being the Python program (no ``` fences).")

    def resolver(lote):
        modelo = lote[0][0]
        user = "\n\n".join(f"Problem {i + 1}:\n{formato(r)}" for i, (_, r) in enumerate(lote))
        payload = {"model": modelo, "messages": [{"role": "system", "content": PROMPT}, {"role": "user", "content": user}],
                   "max_tokens": 4000, "temperature": 0.0, "reasoning_effort": "none"}
        for intento in range(6):
            try:
                req = urllib.request.Request(URL, json.dumps(payload).encode(),
                                             {"Content-Type": "application/json", "Authorization": f"Bearer {KEY}"})
                with urllib.request.urlopen(req, timeout=300) as rr:
                    text = json.load(rr)["choices"][0]["message"]["content"]
                codes = []
                m = re.search(r"\[.*\]", text, re.S)
                if m:
                    try:
                        codes = json.loads(m.group(0))
                    except json.JSONDecodeError:
                        codes = []
                if len(codes) != len(lote):  # qwen3.6 a veces contesta con un bloque ```python por problema
                    codes = re.findall(r"```(?:python)?\s*\n(.*?)```", text, re.S)
                return [str(c) for c in codes] if len(codes) == len(lote) else [None] * len(lote)
            except urllib.error.HTTPError as exc:
                if exc.code in (401, 402, 403):
                    return [None] * len(lote)
                time.sleep(min(90, 8 * 2 ** intento) + random.random() * 5)
            except Exception:  # noqa: BLE001
                time.sleep(5 * (intento + 1))
        return [None] * len(lote)

    # caché de lo ya resuelto a ciegas (para no repetir peticiones al volver a pasar el verificador)
    CACHE = os.path.join(HERE, "ciegas_cache.jsonl")
    cache = {}
    if os.path.exists(CACHE):
        for l in open(CACHE, encoding="utf-8"):
            if l.strip():
                d = json.loads(l)
                cache[d["h"]] = d["code"]
    elif os.path.exists(os.path.join(HERE, "limpio_masivo.jsonl")):
        for l in open(os.path.join(HERE, "limpio_masivo.jsonl"), encoding="utf-8"):
            if l.strip():
                d = json.loads(l)
                if d.get("ciegas"):
                    cache[huella(d["text"])] = d["code"]
        with open(CACHE, "w", encoding="utf-8") as f:
            for h, c in cache.items():
                f.write(json.dumps({"h": h, "code": c}, ensure_ascii=False) + "\n")
    pendientes = [r for r in buenos if huella(r["text"]) not in cache]
    print(f"   a ciegas: {len(buenos) - len(pendientes)} ya resueltos (caché), {len(pendientes)} nuevos", flush=True)
    por_modelo = {}
    for i, r in enumerate(pendientes):
        g = r.get("generador")
        m = RESOLVER.get(g, "qwen3.6") if g in ("qwen3.6", "gemma4") else ("gemma4" if i % 2 else "qwen3.6")
        por_modelo.setdefault(m, []).append(r)
    lotes = [] if args.solo_cache else [[(m, r) for r in rs[i:i + 8]] for m, rs in por_modelo.items() for i in range(0, len(rs), 8)]
    random.Random(0).shuffle(lotes)
    t0 = time.time()
    with cf.ThreadPoolExecutor(max(1, args.paralelo_api * len(por_modelo))) as ex:
        futs = {ex.submit(resolver, lote): lote for lote in lotes}
        for k, fut in enumerate(cf.as_completed(futs), 1):
            with open(CACHE, "a", encoding="utf-8") as fc:
                for (_, r), c in zip(futs[fut], fut.result()):
                    if c:
                        cache[huella(r["text"])] = c
                        fc.write(json.dumps({"h": huella(r["text"]), "code": c}, ensure_ascii=False) + "\n")
            if k % 50 == 0:
                print(f"   a ciegas: {k}/{len(lotes)} lotes, {time.time() - t0:.0f} s", flush=True)
    st2 = Counter()

    def comprobar(r):
        c = cache.get(huella(r["text"]))
        if not c:
            return r, None, None
        c = limpiar_codigo(c)
        return r, c, letra_de(c, r["options"]) if c and "print(" in c else None

    dobles = []
    with cf.ThreadPoolExecutor(12) as ex:
        for r, c, le in ex.map(comprobar, buenos):
            if c is None:
                st2["sin_respuesta"] += 1
                continue
            if le == r["label"]:
                st2["coincide"] += 1
                r["ciegas"] = True
                if calcula(c) and len(c) < len(r["code"]) and c.count("\n") <= 11:
                    r["code"] = c
                if not calcula(r["code"]):
                    st2["coincide_pero_constante"] += 1
                    continue
                dobles.append(r)
            else:
                st2["no_coincide"] += 1
    print(f"2) a ciegas: {dict(st2)}", flush=True)
    finales = dobles
else:
    finales = buenos

# --- salida -----------------------------------------------------------------------------------------------------
with open(os.path.join(HERE, f"limpio_masivo{SUF}.jsonl"), "w", encoding="utf-8", newline="\n") as f:
    for i, r in enumerate(finales):
        r["id"] = f"mas_{i:05d}"
        f.write(json.dumps({k: r.get(k) for k in ("id", "language", "level", "type", "foco", "generador", "ciegas", "text", "options", "label", "code")},
                           ensure_ascii=False) + "\n")
tr = va = 0
with open(os.path.join(DATOS, f"sft_masivo{SUF}.jsonl"), "w", encoding="utf-8", newline="\n") as ft, \
        open(os.path.join(DATOS, f"sft_masivo{SUF}_val.jsonl"), "w", encoding="utf-8", newline="\n") as fv:
    for r in finales:
        row = {"messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": formato(r)},
                            {"role": "assistant", "content": f"```python\n{r['code']}\n```"}]}
        if int(hashlib.sha256(r["id"].encode()).hexdigest(), 16) % 100 < 3:
            fv.write(json.dumps(row, ensure_ascii=False) + "\n")
            va += 1
        else:
            ft.write(json.dumps(row, ensure_ascii=False) + "\n")
            tr += 1
print(f"sft_masivo: {tr} train, {va} val · por foco {dict(Counter(r.get('foco') for r in finales))} · "
      f"por idioma {dict(Counter(r.get('language') for r in finales))} · por generador {dict(Counter(r.get('generador') for r in finales))} · "
      f"letras {dict(sorted(Counter(r['label'] for r in finales).items()))}")

if args.v4:
    filas, hs = [], set()
    constantes = Counter()
    for nombre in ("sft_codigo_v3.jsonl", f"sft_masivo{SUF}.jsonl"):
        for l in open(os.path.join(DATOS, nombre), encoding="utf-8"):
            if not l.strip():
                continue
            msgs = json.loads(l)["messages"]
            if not calcula(limpiar_codigo(msgs[2]["content"])):  # fuera los que imprimen una constante, también en v3
                constantes[nombre] += 1
                continue
            h = hashlib.sha1(msgs[1]["content"].encode()).hexdigest()
            if h not in hs:
                hs.add(h)
                filas.append(l.rstrip("\n"))
    print(f"constantes quitadas: {dict(constantes)}")
    with open(os.path.join(DATOS, f"sft_codigo_v4{args.sufijo}.jsonl"), "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(filas) + "\n")
    vs = []
    for nombre in ("sft_codigo_v3_val.jsonl", f"sft_masivo{SUF}_val.jsonl"):
        vs += [l.rstrip("\n") for l in open(os.path.join(DATOS, nombre), encoding="utf-8")
               if l.strip() and calcula(limpiar_codigo(json.loads(l)["messages"][2]["content"]))]
    with open(os.path.join(DATOS, f"sft_codigo_v4{args.sufijo}_val.jsonl"), "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(vs) + "\n")
    print(f"sft_codigo_v4{args.sufijo}: {len(filas)} train, {len(vs)} val")
