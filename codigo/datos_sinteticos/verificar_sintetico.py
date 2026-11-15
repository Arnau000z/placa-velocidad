"""Verifica los problemas sintéticos generados por un LLM: ejecuta el programa, comprueba que imprime la opción marcada,
quita duplicados y deja un JSONL limpio + el dataset SFT (programa corto) para afinar el 1.7B.

python -X utf8 verificar_sintetico.py  → sintetico/limpio.jsonl, nube/datos/sft_sintetico.jsonl (+ _val)
"""
import glob
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, r"D:\Datathon_A\experimentos")
from util_opciones import LETTERS, match_option, parse_value  # noqa: E402

PRELUDIO = "from fractions import Fraction\nfrom math import *\nfrom itertools import *\nfrom collections import Counter\n"
SYSTEM = """You solve Kangaroo math competition problems by writing a short Python 3 program.
Rules:
- Translate the statement into code faithfully: put the given numbers in variables, then compute. When the problem asks to count, to find a maximum/minimum, or which value satisfies conditions, try all the cases with loops instead of reasoning by hand.
- At most 8 short lines. No comments, no explanations, no functions unless really needed. Standard library only, no input(), must finish in under 2 seconds (never brute-force more than a million cases).
- The last line must be print(answer): the numeric value, or the exact text of the correct option (not its letter).
- Output only the code inside one ```python block."""


def run(code):
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8") as f:
        f.write(PRELUDIO + code)
        p = f.name
    try:
        r = subprocess.run([sys.executable, "-I", "-S", p], capture_output=True, text=True, timeout=3, encoding="utf-8", errors="replace")
        return r.stdout, r.stderr[-200:]
    except subprocess.TimeoutExpired:
        return "", "timeout"
    finally:
        os.unlink(p)


def formato(pr):
    lines = [pr["text"].strip()]
    for k in LETTERS:
        lines.append(f"{k}) {pr['options'][k]}")
    return "\n".join(lines)


def limpiar_codigo(code):
    code = re.sub(r"^```(?:python)?\s*|\s*```$", "", code.strip(), flags=re.M).strip()
    lines = [re.sub(r"(?<!['\"])\s+#.*$", "", ln) for ln in code.splitlines() if not ln.strip().startswith("#")]
    return "\n".join(ln for ln in lines if ln.strip())


buenos, vistos = [], set()
stats = Counter()
for p in sorted(glob.glob(os.path.join(HERE, "generado", "*.jsonl"))):
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
        if not isinstance(o, dict) or len(o) != 5 or r.get("label") not in LETTERS or not r.get("text") or not r.get("code"):
            stats["incompleto"] += 1
            continue
        o = {k: str(v).strip() for k, v in o.items()}
        if len(set(o.values())) < 5:
            stats["opciones_repetidas"] += 1
            continue
        h = hashlib.sha1(re.sub(r"\W+", "", r["text"].lower()).encode()).hexdigest()
        if h in vistos:
            stats["duplicado"] += 1
            continue
        code = limpiar_codigo(r["code"])
        if code.count("\n") > 14 or len(code) > 700:
            stats["codigo_largo"] += 1
            continue
        out, err = run(code)
        letra, _ = (None, "") if not out.strip() else match_option(out, o)
        if letra != r["label"]:
            stats["no_casa_o_distinta"] += 1
            continue
        vistos.add(h)
        buenos.append({"id": f"sint_{len(buenos):05d}", "language": r.get("language", "eng"), "level": int(r.get("level", 4) or 4),
                       "type": r.get("type", "other"), "text": r["text"].strip(), "options": o, "label": r["label"], "code": code, "text_only": True})
        stats["ok"] += 1

os.makedirs(os.path.join(HERE), exist_ok=True)
with open(os.path.join(HERE, "limpio.jsonl"), "w", encoding="utf-8", newline="\n") as f:
    for b in buenos:
        f.write(json.dumps(b, ensure_ascii=False) + "\n")
datos = r"D:\Datathon_A\nube\datos"
os.makedirs(datos, exist_ok=True)
with open(os.path.join(datos, "sft_sintetico.jsonl"), "w", encoding="utf-8", newline="\n") as ft, \
        open(os.path.join(datos, "sft_sintetico_val.jsonl"), "w", encoding="utf-8", newline="\n") as fv:
    for b in buenos:
        row = {"messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": formato(b)},
                            {"role": "assistant", "content": f"```python\n{b['code']}\n```"}]}
        (fv if int(hashlib.sha256(b["id"].encode()).hexdigest(), 16) % 100 < 3 else ft).write(json.dumps(row, ensure_ascii=False) + "\n")
print(dict(stats))
print(f"{len(buenos)} problemas sintéticos verificados → {os.path.join(HERE, 'limpio.jsonl')} y nube/datos/sft_sintetico.jsonl")
print("por nivel:", dict(Counter(b["level"] for b in buenos)), " por tipo:", dict(Counter(b["type"] for b in buenos)), " letras:", dict(Counter(b["label"] for b in buenos)))
