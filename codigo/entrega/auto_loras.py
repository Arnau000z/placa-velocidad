"""Baja el adaptador LoRA de cada candidato de candidatos_lista.txt en cuanto su máquina lo exporta (para las sopas).
Se queda en bucle; los ajustes completos (sin carpeta lora) se ignoran. python -X utf8 auto_loras.py"""
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, r"D:\Datathon_A\nube")
import nube  # noqa: E402

HERE = Path(__file__).resolve().parent
DEST = Path(r"D:\Datathon_A\modelos_entrenados\loras")
BAJAR = str(HERE / "bajar_loras.py")
hechos = set()
while True:
    for l in open(HERE / "candidatos_lista.txt", encoding="utf-8"):
        if ":" not in l or l.startswith("#"):
            continue
        maq, nombre = l.strip().split(":", 1)
        if nombre in hechos or (DEST / nombre / "adapter_model.safetensors").exists() or "full" in nombre:
            hechos.add(nombre)
            continue
        m = nube.state().get(maq)
        if not m:
            continue
        try:
            st = nube.ssh(m["id"], f"cat /root/res/ESTADO; ls /root/salidas/{nombre}/lora/adapter_model.safetensors 2>/dev/null", timeout=60)
        except Exception:  # noqa: BLE001
            continue
        if f"{nombre}: exportado" in st and "adapter_model.safetensors" in st:
            r = subprocess.run([sys.executable, "-X", "utf8", BAJAR, f"{maq}:{nombre}"], capture_output=True, text=True, encoding="utf-8", errors="replace")
            print(time.strftime("%H:%M"), nombre, (r.stdout.strip().splitlines() or ["?"])[-1], flush=True)
    time.sleep(120)
