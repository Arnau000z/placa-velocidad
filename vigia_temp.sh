#!/usr/bin/env bash
# Apunta cada 5 s la temperatura máxima, la frecuencia de cada núcleo, la carga y la memoria libre.
# Sirve para ver si la placa se frena por calor durante una pasada larga.
# Uso: vigia_temp.sh salida.csv   (todo.sh lo lanza en segundo plano y lo para al acabar)
out="${1:-temperatura.csv}"
echo "hora,temp_max_c,mhz_cpu0,mhz_cpu1,mhz_cpu2,mhz_cpu3,carga_1min,mem_libre_mb" > "$out"
while true; do
  tmax=0
  for z in /sys/class/thermal/thermal_zone*/temp; do
    t=$(cat "$z" 2>/dev/null) || continue
    [ "$t" -gt "$tmax" ] 2>/dev/null && tmax=$t
  done
  mhz=""
  for c in 0 1 2 3; do
    f=$(cat "/sys/devices/system/cpu/cpu$c/cpufreq/scaling_cur_freq" 2>/dev/null || echo 0)
    mhz="$mhz,$((f / 1000))"
  done
  carga=$(cut -d' ' -f1 /proc/loadavg)
  mem=$(free -m | awk 'NR==2 {print $7}')
  echo "$(date +%H:%M:%S),$((tmax / 1000))$mhz,$carga,$mem" >> "$out"
  sleep 5
done
