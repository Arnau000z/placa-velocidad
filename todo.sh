#!/usr/bin/env bash
# Todas las pruebas de velocidad en orden, con un vigía de temperatura de fondo.
#   ./todo.sh          completo: 6 modelos con llama-bench, servidor, cadena con 15 problemas (unos 50 min)
#   ./todo.sh rapido   solo el 1.7B Q8 y Q4_0, 1 repetición, cadena con 5 problemas (unos 15 min)
# Para los servicios del reto mientras mide (comen RAM y CPU) y los vuelve a dejar como estaban al acabar.
set -uo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"
source ./config.sh
MODO="${1:-completo}"

exec > >(tee -a "$RES/todo.log") 2>&1
echo "Resultados en $RES  (modo $MODO)"

# sudo una vez al principio, y mantenerlo vivo durante la pasada
sudo -v || { echo "Hace falta la contraseña de sudo para parar los servicios"; exit 1; }
( while true; do sudo -n true 2>/dev/null; sleep 60; done ) &
SUDO_VIVO=$!

ACTIVOS=""
for s in math-llm math-embed; do
  systemctl is-active --quiet "$s" && ACTIVOS="$ACTIVOS $s"
done
[ -n "$ACTIVOS" ] && { echo "==> Parando$ACTIVOS mientras se mide"; sudo systemctl stop $ACTIVOS; }

terminar() {
  kill "$VIGIA" "$SUDO_VIVO" 2>/dev/null
  if [ -n "$ACTIVOS" ]; then
    echo "==> Volviendo a arrancar$ACTIVOS"
    sudo systemctl start $ACTIVOS
  fi
}
VIGIA=""
trap terminar EXIT

otros=$(pgrep -a llama-server || true)
if [ -n "$otros" ]; then
  echo "Hay otros llama-server corriendo (falsean la medida):"
  echo "$otros"
  read -r -p "¿Los paro? [s/N] " r
  [ "$r" = "s" ] && pkill llama-server && sleep 2
fi

bash ./vigia_temp.sh "$RES/temperatura.csv" &
VIGIA=$!

if [ "$MODO" = "rapido" ]; then
  export SOLO="${SOLO:-$PRINCIPAL Qwen_Qwen3-1.7B-Q4_0.gguf}" REPS="${REPS:-1}"
  N_CADENA="${N_CADENA:-5}"
else
  N_CADENA="${N_CADENA:-15}"
fi

echo; echo "######## 0/4 Preparar"
bash ./00_preparar.sh || exit 1
echo; echo "######## 1/4 Info de la placa"
bash ./01_info.sh
echo; echo "######## 2/4 llama-bench"
bash ./02_bench.sh
echo; echo "######## 3/4 Servidor (condiciones de predict.py)"
"$PY" ./03_servidor.py --modelos ${MODELOS_SERVIDOR:-$PRINCIPAL}
echo; echo "######## 4/4 Cadena completa con predict.py"
"$PY" ./04_cadena.py --n "$N_CADENA"

echo; echo "######## Resumen"
"$PY" ./resumen.py todo "$RES"
echo "Pásame $RES/resumen.md (o la carpeta entera)."
