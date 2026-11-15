"""Campaña de fine-tuning del Datathon en una máquina de vast.ai .

python nube.py ofertas                 # mejores gráficas de 80 GB o más ahora mismo (no alquila)
python nube.py alquilar [id_oferta]    # alquila una (la mejor calidad/precio si no se da id)
python nube.py arrancar [trabajos...]  # sube el paquete, prepara la máquina y lanza los trabajos de configs.json
python nube.py progreso                # qué va haciendo (ESTADO, gráfica, resumen de exámenes)
python nube.py vigilar                 # cada 2 min; al ver FIN trae /root/res y borra la máquina
python nube.py traer                   # baja /root/res a nube_res/ sin borrar
python nube.py ssh "comando"           # ejecutar algo a mano
python nube.py borrar                  # destruye la máquina (deja de cobrar)
Variables: DT_GPU_RAM (80), DT_MAX_DPH (1.6), DT_DISK (200), DT_GPU (nombre exacto de gráfica).
"""
from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import tarfile
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent  # D:\Datathon_A
REPO = ROOT / "datathon-UPC-maths-qualcomm-arduino-unoq"
VASTAI = r"C:\Users\arnau\AppData\Roaming\Python\Python310\Scripts\vastai.exe"
KEY = Path.home() / ".ssh/vast_ed25519"
STATE = HERE / "maquinas.json"
IMAGE = "pytorch/pytorch:2.11.0-cuda12.8-cudnn9-devel"


def vast(*args: str) -> object:
    out = subprocess.run([VASTAI, *args, "--raw"], capture_output=True, text=True, encoding="utf-8")
    if out.returncode:
        raise SystemExit(f"vastai {' '.join(args)}: {out.stderr or out.stdout}")
    try:
        return json.loads(out.stdout)
    except json.JSONDecodeError:
        return out.stdout


def state() -> dict:
    return json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {}


def save(data: dict) -> None:
    STATE.write_text(json.dumps(data, indent=1), encoding="utf-8")


def ssh_target(instance_id: str) -> tuple[str, str]:
    info = vast("show", "instance", instance_id)
    host, port = info.get("ssh_host"), str(info.get("ssh_port"))
    direct = (info.get("ports") or {}).get("22/tcp")
    proxy = any(m.get("id") == str(instance_id) and m.get("proxy") for m in state().values())
    if direct and info.get("public_ipaddr") and not proxy:
        host, port = info["public_ipaddr"].strip(), str(direct[0]["HostPort"])
    return host, port


def ssh(instance_id: str, command: str, timeout: int = 120) -> str:
    host, port = ssh_target(instance_id)
    out = subprocess.run(
        ["ssh", "-i", str(KEY), "-p", port, "-o", "StrictHostKeyChecking=accept-new", "-o", "ConnectTimeout=20",
         "-o", "BatchMode=yes", f"root@{host}", command],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)
    return (out.stdout + out.stderr).strip()


def scp(instance_id: str, sources: list[str], dest: str, upload: bool = True) -> None:
    host, port = ssh_target(instance_id)
    base = ["scp", "-i", str(KEY), "-P", port, "-o", "StrictHostKeyChecking=accept-new", "-o", "BatchMode=yes"]
    args = base + sources + [f"root@{host}:{dest}"] if upload else base + [f"root@{host}:{s}" for s in sources] + [dest]
    subprocess.run(args, check=True, timeout=900)


def offers() -> list[dict]:
    gpu = os.environ.get("DT_GPU", "")
    query = (f"{'gpu_name=' + gpu + ' ' if gpu else ''}gpu_ram>={os.environ.get('DT_GPU_RAM', '80')} num_gpus=1 verified=true "
             f"rentable=true reliability>0.99 inet_down>=400 disk_space>={os.environ.get('DT_DISK', '200')} cuda_max_good>=12.8 "
             f"direct_port_count>=1 dph_total<={os.environ.get('DT_MAX_DPH', '1.6')}")
    found = [o for o in vast("search", "offers", query, "-o", "dph_total") if not o["gpu_name"].startswith("CMP")]
    found.sort(key=lambda o: -(o.get("dlperf") or 0) / max(o["dph_total"], 0.01))
    return found


