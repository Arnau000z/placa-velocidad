#!/bin/bash
# GRPO (LoRA, cabe en 24 GB) del Qwen3.5-2B encima de 2b_lora32 (demo 53/52, val 36,7 %): la misma jugada que en el
# 1.7B dio 17b_grpo_lora32 (val de 36,1 a 39,8 %). El adaptador de 2b_lora32 llega en /root/tmp_up/2b_lora32_lora.
R=/root/res; NUBE=/root/dt/nube; EXP=/root/dt/experimentos
export HF_HOME=/root/hf PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
NAME=2b_grpo_lora32; SRC=/root/salidas/2b_lora32; DST=/root/salidas/2b_lora32_junto
mkdir -p $SRC && cp -r /root/tmp_up/2b_lora32_lora $SRC/lora
for f in entrenar_grpo.py sint_limpio.jsonl publicos.jsonl demo_train.jsonl; do cp /root/tmp_up/$f $NUBE/ 2>/dev/null; done
cp /root/tmp_up/util_opciones.py /root/tmp_up/eval_variantes.py $EXP/ 2>/dev/null
echo "$NAME: junta (empieza) $(date +%H:%M)" >> $R/ESTADO
python3 - "$SRC" "$DST" <<'EOP' || { echo "$NAME: FALLO juntar" >> $R/ESTADO; exit 1; }
import sys, torch
from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer
src, dst = sys.argv[1], sys.argv[2]
m = AutoModelForCausalLM.from_pretrained("Qwen/Qwen3.5-2B", dtype=torch.bfloat16, device_map="cpu")
m = PeftModel.from_pretrained(m, f"{src}/lora").merge_and_unload()
m.save_pretrained(dst, safe_serialization=True)
AutoTokenizer.from_pretrained("Qwen/Qwen3.5-2B").save_pretrained(dst)
EOP
sed -e 's/\r$//' -e 's/--lr 1e-6 --max-tokens 220/--lr 1e-5 --max-tokens 200 --lora --prompts-por-paso 4/' \
    -e 's#exportar.sh Qwen/Qwen3-1.7B#exportar.sh Qwen/Qwen3.5-2B#' /root/tmp_up/grpo_remoto.sh > /root/grpo_2b_dentro.sh
bash /root/grpo_2b_dentro.sh $NAME $DST 150
