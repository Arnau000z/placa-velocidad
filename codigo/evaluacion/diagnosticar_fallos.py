"""Diagnóstico de cada fallo de texto del modelo líder con un modelo abierto de Helmcode (deepseek-v4-flash): causa,
explicación corta y la pista mínima (≤10 palabras, sin la respuesta) que habría llevado al modelo pequeño al programa bueno.
Un diagnóstico por problema (id): la fila en inglés si falló, si no la catalana.

python -X utf8 diagnosticar_fallos.py fallos_lider.jsonl diagnosticos.jsonl
"""
import concurrent.futures
import json
import re
import sys

sys.path.insert(0, r"D:\Datathon_A\sintetico")
import helmcode  # noqa: E402

CAUSAS = ["lee_mal_enunciado", "planteamiento_equivocado", "error_de_codigo_o_calculo", "no_conoce_el_metodo",
          "necesita_dibujo_o_figura", "programa_largo_sin_terminar", "etiqueta_dudosa"]
PROMPT = """A small 1.7B model must solve this math competition problem by writing a SHORT Python program whose printed
value is matched against the options. It failed. Diagnose why.

PROBLEM:
{texto}
OPTIONS: {opciones}
CORRECT ANSWER: {label}) {valor}

SMALL MODEL'S PROGRAM(S) AND OUTPUT(S):
{programas}

Reply with JSON only:
{{"causa": one of {causas},
 "explicacion": "<=20 words in Spanish: what exactly went wrong",
 "pista": "<=10 English words that would steer the small model to a correct short program, WITHOUT the answer or any number of it",
 "generica": true if the pista is a general lesson useful for many problems (e.g. 'count overlaps once'), false if it only fits this problem}}"""

entrada, salida = sys.argv[1], sys.argv[2]
fallos = [json.loads(l) for l in open(entrada, encoding="utf-8") if l.strip()]
por_id = {}
for f in fallos:
    if f["id"] not in por_id or f["language"] == "eng":
        por_id[f["id"]] = f


def uno(f):
    progs = "\n".join(f"--- program {i + 1}:\n{p}\n--- output: {(s or '(nothing)').strip()[-200:]}"
                      for i, (p, s) in enumerate(zip(f["programas"], f["salidas"] + [""] * 9))) or "(no program: ran out of time)"
    msg = PROMPT.format(texto=f["text"].strip(), opciones=json.dumps(f["options"], ensure_ascii=False), label=f["label"],
                        valor=f["options"].get(f["label"], "?"), programas=progs, causas=CAUSAS)
    try:
        out, _ = helmcode.chat("deepseek-v4-flash", [{"role": "user", "content": msg}], max_tokens=300)
        d = json.loads(re.search(r"\{.*\}", out, re.S).group(0))
    except Exception as exc:  # noqa: BLE001
        return {"id": f["id"], "error": str(exc)[:100]}
    d.update({"id": f["id"], "language": f["language"], "conjunto": f["conjunto"], "tipo": f["tipo"], "level": f["level"]})
    return d


with open(salida, "w", encoding="utf-8", newline="\n") as fo, concurrent.futures.ThreadPoolExecutor(8) as ex:
    for d in ex.map(uno, por_id.values()):
        fo.write(json.dumps(d, ensure_ascii=False) + "\n")
print(len(por_id), "diagnósticos en", salida)