def bundle() -> Path:
    """Repo (sin .git, imágenes ni results), datos, experimentos (scripts, explicaciones, código) y nube/."""
    buf = io.BytesIO()

    def keep(t):
        name = t.name.replace("\\", "/")
        if any(x in name for x in ("/.git/", "__pycache__", "/data/images", "/results/", "_ocr.jsonl", "/resultados/python_",
                                   "/resultados/ragexpl_", "/lotes/", "/lotes2/", "/lotes3/")):
            return None
        return t

    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        tar.add(REPO, arcname="repo", filter=keep)
        tar.add(REPO / "data" / "index_m3.db", arcname="repo/data/index_m3.db")
        tar.add(ROOT / "experimentos", arcname="experimentos", filter=keep)
        tar.add(HERE, arcname="nube", filter=lambda t: None if t.name.endswith((".tgz", "maquinas.json", "vigia.log")) else keep(t))
    out = HERE / "bundle.tgz"
    out.write_bytes(buf.getvalue())
    return out


def main() -> None:
    action = sys.argv[1] if len(sys.argv) > 1 else "estado"
    data = state()
    if action == "ofertas":
        for o in offers()[:12]:
            print(f"{o['id']:>10} {o['gpu_name']} {o['gpu_ram'] / 1024:.0f} GB {o['dph_total']:.3f} $/h  {o.get('geolocation')}  "
                  f"bajada {int(o['inet_down'])} Mb/s  fiab {o['reliability']:.3f}  DLP/$ {(o.get('dlperf') or 0) / o['dph_total']:.0f}")
    elif action == "alquilar":
        pub = KEY.with_suffix(".pub").read_text().strip()
        found = {str(o["id"]): o for o in offers()}
        wanted = sys.argv[2:]
        chosen = [found[w] for w in wanted if w in found] if wanted else list(found.values())[:1]
        if not chosen:
            raise SystemExit("No encuentro ninguna oferta con esos filtros")
        offer = chosen[0]
        onstart = f"mkdir -p /root/.ssh && echo '{pub}' >> /root/.ssh/authorized_keys && chmod 600 /root/.ssh/authorized_keys"
        result = vast("create", "instance", str(offer["id"]), "--image", IMAGE, "--disk", os.environ.get("DT_DISK", "200"), "--ssh",
                      "--direct", "--label", "datathon-ft", "--cancel-unavail", "--onstart-cmd", onstart)
        instance_id = str(result["new_contract"])
        data["1"] = {"id": instance_id, "precio": offer["dph_total"], "sitio": offer.get("geolocation"), "gpu": offer["gpu_name"]}
        save(data)
        vast("attach", "ssh", instance_id, pub)
        print(f"máquina: {instance_id} · {offer['gpu_name']} · {offer['dph_total']:.3f} $/h · {offer.get('geolocation')}")
    elif action == "estado":
        for job, m in data.items():
            info = vast("show", "instance", m["id"])
            print(f"máquina {job}: {m['id']} {info.get('actual_status')} · {info.get('gpu_name')} · {info.get('dph_total', 0):.3f} $/h")
        if not data:
            print("ninguna máquina alquilada")
    elif action == "arrancar":
        if not data:
            raise SystemExit("primero: python nube.py alquilar")
        jobs = " ".join(sys.argv[2:])
        path = bundle()
        print(f"paquete: {path.stat().st_size / 1e6:.0f} MB")
        pub = KEY.with_suffix(".pub").read_text().strip()
        m = data["1"]
        denied = 0
        while True:
            try:
                if vast("show", "instance", m["id"]).get("actual_status") == "running" and "ok" in ssh(m["id"], "echo ok"):
                    break
            except Exception as exc:  # noqa: BLE001
                if "Permission denied" in str(exc):
                    denied += 1
                    if denied % 4 == 0:
                        vast("attach", "ssh", m["id"], pub)
            time.sleep(15)
        print("máquina responde; subiendo paquete", flush=True)
        scp(m["id"], [str(path)], "/root/bundle.tgz")
        ssh(m["id"], "mkdir -p /root/dt /root/res && tar -xzf /root/bundle.tgz -C /root/dt && sed -i 's/\\r$//' /root/dt/nube/*.sh")
        # preparar (10-15 min: compila llama.cpp con CUDA) y, al LISTO, lanzar los trabajos; todo en segundo plano
        print(ssh(m["id"], "nohup bash -c 'bash /root/dt/nube/preparar_remoto.sh; grep -q LISTO /root/preparar.log && "
                           f"python3 /root/dt/nube/lanzar.py {jobs} > /root/res/lanzar.out 2>&1' > /root/arranque.out 2>&1 < /dev/null & echo lanzado"))
    elif action == "progreso":
        for job, m in data.items():
            print(ssh(m["id"], "tail -n2 /root/preparar.log; echo ---; cat /root/res/ESTADO 2>/dev/null; echo ---; "
                               "nvidia-smi --query-gpu=utilization.gpu,memory.used,memory.total --format=csv,noheader; echo ---; "
                               "cat /root/res/resumen.txt 2>/dev/null; ls /root/res/FIN 2>/dev/null; "
                               "for f in /root/res/entreno_*.log; do [ -f $f ] && echo \"$f: $(tr '\\r' '\\n' < $f | grep -aoE '[0-9]+/[0-9]+ \\[[0-9:]+<' | tail -1)\"; done"))
    elif action == "traer":
        for job, m in data.items():
            folder = HERE / "nube_res" / time.strftime("%Y%m%d-%H%M")
            folder.mkdir(parents=True, exist_ok=True)
            ssh(m["id"], "cd /root/res && tar -czf /root/res.tgz . ; cd /root/salidas && ls */*.gguf 2>/dev/null > /root/res/ggufs.txt", timeout=300)
            scp(m["id"], ["/root/res.tgz"], str(folder / "res.tgz"), upload=False)
            with tarfile.open(folder / "res.tgz") as tar:
                tar.extractall(folder)
            (folder / "res.tgz").unlink()
            print(f"resultados en {folder}")
    elif action == "gguf":
        # python nube.py gguf <trabajo> <Q8_0|Q4_0>: baja ese modelo a modelos_entrenados/
        name, q = sys.argv[2], sys.argv[3]
        dest = ROOT / "modelos_entrenados"
        dest.mkdir(exist_ok=True)
        scp(data["1"]["id"], [f"/root/salidas/{name}/modelo-{q}.gguf"], str(dest / f"{name}-{q}.gguf"), upload=False)
        print(dest / f"{name}-{q}.gguf")
    elif action == "vigilar":
        while data:
            m = data["1"]
            try:
                out = ssh(m["id"], "[ -f /root/res/FIN ] && echo 1 || echo 0; grep -c FALLO /root/res/ESTADO 2>/dev/null || echo 0").split()
            except Exception as exc:  # noqa: BLE001
                print("ssh:", exc)
                time.sleep(120)
                continue
            if out[:1] == ["1"]:
                main_traer = [sys.argv[0], "traer"]
                sys.argv = main_traer
                main()
                print("FIN; borrada:", vast("destroy", "instance", m["id"], "-y"))
                data.pop("1")
                save(data)
                return
            if len(out) > 1 and out[1] != "0":
                print("hay un FALLO; mirar con progreso (la máquina sigue encendida)")
                return
            time.sleep(120)
    elif action == "ssh":
        print(ssh(data["1"]["id"], sys.argv[2], timeout=600))
    elif action == "borrar":
        for job, m in list(data.items()):
            print(job, vast("destroy", "instance", m["id"], "-y"))
            data.pop(job)
        save(data)
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
