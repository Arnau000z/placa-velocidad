"""Generación masiva y dirigida de problemas tipo Canguro con programa, con los modelos abiertos de Helmcode.

Cada petición elige un FOCO sacado del análisis de errores del líder (17b_lora32_v2): lógica (27 % de acierto),
enunciados largos con varias condiciones (33 %), medida y tiempo (38 %), geometría sin figura (42 %), conteo con
trampas, "cuál de las opciones…", catalán y las lecciones de sus fallos reales (experimentos/analisis/diagnosticos.jsonl).

Salida: sintetico/generado_masivo/gm_<foco>_<modelo>_<n>.jsonl (los verifica verificar_masivo.py)

python -X utf8 generar_masivo.py --modelo qwen3.6 --peticiones 200 --paralelo 5 [--desde 0]
"""
import argparse
import concurrent.futures as cf
import glob
import json
import os
import random
import re
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
SAL = os.path.join(HERE, "generado_masivo")
os.makedirs(SAL, exist_ok=True)
p = argparse.ArgumentParser()
p.add_argument("--modelo", default="qwen3.6")
p.add_argument("--peticiones", type=int, default=100)
p.add_argument("--paralelo", type=int, default=5)
p.add_argument("--por-peticion", type=int, default=20)
p.add_argument("--desde", type=int, default=0, help="número de la primera petición (para no pisar ficheros)")
args = p.parse_args()
KEY = open(r"D:\Datathon_A\.helmcode_key", encoding="utf-8").read().strip()
URL = "https://api.helmcode.com/v1/chat/completions"
semillas = sorted(glob.glob(os.path.join(HERE, "semillas", "*.jsonl")))
LECCIONES = []
for l in open(r"D:\Datathon_A\experimentos\analisis\diagnosticos.jsonl", encoding="utf-8"):
    if l.strip():
        d = json.loads(l)
        if d.get("pista"):
            LECCIONES.append(d["pista"].strip().rstrip("."))
LECCIONES = sorted(set(LECCIONES))

FOCOS = {
    "logica": ("LOGIC puzzles, the student's weakest type (27 % correct): truth-tellers and liars, who sits where, who owns what, "
               "rankings and orders deduced from clues, 'exactly one of these statements is true', weekdays and birthdays from clues. "
               "The program must brute-force ALL assignments with itertools.product or permutations and check EVERY clue literally, "
               "then print the asked quantity or the exact text of the matching option."),
    "largos": ("LONG statements (70-110 words) with 3 to 5 conditions that ALL matter, where skipping any one condition gives one of "
               "the distractors (the student solves 61 % of short problems but only 33 % of long ones). The program puts each given "
               "number in a variable and checks every condition inside one loop over the candidates."),
    "medida": ("MEASUREMENT and TIME without figures (38 % correct): clocks and angles between hands, calendars and weekdays, timetables "
               "('the first bus strictly after'), speeds and meeting times, unit conversions, money and change, ages in past and "
               "future years, percentages of percentages. Watch inclusive vs exclusive ranges and 12/24-hour times."),
    "geometria": ("GEOMETRY that can be described fully in words (42 % correct): rectangles and squares cut or joined (perimeter "
                  "changes), cubes painted then cut into small cubes, grids and lattice points, coordinates, diagonals and angles of "
                  "regular polygons, areas of shapes made of unit squares, nets, Euler's formula. The program uses coordinates, "
                  "brute force over unit cells or exact formulas with Fraction."),
    "conteo": ("COUNTING with traps: ordered vs unordered pairs, 'at least' / 'at most', different digits, inclusive ranges, "
               "fence-posts, handshakes, paths on small grids, numbers with a digit property, arrangements with restrictions. "
               "The program counts by brute force with range, product, permutations or combinations, never with a hand formula."),
    "cual_opcion": ("'WHICH OF THE FOLLOWING...' problems: the five options are numbers, expressions or short statements and exactly "
                    "one satisfies the property described (is a possible value, cannot be the sum, is true for all n...). The "
                    "program tests each of the five candidates and prints the one that works, as the exact option value or text."),
    "trampas": ("Problems where one of the student's REAL mistakes decides the answer. Its lessons from real failures:\n- {lecciones}\n"
                "Design every problem so a fast reader falls into one of these traps and picks a distractor, and make the program "
                "avoid the trap explicitly."),
    "catalan": ("Problems of every type written in natural CATALAN (correct accents and Catalan vocabulary: 'quants', 'quina', "
                "'nombre', 'xifres', 'parells', 'com a mínim', 'exactament'), because the exam is half in Catalan and the student is "
                "6-8 points weaker there. Mix counting, logic, arithmetic, measurement and number theory."),
}
ORDEN = ["logica", "largos", "medida", "trampas", "geometria", "conteo", "cual_opcion", "catalan", "logica", "largos"]

