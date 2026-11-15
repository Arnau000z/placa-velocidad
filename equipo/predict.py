#!/usr/bin/env python3
"""predict.py del equipo (fuera del repo oficial; se copia a la placa junto a copilot/ si hace falta).

    python3 predict.py --input problems.jsonl --output predictions.csv [--url http://127.0.0.1:8080] [--limite 56]

Por problema (≤ 60 s, sin red), con el 1.7B en llama-server (prefijo de sistema cacheado):
  0. ¿Es un duplicado de train con las mismas opciones? → su etiqueta (huella: números del enunciado + opciones), 0 s.
  1. Programa Python corto (presupuesto de tokens calculado con la velocidad real medida al vuelo), ejecutado con límites
     de memoria y tiempo; si imprime un valor que casa con una opción → esa letra.
  2. Si no casa y queda tiempo → el valor razonado (Final answer) y casado.
  3. Si no → letra con gramática (1 token). Siempre sale una letra.
Solo biblioteca estándar. Todo lo que pueda fallar está en try/except: la fila siempre se escribe.
"""
import argparse
import csv
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.request

LETTERS = "ABCDE"
SYSTEM_CODE = """You solve Kangaroo math competition problems by writing a short Python 3 program.
Rules:
- Translate the statement into code faithfully: put the given numbers in variables, then compute. When the problem asks to count, to find a maximum/minimum, or which value satisfies conditions, try all the cases with loops instead of reasoning by hand.
- At most 8 short lines. No comments, no explanations, no functions unless really needed. Standard library only, no input(), must finish in under 2 seconds (never brute-force more than a million cases).
- The last line must be print(answer): the numeric value, or the exact text of the correct option (not its letter).
- Output only the code inside one ```python block."""
SYSTEM_VALOR = ("You are an expert at Kangaroo math competition problems. Solve the problem in a short plain-text explanation "
                "(at most 60 words, no LaTeX). Finish with exactly 'Final answer: <value>' where <value> is the number or text "
                "of the result (not a letter), and then 'Answer: X' with the matching option letter.")
PRELUDIO = "from fractions import Fraction\nfrom math import *\nfrom itertools import *\nfrom collections import Counter\n"
HERE = os.path.dirname(os.path.abspath(__file__))


# ----------------------------------------------------------------------------- opciones
def parse_value(s):
    t = str(s).strip().lower()
    if "!" in t or re.search(r"\d{7,}", t) or t.count("^") > 1 or t.count("**") > 1:
        return None
    t = re.sub(r"[€$%°º]", " ", t)
    t = re.sub(r"\b(km|cm|mm|m|kg|g|l|ml|min|h|s|hores|horas|hours|minuts|minutos|minutes|anys|años|years|dies|días|days)"
               r"(²|³|\^2|\^3)?(\s*/\s*(h|s|min))?\b", " ", t)
    t = t.replace("²", "**2").replace("³", "**3").replace("^", "**").replace("×", "*").replace("·", "*").replace("x", "*")
    t = t.replace("−", "-").replace("–", "-").replace("π", "*pi").replace("√", "*sqrt")
    t = re.sub(r"(\d),(\d)", r"\1.\2", t)
    t = re.sub(r"sqrt\s*(\d+(\.\d+)?)", r"sqrt(\1)", t)
    t = re.sub(r"^\*", "", t.strip())
    t = re.sub(r"\(\s*\*", "(", t)
    t = re.sub(r"\s+", "", t).lstrip("*")
    if not t or not re.fullmatch(r"[\d.+\-*/()pisqrt]+", t) or re.search(r"\*\*\d{3,}", t):
        return None
    try:
        import math
        return float(eval(t, {"__builtins__": {}}, {"pi": math.pi, "sqrt": math.sqrt}))
    except Exception:
        return None


def norm_text(s):
    return re.sub(r"[\s.,;:']", "", str(s).strip().lower())


def match_option(output, options):
    out = output.strip().splitlines()[-1].strip() if output.strip() else ""
    if not out or (len(out) == 1 and out.upper() in LETTERS):
        return None
    for k in LETTERS:
        if k in options and norm_text(options[k]) and norm_text(options[k]) == norm_text(out):
            return k
    v = parse_value(out)
    if v is None:
        return None
    best, best_err = None, 1e-6
    for k in LETTERS:
        ov = parse_value(options.get(k, ""))
        if ov is None:
            continue
        err = abs(ov - v) / max(1.0, abs(ov))
        if err < best_err:
            best, best_err = k, err
    return best


def format_problem(pr):
    lines = [pr["text"].strip()]
    o = pr.get("options") or {}
    for k in LETTERS:
        if k in o and str(o[k]).strip():
            lines.append(f"{k}) {o[k]}")
    return "\n".join(lines)


