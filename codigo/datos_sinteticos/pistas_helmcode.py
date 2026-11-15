"""Pista de 3-8 palabras (tipo de problema + método) para cada problema, con un modelo abierto de Helmcode.
Sirve para medir si una «chuleta» mínima ayuda al modelo afinado: primero pista del propio problema (techo, oráculo);
si ayuda, pistas de train recuperadas por parecido (lo realista).

python -X utf8 pistas_helmcode.py <entrada.jsonl> <salida.jsonl> [modelo=deepseek-v4-flash] [hilos=8]
"""
import concurrent.futures
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import helmcode  # noqa: E402

PROMPT = ("Read this math competition problem. In 3 to 8 English words, name the problem type and the method a short "
          "Python program should use to solve it (examples: 'counting: enumerate all cases with itertools', "
          "'parity invariant: simulate moves', 'digits: brute force over all numbers'). Do NOT give the answer, "
          "any number from the problem, or any explanation. Reply with the words only.\n\n")

entrada, salida = sys.argv[1], sys.argv[2]
modelo = sys.argv[3] if len(sys.argv) > 3 else "deepseek-v4-flash"
hilos = int(sys.argv[4]) if len(sys.argv) > 4 else 8
rows = [json.loads(l) for l in open(entrada, encoding="utf-8") if l.strip()]
hechos = set()
if Path(salida).exists():
    hechos = {(r["id"], r["language"]) for r in (json.loads(l) for l in open(salida, encoding="utf-8") if l.strip())}
pend = [r for r in rows if (r["id"], r["language"]) not in hechos]


def uno(r):
    o = r.get("options") or {}
    txt = r["text"].strip() + "\n" + "\n".join(f"{k}) {o[k]}" for k in "ABCDE" if k in o)
    try:
        out, _ = helmcode.chat(modelo, [{"role": "user", "content": PROMPT + txt}], max_tokens=40)
    except Exception as exc:  # noqa: BLE001
        return None, str(exc)[:80]
    p = re.sub(r"\s+", " ", out.strip().strip("'\"").splitlines()[0] if out.strip() else "")
    p = " ".join(p.split()[:10])
    return {"id": r["id"], "language": r["language"], "pista": p}, None


n = 0
with open(salida, "a", encoding="utf-8", newline="\n") as f, concurrent.futures.ThreadPoolExecutor(hilos) as ex:
    for res, err in ex.map(uno, pend):
        if res and res["pista"]:
            f.write(json.dumps(res, ensure_ascii=False) + "\n")
            f.flush()
            n += 1
        elif err:
            print("error:", err, flush=True)
print(f"{n} pistas nuevas en {salida}", flush=True)
