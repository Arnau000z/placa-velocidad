#!/usr/bin/env bash
# Deja la placa lista: compila llama-bench (el repo del reto solo compila llama-server y llama-cli)
# y baja de Hugging Face los modelos que falten. Se puede repetir: lo que ya está, se salta.
set -uo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/config.sh"

echo "==> llama.cpp en $LLAMA_DIR"
if [ ! -x "$BIN/llama-server" ]; then
  echo "  FALTA $BIN/llama-server: haz antes los pasos 1-4 del README del reto"
  exit 1
fi
if [ ! -x "$BIN/llama-bench" ]; then
  echo "==> Compilando llama-bench (unos minutos en la placa)"
  cmake --build "$LLAMA_DIR/build" --config Release -j4 --target llama-bench || { echo "  FALLO al compilar llama-bench"; exit 1; }
fi
echo "  OK    llama-bench"

mkdir -p "$MODELOS"
lista=("${MODELOS_BENCH[@]}")
[[ " ${lista[*]} " == *" $PRINCIPAL "* ]] || lista+=("$PRINCIPAL")

for f in "${lista[@]}"; do
  dest="$(ruta_modelo "$f")"
  esperado="${TAM[$(basename "$f")]:-0}"
  if [ -f "$dest" ]; then
    tam=$(stat -c %s "$dest")
    if [ "$esperado" = 0 ] || [ "$tam" = "$esperado" ]; then
      echo "  OK    $(basename "$f") ($((tam / 1000000)) MB)"
      continue
    fi
  fi
  if [ "$esperado" = 0 ]; then
    echo "  FALTA $f (no sé de dónde bajarlo: cópialo a $MODELOS)"
    continue
  fi
  libre=$(df -Pk "$MODELOS" | awk 'NR==2 {print $4 * 1024}')
  if [ "$libre" -lt $((esperado + 1000000000)) ]; then
    echo "  FALTA $f: no hay sitio ($((libre / 1000000)) MB libres, hacen falta $((esperado / 1000000)) MB + 1 GB)"
    continue
  fi
  echo "==> Bajando $f ($((esperado / 1000000)) MB)"
  if wget -q --show-progress -c -O "$dest" "$(hf_url "$f")" && [ "$(stat -c %s "$dest")" = "$esperado" ]; then
    echo "  OK    $f"
  else
    echo "  FALLO bajando $f (vuelve a lanzar este paso: sigue donde lo dejó)"
  fi
done

echo
df -h "$MODELOS" | tail -1 | awk '{print "Disco: " $4 " libres de " $2}'
