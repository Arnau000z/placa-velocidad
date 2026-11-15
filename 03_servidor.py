#!/usr/bin/env python3
"""Velocidad real en las condiciones de predict.py: llama-server con los ajustes del reto, el prompt de sistema del equipo
cacheado y un enunciado nuevo en cada petición. Es lo que de verdad cuenta en los 60 s de cada problema.

python3 03_servidor.py [--modelos a.gguf b.gguf] [--n 4] [--escribir 64]

Para cada modelo: tiempo de carga, memoria, y por petición cuántos tokens nuevos lee y a qué velocidad, y a qué velocidad
escribe. La primera petición lee también el prompt de sistema (frío); las demás lo tienen en caché.
"""
import argparse
import json
import os
import statistics
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib_servidor as L  # noqa: E402

p = argparse.ArgumentParser()
p.add_argument("--modelos", nargs="+", default=[L.PRINCIPAL])
p.add_argument("--n", type=int, default=4, help="peticiones por modelo")
p.add_argument("--escribir", type=int, default=64, help="tokens que escribe en cada petición")
p.add_argument("--problemas", default=os.path.join(L.DATOS, "val.jsonl"))
args = p.parse_args()

pred, ruta_pred = L.cargar_predict()
if pred:
    SYSTEM = pred.SYSTEM_CODE
    formato = pred.format_problem
    print(f"  prompt de sistema de {ruta_pred}")
else:
    print(f"  (no encuentro {ruta_pred}: uso un prompt de sistema genérico)")
    SYSTEM = "You solve Kangaroo math competition problems by writing a short Python 3 program. Output only the code inside one ```python block."

    def formato(pr):
        return pr["text"].strip() + "\n" + "\n".join(f"{k}) {v}" for k, v in pr["options"].items())

problemas, origen = L.cargar_problemas(args.problemas, args.n)
salida = open(os.path.join(L.RES, "servidor.jsonl"), "a", encoding="utf-8")

for nombre in args.modelos:
    modelo = L.ruta_modelo(nombre)
    base = os.path.basename(modelo).removesuffix(".gguf")
    if not os.path.exists(modelo):
        print(f"  (no está {base}, lo salto)")
        continue
    print(f"==> {base}: arrancando llama-server en el puerto {L.PUERTO}")
    try:
        with L.Servidor(modelo, os.path.join(L.RES, f"servidor_{base}.log")) as s:
            print(f"  cargado en {s.carga_s:.0f} s · el servidor ocupa {s.rss_mb} MB · quedan {s.mem_libre_mb} MB libres")
            if s.system_info:
                print("  " + s.system_info[:200])
            filas = []
            for i, pr in enumerate(problemas):
                msgs = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": formato(pr)}]
                payload = {"messages": msgs, "max_tokens": args.escribir, "temperature": 0, "seed": 42,
                           "cache_prompt": True, "ignore_eos": True}
                t0 = time.time()
                d = L.post(s.url + "/v1/chat/completions", payload)
                pared = time.time() - t0
                t = d.get("timings") or {}
                fila = {"modelo": base, "i": i, "frio": i == 0, "problema": pr.get("id"),
                        "tokens_prompt": (d.get("usage") or {}).get("prompt_tokens"), "cacheados": t.get("cache_n"),
                        "leidos": t.get("prompt_n"), "lee_tps": t.get("prompt_per_second"), "lee_s": (t.get("prompt_ms") or 0) / 1000,
                        "escritos": t.get("predicted_n"), "escribe_tps": t.get("predicted_per_second"),
                        "escribe_s": (t.get("predicted_ms") or 0) / 1000, "pared_s": pared,
                        "carga_s": s.carga_s, "rss_mb": s.rss_mb, "mem_libre_mb": s.mem_libre_mb, "system_info": s.system_info}
                filas.append(fila)
                salida.write(json.dumps(fila, ensure_ascii=False) + "\n")
                salida.flush()
                print(f"  [{i + 1}/{len(problemas)}] {'frío ' if i == 0 else 'caché'} lee {fila['leidos']} tokens a {fila['lee_tps'] or 0:.2f} t/s "
                      f"({fila['lee_s']:.1f} s) · escribe {fila['escritos']} a {fila['escribe_tps'] or 0:.2f} t/s ({fila['escribe_s']:.1f} s) · total {pared:.1f} s")
            calientes = [f for f in filas if not f["frio"]] or filas
            lee = statistics.mean(f["lee_tps"] or 0 for f in calientes)
            esc = statistics.mean(f["escribe_tps"] or 0 for f in calientes)
            nuevos = statistics.mean(f["leidos"] or 0 for f in calientes)
            print(f"  ==> {base}: con el sistema en caché lee {lee:.2f} t/s ({nuevos:.0f} tokens nuevos por problema) y escribe {esc:.2f} t/s")
    except Exception as e:  # noqa: BLE001
        print(f"  FALLO con {base}: {e}")
print(f"  OK    {os.path.join(L.RES, 'servidor.jsonl')}  (problemas: {origen})")
