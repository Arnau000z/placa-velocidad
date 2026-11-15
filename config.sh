# Ajustes comunes de las pruebas de velocidad. Se carga con `source`, no se ejecuta.
# Todo se puede cambiar desde fuera: p. ej. `HILOS=3 ./todo.sh`.

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Rutas de la placa (las mismas que usa el repo del reto)
LLAMA_DIR="${LLAMA_DIR:-$HOME/llama.cpp}"
BIN="${BIN:-$LLAMA_DIR/build/bin}"
MODELOS="${MODELOS:-$HOME/models}"
DATOS="${DATOS:-$HOME/datathon-UPC-maths-qualcomm-arduino-unoq/data}"

HILOS="${HILOS:-4}"
PUERTO="${PUERTO:-8090}"          # puerto propio para no chocar con los servicios del reto (8081/8082)
PY="${PY:-python3}"

# Modelo de la entrega: el que se usa en la prueba del servidor y en la cadena completa
PRINCIPAL="${PRINCIPAL:-Qwen_Qwen3-1.7B-Q8_0.gguf}"

# Modelos que se miden con llama-bench. SOLO="a.gguf b.gguf" mide solo esos.
# EXTRA="/ruta/al/afinado.gguf" añade modelos propios (p. ej. el 1.7B afinado) sin bajarlos.
MODELOS_BENCH=(
  Qwen_Qwen3-1.7B-Q8_0.gguf      # el de ahora
  Qwen_Qwen3-1.7B-Q4_0.gguf      # ¿lee más rápido en 4 bits?
  Qwen_Qwen3-1.7B-Q4_K_M.gguf
  Qwen_Qwen3-1.7B-Q6_K.gguf
  Qwen_Qwen3.5-0.8B-Q8_0.gguf    # referencia: el README del reto dice 11 leyendo / 5 escribiendo
  Qwen_Qwen3.5-2B-Q4_0.gguf      # candidato de la investigación
)
if [ -n "${SOLO:-}" ]; then
  read -r -a MODELOS_BENCH <<< "$SOLO"
fi

# Tamaños exactos en Hugging Face (bartowski), para saber si una descarga quedó a medias
declare -A TAM=(
  [Qwen_Qwen3-1.7B-Q8_0.gguf]=2165039520
  [Qwen_Qwen3-1.7B-Q6_K.gguf]=1673007520
  [Qwen_Qwen3-1.7B-Q5_K_M.gguf]=1471805856
  [Qwen_Qwen3-1.7B-Q4_K_M.gguf]=1282439584
  [Qwen_Qwen3-1.7B-Q4_0.gguf]=1231813024
  [Qwen_Qwen3-1.7B-IQ4_NL.gguf]=1229453728
  [Qwen_Qwen3.5-0.8B-Q8_0.gguf]=835325024
  [Qwen_Qwen3.5-2B-Q4_0.gguf]=1296764000
  [Qwen_Qwen3.5-2B-Q8_0.gguf]=2080140384
)

# URL de descarga: Qwen_Qwen3-1.7B-Q4_0.gguf -> bartowski/Qwen_Qwen3-1.7B-GGUF
hf_url() {
  local f="$1"
  echo "https://huggingface.co/bartowski/${f%-*}-GGUF/resolve/main/$f"
}

# Ruta completa de un modelo (acepta nombre suelto o ruta)
ruta_modelo() {
  case "$1" in
    /*|./*) echo "$1" ;;
    *) echo "$MODELOS/$1" ;;
  esac
}

# Carpeta de resultados de esta pasada (todo.sh la fija para todos los pasos)
if [ -z "${RES:-}" ]; then
  RES="$REPO/resultados/$(hostname)_$(date +%m%d_%H%M)"
fi
mkdir -p "$RES"
export RES
