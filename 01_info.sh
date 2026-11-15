#!/usr/bin/env bash
# Foto de la placa antes de medir: CPU y sus instrucciones, frecuencias, temperatura, memoria, disco y versión de llama.cpp.
set -uo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/config.sh"

temperaturas() {
  for z in /sys/class/thermal/thermal_zone*; do
    [ -r "$z/temp" ] || continue
    t=$(cat "$z/temp" 2>/dev/null) || continue
    echo "  $(cat "$z/type" 2>/dev/null): $((t / 1000)) C"
  done
}

{
  echo "## Placa"
  date
  hostname
  uname -a
  echo
  echo "## CPU"
  lscpu 2>/dev/null || cat /proc/cpuinfo
  echo
  echo "## Instrucciones (asimddp = dotprod, i8mm: si no salen, llama.cpp va por el camino lento)"
  grep -m1 -i '^features' /proc/cpuinfo
  echo
  echo "## Frecuencias (gobernador, actual, máxima en kHz)"
  for c in /sys/devices/system/cpu/cpu[0-9]*; do
    echo "  $(basename "$c"): $(cat "$c/cpufreq/scaling_governor" 2>/dev/null) $(cat "$c/cpufreq/scaling_cur_freq" 2>/dev/null) max $(cat "$c/cpufreq/cpuinfo_max_freq" 2>/dev/null)"
  done
  echo
  echo "## Temperaturas"
  temperaturas
  echo
  echo "## Memoria"
  free -m
  echo
  echo "## Disco"
  df -h "$MODELOS"
  echo
  echo "## llama.cpp"
  git -C "$LLAMA_DIR" log -1 --format='%H %cd' 2>/dev/null
  "$BIN/llama-cli" --version 2>&1 | tail -3
  echo
  echo "## Servicios del reto"
  systemctl is-active math-llm math-embed 2>&1
  echo
  echo "## Modelos"
  ls -l "$MODELOS"/*.gguf 2>/dev/null
} > "$RES/info.txt" 2>&1

grep -A1 -i '^## Instrucciones' "$RES/info.txt" | tail -1
grep -i 'model name' "$RES/info.txt" | head -1
free -m | awk 'NR==2 {print "Memoria: " $2 " MB, libres " $7 " MB"}'
echo "  OK    info.txt"
