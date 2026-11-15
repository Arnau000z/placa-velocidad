"""Rejilla de variantes del sistema para los problemas SIN figura (donde el modelo puede acertar de verdad):
número y elección de ejemplos, estructura del prompt (JSON, valor numérico, pasos), votación, verificación…
Cada variante se mide en los mismos problemas y da acierto, tokens y segundos estimados en la placa.

python -X utf8 eval_variantes.py <repo> --url http://127.0.0.1:8087 --variantes all --paralelo 8 --nombre 1.7B
   --limit 0 = todos los problemas de texto de val (~370); --todos incluye también los de figura.
Necesita bge-m3 en :8084 y un llama-server con --parallel >= --paralelo.
"""
import argparse
import collections
import concurrent.futures as cf
import glob
import json
import os
import random
import re
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from util_opciones import LETTERS, extract_answer, extract_code, match_option, parse_value  # noqa: E402

p = argparse.ArgumentParser()
p.add_argument("repo")
p.add_argument("--url", default="http://127.0.0.1:8087")
p.add_argument("--variantes", default="all")
p.add_argument("--limit", type=int, default=0)
p.add_argument("--todos", action="store_true", help="también los problemas con figura")
p.add_argument("--paralelo", type=int, default=4)
p.add_argument("--tps", default="6,3")
p.add_argument("--nombre", default="x")
p.add_argument("--codigo", default=os.path.join(HERE, "codigo", "verificado.jsonl"))
p.add_argument("--modelo", default="", help="nombre del modelo para el campo 'model' (vLLM lo exige)")
p.add_argument("--sin-pensar", action="store_true", help="vLLM: chat_template_kwargs enable_thinking=false (en llama.cpp se usa --reasoning off)")
p.add_argument("--prefijo-cacheado", type=int, default=0, help="tokens del prompt de sistema que la placa no vuelve a leer (caché de prefijo), por llamada")
p.add_argument("--datos", default="", help="otro JSONL de problemas (p. ej. el examen de prueba) en vez de data/val.jsonl del repo")
args = p.parse_args()
TPS_IN, TPS_OUT = (float(x) for x in args.tps.split(","))
os.environ["EMBED_PORT"] = "8084"
os.environ["EMBED_QUERY_PREFIX"] = ""
sys.path.insert(0, args.repo)
from copilot.llm import format_problem  # noqa: E402
from copilot.rag import Index  # noqa: E402

URL = args.url + "/v1/chat/completions"
PY = sys.executable
SYSTEM_CODE = """You solve Kangaroo math competition problems by writing a short Python 3 program.
Rules:
- Translate the statement into code faithfully: put the given numbers in variables, then compute. When the problem asks to count, to find a maximum/minimum, or which value satisfies conditions, try all the cases with loops instead of reasoning by hand.
- At most 20 lines. No comments, no explanations, no functions unless really needed. Standard library only, no input(), must finish in under 2 seconds (never brute-force more than a million cases).
- The last line must be print(answer): the numeric value, or the exact text of the correct option (not its letter).
- Output only the code inside one ```python block."""
EJEMPLOS_FIJOS = [
    ("Tom has some marbles. If he gives 7 to Ana he has twice as many as her; if instead Ana gives 7 to Tom, he has five times as many as her. How many marbles do they have together?\nA) 48\nB) 56\nC) 60\nD) 64\nE) 72",
     "```python\nanswer = None\nfor t in range(1, 200):\n    for a in range(1, 200):\n        if t - 7 == 2 * (a + 7) and t + 7 == 5 * (a - 7):\n            answer = t + a\nprint(answer)\n```"),
    ("How many three-digit numbers have digits that add up to 5 and contain no zero?\nA) 4\nB) 6\nC) 8\nD) 10\nE) 12",
     "```python\ncount = 0\nfor n in range(100, 1000):\n    d = [int(c) for c in str(n)]\n    if sum(d) == 5 and 0 not in d:\n        count += 1\nprint(count)\n```"),
]
SYSTEM_RAZONA = ("You are an expert at Kangaroo math competition problems. Answer in the same style as the examples: "
                 "a short plain-text explanation (at most 60 words, no LaTeX) that reaches the result, checks it "
                 "against the options and ends with exactly 'Answer: X'.")
SYSTEM_VALOR = ("You are an expert at Kangaroo math competition problems. Solve the problem in a short plain-text explanation "
                "(at most 60 words, no LaTeX). Finish with exactly 'Final answer: <value>' where <value> is the number or text "
                "of the result (not a letter), and then 'Answer: X' with the matching option letter.")
SYSTEM_JSON = ("You are an expert at Kangaroo math competition problems. The problem comes as a JSON object. Reply with ONE JSON "
               "object only: {\"reasoning\": \"<at most 50 words>\", \"value\": \"<the computed result>\", \"answer\": \"<letter A-E>\"}.")
SYSTEM_INGLES = ("You are an expert at Kangaroo math competition problems. First restate the problem in English in one short "
                 "sentence (the statements may be in Catalan or Spanish). Then solve it in at most 60 plain-text words, check "
                 "the result against the options and end with exactly 'Answer: X'.")
