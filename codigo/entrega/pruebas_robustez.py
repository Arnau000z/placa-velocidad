"""Batería de pruebas del sistema congelado (predict.py + sopa_z10) que no dependen de la nota:
1) formato oficial con sample_problems.jsonl del reto, 2) casos raros (sin opciones, 4 opciones, texto vacío, enunciado
enorme, opciones de texto, repetidas, unicode, sin id…), 3) determinismo (dos pasadas iguales).
python -X utf8 pruebas_robustez.py <url> <carpeta_salida>"""
import csv
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
URL, OUT = sys.argv[1], sys.argv[2]
os.makedirs(OUT, exist_ok=True)
PY = sys.executable
TRAIN = r"D:\Datathon_A\datathon-UPC-maths-qualcomm-arduino-unoq\data\train.jsonl"

raros = [
    {"id": "sin_opciones", "language": "eng", "text": "How much is 2+2?", "options": {}},
    {"id": "cuatro_opciones", "language": "eng", "text": "How much is 2+2?", "options": {"A": "3", "B": "4", "C": "5", "D": "6"}},
    {"id": "texto_vacio", "language": "cat", "text": "", "options": {"A": "1", "B": "2", "C": "3", "D": "4", "E": "5"}},
    {"id": "enorme", "language": "eng", "text": "A farmer has many fields. " * 150 + "How many fields are there if he has 7 rows of 6 fields?",
     "options": {"A": "13", "B": "36", "C": "42", "D": "48", "E": "49"}},
    {"id": "opciones_texto", "language": "eng", "text": "Which of these numbers is prime?",
     "options": {"A": "nine", "B": "fifteen", "C": "twenty-one", "D": "twenty-three", "E": "twenty-seven"}},
    {"id": "repetidas", "language": "eng", "text": "What is 3 times 3?", "options": {"A": "9", "B": "9", "C": "6", "D": "12", "E": "3"}},
    {"id": "unicode", "language": "cat", "text": "Quant val √16 + ½ · 4 − 2²?", "options": {"A": "−2", "B": "2", "C": "4", "D": "½", "E": "π"}},
    {"id": "fracciones", "language": "eng", "text": "What is 1/2 + 1/3?", "options": {"A": "2/5", "B": "5/6", "C": "1/6", "D": "1", "E": "3/5"}},
    {"id": "horas", "language": "eng", "text": "A film starts at 8:45 and lasts 95 minutes. When does it end?",
     "options": {"A": "10:10", "B": "10:20", "C": "10:30", "D": "9:55", "E": "10:00"}},
    {"id": "decimal_coma", "language": "cat", "text": "En Pau compra 3 llibretes de 2,5 € cadascuna. Quant paga?",
     "options": {"A": "5 €", "B": "6,5 €", "C": "7,5 €", "D": "8 €", "E": "10 €"}},
    {"language": "eng", "text": "Problem without id: what is 10-3?", "options": {"A": "6", "B": "7", "C": "8", "D": "9", "E": "13"}},
    {"id": "figura", "language": "eng", "text_only": False, "text": "In the figure, how many triangles are there?",
     "options": {"A": "4", "B": "5", "C": "6", "D": "8", "E": "9"}},
    {"id": "castellano", "language": "esp", "text": "¿Cuánto es 15 dividido entre 3?", "options": {"A": "3", "B": "4", "C": "5", "D": "6", "E": "45"}},
    {"id": "bucle_infinito", "language": "eng", "text": "Find the largest prime number.", "options": {"A": "97", "B": "101", "C": "997", "D": "1009", "E": "None"}},
]
f_raros = os.path.join(OUT, "raros.jsonl")
open(f_raros, "w", encoding="utf-8").write("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in raros))


def correr(entrada, salida, extra=()):
    r = subprocess.run([PY, "-X", "utf8", os.path.join(HERE, "predict.py"), "--input", entrada, "--output", salida, "--url", URL,
                        "--train", TRAIN, *extra], capture_output=True, text=True, encoding="utf-8", errors="replace")
    filas = list(csv.DictReader(open(salida, encoding="utf-8"))) if os.path.exists(salida) else []
    return r.returncode, filas, r.stderr[-500:]


def informe(nombre, rc, filas, n, err=""):
    letras_ok = all(f["answer"] in "ABCDE" and len(f["answer"]) == 1 for f in filas)
    seg = max((float(f["seconds"]) for f in filas), default=0)
    print(f"{nombre}: código {rc}, filas {len(filas)}/{n}, letras válidas {letras_ok}, máx {seg:.1f} s simulados"
          + (f"\n   stderr: {err}" if rc else ""), flush=True)
    for f in filas:
        print(f"   {f['id'][:16]:16s} {f['language']:4s} {f['answer']} {float(f['seconds']):5.1f} s  {f['status']}", flush=True)


sample = r"D:\Datathon_A\datathon-UPC-maths-qualcomm-arduino-unoq\data\sample_problems.jsonl"
n_sample = sum(1 for l in open(sample, encoding="utf-8") if l.strip())
rc, filas, err = correr(sample, os.path.join(OUT, "sample.csv"), ("--tps-forzado", "4.6,2.7"))
informe("1) sample_problems (formato oficial)", rc, filas, n_sample, err)
print("   cabecera:", open(os.path.join(OUT, "sample.csv"), encoding="utf-8").readline().strip(), flush=True)
rc, filas, err = correr(f_raros, os.path.join(OUT, "raros.csv"), ("--tps-forzado", "4.6,2.7"))
informe("2) casos raros", rc, filas, len(raros), err)
_, f1, _ = correr(sample, os.path.join(OUT, "det1.csv"), ("--tps-forzado", "4.6,2.7"))
_, f2, _ = correr(sample, os.path.join(OUT, "det2.csv"), ("--tps-forzado", "4.6,2.7"))
iguales = [a["answer"] for a in f1] == [b["answer"] for b in f2]
print(f"3) determinismo (dos pasadas de sample_problems): {'IGUALES' if iguales else 'DISTINTAS'}", flush=True)
