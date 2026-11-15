#!/usr/bin/env python3
"""EXPERIMENTO (no es el predict.py congelado): segunda opinion (VERIFICA=1). predict.py del equipo (fuera del repo oficial; se copia a la placa junto a copilot/ si hace falta).

    python3 predict.py --input problems.jsonl --output predictions.csv [--url http://127.0.0.1:8080] [--limite 56]

Por problema (≤ 60 s, sin red), con el 1.7B en llama-server (prefijo de sistema cacheado):
  0. ¿Es un duplicado de train con las mismas opciones? → su etiqueta (mismas 5 opciones y enunciado parecido), ~2 ms.
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
        self.tps_in, self.tps_out = 4.6, 2.7  # medido en la UNO Q con el 1.7B Q4_0 (15/11); se afinan con los timings reales
        self.forzado = tps_forzado  # (leer, escribir) para SIMULAR la placa desde el PC: fija las velocidades y suma el tiempo estimado
        if tps_forzado:
            self.tps_in, self.tps_out = tps_forzado
        self.simulado = 0.0  # segundos de placa estimados en el problema actual
        self.cacheado = 0  # tokens ya en caché dentro del problema actual (simulación)

    def chat(self, msgs, max_tokens, grammar=None, timeout=58, stop=None, temperature=0.0, seed=42):
        payload = {"messages": msgs, "max_tokens": max_tokens, "temperature": temperature, "seed": seed, "cache_prompt": True}
        if grammar:
            payload["grammar"] = grammar
        if stop:
            payload["stop"] = stop
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

    def warm(self, espera=300):
        """Espera a que el servidor responda /health y deja el prompt de sistema en la caché (la 1.ª lectura en frío tarda >60 s)."""
        t0 = time.time()
        while time.time() - t0 < espera:
            try:
                with urllib.request.urlopen(self.url + "/health", timeout=5) as r:
                    if b"ok" in r.read():
                        break
            except Exception:
                time.sleep(2)
        tps = (self.tps_in, self.tps_out)
        try:
            forzado, self.forzado = self.forzado, None  # el calentamiento no cuenta como tiempo de problema
            self.chat([{"role": "system", "content": SYSTEM_CODE}, {"role": "user", "content": "1 + 1 = ?\nA) 1\nB) 2\nC) 3\nD) 4\nE) 5"}], 1,
                      grammar="root ::= [A-E]", timeout=240)
        except Exception:
            pass
        finally:
            self.forzado = forzado
            if forzado:
                self.tps_in, self.tps_out = tps


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
NUM_INICIAL = re.compile(r"^\s*\d+\s*[.):-]\s*")


def _texto_dup(t):
    """Enunciado sin el número del problema (cambia entre niveles), sin acentos y solo letras y cifras."""
    import unicodedata
    t = unicodedata.normalize("NFKD", NUM_INICIAL.sub("", t or "").lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", t).strip()


def _opciones_dup(pr):
    o = pr.get("options") or {}
    if len(o) != 5:
        return None
    t = tuple(norm_text(o.get(k, "")) for k in LETTERS)
    return t if all(t) else None


def cargar_huellas(path):
    """{5 opciones normalizadas: [(enunciado normalizado, etiqueta), ...]} de train."""
    tabla = {}
    try:
        for l in open(path, encoding="utf-8"):
            if l.strip():
                r = json.loads(l)
                o = _opciones_dup(r)
                if o and r.get("label") in LETTERS:
                    tabla.setdefault(o, []).append((_texto_dup(r.get("text")), r["label"]))
    except Exception:
        pass
    return tabla


def buscar_duplicado(pr, tabla, umbral=0.6):
    """Letra de un problema de train con EXACTAMENTE las mismas 5 opciones y enunciado parecido (difflib >= 0,6), o None.
    Si dos candidatos casi empatados tienen etiquetas distintas, no contesta. En val: 13 contestados, 13 correctos, ~2 ms."""
    try:
        import difflib
        o = _opciones_dup(pr)
        if not o or o not in tabla:
            return None
        q = _texto_dup(pr.get("text"))
        cand = [(difflib.SequenceMatcher(None, q, t).ratio(), lab) for t, lab in tabla[o]]
        mejor = max(c[0] for c in cand)
        if mejor < umbral:
            return None
        letras = {lab for r, lab in cand if r >= mejor - 0.05}
        return letras.pop() if len(letras) == 1 else None
    except Exception:
        return None


class Buscador:
    """Pista del problema de train más parecido: TF-IDF de palabras (sin el número del problema ni cifras), coseno."""

    def __init__(self, train_path, pistas_path, umbral):
        import collections
        import math
        self.umbral = umbral
        pistas = {r["id"]: r["pista"] for r in (json.loads(l) for l in open(pistas_path, encoding="utf-8") if l.strip())}
        docs = []
        for l in open(train_path, encoding="utf-8"):
            if l.strip():
                r = json.loads(l)
                if r.get("id") in pistas:
                    docs.append((pistas[r["id"]], collections.Counter(self._tok(r.get("text")))))
        df = collections.Counter(w for _, c in docs for w in c)
        self.idf = {w: math.log(len(docs) / n) for w, n in df.items()}
        self.indice = collections.defaultdict(list)
        self.pistas = []
        for i, (pista, c) in enumerate(docs):
            v = {w: (1 + math.log(n)) * self.idf[w] for w, n in c.items()}
            norma = math.sqrt(sum(x * x for x in v.values())) or 1.0
            for w, x in v.items():
                self.indice[w].append((i, x / norma))
            self.pistas.append(pista)

    @staticmethod
    def _tok(t):
        return [w for w in _texto_dup(t).split() if len(w) > 2 and not w.isdigit()]

    def pista(self, pr):
        import collections
        import math
        try:
            c = collections.Counter(self._tok(pr.get("text")))
            v = {w: (1 + math.log(n)) * self.idf[w] for w, n in c.items() if w in self.idf}
            norma = math.sqrt(sum(x * x for x in v.values())) or 1.0
            puntos = collections.defaultdict(float)
            for w, x in v.items():
                for i, y in self.indice[w]:
                    puntos[i] += x / norma * y
            if not puntos:
                return None
            i, sim = max(puntos.items(), key=lambda kv: kv[1])
            return self.pistas[i] if sim >= self.umbral else None
        except Exception:  # noqa: BLE001
            return None


BUSCADOR = None  # experimento: se carga en main si PISTAS_TRAIN está definido


# ----------------------------------------------------------------------------- resolver
LOG = None  # fichero JSONL con lo que escribe el modelo en cada problema (para ver por qué fallan los programas)


def gramatica_letras(opts, modo):
    """Gramática de la letra de reserva. 'descarte': si las 5 opciones son números distintos, quita los dos extremos (el menor
    y el mayor son la respuesta solo el 10 % y el 13 % de las veces en el Canguro) y deja elegir al modelo entre las 3 centrales."""
    if modo == "descarte" and len(opts) == 5:
        vals = {k: parse_value(v) for k, v in opts.items()}
        if all(v is not None for v in vals.values()) and len(set(vals.values())) == 5:
            centrales = sorted(LETTERS, key=lambda k: vals[k])[1:4]
            return "root ::= [" + "".join(sorted(centrales)) + "]"
    return "root ::= [A-E]"


def reserva(opts, letra_modelo):
    """Qué contestar si no hay programa que case. 'mediana': si las 5 opciones son números distintos, la del medio (en el
    Canguro la correcta es la central el ~30 % de las veces y los extremos solo el 10-13 %); si no, la letra del modelo o D.
    Ojo: el modelo afinado contesta casi siempre la misma letra sin razonar, así que su letra vale como una constante."""
    if RESERVA == "mediana" and len(opts) == 5:
        vals = {k: parse_value(v) for k, v in opts.items()}
        if all(v is not None for v in vals.values()) and len(set(vals.values())) == 5:
            return sorted(LETTERS, key=lambda k: vals[k])[2], "mediana"
    # Opciones de texto (o números repetidos): la E. En M3Kang-train es la letra más frecuente en esos casos (23 % frente
    # al 20 % de la A que dice siempre el modelo afinado); en val de texto eng+cat, vía letra: E 12/22 frente a A 4/22.
    if RESERVA_TEXTO != "modelo":
        return RESERVA_TEXTO, "letra_" + RESERVA_TEXTO
    return letra_modelo or os.environ.get("FALLBACK_ANSWER", "D"), "letra"


def resolver(pr, llm, huellas, limite):
    t0 = time.time()
    llm.simulado, llm.cacheado = 0.0, 0
    opts = {k: v for k, v in (pr.get("options") or {}).items() if str(v).strip()}
    restante = (lambda: limite - llm.simulado) if llm.forzado else (lambda: limite - (time.time() - t0))  # noqa: E731
    traza = {"id": pr.get("id"), "language": pr.get("language")}
    dup = buscar_duplicado(pr, huellas)
    if dup:
        return dup, "duplicado", traza
    if not opts:
        return os.environ.get("FALLBACK_ANSWER", "D"), "sin_opciones", traza
    contenido = format_problem(pr)
    pista = PISTAS.get(pr.get("id")) or (BUSCADOR.pista(pr) if BUSCADOR else None)
    if pista:
        contenido += "\nHint: " + pista
        traza["pista"] = pista
    msgs = [{"role": "system", "content": SYSTEM_CODE}, {"role": "user", "content": contenido}]
    # 1) PRIMERO la letra (1 token, con gramática): cuesta solo leer el enunciado (~13-15 s) y deja la lectura en caché
    #    para el programa. Así siempre hay una letra del modelo de reserva aunque el programa no termine.
    letra_modelo = None
    try:
        t1, _ = llm.chat(msgs, 1, grammar=gramatica_letras(opts, RESERVA), timeout=max(5, restante() - 1))
        letra_modelo = t1.strip()[:1] if t1.strip()[:1] in LETTERS else None
    except Exception:
        pass
    traza["letra"] = letra_modelo
    # 2) problemas con figura: el programa no puede verla; nos quedamos con la letra (ahorra ~40 s)
    if pr.get("text_only") is False and os.environ.get("FIGURA_PROGRAMA", "1") != "1":  # 15/11: con la sopa, figura 2/20 → 4/20
        a, via = reserva(opts, letra_modelo)
        return a, via + "_figura", traza
    # 3) programa con el mismo prompt que la letra (caché: no se relee el enunciado) y parada al cerrar el bloque.
    #    Si no casa y queda tiempo, otro intento muestreado (los programas buenos son cortos: ~50 tokens, ~18 s).
    constante = None
    for intento in range(1 + REINTENTOS):
        disponibles = restante() - 4  # 4 s para ejecutar el programa y casar
        n_pred = int(min(220, disponibles * llm.tps_out))
        if n_pred < (25 if intento == 0 else 45):
            break
        try:
            text, _ = llm.chat(msgs, n_pred, stop=["\n```"], timeout=max(5, restante() - 2),
                               temperature=0.0 if intento == 0 else 0.7, seed=42 + intento)
            code = extract_code(text + "\n```")
            traza.setdefault("programas", []).append(code[-1500:])
            out = run_code(code, min(3.0, max(1.0, restante() - 1)))
            traza.setdefault("salidas", []).append(out[-300:])
            letra = match_option(out, opts)
            if letra and RECHAZA_CONSTANTE and imprime_constante(code):
                # el programa no calcula: acaba en print(48). Casan y aciertan solo el 31 % (63/205 en las simulaciones)
                # frente al 75 % de los que calculan → se guarda como candidata y se pide otro programa
                constante = constante or letra
                continue
            if letra and VERIFICA:
                # segunda opinion: si sobra tiempo, otros programas a T=0,7; gana la letra con mas votos (empate: el primero)
                votos = [letra]
                for extra in range(VERIFICA_MAX):
                    disp2 = restante() - 4
                    n2 = int(min(160, disp2 * llm.tps_out))
                    if n2 < 45:
                        break
                    try:
                        t2, _ = llm.chat(msgs, n2, stop=[FIN_BLOQUE], timeout=max(5, restante() - 2), temperature=0.7, seed=100 + extra)
                        c2 = extract_code(t2 + FIN_BLOQUE)
                        o2 = run_code(c2, min(3.0, max(1.0, restante() - 1)))
                        l2 = match_option(o2, opts)
                        traza.setdefault("verifica", []).append([c2[-400:], o2[-60:], l2])
                        if l2 and not imprime_constante(c2):
                            votos.append(l2)
                    except Exception:  # noqa: BLE001
                        break
                    if len(votos) >= 2 and votos[-1] == votos[0]:
                        break  # confirmada
                cuenta = {v: votos.count(v) for v in votos}
                mejor = max(cuenta, key=lambda v: (cuenta[v], v == votos[0]))
                return mejor, ("python" if mejor == votos[0] else "python_verificada"), traza
            if letra:
                return letra, "python" if intento == 0 else f"python{intento + 1}", traza
        except Exception as exc:  # noqa: BLE001
            traza["error"] = type(exc).__name__
    if constante:
        return constante, "python_constante", traza
    a, via = reserva(opts, letra_modelo)
    return a, via, traza


RESERVA = os.environ.get("RESERVA", "mediana")
RECHAZA_CONSTANTE = os.environ.get("RECHAZA_CONSTANTE", "1") == "1"
VERIFICA = os.environ.get("VERIFICA", "1") == "1"
VERIFICA_MAX = int(os.environ.get("VERIFICA_MAX", "2"))
FIN_BLOQUE = chr(10) + "```"
_CONSTANTE = re.compile(r"print\(\s*(-?\d+(\.\d+)?|\"[^\"]*\"|'[^']*')\s*\)")


def imprime_constante(code):
    """¿La última línea del programa imprime un literal (no calcula)?"""
    lineas = [x.strip() for x in (code or "").splitlines() if x.strip()]
    return bool(lineas) and bool(_CONSTANTE.fullmatch(lineas[-1]))
REINTENTOS = int(os.environ.get("REINTENTOS", "2"))
RESERVA_TEXTO = os.environ.get("RESERVA_TEXTO", "E")  # letra de reserva si las opciones no son 5 números distintos; "modelo" = la del modelo
PISTAS = {}  # experimento: PISTAS=<jsonl con {id, pista}> → "Hint: ..." tras las opciones (apagado si no se da)
try:
    if os.environ.get("PISTAS"):
        PISTAS = {r["id"]: r["pista"] for r in (json.loads(l) for l in open(os.environ["PISTAS"], encoding="utf-8") if l.strip())}
except Exception:  # noqa: BLE001
    PISTAS = {}


def puerto_oficial():
    """LLM_PORT del config.env del repo oficial (8081 en la placa); si no se encuentra, 8081."""
    for c in (os.path.join(HERE, "config.env"), os.path.join(HERE, "..", "config.env"),
              os.path.expanduser("~/datathon-UPC-maths-qualcomm-arduino-unoq/config.env")):
        try:
            for l in open(c, encoding="utf-8"):
                if l.strip().startswith("LLM_PORT="):
                    return l.split("=", 1)[1].split("#")[0].strip()
        except OSError:
            pass
    return os.environ.get("LLM_PORT", "8081")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--input", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--url", default=os.environ.get("LLM_URL", f"http://127.0.0.1:{puerto_oficial()}"))
    p.add_argument("--limite", type=float, default=56.0, help="segundos útiles por problema (60 menos margen)")
    p.add_argument("--train", default=os.path.join(HERE, "data", "train.jsonl"), help="para el atajo de duplicados")
    p.add_argument("--tps-forzado", default="", help="simular la placa desde el PC: 'leer,escribir' tokens/s, p. ej. 3.8,2.5")
    p.add_argument("--reserva", default=os.environ.get("RESERVA", "mediana"), choices=["letra", "descarte", "mediana"],
                   help="letra de reserva: el modelo elige entre las 5 (letra) o entre las 3 centrales si son números (descarte)")
    p.add_argument("--log", default="", help="JSONL con lo que escribe el modelo en cada problema (por defecto <output>.log.jsonl)")
    args = p.parse_args()
    global RESERVA
    RESERVA = args.reserva
    llm = LLM(args.url, tuple(float(x) for x in args.tps_forzado.split(",")) if args.tps_forzado else None)
    llm.warm()
    huellas = cargar_huellas(args.train)
    global BUSCADOR
    try:
        if os.environ.get("PISTAS_TRAIN"):
            BUSCADOR = Buscador(args.train, os.environ["PISTAS_TRAIN"], float(os.environ.get("PISTAS_UMBRAL", "0.2")))
    except Exception:  # noqa: BLE001
        BUSCADOR = None
    with open(args.input, encoding="utf-8") as f:
        problems = [json.loads(l) for l in f if l.strip()]
    with open(args.output, "w", newline="", encoding="utf-8") as out:
        w = csv.writer(out)
        w.writerow(["id", "language", "answer", "seconds", "status"])
        for n, pr in enumerate(problems, 1):
            t0 = time.time()
            traza = {"id": pr.get("id")}
            try:
                a, via, traza = resolver(pr, llm, huellas, args.limite)
            except Exception as exc:  # noqa: BLE001
                a, via = os.environ.get("FALLBACK_ANSWER", "D"), f"error:{type(exc).__name__}"
            if a not in LETTERS:
                a = os.environ.get("FALLBACK_ANSWER", "D")
            seg = llm.simulado if llm.forzado else time.time() - t0
            w.writerow([pr.get("id", ""), pr.get("language", ""), a, f"{seg:.1f}", via])
            out.flush()
            traza.update({"respuesta": a, "via": via, "segundos": round(seg, 1)})
            with open(args.log or args.output + ".log.jsonl", "a", encoding="utf-8") as lf:
                lf.write(json.dumps(traza, ensure_ascii=False) + "\n")
            print(f"[{n}/{len(problems)}] {pr.get('id')} -> {a} en {seg:.1f} s ({via}; lee {llm.tps_in:.1f}, escribe {llm.tps_out:.1f} tok/s)", file=sys.stderr, flush=True)


if __name__ == "__main__":
    main()
