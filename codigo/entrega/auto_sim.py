"""Espera a que cada modelo candidato termine en su máquina, baja su GGUF, lo sirve en la torre y pasa la simulación de
placa (predict.py sobre la demo a 4,6/2,7 tok/s). Escribe el resultado en entrega/candidatos.txt.
Una sola instancia a la vez: todas usan el puerto 8095.

python -X utf8 auto_sim.py "1:17b_lora32_v2" "4:2b_lora32" "2:17b_auto2_pub" "3:17b_v2_lr2e4" ...

La descarga va en trozos de 200 MB con reintentos y comprobación md5: el enlace de algunas máquinas se corta a mitad
de un scp de 2 GB y deja un fichero truncado.
"""
import concurrent.futures
import hashlib
import re
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, r"D:\Datathon_A\nube")
import nube  # noqa: E402

HERE = Path(__file__).resolve().parent
SALIDA = Path(r"D:\Datathon_A\modelos_entrenados")
SERVER = r"D:\Datathon_A\herramientas\llama-win-b12308\cuda\llama-server.exe"
PY = sys.executable
pendientes = [a.split(":", 1) for a in sys.argv[1:]]
hechos = set()
try:  # los ya simulados (en val_sims.txt) no se repiten al relanzar
    _vistos = open(HERE / "val_sims.txt", encoding="utf-8").read()
    hechos = {n for _, n in pendientes if f" val_{n} reserva=" in _vistos}
except OSError:
    pass


def log(msg):
    print(msg, flush=True)
    with open(HERE / "candidatos.txt", "a", encoding="utf-8") as f:
        f.write(time.strftime("%H:%M ") + msg + "\n")


def md5(path):
    h = hashlib.md5()
    with open(path, "rb") as f:
        for blk in iter(lambda: f.read(1 << 22), b""):
            h.update(blk)
    return h.hexdigest()


def bajar(m, remoto, dst):
    """Trocea en la máquina, baja los trozos en paralelo con reintentos, junta y comprueba el md5."""
    rdir = f"/root/trozos/{dst.stem}"
    info = nube.ssh(m["id"], f"mkdir -p {rdir} && cd {rdir} && ( [ -f hecho ] || ( rm -f trozo_* && split -b 200M -d -a 3 {remoto} trozo_ "
                             f"&& md5sum {remoto} | cut -d' ' -f1 > md5 && touch hecho ) ) && echo MD5 $(cat md5) && stat -c 'TROZO %n %s' trozo_*",
                    timeout=900)
    suma = re.search(r"MD5 ([0-9a-f]{32})", info).group(1)
    trozos = re.findall(r"TROZO (trozo_\d+) (\d+)", info)
    ldir = SALIDA / "trozos" / dst.stem
    ldir.mkdir(parents=True, exist_ok=True)

    def uno(t):
        nombre, tam = t
        local = ldir / nombre
        for _ in range(6):
            if local.exists() and local.stat().st_size == int(tam):
                return
            try:
                nube.scp(m["id"], [f"{rdir}/{nombre}"], str(local), upload=False)
            except Exception:  # noqa: BLE001
                time.sleep(5)
        if not (local.exists() and local.stat().st_size == int(tam)):
            raise RuntimeError(f"trozo {nombre} incompleto")

    with concurrent.futures.ThreadPoolExecutor(4) as ex:
        list(ex.map(uno, trozos))
    part = dst.with_suffix(".part")
    with open(part, "wb") as out:
        for nombre, _ in trozos:
            out.write((ldir / nombre).read_bytes())
    if md5(part) != suma:
        part.unlink()
        for f in ldir.iterdir():
            f.unlink()
        raise RuntimeError("md5 distinto")
    part.rename(dst)
    for f in ldir.iterdir():
        f.unlink()
    ldir.rmdir()
    nube.ssh(m["id"], f"rm -rf {rdir}", timeout=60)


def simular(dst, nombre):
    srv = subprocess.Popen([SERVER, "-m", str(dst), "--host", "127.0.0.1", "--port", "8095", "--threads", "4", "--ctx-size", "4096",
                            "--parallel", "1", "--cache-ram", "0", "--jinja", "--reasoning", "off", "--reasoning-budget", "0", "-ngl", "99"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(60):
            try:
                with urllib.request.urlopen("http://127.0.0.1:8095/health", timeout=3) as r:
                    if b"ok" in r.read():
                        break
            except Exception:  # noqa: BLE001
                time.sleep(3)
        lineas = []
        for nom, extra in ((nombre, []), (f"val_{nombre}", ["--demo", r"D:\Datathon_A\demo\val_ec_texto.jsonl"])):
            r = subprocess.run([PY, "-X", "utf8", str(HERE / "sim_demo.py"), "http://127.0.0.1:8095", nom, "--reserva", "mediana"] + extra,
                               capture_output=True, text=True, encoding="utf-8", errors="replace")
            lineas.append((r.stdout.strip().splitlines() or ["(sin salida)"])[-1])
        with open(HERE / "val_sims.txt", "a", encoding="utf-8") as f:
            f.write(time.strftime("%H:%M ") + lineas[1] + "\n")
        return "\n      ".join(lineas)
    finally:
        srv.terminate()
        srv.wait()


LISTA = HERE / "candidatos_lista.txt"  # una línea «maq:nombre» por candidato; se relee en cada vuelta
while True:
    try:
        for l in open(LISTA, encoding="utf-8"):
            if ":" in l and not l.startswith("#") and l.strip().split(":", 1) not in pendientes:
                pendientes.append(l.strip().split(":", 1))
    except OSError:
        pass
    for maq, nombre in pendientes:
        if nombre in hechos:
            continue
        m = nube.state().get(maq)
        if not m:
            hechos.add(nombre)
            continue
        try:
            estado = nube.ssh(m["id"], "cat /root/res/ESTADO 2>/dev/null; ls /root/salidas/%s/modelo-Q8_0.gguf 2>/dev/null" % nombre, timeout=60)
        except Exception:  # noqa: BLE001
            continue
        if f"{nombre}: FALLO" in estado:
            log(f"{nombre}: FALLO en M{maq}")
            hechos.add(nombre)
            continue
        if f"{nombre}: exportado" not in estado or "modelo-Q8_0.gguf" not in estado:
            continue
        dst = SALIDA / f"{nombre}-Q8_0.gguf"
        try:
            if not dst.exists():
                t0 = time.time()
                bajar(m, f"/root/salidas/{nombre}/modelo-Q8_0.gguf", dst)
                print(f"{nombre}: bajado en {time.time() - t0:.0f} s", flush=True)
        except Exception as exc:  # noqa: BLE001
            log(f"{nombre}: error al bajar, reintento ({str(exc)[:80]})")
            continue
        log(simular(dst, nombre))
        hechos.add(nombre)
    time.sleep(60)
log("auto_sim: fin")
