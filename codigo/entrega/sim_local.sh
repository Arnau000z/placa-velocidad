#!/bin/bash
# Simula en la torre un GGUF local (demo + val texto eng+cat) en el puerto 8096 y apunta el resultado en candidatos.txt.
# Uso: bash sim_local.sh <gguf> <nombre>
cd /d/Datathon_A/entrega
PY=/d/venvs/datathon-m3kang/Scripts/python.exe
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"Name='llama-server.exe'\" | Where-Object { \$_.CommandLine -match 'port 8096' } | ForEach-Object { Stop-Process -Id \$_.ProcessId -Force }"
sleep 2
/d/Datathon_A/herramientas/llama-win-b12308/cuda/llama-server.exe -m "$1" --host 127.0.0.1 --port 8096 --threads 4 --ctx-size 4096 --parallel 1 --cache-ram 0 --jinja --reasoning off --reasoning-budget 0 -ngl 99 > "$TEMP/srv8096.log" 2>&1 &
for i in $(seq 1 60); do curl -s 127.0.0.1:8096/health | grep -q ok && break; sleep 2; done
n=$(basename "$(echo "$1" | tr '\\' '/')")
curl -s 127.0.0.1:8096/props | grep -q "$n" || { echo "el 8096 no sirve $n"; exit 1; }
d=$($PY -X utf8 sim_demo.py http://127.0.0.1:8096 "$2" --reserva mediana | tail -1)
v=$($PY -X utf8 sim_demo.py http://127.0.0.1:8096 "val_$2" --reserva mediana --demo 'D:\Datathon_A\demo\val_ec_texto.jsonl' | tail -1)
echo "$(date +%H:%M) $d" >> candidatos.txt; echo "      $v" >> candidatos.txt; echo "$(date +%H:%M) $v" >> val_sims.txt
echo "$d"; echo "$v"
