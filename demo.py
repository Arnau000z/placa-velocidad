#!/usr/bin/env python3
"""Demo en directo en la placa: un problema cada vez, con lo que hace el sistema por dentro.

    python3 demo.py                       los 6 problemas de problemas_demo.jsonl (inventados por el equipo)
    python3 demo.py otro.jsonl            otros problemas (mismo formato que el examen)
    python3 demo.py --seguido             sin esperar a Enter entre problemas

Para cada problema ejecuta el predict.py de verdad (el que correrá el jurado) contra el servicio math-llm de la
placa y enseña el enunciado, la letra rápida, el programa que escribe el modelo, lo que imprime, la respuesta y los
segundos. Solo biblioteca estándar.
"""
import csv
import json
import os
import subprocess
import sys
import tempfile
import textwrap
import threading
import time

AQUI = os.path.dirname(os.path.abspath(__file__))
RETO = os.environ.get("RETO", os.path.expanduser("~/datathon-UPC-maths-qualcomm-arduino-unoq"))
PREDICT = os.path.join(RETO, "predict.py") if os.path.exists(os.path.join(RETO, "predict.py")) else os.path.join(AQUI, "equipo", "predict.py")

B, D, R = "\033[1m", "\033[2m", "\033[0m"
AZUL, VIOLETA, VERDE, ROJO, AMARILLO = "\033[38;5;33m", "\033[38;5;135m", "\033[38;5;35m", "\033[38;5;203m", "\033[38;5;214m"
ANCHO = 78


def caja(titulo, lineas, color):
    print(f"{color}┌─ {B}{titulo}{R}{color} " + "─" * max(0, ANCHO - len(titulo) - 3) + f"┐{R}")
    for ln in lineas:
        sangria = len(ln) - len(ln.lstrip(" "))
        trozos = textwrap.wrap(ln, ANCHO - 2, subsequent_indent=" " * sangria, drop_whitespace=False) or [""]
        for trozo in trozos:
            print(f"{color}│{R} {trozo.ljust(ANCHO - 1)}{color}│{R}")
    print(f"{color}└" + "─" * ANCHO + f"┘{R}")


def reloj(parar, t0):
    while not parar.is_set():
        s = time.time() - t0
        barra = "█" * int(min(s, 60) / 60 * 40)
        print(f"\r  {D}pensando{R} {s:5.1f} s  {AMARILLO}{barra.ljust(40, '·')}{R} 60 s", end="", flush=True)
        time.sleep(0.2)
    print("\r" + " " * 70 + "\r", end="")


def resolver(pr):
    with tempfile.TemporaryDirectory() as tmp:
        entrada, salida = os.path.join(tmp, "p.jsonl"), os.path.join(tmp, "r.csv")
        with open(entrada, "w", encoding="utf-8") as f:
            f.write(json.dumps({k: v for k, v in pr.items() if k != "label"}, ensure_ascii=False) + "\n")
        parar, t0 = threading.Event(), time.time()
        hilo = threading.Thread(target=reloj, args=(parar, t0), daemon=True)
        hilo.start()
        subprocess.run([sys.executable, PREDICT, "--input", entrada, "--output", salida], cwd=os.path.dirname(PREDICT),
                       capture_output=True, text=True)
        parar.set()
        hilo.join()
        fila = next(csv.DictReader(open(salida, encoding="utf-8")), {})
        log = {}
        if os.path.exists(salida + ".log.jsonl"):
            lineas = [l for l in open(salida + ".log.jsonl", encoding="utf-8") if l.strip()]
            log = json.loads(lineas[-1]) if lineas else {}
        return fila, log, time.time() - t0


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    seguido = "--seguido" in sys.argv
    fichero = args[0] if args else os.path.join(AQUI, "problemas_demo.jsonl")
    problemas = [json.loads(l) for l in open(fichero, encoding="utf-8") if l.strip()]
    print(f"\n{B}Copiloto de matemáticas · Arduino UNO Q · sin red{R}")
    print(f"{D}predict.py: {PREDICT}{R}\n")
    bien = total = 0
    for n, pr in enumerate(problemas, 1):
        opciones = [f"{k}) {v}" for k, v in (pr.get("options") or {}).items()]
        caja(f"Problema {n}/{len(problemas)} · {pr.get('language', '')}", [pr["text"], ""] + opciones, AZUL)
        if not seguido:
            input(f"  {D}Enter para resolverlo…{R}")
        fila, log, pared = resolver(pr)
        letra = fila.get("answer", "?")
        segundos = float(fila.get("seconds") or pared)
        if log.get("letra"):
            print(f"  {VIOLETA}1 · Letra rápida del modelo (1 token):{R} {log['letra']}")
        for i, (prog, sal) in enumerate(zip(log.get("programas") or [], log.get("salidas") or [])):
            caja(f"2 · Programa que escribe el modelo{' (otro intento)' if i else ''}", prog.rstrip().splitlines(), VIOLETA)
            print(f"  {AZUL}3 · Lo ejecuta la CPU e imprime:{R} {B}{(sal or '').strip() or '(nada)'}{R}")
        via = fila.get("status", log.get("via", ""))
        print(f"  {AZUL}4 · Vía:{R} {via}")
        ok = pr.get("label") == letra if pr.get("label") else None
        marca = f"{VERDE}✔ correcta{R}" if ok else (f"{ROJO}✘ la buena era {pr.get('label')}{R}" if ok is False else "")
        print(f"\n  {B}Respuesta: {letra}{R}  ({pr.get('options', {}).get(letra, '')})  {marca}   {D}{segundos:.1f} s de 60{R}\n")
        total += 1
        bien += bool(ok)
    if total:
        print(f"{B}{bien}/{total} correctas{R}\n")


if __name__ == "__main__":
    main()
