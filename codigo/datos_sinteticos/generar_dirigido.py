"""(DIRIGIDO: con la lista de errores típicos del modelo líder, experimentos/analisis/diagnosticos.jsonl)
Genera problemas sintéticos tipo Canguro con los modelos abiertos de Helmcode (API compatible con OpenAI, clave del
hackathon en D:\\Datathon_A\\.helmcode_key). Cada petición: ~18 problemas semilla → 20 problemas nuevos con programa.
Salida: sintetico/generado/gen_hc_<modelo>_<n>.jsonl (los verifica después verificar_sintetico.py).

python -X utf8 generar_helmcode.py --modelo deepseek-v4-flash --peticiones 60 --paralelo 8
"""
import argparse
import concurrent.futures as cf
import glob
import json
import os
import random
import re
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
p = argparse.ArgumentParser()
p.add_argument("--modelo", default="deepseek-v4-flash")
p.add_argument("--peticiones", type=int, default=20)
p.add_argument("--paralelo", type=int, default=6)
p.add_argument("--por-peticion", type=int, default=20)
p.add_argument("--catalan", type=float, default=0.25)
args = p.parse_args()
KEY = open(r"D:\Datathon_A\.helmcode_key", encoding="utf-8").read().strip()
URL = "https://api.helmcode.com/v1/chat/completions"
semillas = sorted(glob.glob(os.path.join(HERE, "semillas", "*.jsonl")))

INSTRUCCIONES = """You write NEW Kangaroo-style (Mathematical Kangaroo) multiple-choice math problems with a short Python program that solves each one.

You are given real Kangaroo problems as a style reference (text, options, correct letter, level 0-7 where 0 is age 10 and 7 is the last year of high school, type). Real Kangaroo problems are not textbook drills: they have a situation, a twist, and a condition that is easy to miss when reading fast.

Write {n} NEW problems (do not copy or paraphrase the references; change situations, numbers and structure), spread over levels 0-7 and over the types (algebra, counting, arithmetic, number_theory, geometry without figure, logic, measurement, patterns, probability). {cat} of them in Catalan (language "cat", correct accents), the rest in English (language "eng"). Each must be solvable from the text alone (no figure), 25-90 words, with the typical Kangaroo traps ("at least", "different", "on each side", "in pairs", "not counting the first", working backwards, parity, extreme cases). At least half must need two or more reasoning steps or trying cases. The five options must be plausible distractors of typical mistakes, and the correct letter must be spread evenly over A-E across the {n} problems. Options should be numeric (numbers, fractions like 3/4, times like 9:10, quantities with units); at most 3 of the {n} with text options.

For each problem write a Python 3 program that COMPUTES the answer from the data (never a direct print of the number): variables with the data, loops to count or try cases when needed, at most 10 lines, no comments, no functions unless needed, standard library only (math, itertools and fractions are already imported: permutations, combinations, gcd, Fraction, comb can be used directly), ending in a print of the value (number or exact text of the option, not the letter). Solve each problem yourself first; the program's output must equal the marked option.



The student model that will learn from your programs makes these modelling mistakes (lessons from its real failures):
- Add years to every age, then compare sums
- Appending digit d: new number equals 10*x + d
- Avoid integer division; consider all subsets and compare products as fractions
- Chain ratios through the shared middle term before summing
- Check all three triangle inequalities, not just one
- Check denominator factors: only 2s and 5s give terminating decimals
- Check triangle inequality: each side less than sum of other two
- Close parentheses and print max of all five values
- Close syntax and print the found value
- Convert PM time to 24-hour format, then take result modulo 24
- Count unordered pairs once, not both orders
- Derive order from constraints, then index the sorted result
- Each edge belongs to two faces, so count shared coverage
- Encode each person's statement as a local constraint on neighbors
- Enforce total value constraint, not just coin count
- Find neighbors of the target in the sorted list, then subtract them
- Find the smallest departure time strictly after arrival
- For the last element of the first half, use index n//2 - 1
- Generate house numbers skipping any containing the forbidden digit, then pick the nth
- Generate terms iteratively using the recurrence rule, then sum
- Let pair sums equal twice the given pair averages
- Loop over both coin types and check exact sum
- Maximize sum of the assignment, not loop index
- Print each evaluation and the final selected option
- Product of x and y means x*y, not x squared
- Read each exchange direction carefully; set ratios so units cancel
- Relate perimeters before and after cutting; the cut adds two equal sides
- Replace literal 8 with a variable and compare values
- Set each expression equal to same k, then solve for each variable
- Set equation new_num/denominator_ratio equals double original fraction
- Set up one equation with two unknowns and solve for their ratio
- Substitute x and its reciprocal to form a two-equation system
- Sum actual element values, not bit positions
- Test all options symbolically or with multiple odd pairs
- Track operation order step by step, grouping each result before next operation
- Track positions carefully; the loop count must match the target index
- Translate each phrase into an equation about remaining amount
- Translate each phrase to an equation literally, term by term
- Translate each statement into a constraint on men and women counts
- Translate fractions to operations on the whole crowd, not fixed counts
- Trust the program's printed output; verify arithmetic carefully
- Try each plate as removed, test all almond amounts
- Use Euler: V - E + F = 2 for polyhedra
- Use age/role constraints, not name string comparisons
- Use itertools.permutations to assign all cards, then filter
- Use symbolic variables and equations, not fixed integer lists
- Use total sums: three-class total and four-class total, then subtract
- Write complete short code that prints one result per option
Design every problem so that one of these traps decides the answer (a fast reader would pick a distractor), and make the program avoid the trap explicitly: encode EVERY condition of the statement (prefer brute force over all cases with a check of each condition, exact Fractions, "strictly"/"at least" exactly as written, unordered vs ordered as asked).

Output ONLY a JSON array of {n} objects, no prose, each exactly like:
{{"text": "...", "options": {{"A": "...", "B": "...", "C": "...", "D": "...", "E": "..."}}, "label": "C", "level": 3, "type": "counting", "language": "eng", "code": "a = 7\\nb = 12\\nprint(a * b)"}}"""


