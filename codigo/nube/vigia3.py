"""Vigía que RELLENA: cada 2 minutos mira cada máquina; si lleva 2 lecturas seguidas sin gráfica ni procesos, lanza el
siguiente trabajo de su cola (nube/cola_M<n>.txt, una línea = un comando bash remoto). Registra todo en estado_maquinas.log.

python vigia3.py [minutos=40] [maquinas=2,3,4,5]
"""
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import nube  # noqa: E402

HERE = Path(__file__).resolve().parent
minutos = int(sys.argv[1]) if len(sys.argv) > 1 else 40
maqs = (sys.argv[2] if len(sys.argv) > 2 else "2,3,4,5").split(",")
LOG = HERE / "estado_maquinas.log"
CMD = ("echo GPU $(nvidia-smi --query-gpu=utilization.gpu,memory.used --format=csv,noheader); "
       "echo PROC $(ps aux | grep -E 'curl -sS[L]|cmake --buil[d]|pip instal[l]|entrenar.p[y]|eval_variante[s]|autodestila[r]|curva.p[y]|exportar.s[h]|convert_hf_to_ggu[f]|entrenar_grp[o]|grpo_v2_m[1]|eval_v2_m[1]|grpo_2[b]|cadena_309[0]|trabajo_v[2]|trabajo_lora_[t]otal|trabajo_lora_2[b]|auto_publico[s]' | wc -l); "
       "tail -n 2 /root/res/ESTADO 2>/dev/null; for f in /root/res/auto.log /root/res/investigar.log; do [ -f $f ] && tail -n 1 $f; done; "
       "grep -ah '%  eng' /root/res/*.txt 2>/dev/null | sort -u")


def log(msg):
    print(msg, flush=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(msg + "\n")


def siguiente_trabajo(m):
    cola = HERE / f"cola_M{m}.txt"
    if not cola.exists():
        return None
    lineas = [l for l in cola.read_text(encoding="utf-8").splitlines() if l.strip() and not l.startswith("#")]
    if not lineas:
        return None
    cola.write_text("\n".join(lineas[1:]) + ("\n" if lineas[1:] else ""), encoding="utf-8")
    return lineas[0]


vistos = {m: set() for m in maqs}
paradas = {m: 0 for m in maqs}
t_fin = time.time() + minutos * 60
while True:
    for m in maqs:
        d = nube.state().get(m)
        if not d:
            continue
        try:
            out = nube.ssh(d["id"], CMD, timeout=90)
        except Exception as exc:  # noqa: BLE001
            log(f"[{time.strftime('%H:%M')} M{m}] ssh: {str(exc)[:80]}")
            continue
        lines = [l for l in out.splitlines() if l.strip() and "Welcome" not in l and "Have fun" not in l]
        gpu = next((l for l in lines if l.startswith("GPU")), "GPU ? ,")
        proc = next((l for l in lines if l.startswith("PROC")), "PROC 0")
        try:
            util = int(gpu.split()[1].rstrip("%,"))
        except Exception:  # noqa: BLE001
            util = -1
        try:
            ocupada = int(proc.split()[1])
        except Exception:  # noqa: BLE001
            ocupada = 0
        nuevas = [l for l in lines if "%  eng" in l and l not in vistos[m]]
        vistos[m].update(l for l in lines if "%  eng" in l)
        paradas[m] = paradas[m] + 1 if (util <= 2 and ocupada == 0) else 0
        estado = " · ".join(l for l in lines if not l.startswith(("GPU", "PROC")) and "%  eng" not in l)[-160:]
        msg = f"[{time.strftime('%H:%M')} M{m}] {gpu} {proc} | {estado}"
        if nuevas:
            msg += "\n   NUEVO: " + "\n   NUEVO: ".join(l.strip()[:150] for l in nuevas)
        if paradas[m] >= 2:
            trabajo = siguiente_trabajo(m)
            if trabajo:
                try:
                    nube.ssh(d["id"], f"setsid nohup bash -c {trabajo!r} > /root/res/cola_{int(time.time())}.log 2>&1 < /dev/null & echo lanzado", timeout=60)
                    msg += f"\n   LANZADO en M{m}: {trabajo[:120]}"
                    paradas[m] = 0
                except Exception as exc:  # noqa: BLE001
                    msg += f"\n   ERROR al lanzar en M{m}: {str(exc)[:100]}"
            else:
                msg += f"\n   AVISO: M{m} parada ({paradas[m]} lecturas) y SIN COLA"
        log(msg)
    if time.time() >= t_fin:
        break
    time.sleep(120)
log("fin del vigía")