def extract_code(text):
    m = re.search(r"```(?:python)?\s*\n(.*?)```", text, re.S)
    if m:
        return m.group(1)
    m = re.search(r"```(?:python)?\s*\n(.*)$", text, re.S)
    return m.group(1) if m else text


# ----------------------------------------------------------------------------- servidor
class LLM:
    def __init__(self, url, tps_forzado=None):
        self.url = url.rstrip("/")
        self.tps_in, self.tps_out = 4.0, 2.5  # se afinan con los timings reales de cada respuesta
        self.forzado = tps_forzado  # (leer, escribir) para SIMULAR la placa desde el PC: fija las velocidades y suma el tiempo estimado
        if tps_forzado:
            self.tps_in, self.tps_out = tps_forzado
        self.simulado = 0.0  # segundos de placa estimados en el problema actual
        self.cacheado = 0  # tokens ya en caché dentro del problema actual (simulación)

    def chat(self, msgs, max_tokens, grammar=None, timeout=58):
        payload = {"messages": msgs, "max_tokens": max_tokens, "temperature": 0, "seed": 42, "cache_prompt": True}
        if grammar:
            payload["grammar"] = grammar
        req = urllib.request.Request(self.url + "/v1/chat/completions", json.dumps(payload).encode(), {"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            d = json.load(r)
        t = d.get("timings") or {}
        if self.forzado:
            u = d.get("usage", {})
            # caché de prefijo: el prompt de sistema (~160 tokens) siempre, y dentro del mismo problema todo lo ya procesado
            pt, ct = u.get("prompt_tokens", 0), u.get("completion_tokens", 0)
            nuevos = max(0, pt - max(160, self.cacheado))
            self.simulado += nuevos / self.tps_in + ct / self.tps_out + 0.5
            self.cacheado = pt + ct
        else:
            if t.get("prompt_per_second") and t.get("prompt_n", 0) > 20:
                self.tps_in = 0.7 * self.tps_in + 0.3 * t["prompt_per_second"]
            if t.get("predicted_per_second") and t.get("predicted_n", 0) > 5:
                self.tps_out = 0.7 * self.tps_out + 0.3 * t["predicted_per_second"]
        return d["choices"][0]["message"]["content"], d.get("usage", {})

    def warm(self):
        try:
            self.chat([{"role": "system", "content": SYSTEM_CODE}, {"role": "user", "content": "1 + 1 = ?\nA) 1\nB) 2\nC) 3\nD) 4\nE) 5"}], 8)
        except Exception:
            pass


def run_code(code, segundos, mem_mb=256):
    code = re.sub(r"(?<=\d),(?=\d)", ".", code)
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8") as f:
        f.write(PRELUDIO + code)
        path = f.name
    pre = None
    if os.name != "nt":
        def pre():  # noqa: E306
            import resource
            resource.setrlimit(resource.RLIMIT_AS, (mem_mb * 1024 * 1024, mem_mb * 1024 * 1024))
            os.setsid()
    try:
        r = subprocess.run([sys.executable, "-I", "-S", path], capture_output=True, text=True, timeout=max(1.0, segundos),
                           encoding="utf-8", errors="replace", preexec_fn=pre)
        return r.stdout
    except Exception:
        return ""
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


# ----------------------------------------------------------------------------- duplicados de train
def huella(pr):
    nums = tuple(re.findall(r"\d+(?:[.,]\d+)?", pr.get("text", "")))
    o = pr.get("options") or {}
    opts = tuple(norm_text(o.get(k, "")) for k in LETTERS)
    return nums, opts


def cargar_huellas(path):
    tabla = {}
    try:
        for l in open(path, encoding="utf-8"):
            if l.strip():
                r = json.loads(l)
                if len(r.get("options") or {}) == 5 and len(huella(r)[0]) >= 2:
                    tabla[huella(r)] = r["label"]
    except Exception:
        pass
    return tabla


# ----------------------------------------------------------------------------- resolver
def resolver(pr, llm, huellas, limite):
    t0 = time.time()
    llm.simulado, llm.cacheado = 0.0, 0
    opts = {k: v for k, v in (pr.get("options") or {}).items() if str(v).strip()}
    restante = (lambda: limite - llm.simulado) if llm.forzado else (lambda: limite - (time.time() - t0))  # noqa: E731
    if len(opts) == 5 and huella(pr) in huellas and len(huella(pr)[0]) >= 3:
        return huellas[huella(pr)], "duplicado"
    user = format_problem(pr)
    n_user = max(20, len(user) // 3)
    # 1) programa corto: tokens que caben tras leer el enunciado, con margen para ejecutar y casar
    disponibles = restante() - n_user / llm.tps_in - 4  # 4 s para ejecutar el programa y casar
    n_pred = int(min(220, max(40, disponibles * llm.tps_out)))
    if disponibles < 10:  # no da tiempo ni a un programa mínimo: directo a la reserva
        text = ""
        if RESERVA == "mediana" and len(opts) == 5:
            vals = {k: parse_value(v) for k, v in opts.items()}
            if all(v is not None for v in vals.values()) and len(set(vals.values())) == 5:
                return sorted(LETTERS, key=lambda k: vals[k])[2], "mediana"
        return "C", "sin_tiempo"
    msgs = [{"role": "system", "content": SYSTEM_CODE}, {"role": "user", "content": user}]
    text = ""
    try:
        text, _ = llm.chat(msgs, n_pred, timeout=max(5, restante() - 2))
        code = extract_code(text)
        out = run_code(code, min(3.0, max(1.0, restante() - 3)))
        letra = match_option(out, opts) if opts else None
        if letra:
            return letra, "python"
    except Exception:
        pass
    # 2) valor razonado si queda tiempo para ~120 tokens
    if restante() > 120 / llm.tps_out + n_user / llm.tps_in + 4 and opts:
        try:
            n_pred = int(min(260, (restante() - n_user / llm.tps_in - 4) * llm.tps_out))
            t2, _ = llm.chat([{"role": "system", "content": SYSTEM_VALOR}, {"role": "user", "content": user}], n_pred, timeout=max(5, restante() - 2))
            m = re.search(r"Final answer:\s*(.+)", t2)
            if m:
                letra = match_option(m.group(1).strip(), opts)
                if letra:
                    return letra, "valor"
            m = re.findall(r"Answer:\s*\**\s*\(?([A-E])\b", t2)
            if m:
                return m[-1], "valor_letra"
        except Exception:
            pass
    # 3) reserva: mediana de las opciones numéricas (28-30 % en train/val) o letra del modelo con gramática (12-18 %, azar)
    if RESERVA == "mediana" and len(opts) == 5:
        vals = {k: parse_value(v) for k, v in opts.items()}
        if all(v is not None for v in vals.values()) and len(set(vals.values())) == 5:
            return sorted(LETTERS, key=lambda k: vals[k])[2], "mediana"
    try:
        if restante() > 3:
            t3, _ = llm.chat(msgs + [{"role": "assistant", "content": text or "..."}, {"role": "user", "content": "Answer letter:"}], 1,
                             grammar="root ::= [A-E]", timeout=max(3, restante() - 1))
            a = t3.strip()[:1]
            if a in LETTERS:
                return a, "letra"
    except Exception:
        pass
    return "C", "defecto"


RESERVA = os.environ.get("RESERVA", "letra")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--input", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--url", default=os.environ.get("LLM_URL", "http://127.0.0.1:8080"))
    p.add_argument("--limite", type=float, default=56.0, help="segundos útiles por problema (60 menos margen)")
    p.add_argument("--train", default=os.path.join(HERE, "data", "train.jsonl"), help="para el atajo de duplicados")
    p.add_argument("--tps-forzado", default="", help="simular la placa desde el PC: 'leer,escribir' tokens/s, p. ej. 3.8,2.5")
    p.add_argument("--reserva", default=os.environ.get("RESERVA", "letra"), choices=["letra", "mediana"], help="qué contestar si el programa no casa")
    args = p.parse_args()
    global RESERVA
    RESERVA = args.reserva
    llm = LLM(args.url, tuple(float(x) for x in args.tps_forzado.split(",")) if args.tps_forzado else None)
    llm.warm()
    huellas = cargar_huellas(args.train)
    with open(args.input, encoding="utf-8") as f:
        problems = [json.loads(l) for l in f if l.strip()]
    with open(args.output, "w", newline="", encoding="utf-8") as out:
        w = csv.writer(out)
        w.writerow(["id", "language", "answer", "seconds", "status"])
        for n, pr in enumerate(problems, 1):
            t0 = time.time()
            try:
                a, via = resolver(pr, llm, huellas, args.limite)
            except Exception as exc:  # noqa: BLE001
                a, via = "C", f"error:{type(exc).__name__}"
            if a not in LETTERS:
                a = "C"
            seg = llm.simulado if llm.forzado else time.time() - t0
            w.writerow([pr.get("id", ""), pr.get("language", ""), a, f"{seg:.1f}", via])
            out.flush()
            print(f"[{n}/{len(problems)}] {pr.get('id')} -> {a} en {seg:.1f} s ({via}; lee {llm.tps_in:.1f}, escribe {llm.tps_out:.1f} tok/s)", file=sys.stderr, flush=True)


if __name__ == "__main__":
    main()