SYSTEM_PASOS = ("You are an expert at Kangaroo math competition problems. Solve it in numbered steps: 'Step 1:', 'Step 2:', ... "
                "each one line with its computation (at most 5 steps, no LaTeX), then 'Check:' against the options, then exactly 'Answer: X'.")

# --- bancos ---------------------------------------------------------------
expl, tipo, codigo_ok = {}, {}, {}
tot_path = os.path.join(HERE, "explicaciones", "explicaciones_total.jsonl")
paths = [tot_path] if os.path.exists(tot_path) else glob.glob(os.path.join(HERE, "explicaciones", "resultados", "*.jsonl"))
for path in paths:
    for line in open(path, encoding="utf-8"):
        if line.strip():
            e = json.loads(line)
            expl[f"{e['id']}|{e['language']}"] = e["solution"].strip()
            tipo[e["id"]] = e.get("type", "other")
for line in open(args.codigo, encoding="utf-8"):
    if line.strip():
        c = json.loads(line)
        if c["status"] == "ok":
            codigo_ok[c["id"]] = c["code"].strip()
index = Index(os.path.join(args.repo, "data", "index_m3.db"))
print(f"explicaciones {len(expl)}, tipos {len(tipo)}, códigos verificados {len(codigo_ok)}", flush=True)


