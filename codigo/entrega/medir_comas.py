"""¿Cuánto pierde predict.py por cambiar las comas entre cifras por puntos ANTES de ejecutar? Rompe código válido como
permutations([1,2,3,4]) → [1.2.3.4] (error de sintaxis, salida vacía). Re-ejecuta los programas guardados en los
registros de la simulación: primero tal cual y, si no imprime nada, con las comas cambiadas (para 2,5 → 2.5).
python -X utf8 medir_comas.py <log_demo> <log_val>"""
import json
import re
import sys

sys.path.insert(0, r"D:\Datathon_A\entrega")
import predict  # noqa: E402

DATOS = {0: r"D:\Datathon_A\demo\train.jsonl", 1: r"D:\Datathon_A\demo\val_ec_texto.jsonl"}


def run_crudo(code, seg=3.0):
    """Igual que predict.run_code pero sin tocar las comas."""
    import os
    import subprocess
    import tempfile
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8") as f:
        f.write(predict.PRELUDIO + code)
        path = f.name
    try:
        r = subprocess.run([sys.executable, "-I", "-S", path], capture_output=True, text=True, timeout=seg, encoding="utf-8", errors="replace")
        return r.stdout
    except Exception:  # noqa: BLE001
        return ""
    finally:
        os.unlink(path)


for i, log in enumerate(sys.argv[1:3]):
    prs = {(r["id"], r["language"]): r for r in map(json.loads, open(DATOS[i], encoding="utf-8"))}
    antes = despues = n = rotos = 0
    for t in map(json.loads, open(log, encoding="utf-8")):
        if t["via"] == "duplicado":
            continue
        n += 1
        pr = prs[(t["id"], t["language"])]
        opts = {k: v for k, v in pr["options"].items() if str(v).strip()}
        resp = "E" if t["via"] in ("letra", "letra_figura") else t["respuesta"]
        antes += resp == pr["label"]
        progs = t.get("programas") or []
        if progs and not t["via"].startswith("python"):
            code = progs[0]
            if re.search(r"(?<=\d),(?=\d)", code):
                out = run_crudo(code)
                if out.strip():
                    rotos += 1
                    letra = predict.match_option(out, opts)
                    if letra and not predict.imprime_constante(code):
                        resp = letra
        despues += resp == pr["label"]
    print(f"{log[:40]:40s} filas {n}: ahora {antes}, sin romper comas {despues} (programas que el arreglo hace funcionar: {rotos})")
