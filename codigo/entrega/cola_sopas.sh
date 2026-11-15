#!/bin/bash
# Sopas en serie (una a la vez: cada una ocupa ~10 GB de RAM) y su simulación. Uso: bash cola_sopas.sh
# Cada línea de cola_sopas.txt: <nombre> <ESCALA> <lora1> <lora2> ... (nombres de carpetas en modelos_entrenados/loras)
L=/d/Datathon_A/modelos_entrenados/loras
while read -r nombre escala resto; do
  [ -z "$nombre" ] && continue
  case "$nombre" in \#*) continue;; esac
  grep -q " val_${nombre} reserva=" /d/Datathon_A/entrega/val_sims.txt && continue
  carpetas=""; for x in $resto; do carpetas="$carpetas $L/$x"; done
  # no empezar una sopa si la torre tiene menos de 10 GB libres (el sistema mata tareas por falta de memoria)
  for i in $(seq 1 60); do
    libre=$(powershell -NoProfile -Command "[int]((Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory/1MB)")
    [ "${libre:-0}" -ge 10 ] && break; sleep 30
  done
  if [ ! -f "/d/Datathon_A/modelos_entrenados/${nombre}-Q8_0.gguf" ]; then
    (cd /d/Datathon_A/nube && ESCALA=$escala /d/venvs/datathon-entreno/Scripts/python.exe -X utf8 sopa_ligera.py "$nombre" $carpetas 2>&1 | grep -E "GGUF|Error" | tail -2)
  fi
  (cd /d/Datathon_A/entrega && timeout 1200 bash sim_local.sh "D:/Datathon_A/modelos_entrenados/${nombre}-Q8_0.gguf" "$nombre" | tail -2)
done < /d/Datathon_A/entrega/cola_sopas.txt
