#!/bin/bash
# Trabajo de cola para una 3090: LoRA r16 del 1.7B sobre sft_codigo_total (datos en /root/dt/nube/datos), exportar Q8 y
# examinar en la demo y en val con la cadena de placa. Uso: bash trabajo_lora_total.sh <nombre> [epocas] [lr] [rango]
NAME=${1:-17b_lora_total}; EP=${2:-2}; LR=${3:-1e-4}; R16=${4:-16}; DATOS=${5:-sft_codigo_total.jsonl}
REPO=/root/dt/repo; EXP=/root/dt/experimentos; R=/root/res; NUBE=/root/dt/nube; SRV=/root/llama.cpp/build/bin/llama-server
export HF_HOME=/root/hf PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
mkdir -p $R /root/demo; cp $NUBE/demo_train.jsonl /root/demo/train.jsonl 2>/dev/null
echo "$NAME: entreno (empieza) $(date +%H:%M)" >> $R/ESTADO
cd /root/dt && python3 -X utf8 $NUBE/entrenar.py --base Qwen/Qwen3-1.7B --datos $NUBE/datos/$DATOS --salida /root/salidas/$NAME \
  --epocas $EP --lr $LR --rango $R16 --lote 4 --acumular 4 --max-tokens 1024 --como-texto > $R/entreno_$NAME.log 2>&1 || { echo "$NAME: FALLO entreno" >> $R/ESTADO; exit 1; }
bash $NUBE/exportar.sh Qwen/Qwen3-1.7B /root/salidas/$NAME "Q8_0" > $R/exportar_$NAME.log 2>&1 || { echo "$NAME: FALLO exportar" >> $R/ESTADO; exit 1; }
echo "$NAME: exportado $(date +%H:%M)" >> $R/ESTADO
$SRV -m /root/salidas/$NAME/modelo-Q8_0.gguf --host 127.0.0.1 --port 9701 --threads 8 --ctx-size 32768 --parallel 16 --cache-ram 0 --jinja --reasoning off --reasoning-budget 0 -ngl 99 > $R/server_$NAME.log 2>&1 < /dev/null &
P=$!
for i in $(seq 1 150); do curl -s 127.0.0.1:9701/health | grep -q ok && break; sleep 2; done
cd $EXP && python3 -X utf8 eval_variantes.py $REPO --url http://127.0.0.1:9701 --paralelo 16 --tps 3.8,2.5 --prefijo-cacheado 160 --nombre "demo_$NAME" \
  --datos /root/demo/train.jsonl --todos --variantes codigo150_letra,codigo220_letra,codigo150_mediana,k0_valor >> $R/total_demo_$NAME.txt 2>&1
python3 -X utf8 eval_variantes.py $REPO --url http://127.0.0.1:9701 --paralelo 16 --tps 3.8,2.5 --prefijo-cacheado 160 --nombre "val_$NAME" \
  --variantes codigo150_letra,codigo150_mediana >> $R/total_val_$NAME.txt 2>&1
kill $P 2>/dev/null; wait $P 2>/dev/null
echo "$NAME: hecho $(date +%H:%M)" >> $R/ESTADO
