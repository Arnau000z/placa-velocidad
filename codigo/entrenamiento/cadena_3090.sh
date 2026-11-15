#!/bin/bash
# Cadena larga para una 3090 (que no se quede parada): LoRA del 1.7B sobre la mezcla v2 con la receta indicada y, al
# acabar, GRPO (LoRA) encima de ese modelo. Uso: bash cadena_3090.sh <nombre> <epocas> <lr> <rango>
NAME=$1; EP=$2; LR=$3; RG=$4
NUBE=/root/dt/nube; R=/root/res
export HF_HOME=/root/hf PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
cp /root/tmp_up/sft_codigo_v2*.jsonl $NUBE/datos/ 2>/dev/null
for f in trabajo_lora_total.sh entrenar.py exportar.sh entrenar_grpo.py grpo_remoto.sh sint_limpio.jsonl publicos.jsonl demo_train.jsonl; do cp /root/tmp_up/$f $NUBE/ 2>/dev/null; done
cp /root/tmp_up/util_opciones.py /root/tmp_up/eval_variantes.py /root/dt/experimentos/ 2>/dev/null
sed -i 's/\r$//' $NUBE/*.sh
bash $NUBE/trabajo_lora_total.sh $NAME $EP $LR $RG sft_codigo_v2.jsonl
# GRPO con LoRA (cabe en 24 GB) encima del modelo recién entrenado: juntar el LoRA con la base y lanzar
python3 - /root/salidas/$NAME /root/salidas/${NAME}_junto <<'EOF'
import sys, torch
from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer
src, dst = sys.argv[1], sys.argv[2]
m = AutoModelForCausalLM.from_pretrained("Qwen/Qwen3-1.7B", dtype=torch.bfloat16, device_map="cpu")
m = PeftModel.from_pretrained(m, f"{src}/lora").merge_and_unload()
m.save_pretrained(dst, safe_serialization=True)
AutoTokenizer.from_pretrained("Qwen/Qwen3-1.7B").save_pretrained(dst)
EOF
sed -i 's/--lr 1e-6 --max-tokens 220/--lr 1e-5 --max-tokens 200 --lora --prompts-por-paso 4/' $NUBE/grpo_remoto.sh
cp $NUBE/grpo_remoto.sh /root/tmp_up/grpo_remoto.sh
bash $NUBE/grpo_remoto.sh ${NAME}_grpo /root/salidas/${NAME}_junto 150
