"""Sopa de LoRA con poca memoria (la torre se quedó sin RAM con sopa_loras.py, ~10 GB por sopa): suma los deltas
matriz a matriz en fp32 y los aplica en el sitio, sin acumular todos a la vez (~4,5 GB de pico). Mismo resultado.

python -X utf8 sopa_ligera.py <salida_nombre> <carpeta_lora1> <carpeta_lora2> [...]   (venv datathon-entreno)
"""
import gc
import json
import os
import subprocess
import sys
from pathlib import Path

os.environ.setdefault("HF_HOME", r"D:\hf")
import torch  # noqa: E402
from safetensors import safe_open  # noqa: E402
from transformers import AutoModelForCausalLM, AutoTokenizer  # noqa: E402

BASE = "Qwen/Qwen3-1.7B"
nombre, carpetas = sys.argv[1], sys.argv[2:]
salida = Path(r"D:\Datathon_A\modelos_entrenados") / f"{nombre}-hf"
escala_extra = float(os.environ.get("ESCALA", "1"))
modelo = AutoModelForCausalLM.from_pretrained(BASE, dtype=torch.bfloat16, device_map="cpu", low_cpu_mem_usage=True)
pesos = dict(modelo.named_parameters())
fuentes = []
for c in carpetas:
    cfg = json.load(open(Path(c) / "adapter_config.json", encoding="utf-8"))
    fuentes.append((safe_open(str(Path(c) / "adapter_model.safetensors"), framework="pt"), cfg["lora_alpha"] / cfg["r"]))
claves = [k for k in fuentes[0][0].keys() if ".lora_A." in k]
with torch.no_grad():
    for k in claves:
        destino = k.replace("base_model.model.", "", 1).replace(".lora_A.weight", ".weight")
        d = None
        for f, esc in fuentes:
            if k not in f.keys():
                continue
            x = (f.get_tensor(k.replace(".lora_A.", ".lora_B.")).float() @ f.get_tensor(k).float()) * esc
            d = x if d is None else d + x
        d *= escala_extra / len(fuentes)
        pesos[destino].copy_((pesos[destino].float() + d).to(torch.bfloat16))
modelo.save_pretrained(str(salida), safe_serialization=True)
AutoTokenizer.from_pretrained(BASE).save_pretrained(str(salida))
del modelo, pesos, fuentes
gc.collect()
print("sopa en", salida, "con", len(claves), "matrices", flush=True)
gguf_bf16 = salida.parent / f"{nombre}-bf16.gguf"
gguf_q8 = salida.parent / f"{nombre}-Q8_0.gguf"
subprocess.run([sys.executable, r"D:\Datathon_A\llama.cpp\convert_hf_to_gguf.py", str(salida), "--outtype", "bf16", "--outfile", str(gguf_bf16)], check=True)
subprocess.run([r"D:\Datathon_A\herramientas\llama-win-b12308\cuda\llama-quantize.exe", str(gguf_bf16), str(gguf_q8), "Q8_0"], check=True,
               stdout=subprocess.DEVNULL)
gguf_bf16.unlink()
import shutil  # noqa: E402
shutil.rmtree(salida, ignore_errors=True)  # la carpeta HF ocupa 3,4 GB y se rehace en 1 min: el disco D se llenó
print("GGUF:", gguf_q8, gguf_q8.stat().st_size, flush=True)