def post(payload, timeout=600):
    req = urllib.request.Request(URL, json.dumps(payload).encode(), {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def run_code(code):
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8") as f:
        f.write("from fractions import Fraction\nfrom math import *\nfrom itertools import *\nfrom collections import Counter\n" + code)
        path = f.name
    try:
        r = subprocess.run([PY, "-I", "-S", path], capture_output=True, text=True, timeout=3, encoding="utf-8", errors="replace")
        return r.stdout, (r.stderr.strip().splitlines()[-1] if r.stderr.strip() else "")
    except subprocess.TimeoutExpired:
        return "", "TimeoutError"
    finally:
        os.unlink(path)


class Ctx:
    """Un problema: sus vecinos (una sola búsqueda) y la cuenta de tokens."""

    def __init__(self, pr):
        self.pr = pr
        self.opts = pr.get("options") or {}
        self.vecinos = index.search(pr, k=12, exclude_id=pr["id"])
        self.tin = self.tout = 0
        self.llamadas = 0
        self.salidas = []

    def chat(self, msgs, max_tokens, temperature=0, seed=42, **extra):
        payload = {"messages": msgs, "max_tokens": max_tokens, "temperature": temperature, "seed": seed, "cache_prompt": True, **extra}
        if args.modelo:
            payload["model"] = args.modelo
        if args.sin_pensar:
            payload["chat_template_kwargs"] = {"enable_thinking": False}
        r = post(payload)
        u = r.get("usage", {})
        self.tin += u.get("prompt_tokens", 0)
        self.tout += u.get("completion_tokens", 0)
        self.llamadas += 1
        text = r["choices"][0]["message"]["content"]
        self.salidas.append(text)
        return text

    def ejemplos_codigo(self, k, mismo_tipo=False):
        cands = [ex for _s, ex in self.vecinos if ex["id"] in codigo_ok and len(ex.get("options") or {}) == 5]
        if mismo_tipo and self.vecinos:
            t = tipo.get(self.vecinos[0][1]["id"])
            same = [ex for ex in cands if tipo.get(ex["id"]) == t]
            cands = same + [ex for ex in cands if ex not in same]
        ej = [(format_problem(ex), "```python\n" + codigo_ok[ex["id"]] + "\n```") for ex in cands]
        return (ej + EJEMPLOS_FIJOS)[:k]

    def ejemplos_expl(self, k):
        return [(format_problem(ex), expl.get(f"{ex['id']}|{ex['language']}", f"Answer: {ex['label']}")) for _s, ex in self.vecinos[:k]]


def msgs_con(system, ejemplos, user):
    m = [{"role": "system", "content": system}]
    for q, a in ejemplos:
        m += [{"role": "user", "content": q}, {"role": "assistant", "content": a}]
    m.append({"role": "user", "content": user})
    return m


# --- piezas ---------------------------------------------------------------
def via_codigo(c, k=2, mismo_tipo=False, temperature=0, seed=42, max_tokens=450):
    text = c.chat(msgs_con(SYSTEM_CODE, c.ejemplos_codigo(k, mismo_tipo), format_problem(c.pr)), max_tokens, temperature, seed)
    out, err = run_code(extract_code(text))
    letra, _raw = (None, "") if not out.strip() else match_option(out, c.opts)
    return letra


def via_razona(c, k=2, system=SYSTEM_RAZONA, max_tokens=300, temperature=0, seed=42, user=None):
    text = c.chat(msgs_con(system, c.ejemplos_expl(k), user or format_problem(c.pr)), max_tokens, temperature, seed)
    return extract_answer(text), text


def via_valor(c, k=2, max_tokens=320, user=None):
    ej = [(q, a.replace("Answer:", "Final answer: (see above)\nAnswer:")) for q, a in c.ejemplos_expl(k)]
    text = c.chat(msgs_con(SYSTEM_VALOR, ej, user or format_problem(c.pr)), max_tokens)
    m = re.search(r"Final answer:\s*(.+)", text)
    if m:
        letra, _ = match_option(m.group(1).strip(), c.opts)
        if letra:
            return letra, text
    return extract_answer(text), text


def problema_json(pr):
    return json.dumps({"problem": pr["text"].strip(), "options": pr.get("options") or {}}, ensure_ascii=False)


def via_json(c, k=2):
    ej = []
    for _s, ex in c.vecinos[:k]:
        sol = expl.get(f"{ex['id']}|{ex['language']}", "")
        ej.append((problema_json(ex), json.dumps({"reasoning": sol[: sol.rfind("Answer:")].strip()[:300] if "Answer:" in sol else sol[:300],
                                                  "value": (ex.get("options") or {}).get(ex["label"], ""), "answer": ex["label"]}, ensure_ascii=False)))
    text = c.chat(msgs_con(SYSTEM_JSON, ej, problema_json(c.pr)), 320)
    m = re.search(r'"answer"\s*:\s*"?\s*([A-E])', text)
    if m:
        return m.group(1), text
    m = re.search(r'"value"\s*:\s*"([^"]*)"', text)
    if m:
        letra, _ = match_option(m.group(1), c.opts)
        return letra, text
    return extract_answer(text), text


def voto(respuestas):
    r = [x for x in respuestas if x]
    if not r:
        return None
    cnt = collections.Counter(r).most_common()
    return cnt[0][0]


# --- variantes: nombre → función(ctx) → (letra, vía) ------------------------
def v_base(c):
    a = via_codigo(c, 2)
    if a:
        return a, "python"
    a, _ = via_razona(c, 2)
    return a, "razona"


def v_k0(c):
    a = via_codigo(c, 0)
    if a:
        return a, "python"
    a, _ = via_razona(c, 0)
    return a, "razona"


def v_k1(c):
    a = via_codigo(c, 1)
    if a:
        return a, "python"
    a, _ = via_razona(c, 1)
    return a, "razona"


def v_k3(c):
    a = via_codigo(c, 3)
    if a:
        return a, "python"
    a, _ = via_razona(c, 3)
    return a, "razona"


def v_tipo(c):
    a = via_codigo(c, 2, mismo_tipo=True)
    if a:
        return a, "python"
    a, _ = via_razona(c, 2)
    return a, "razona"


def v_valor(c):
    a = via_codigo(c, 2)
    if a:
        return a, "python"
    a, _ = via_valor(c, 2)
    return a, "valor"


def v_json(c):
    a, _ = via_json(c, 2)
    return a, "json"


def v_json_tras_codigo(c):
    a = via_codigo(c, 2)
    if a:
        return a, "python"
    a, _ = via_json(c, 2)
    return a, "json"


def v_ingles(c):
    a = via_codigo(c, 2)
    if a:
        return a, "python"
    a, _ = via_razona(c, 2, system=SYSTEM_INGLES, max_tokens=340)
    return a, "ingles"


def v_pasos(c):
    a = via_codigo(c, 2)
    if a:
        return a, "python"
    a, _ = via_razona(c, 2, system=SYSTEM_PASOS, max_tokens=320)
    return a, "pasos"


def v_razona_k0(c):
    a, _ = via_razona(c, 0)
    return a, "razona"


def v_razona_k2(c):
    a, _ = via_razona(c, 2)
    return a, "razona"


def v_razona_k4(c):
    a, _ = via_razona(c, 4)
    return a, "razona"


def v_razona_primero(c):
    a, _ = via_razona(c, 2)
    b = via_codigo(c, 2)
    if b and a and a == b:
        return a, "acuerdo"
    if b:
        return b, "python"
    return a, "razona"


def v_voto3_codigo(c):
    r = [via_codigo(c, 2, temperature=0.8, seed=s) for s in (1, 2, 3)]
    a = voto(r)
    if a:
        return a, "voto"
    a, _ = via_razona(c, 2)
    return a, "razona"


def v_voto3_razona(c):
    r = [via_razona(c, 2, temperature=0.8, seed=s)[0] for s in (1, 2, 3)]
    return voto(r), "voto"


def v_verifica(c):
    a = via_codigo(c, 2)
    if a:
        return a, "python"
    a, text = via_razona(c, 2)
    if not a:
        return a, "razona"
    msgs = msgs_con(SYSTEM_RAZONA, c.ejemplos_expl(2), format_problem(c.pr)) + [
        {"role": "assistant", "content": text},
        {"role": "user", "content": "Check your answer by substituting it back into the statement in one or two lines. If it does not fit, "
                                    "correct it. End again with exactly 'Answer: X'."}]
    t2 = c.chat(msgs, 200)
    b = extract_answer(t2)
    return (b or a), "verifica"


def v_voto_mixto(c):
    """Código a temperatura 0 + razona + valor: mayoría; si no hay, código."""
    a = via_codigo(c, 2)
    b, _ = via_razona(c, 2)
    d, _ = via_valor(c, 2)
    v = voto([a, b, d])
    return (v or a or b or d), "mixto"


def v_k0_valor(c):
    a = via_codigo(c, 0)
    if a:
        return a, "python"
    a, _ = via_valor(c, 0)
    return a, "valor"


def v_k1_valor(c):
    a = via_codigo(c, 1)
    if a:
        return a, "python"
    a, _ = via_valor(c, 1)
    return a, "valor"


def v_valor_k0_solo(c):
    a, _ = via_valor(c, 0)
    return a, "valor"


def v_k1_valor_corto(c):
    """Lo que cabría en 60 s: 1 ejemplo, código de 300 tokens, valor de 220."""
    a = via_codigo(c, 1, max_tokens=300)
    if a:
        return a, "python"
    a, _ = via_valor(c, 1, max_tokens=220)
    return a, "valor"


def v_k0_valor_corto(c):
    a = via_codigo(c, 0, max_tokens=300)
    if a:
        return a, "python"
    a, _ = via_valor(c, 0, max_tokens=220)
    return a, "valor"


SYSTEM_CHECK = """You solve Kangaroo multiple-choice problems by writing a Python 3 checker, not by computing the answer.
Write a function `def cumple(x):` that returns True exactly when the candidate answer x (a number, or the option text as a string) satisfies every condition of the statement, and False otherwise. Translate each condition faithfully; use loops to test cases when needed. Standard library only, under 2 seconds. Output only the code inside one ```python block, with no calls or prints."""
SYSTEM_PARSEO = ("Rewrite the math problem as a structured sheet, nothing else:\nGiven: <each number and fact, one per line>\n"
                 "Asked: <exactly what quantity is requested, with its unit>\nConditions: <every constraint>\nAt most 80 words. Keep all numbers.")
SYSTEM_SIMPLIFICA = ("Rewrite the math problem in English using short simple sentences, keeping every number, name and condition "
                     "exactly, and ending with the question. At most 80 words. Output only the rewritten problem.")


def via_verifica_opciones(c):
    text = c.chat(msgs_con(SYSTEM_CHECK, [], format_problem(c.pr)), 450)
    code = extract_code(text)
    pruebas = []
    for k in LETTERS:
        v = parse_value(c.opts.get(k, ""))
        pruebas.append(repr(v) if v is not None else repr(str(c.opts.get(k, ""))))
    prueba = code + "\nimport sys\n_res = []\nfor _k, _x in zip('ABCDE', [" + ", ".join(pruebas) + "]):\n    try:\n        _res.append(_k if cumple(_x) else '')\n    except Exception:\n        _res.append('')\nprint(''.join(_res))\n"
    out, err = run_code(prueba)
    ok = out.strip().splitlines()[-1].strip() if out.strip() else ""
    if len(ok) == 1 and ok in LETTERS:
        return ok
    return None


def v_verifica_opciones(c):
    a = via_codigo(c, 1)
    if a:
        return a, "python"
    a = via_verifica_opciones(c)
    if a:
        return a, "checker"
    a, _ = via_valor(c, 1)
    return a, "valor"


def v_checker_primero(c):
    a = via_verifica_opciones(c)
    if a:
        return a, "checker"
    a = via_codigo(c, 1)
    if a:
        return a, "python"
    a, _ = via_valor(c, 1)
    return a, "valor"


def _reescrito(c, system):
    return c.chat([{"role": "system", "content": system}, {"role": "user", "content": format_problem(c.pr)}], 160)


def v_parseo(c):
    hoja = _reescrito(c, SYSTEM_PARSEO)
    user = hoja.strip() + "\n\nOriginal problem:\n" + format_problem(c.pr)
    text = c.chat(msgs_con(SYSTEM_CODE, c.ejemplos_codigo(1), user), 450)
    out, err = run_code(extract_code(text))
    letra, _ = (None, "") if not out.strip() else match_option(out, c.opts)
    if letra:
        return letra, "python"
    a, _ = via_valor(c, 1)
    return a, "valor"


def v_simplifica(c):
    simple = _reescrito(c, SYSTEM_SIMPLIFICA)
    opciones = "\n".join(f"{k}) {c.opts[k]}" for k in LETTERS if k in c.opts)
    user = simple.strip() + "\n" + opciones
    text = c.chat(msgs_con(SYSTEM_CODE, c.ejemplos_codigo(1), user), 450)
    out, err = run_code(extract_code(text))
    letra, _ = (None, "") if not out.strip() else match_option(out, c.opts)
    if letra:
        return letra, "python"
    a, _ = via_valor(c, 1, user=user)
    return a, "valor"


SYSTEM_SFT = ("You are an expert at Kangaroo math competition problems. Solve the problem: explain the key idea in a few "
              "plain-text lines, compute (with a short Python program when counting or checking cases helps), check the "
              "result against the five options and finish with exactly 'Answer: X'.")
SYSTEM_VALOR_DIRECTO = ("You are an expert at Kangaroo math competition problems. Reply with the final result only: the number or "
                        "the exact text of the correct option, nothing else.")
SYSTEM_CODE_CORTO = SYSTEM_CODE.replace("At most 20 lines", "At most 8 short lines")


def v_sft(c):
    """Lo que se le enseñó en el fine-tuning: sin ejemplos, explicación corta + programa si hace falta + Answer."""
    text = c.chat(msgs_con(SYSTEM_SFT, [], format_problem(c.pr)), 400)
    if "```" in text:
        out, err = run_code(extract_code(text))
        letra, _ = (None, "") if not out.strip() else match_option(out, c.opts)
        if letra:
            return letra, "python"
    a = extract_answer(text)
    if a:
        return a, "answer"
    m = re.search(r"Final answer:\s*(.+)", text)
    if m:
        letra, _ = match_option(m.group(1).strip(), c.opts)
        return letra, "valor"
    return None, "nada"


def v_valor_directo(c):
    text = c.chat(msgs_con(SYSTEM_VALOR_DIRECTO, [], format_problem(c.pr)), 24)
    letra, _ = match_option(text.strip(), c.opts)
    return letra, "directo"


def v_codigo_corto(c):
    """Lo que cabe en 60 s con el 1.7B Q8 en la placa: ~130 tokens de programa; si no casa, valor directo."""
    text = c.chat(msgs_con(SYSTEM_CODE_CORTO, [], format_problem(c.pr)), 130)
    out, err = run_code(extract_code(text))
    letra, _ = (None, "") if not out.strip() else match_option(out, c.opts)
    if letra:
        return letra, "python"
    return v_valor_directo(c)[0], "directo"


def v_k0_valor_60(c):
    text = c.chat(msgs_con(SYSTEM_CODE_CORTO, [], format_problem(c.pr)), 130)
    out, err = run_code(extract_code(text))
    letra, _ = (None, "") if not out.strip() else match_option(out, c.opts)
    if letra:
        return letra, "python"
    a, _ = via_valor(c, 0, max_tokens=90)
    return a, "valor"


SYSTEM_TOOLBOX = SYSTEM_CODE + """
Pick the idiom that fits and use it literally:
- assignments/orderings of named people or objects: `for p in itertools.permutations(values): if <all conditions>: print(...)`
- "how many N-digit numbers / times / arrangements": loop over every candidate with range() and count the ones that satisfy ALL conditions
- processes that repeat ("each day", "each cut", "each move"): simulate step by step with a while loop and a counter
- "which of the options cannot / can / must": test each option value in a loop and print the one that fails/passes
- equal cubes, tiles, regular spacing: use gcd/lcm; "on each side / both ends / in pairs" means multiply or equate counts
- fractions and ratios: use Fraction, never floats
Re-read the question before printing: print the quantity asked, in the unit asked."""
PREGUNTA_OPCIONES = re.compile(r"which of (the following|these)|cannot be|could be|can be the|must be|is (not )?possible|"
                               r"quin(a)? dels? seg(ü|u)ents|quina? (no )?pot ser|cu[aá]l de l[oa]s siguientes|no puede ser|puede ser", re.I)


def v_toolbox(c):
    text = c.chat(msgs_con(SYSTEM_TOOLBOX, [], format_problem(c.pr)), 450)
    out, err = run_code(extract_code(text))
    letra, _ = (None, "") if not out.strip() else match_option(out, c.opts)
    if letra:
        return letra, "python"
    a, _ = via_valor(c, 0)
    return a, "valor"


def v_toolbox_k1(c):
    text = c.chat(msgs_con(SYSTEM_TOOLBOX, c.ejemplos_codigo(1), format_problem(c.pr)), 450)
    out, err = run_code(extract_code(text))
    letra, _ = (None, "") if not out.strip() else match_option(out, c.opts)
    if letra:
        return letra, "python"
    a, _ = via_valor(c, 1)
    return a, "valor"


def v_ruta_pregunta(c):
    """Si la pregunta es 'cuál de las opciones…', primero el checker; si no, código con la caja de herramientas."""
    if PREGUNTA_OPCIONES.search(c.pr["text"]):
        a = via_verifica_opciones(c)
        if a:
            return a, "checker"
    return v_toolbox(c)


SYSTEM_LETRA = ("You solve multiple-choice math competition problems for school students. Read the problem and the options, "
                "then reply with the letter of the correct option.")


def v_letra(c):
    """El flujo del reto: letra directa con gramática, 1 token (lo único que cabe seguro en la placa con el 1.7B)."""
    text = c.chat([{"role": "system", "content": SYSTEM_LETRA}, {"role": "user", "content": format_problem(c.pr) + "\nAnswer:"}], 1,
                  grammar="root ::= [A-E]")
    a = text.strip()[:1]
    return (a if a in LETTERS else None), "letra"


def v_letra_k2(c):
    ej = [(format_problem(ex) + "\nAnswer:", ex["label"]) for _s, ex in c.vecinos[:2]]
    text = c.chat(msgs_con(SYSTEM_LETRA, ej, format_problem(c.pr) + "\nAnswer:"), 1, grammar="root ::= [A-E]")
    a = text.strip()[:1]
    return (a if a in LETTERS else None), "letra"


def v_letra_razon_corta(c):
    """Una frase de razonamiento (40 tokens) y después la letra con gramática: lo que cabe si la lectura deja 15 s."""
    msgs = [{"role": "system", "content": "Solve the problem. Write ONE short sentence with the key computation, then stop."},
            {"role": "user", "content": format_problem(c.pr)}]
    t1 = c.chat(msgs, 40)
    t2 = c.chat(msgs + [{"role": "assistant", "content": t1}, {"role": "user", "content": "Answer letter:"}], 1, grammar="root ::= [A-E]")
    a = t2.strip()[:1]
    return (a if a in LETTERS else None), "letra_razon"


_BIAS = {}


def bias_sin_comentarios():
    """logit_bias que prohíbe los tokens de '#' (calculado una vez con /tokenize del servidor)."""
    if "v" not in _BIAS:
        ids = set()
        for s in ("#", " #", "  #", "\n#", "#\n", " # "):
            try:
                ids.update(post_raw("/tokenize", {"content": s}).get("tokens", []))
            except Exception:  # noqa: BLE001
                pass
        for s in (" ", "  ", "\n"):
            try:
                ids.difference_update(post_raw("/tokenize", {"content": s}).get("tokens", []))
            except Exception:  # noqa: BLE001
                pass
        _BIAS["v"] = [[int(i), False] for i in ids] if not args.modelo else {str(i): -100 for i in ids}
    return _BIAS["v"]


def post_raw(path, payload):
    req = urllib.request.Request(args.url + path, json.dumps(payload).encode(), {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.load(r)


def _codigo_letra(n, sin_comentarios):
    """Lo que cabe en la placa con el 1.7B: programa corto (n tokens) y, si no casa, la letra con gramática en la misma
    conversación (1 token más). Sin valor razonado."""
    def f(c):
        msgs = msgs_con(SYSTEM_CODE_CORTO, [], format_problem(c.pr))
        extra = {"logit_bias": bias_sin_comentarios()} if sin_comentarios else {}
        text = c.chat(msgs, n, **extra)
        out, err = run_code(extract_code(text))
        letra, _ = (None, "") if not out.strip() else match_option(out, c.opts)
        if letra and not (len(out.strip().splitlines()[-1].strip()) == 1 and out.strip().splitlines()[-1].strip().upper() in LETTERS):
            return letra, "python"
        t2 = c.chat(msgs + [{"role": "assistant", "content": text}, {"role": "user", "content": "Answer letter:"}], 1, grammar="root ::= [A-E]")
        a = t2.strip()[:1]
        return (a if a in LETTERS else None), "letra"
    return f


VARIANTES = {
    "letra": v_letra, "letra_k2": v_letra_k2, "letra_razon_corta": v_letra_razon_corta,
    "toolbox": v_toolbox, "toolbox_k1": v_toolbox_k1, "ruta_pregunta": v_ruta_pregunta,
    "sft": v_sft, "valor_directo": v_valor_directo, "codigo_corto": v_codigo_corto, "k0_valor_60": v_k0_valor_60,
    "verifica_opciones": v_verifica_opciones, "checker_primero": v_checker_primero, "parseo": v_parseo, "simplifica": v_simplifica,
    "k0_valor": v_k0_valor, "k1_valor": v_k1_valor, "valor_k0_solo": v_valor_k0_solo, "k1_valor_corto": v_k1_valor_corto,
    "k0_valor_corto": v_k0_valor_corto,
    "base": v_base, "k0": v_k0, "k1": v_k1, "k3": v_k3, "tipo": v_tipo, "valor": v_valor, "json": v_json,
    "json_tras_codigo": v_json_tras_codigo, "ingles": v_ingles, "pasos": v_pasos, "razona_k0": v_razona_k0,
    "razona_k2": v_razona_k2, "razona_k4": v_razona_k4, "razona_primero": v_razona_primero, "voto3_codigo": v_voto3_codigo,
    "voto3_razona": v_voto3_razona, "verifica": v_verifica, "voto_mixto": v_voto_mixto,
}
# --- familia con presupuesto de tokens de salida (lo que de verdad cabe en 60 s según modelo y cuantización) ---
def _codigo_n(n, k=0):
    def f(c):
        text = c.chat(msgs_con(SYSTEM_CODE_CORTO if n <= 150 else SYSTEM_CODE, c.ejemplos_codigo(k), format_problem(c.pr)), n)
        out, err = run_code(extract_code(text))
        letra, _ = (None, "") if not out.strip() else match_option(out, c.opts)
        if letra:
            return letra, "python"
        return v_valor_directo(c)[0], "directo"
    return f


def _valor_n(n, k=0):
    def f(c):
        a, _ = via_valor(c, k, max_tokens=n)
        return a, "valor"
    return f


def _codigo_valor_n(n_cod, n_val, k=0):
    def f(c):
        text = c.chat(msgs_con(SYSTEM_CODE_CORTO if n_cod <= 150 else SYSTEM_CODE, c.ejemplos_codigo(k), format_problem(c.pr)), n_cod)
        out, err = run_code(extract_code(text))
        letra, _ = (None, "") if not out.strip() else match_option(out, c.opts)
        if letra:
            return letra, "python"
        a, _ = via_valor(c, k, max_tokens=n_val)
        return a, "valor"
    return f


for _n in (80, 110, 150, 220):
    VARIANTES[f"codigo{_n}_letra"] = _codigo_letra(_n, False)
    VARIANTES[f"codigo{_n}_sincom_letra"] = _codigo_letra(_n, True)

for _n in (100, 150, 200, 270, 350):
    VARIANTES[f"codigo{_n}"] = _codigo_n(_n)
    VARIANTES[f"k1_codigo{_n}"] = _codigo_n(_n, 1)
    VARIANTES[f"valor{_n}"] = _valor_n(_n)
for _nc, _nv in ((150, 100), (200, 120), (270, 150)):
    VARIANTES[f"codigo{_nc}_valor{_nv}"] = _codigo_valor_n(_nc, _nv)



def user_sin_opciones(pr):
    """Enunciado sin las opciones cuando son numéricas (ahorra 20-40 tokens de lectura; el valor se casa igual)."""
    o = pr.get("options") or {}
    if len(o) == 5 and all(parse_value(v) is not None for v in o.values()):
        return pr["text"].strip()
    return format_problem(pr)


def _codigo_letra_sinopc(n):
    def f(c):
        msgs = msgs_con(SYSTEM_CODE_CORTO, [], user_sin_opciones(c.pr))
        text = c.chat(msgs, n)
        out, err = run_code(extract_code(text))
        letra, _ = (None, "") if not out.strip() else match_option(out, c.opts)
        if letra:
            return letra, "python"
        opciones = "\n".join(f"{k}) {c.opts[k]}" for k in LETTERS if k in c.opts)
        t2 = c.chat(msgs + [{"role": "assistant", "content": text}, {"role": "user", "content": "Options:\n" + opciones + "\nAnswer letter:"}], 1, grammar="root ::= [A-E]")
        a = t2.strip()[:1]
        return (a if a in LETTERS else None), "letra"
    return f


def v_k0_valor_sinopc(c):
    text = c.chat(msgs_con(SYSTEM_CODE, [], user_sin_opciones(c.pr)), 450)
    out, err = run_code(extract_code(text))
    letra, _ = (None, "") if not out.strip() else match_option(out, c.opts)
    if letra:
        return letra, "python"
    a, _ = via_valor(c, 0)
    return a, "valor"


VARIANTES["codigo150_letra_sinopc"] = _codigo_letra_sinopc(150)
VARIANTES["codigo220_letra_sinopc"] = _codigo_letra_sinopc(220)
VARIANTES["k0_valor_sinopc"] = v_k0_valor_sinopc



def _codigo_x2(n, reserva_mediana):
    """Dos programas (T=0 y T=0,7): el primero cuya salida casa con una opción; si ninguno, mediana o letra."""
    def f(c):
        msgs = msgs_con(SYSTEM_CODE_CORTO, [], format_problem(c.pr))
        text = c.chat(msgs, n)
        out, err = run_code(extract_code(text))
        letra, _ = (None, "") if not out.strip() else match_option(out, c.opts)
        if letra:
            return letra, "python"
        text2 = c.chat(msgs, n, temperature=0.7, seed=7)
        out2, err2 = run_code(extract_code(text2))
        letra, _ = (None, "") if not out2.strip() else match_option(out2, c.opts)
        if letra:
            return letra, "python2"
        if reserva_mediana:
            vals = {k: parse_value(v) for k, v in c.opts.items()}
            if len(vals) == 5 and all(v is not None for v in vals.values()) and len(set(vals.values())) == 5:
                return sorted(LETTERS, key=lambda k: vals[k])[2], "mediana"
        t3 = c.chat(msgs + [{"role": "assistant", "content": text}, {"role": "user", "content": "Answer letter:"}], 1, grammar="root ::= [A-E]")
        a = t3.strip()[:1]
        return (a if a in LETTERS else None), "letra"
    return f


def _codigo_mediana(n):
    def f(c):
        msgs = msgs_con(SYSTEM_CODE_CORTO, [], format_problem(c.pr))
        text = c.chat(msgs, n)
        out, err = run_code(extract_code(text))
        letra, _ = (None, "") if not out.strip() else match_option(out, c.opts)
        if letra:
            return letra, "python"
        vals = {k: parse_value(v) for k, v in c.opts.items()}
        if len(vals) == 5 and all(v is not None for v in vals.values()) and len(set(vals.values())) == 5:
            return sorted(LETTERS, key=lambda k: vals[k])[2], "mediana"
        t3 = c.chat(msgs + [{"role": "assistant", "content": text}, {"role": "user", "content": "Answer letter:"}], 1, grammar="root ::= [A-E]")
        a = t3.strip()[:1]
        return (a if a in LETTERS else None), "letra"
    return f


VARIANTES["codigo110_x2_mediana"] = _codigo_x2(110, True)
VARIANTES["codigo150_x2_mediana"] = _codigo_x2(150, True)
VARIANTES["codigo150_x2_letra"] = _codigo_x2(150, False)
VARIANTES["codigo150_mediana"] = _codigo_mediana(150)
VARIANTES["codigo110_mediana"] = _codigo_mediana(110)



def v_letra_probs(c):
    """Letra por probabilidades: un token con logprobs tras 'Answer: (' y argmax entre A-E (sin gramática). Guarda las 5
    probabilidades en la salida para calibrar el sesgo por letra después (PriDe)."""
    msgs = [{"role": "system", "content": SYSTEM_LETRA}, {"role": "user", "content": format_problem(c.pr) + "\nAnswer: ("}]
    payload = {"messages": msgs, "max_tokens": 1, "temperature": 0, "seed": 42, "cache_prompt": True, "logprobs": True, "top_logprobs": 10,
               "grammar": "root ::= [A-E]"}
    if args.modelo:
        payload["model"] = args.modelo
    if args.sin_pensar:
        payload["chat_template_kwargs"] = {"enable_thinking": False}
    r = post(payload)
    u = r.get("usage", {})
    c.tin += u.get("prompt_tokens", 0)
    c.tout += u.get("completion_tokens", 0)
    c.llamadas += 1
    probs = {}
    try:
        for t in r["choices"][0]["logprobs"]["content"][0]["top_logprobs"]:
            k = t["token"].strip().strip("()").upper()
            if k in LETTERS and k not in probs:
                probs[k] = t["logprob"]
    except Exception:  # noqa: BLE001
        pass
    c.salidas.append(json.dumps(probs))
    if not probs:
        return None, "letra_probs"
    return max(probs, key=probs.get), "letra_probs"


VARIANTES["letra_probs"] = v_letra_probs

nombres = list(VARIANTES) if args.variantes == "all" else args.variantes.split(",")

val = [json.loads(l) for l in open(args.datos or os.path.join(args.repo, "data", "val.jsonl"), encoding="utf-8") if l.strip()]
random.Random(42).shuffle(val)
if not args.todos:
    val = [r for r in val if r["text_only"]]
val = [r for r in val if len(r.get("options") or {}) == 5]
if args.limit:
    val = val[:args.limit]
print(f"{len(val)} problemas, variantes: {nombres}", flush=True)

ctxs = {}
lock = threading.Lock()


def ctx_de(pr):
    k = (pr["id"], pr["language"])
    with lock:
        if k not in ctxs:
            ctxs[k] = Ctx(pr)
    return ctxs[k]


os.makedirs(os.path.join(HERE, "resultados"), exist_ok=True)
salida = os.path.join(HERE, "resultados", f"variantes_{args.nombre}.jsonl")
resumen = []
for nombre in nombres:
    fn = VARIANTES[nombre]
    t0 = time.time()

    def uno(pr):
        c = ctx_de(pr)
        tin0, tout0, ll0, s0 = c.tin, c.tout, c.llamadas, len(c.salidas)
        try:
            a, via = fn(c)
        except Exception as exc:  # noqa: BLE001
            a, via = None, f"error:{type(exc).__name__}"
        tin, tout = c.tin - tin0, c.tout - tout0
        ll = c.llamadas - ll0
        leidos = max(0, tin - args.prefijo_cacheado * ll)
        return {"variante": nombre, "id": pr["id"], "language": pr["language"], "level": pr["level"], "text_only": pr["text_only"],
                "label": pr["label"], "answer": a, "ok": a == pr["label"], "via": via, "tin": tin, "tout": tout,
                "llamadas": ll, "seg_placa": round(leidos / TPS_IN + tout / TPS_OUT, 1),
                "salidas": [s[:1500] for s in c.salidas[s0:]]}

    with cf.ThreadPoolExecutor(args.paralelo) as ex:
        filas = list(ex.map(uno, val))
    with open(salida, "a", encoding="utf-8") as f:
        for d in filas:
            f.write(json.dumps(d, ensure_ascii=False) + "\n")
    n = len(filas)
    ok = sum(d["ok"] for d in filas)
    por_idioma = {lg: (sum(d["ok"] for d in filas if d["language"] == lg), sum(1 for d in filas if d["language"] == lg)) for lg in ("eng", "cat", "esp")}
    vias = collections.Counter(d["via"] for d in filas)
    vias_ok = collections.Counter(d["via"] for d in filas if d["ok"])
    seg = sorted(d["seg_placa"] for d in filas)
    linea = (f"{nombre:18s} {ok:3d}/{n} = {100 * ok / n:4.1f}%  " + "  ".join(f"{lg} {100 * a / max(1, b):.0f}%" for lg, (a, b) in por_idioma.items())
             + f"  placa media {sum(seg) / n:.0f} s, mediana {seg[n // 2]:.0f} s, <=60 s: {100 * sum(1 for s in seg if s <= 60) / n:.0f}%"
             + "  vías: " + ", ".join(f"{v} {vias_ok[v]}/{vias[v]}" for v in vias) + f"   ({time.time() - t0:.0f} s)")
    print(linea, flush=True)
    resumen.append(linea)
print("\nRESUMEN", args.nombre)
print("\n".join(resumen))
