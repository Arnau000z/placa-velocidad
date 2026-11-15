"""Baja adaptadores LoRA (comprimidos, md5) de las máquinas: python bajar_loras.py 1:17b_lora32_v2 3:17b_v2_lr2e4 ..."""
import hashlib
import re
import sys
import tarfile
from pathlib import Path

sys.path.insert(0, r"D:\Datathon_A\nube")
import nube  # noqa: E402

dest = Path(r"D:\Datathon_A\modelos_entrenados\loras")
dest.mkdir(exist_ok=True)
for arg in sys.argv[1:]:
    maq, nombre = arg.split(":", 1)
    if (dest / nombre / "adapter_model.safetensors").exists():
        print("ya está", nombre)
        continue
    m = nube.state()[maq]["id"]
    info = nube.ssh(m, f"cd /root/salidas/{nombre} && tar czf /root/{nombre}_lora.tgz lora && md5sum /root/{nombre}_lora.tgz", timeout=300)
    remoto = re.search(rf"([0-9a-f]{{32}})\s+/root/{nombre}_lora.tgz", info).group(1)
    local = dest / f"{nombre}_lora.tgz"
    for _ in range(5):
        try:
            nube.scp(m, [f"/root/{nombre}_lora.tgz"], str(local), upload=False)
        except Exception as exc:  # noqa: BLE001
            print("reintento:", str(exc)[:80])
            continue
        if hashlib.md5(local.read_bytes()).hexdigest() == remoto:
            break
    with tarfile.open(local) as t:
        t.extractall(dest / nombre)
    (dest / nombre / "lora").rename(dest / nombre / "tmp")
    for f in (dest / nombre / "tmp").iterdir():
        f.rename(dest / nombre / f.name)
    (dest / nombre / "tmp").rmdir()
    local.unlink()
    print("bajado", nombre)