def pedir(i):
    sem = semillas[i % len(semillas)]
    ref = [json.loads(l) for l in open(sem, encoding="utf-8") if l.strip()]
    random.Random(i).shuffle(ref)
    ref_txt = "\n".join(json.dumps({k: r[k] for k in ("text", "options", "label", "level", "type")}, ensure_ascii=False) for r in ref[:12])
    n = args.por_peticion
    msgs = [{"role": "system", "content": INSTRUCCIONES.format(n=n, cat=max(1, round(n * args.catalan)))},
            {"role": "user", "content": "Reference problems:\n" + ref_txt + f"\n\nNow write the {n} new problems as a JSON array."}]
    payload = {"model": args.modelo, "messages": msgs, "max_tokens": 9000, "temperature": 0.9, "reasoning_effort": "none"}
    for intento in range(3):
        try:
            req = urllib.request.Request(URL, json.dumps(payload).encode(), {"Content-Type": "application/json", "Authorization": f"Bearer {KEY}"})
            with urllib.request.urlopen(req, timeout=600) as r:
                d = json.load(r)
            text = d["choices"][0]["message"]["content"]
            m = re.search(r"\[.*\]", text, re.S)
            items = json.loads(m.group(0)) if m else []
            out = os.path.join(HERE, "generado", f"gen_dir_{args.modelo.replace('.', '')}_{i:03d}.jsonl")
            with open(out, "w", encoding="utf-8") as f:
                for it in items:
                    if isinstance(it, dict):
                        f.write(json.dumps(it, ensure_ascii=False) + "\n")
            return len(items), d.get("usage", {}).get("total_tokens", 0)
        except Exception as exc:  # noqa: BLE001
            err = str(exc)[:120]
            time.sleep(5 * (intento + 1))
    return 0, 0


t0 = time.time()
tot = toks = 0
with cf.ThreadPoolExecutor(args.paralelo) as ex:
    for k, (n, t) in enumerate(ex.map(pedir, range(args.peticiones)), 1):
        tot += n
        toks += t
        if k % 5 == 0 or k == args.peticiones:
            print(f"  {k}/{args.peticiones} peticiones, {tot} problemas, {toks} tokens, {time.time() - t0:.0f} s", flush=True)
print(f"hecho: {tot} problemas de {args.modelo}")
