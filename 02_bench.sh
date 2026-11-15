#!/usr/bin/env bash
# Velocidad pura de cada modelo con llama-bench: leer (pp, tokens/s del enunciado) y escribir (tg, tokens/s de la respuesta).
# Sin servidor, sin caché: es el dato limpio para comparar cuantizaciones.
# Tamaños por defecto parecidos a un problema real: 200 tokens de enunciado, 64 de respuesta, 2 repeticiones.
set -uo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/config.sh"

P="${P_TOKENS:-200}"
N="${N_TOKENS:-64}"
R="${REPS:-2}"

lista=("${MODELOS_BENCH[@]}")
for e in ${EXTRA:-}; do lista+=("$e"); done

for f in "${lista[@]}"; do
  m="$(ruta_modelo "$f")"
  nombre="$(basename "$m" .gguf)"
  if [ ! -f "$m" ]; then
    echo "  (no está $nombre, lo salto)"
    continue
  fi
  echo "==> $nombre  (leer $P, escribir $N, $R repeticiones, $HILOS hilos)"
  inicio=$(date +%s)
  "$BIN/llama-bench" -m "$m" -t "$HILOS" -p "$P" -n "$N" -r "$R" -o csv --progress \
    > "$RES/bench_$nombre.csv" 2> >(tee "$RES/bench_$nombre.log" >&2)
  estado=$?
  if [ $estado -ne 0 ]; then
    echo "  FALLO llama-bench ($estado): mira $RES/bench_$nombre.log"
    continue
  fi
  "$PY" "$REPO/resumen.py" bench "$RES/bench_$nombre.csv"
  echo "  ($(( $(date +%s) - inicio )) s)"
done
