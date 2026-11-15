"""Sopa de modelos: base + MEDIA de los deltas (B·A·alpha/r) de varios LoRA del mismo 1.7B, en CPU, y a GGUF Q8_0.
Promediar ajustes con los mismos datos y distintos hiperparámetros suele sumar 1-2 puntos sin coste en la placa.

python -X utf8 sopa_loras.py <salida_nombre> <carpeta_lora1> <carpeta_lora2> [...]
(cada carpeta con adapter_config.json y adapter_model.safetensors; usa el venv datathon-entreno, HF_HOME=D:\\hf)
"""
import json
import os
import subprocess
import sys
from pathlib import Path

os.environ.setdefault("HF_HOME", r"D:\hf")
import torch  # noqa: E402
from safetensors.torch import load_file  # noqa: E402
from transformers import AutoModelForCausalLM, AutoTokenizer  # noqa: E402

BASE = "Qwen/Qwen3-1.7B"
nombre, carpetas = sys.argv[1], sys.argv[2:]
salida = Path(r"D:\Datathon_A\modelos_entrenados") / f"{nombre}-hf"
modelo = AutoModelForCausalLM.from_pretrained(BASE, dtype=torch.bfloat16, device_map="cpu")
pesos = dict(modelo.named_parameters())
acum = {}
for c in carpetas:
    cfg = json.load(open(Path(c) / "adapter_config.json", encoding="utf-8"))
    escala = cfg["lora_alpha"] / cfg["r"]
    sd = load_file(str(Path(c) / "adapter_model.safetensors"))
    for k, a in sd.items():
        if ".lora_A." not in k:
            continue
        b = sd[k.replace(".lora_A.", ".lora_B.")]
        destino = k.replace("base_model.model.", "", 1).replace(".lora_A.weight", ".weight")
        if destino not in pesos:
            raise KeyError(destino)
        d = (b.float() @ a.float()) * escala / len(carpetas) * float(os.environ.get("ESCALA", "1"))  # ESCALA>1: extrapola
        acum[destino] = acum[destino] + d if destino in acum else d
    print("sumado", c, flush=True)
with torch.no_grad():
    for k, d in acum.items():
        pesos[k].copy_((pesos[k].float() + d).to(torch.bfloat16))
modelo.save_pretrained(str(salida), safe_serialization=True)
AutoTokenizer.from_pretrained(BASE).save_pretrained(str(salida))
print("sopa en", salida, "con", len(acum), "matrices", flush=True)
gguf_bf16 = salida.parent / f"{nombre}-bf16.gguf"
gguf_q8 = salida.parent / f"{nombre}-Q8_0.gguf"
subprocess.run([sys.executable, r"D:\Datathon_A\llama.cpp\convert_hf_to_gguf.py", str(salida), "--outtype", "bf16", "--outfile", str(gguf_bf16)], check=True)
subprocess.run([r"D:\Datathon_A\herramientas\llama-win-b12308\cuda\llama-quantize.exe", str(gguf_bf16), str(gguf_q8), "Q8_0"], check=True,
               stdout=subprocess.DEVNULL)
gguf_bf16.unlink()
print("GGUF:", gguf_q8, gguf_q8.stat().st_size, flush=True)
