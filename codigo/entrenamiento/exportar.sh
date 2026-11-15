#!/bin/bash
# Junta el LoRA con la base y lo pasa a GGUF en las cuantizaciones pedidas (sin Ollama: llama.cpp directo).
# Uso: bash exportar.sh <base HF> <carpeta de salida de entrenar.py> "Q8_0 Q4_0"
set -e
BASE=$1; OUT=$2; QUANTS=${3:-"Q8_0 Q4_0"}
export HF_HOME=/root/hf
if [ -f "$OUT/junto/config.json" ]; then echo "ya junto (ajuste completo)"; else
python3 - "$BASE" "$OUT" <<'EOF'
import os, shutil, sys, torch
from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer
from huggingface_hub import snapshot_download
base, out = sys.argv[1], sys.argv[2]
model = AutoModelForCausalLM.from_pretrained(base, dtype=torch.bfloat16, device_map="cpu")
model = PeftModel.from_pretrained(model, f"{out}/lora").merge_and_unload()
model.save_pretrained(f"{out}/junto", safe_serialization=True)
AutoTokenizer.from_pretrained(base).save_pretrained(f"{out}/junto")
src = snapshot_download(base, allow_patterns=["*.json", "*.jinja", "*.model", "*.txt"])
for name in os.listdir(src):
    if not os.path.exists(f"{out}/junto/{name}") and "safetensors" not in name:
        shutil.copy(os.path.join(src, name), f"{out}/junto/{name}")
print("junto")
EOF
fi
python3 /root/llama.cpp/convert_hf_to_gguf.py "$OUT/junto" --outtype bf16 --outfile "$OUT/modelo-bf16.gguf"
for q in $QUANTS; do
  /root/llama.cpp/build/bin/llama-quantize "$OUT/modelo-bf16.gguf" "$OUT/modelo-$q.gguf" "$q" > /dev/null
done
rm -rf "$OUT/junto" "$OUT/modelo-bf16.gguf"
ls -la "$OUT"/*.gguf