BASE = """You write NEW multiple-choice math problems in the style of the Mathematical Kangaroo, each with a short Python program that solves it. They will train a small student model that answers by writing such a program.

FOCUS OF THIS BATCH: {foco}

You get real Kangaroo problems as a style reference (text, options, correct letter, level 0-7 where 0 is age 10 and 7 the last year of high school). Real Kangaroo problems are not textbook drills: there is a situation, a twist and a condition that is easy to miss.

Write {n} NEW problems (do not copy or paraphrase the references; new situations, numbers and structure), spread over levels 0-7. {idioma} Each must be solvable from the text alone (no figure). Five plausible options built from the typical mistakes (forgetting x2, counting one too many, ordered instead of unordered, perimeter instead of area). Spread the correct letter evenly over A-E. Prefer numeric options (integers, fractions like 3/4, times like 9:10, quantities with units); at most 4 of the {n} with text options.

For each problem write a Python 3 program that COMPUTES the answer from the data (never a direct print of the result): data in variables, loops to count or try cases when needed, AT MOST 8 short lines, no comments, no functions unless needed, standard library only (math, itertools, fractions and collections.Counter are already imported: permutations, combinations, product, gcd, Fraction, comb can be used directly), under one million iterations, last line print(answer) with the number or the exact text of the option (never the letter). Solve each problem yourself first and make sure the program prints exactly the marked option.

Output ONLY a JSON array of {n} objects, no prose, each exactly like:
{{"text": "...", "options": {{"A": "...", "B": "...", "C": "...", "D": "...", "E": "..."}}, "label": "C", "level": 3, "type": "counting", "language": "eng", "code": "a = 7\\nb = 12\\nprint(a * b)"}}"""


def pedir(i):
    rnd = random.Random(1000 + i)
    foco = ORDEN[i % len(ORDEN)]
    n = args.por_peticion
    texto_foco = FOCOS[foco].format(lecciones="\n- ".join(rnd.sample(LECCIONES, min(14, len(LECCIONES)))))
    if foco == "catalan":
        idioma = 'All of them in Catalan (language "cat").'
    else:
        ncat = round(n * 0.4)
        idioma = f'{ncat} of them in Catalan (language "cat", correct accents), the rest in English (language "eng").'
    sem = semillas[i % len(semillas)]
    ref = [json.loads(l) for l in open(sem, encoding="utf-8") if l.strip()]
    rnd.shuffle(ref)
    ref_txt = "\n".join(json.dumps({k: r[k] for k in ("text", "options", "label", "level", "type")}, ensure_ascii=False) for r in ref[:10])
    msgs = [{"role": "system", "content": BASE.format(foco=texto_foco, n=n, idioma=idioma)},
            {"role": "user", "content": "Reference problems:\n" + ref_txt + f"\n\nNow write the {n} new problems as a JSON array."}]
    payload = {"model": args.modelo, "messages": msgs, "max_tokens": 9000, "temperature": 0.9, "reasoning_effort": "none"}
    out = os.path.join(SAL, f"gm_{foco}_{args.modelo.replace('.', '')}_{i:04d}.jsonl")
    if os.path.exists(out):
        return foco, 0, 0, "ya estaba"
    err = ""
    for intento in range(6):
        try:
            req = urllib.request.Request(URL, json.dumps(payload).encode(),
                                         {"Content-Type": "application/json", "Authorization": f"Bearer {KEY}"})
            with urllib.request.urlopen(req, timeout=600) as r:
                d = json.load(r)
            text = d["choices"][0]["message"]["content"]
            m = re.search(r"\[.*\]", text, re.S)
            items = [it for it in (json.loads(m.group(0)) if m else []) if isinstance(it, dict)]
            with open(out, "w", encoding="utf-8") as f:
                for it in items:
                    it["foco"] = foco
                    it["generador"] = args.modelo
                    f.write(json.dumps(it, ensure_ascii=False) + "\n")
            return foco, len(items), d.get("usage", {}).get("total_tokens", 0), ""
        except urllib.error.HTTPError as exc:
            err = f"HTTP {exc.code}"
            if exc.code in (401, 402, 403):
                return foco, 0, 0, err
            time.sleep(min(90, 8 * 2 ** intento) + random.random() * 5)
        except Exception as exc:  # noqa: BLE001
            err = str(exc)[:80]
            time.sleep(5 * (intento + 1))
    return foco, 0, 0, err


t0 = time.time()
tot = toks = 0
errores = {}
por_foco = {}
with cf.ThreadPoolExecutor(args.paralelo) as ex:
    for k, (foco, n, t, err) in enumerate(ex.map(pedir, range(args.desde, args.desde + args.peticiones)), 1):
        tot += n
        toks += t
        por_foco[foco] = por_foco.get(foco, 0) + n
        if err:
            errores[err] = errores.get(err, 0) + 1
        if k % 5 == 0 or k == args.peticiones:
            print(f"  {k}/{args.peticiones} peticiones, {tot} problemas, {toks} tokens, {time.time() - t0:.0f} s, errores {errores}", flush=True)
print(f"hecho: {tot} problemas de {args.modelo} · por foco {por_foco}")
