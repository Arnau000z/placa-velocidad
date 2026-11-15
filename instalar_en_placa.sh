#!/usr/bin/env bash
# Deja la placa lista para el examen con el sistema del equipo y lo prueba con el reloj de verdad.
#
#   ./instalar_en_placa.sh              instala el modelo final y nuestro predict.py, y prueba 6 problemas
#   ./instalar_en_placa.sh --probar     solo la prueba, sin tocar nada (N=20 ./instalar_en_placa.sh --probar)
#   ./instalar_en_placa.sh --deshacer   vuelve al modelo y al predict.py del reto
#
# Antes, desde el PC:  .\subir_a_placa.ps1 -Extra D:\Datathon_A\modelos_entrenados\sopa_z10-Q8_0.gguf
#
# Qué hace al instalar:
#   1. comprueba que ~/models/sopa_z10-Q8_0.gguf está entero (md5)
#   2. pone LLM_FILE=sopa_z10-Q8_0.gguf en el config.env del reto (copia en config.env.orig)
#   3. reinstala los servicios con board/04_install_services.sh, como dice el README del reto (pide sudo)
#   4. copia equipo/predict.py como predict.py del repo del reto (el original queda en predict_oficial.py)
# y luego pasa N problemas de val por el servicio math-llm real, como lo hará el jurado.
set -uo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"
KIT="$(pwd)"
source ./config.sh
RETO="${RETO:-$(dirname "$DATOS")}"
MODELO="${MODELO:-sopa_z10-Q8_0.gguf}"
MD5="${MD5:-c1ba1d47e8f818378e27be6a7c1a01b2}"
N="${N:-6}"
MODO="${1:-instalar}"

ok()  { echo "  OK    $*"; }
mal() { echo "  FALLO $*"; exit 1; }

[ -d "$RETO" ] || mal "no encuentro el repo del reto en $RETO (pásalo con RETO=/ruta)"
CONF="$RETO/config.env"

if [ "$MODO" = "--deshacer" ]; then
  [ -f "$CONF.orig" ] && cp "$CONF.orig" "$CONF" && ok "config.env original"
  [ -f "$RETO/predict_oficial.py" ] && cp "$RETO/predict_oficial.py" "$RETO/predict.py" && ok "predict.py original"
  bash "$RETO/board/04_install_services.sh"
  exit $?
fi

if [ "$MODO" != "--probar" ]; then
  echo "==> 1/4 Modelo"
  F="$MODELOS/$MODELO"
  if [ ! -f "$F" ]; then
    URL="https://github.com/Arnau000z/placa-velocidad/releases/download/modelo-final/$MODELO"
    echo "  no está en $MODELOS: lo bajo de la release del repo (1,83 GB)"
    mkdir -p "$MODELOS"
    wget -c -q --show-progress -O "$F.part" "$URL" && mv "$F.part" "$F" \
      || mal "no se pudo bajar; súbelo desde el PC con  .\\subir_a_placa.ps1 -Extra ...\\$MODELO"
  fi
  echo "  comprobando md5 (unos 20 s)..."
  m="$(md5sum "$F" | cut -d' ' -f1)"
  [ "$m" = "$MD5" ] || mal "md5 distinto ($m): la copia está mal, vuelve a subirlo"
  ok "$MODELO, $(( $(stat -c %s "$F") / 1000000 )) MB, md5 correcto"

  echo "==> 2/4 config.env del reto apunta al modelo del equipo"
  [ -f "$CONF.orig" ] || cp "$CONF" "$CONF.orig"
  sed -i "s|^LLM_FILE=.*|LLM_FILE=$MODELO|; s|^LLM_ALIAS=.*|LLM_ALIAS=equipo|" "$CONF"
  grep -E "^LLM_FILE|^LLM_ALIAS|^LLM_PORT|^LLM_CTX" "$CONF" | sed 's/^/        /'

  echo "==> 3/4 Servicios math-llm y math-embed (pide sudo)"
  bash "$RETO/board/04_install_services.sh" || mal "no arrancaron los servicios. Mira: journalctl -u math-llm -n 50"

  echo "==> 4/4 predict.py del equipo en el repo del reto"
  [ -f "$RETO/predict_oficial.py" ] || cp "$RETO/predict.py" "$RETO/predict_oficial.py"
  cp "$KIT/equipo/predict.py" "$RETO/predict.py"
  ok "$RETO/predict.py (el original queda en predict_oficial.py)"
fi

echo
echo "==> Prueba: $N problemas de val por el servicio de verdad, con el reloj de verdad"
systemctl is-active --quiet math-llm || mal "math-llm no está activo"
grep -q "^LLM_FILE=$MODELO" "$CONF" || echo "  AVISO: el servicio no usa $MODELO ($(grep ^LLM_FILE "$CONF"))"
PRUEBA="$KIT/resultados/prueba_$(date +%m%d_%H%M)"
mkdir -p "$PRUEBA"
"$PY" - "$DATOS" "$N" "$PRUEBA/problemas.jsonl" <<'EOF'
import json, os, random, sys
datos, n, salida = sys.argv[1], int(sys.argv[2]), sys.argv[3]
filas = []
p = os.path.join(datos, "val.jsonl")
if os.path.exists(p):
    filas = [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]
    filas = [r for r in filas if r.get("text_only") and len(r.get("options") or {}) == 5 and r.get("language") in ("eng", "cat")]
if not filas:
    p = os.path.join(datos, "sample_problems.jsonl")
    filas = [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]
random.Random(7).shuffle(filas)
with open(salida, "w", encoding="utf-8") as f:
    for r in filas[:n]:
        f.write(json.dumps({k: r[k] for k in ("id", "language", "text", "options", "text_only", "label") if k in r}, ensure_ascii=False) + "\n")
print(f"  {min(n, len(filas))} problemas de {os.path.basename(p)}")
EOF
cd "$RETO"
t0=$(date +%s)
"$PY" predict.py --input "$PRUEBA/problemas.jsonl" --output "$PRUEBA/respuestas.csv" 2>&1 | tail -n 3 | sed 's/^/        /'
t1=$(date +%s)
"$PY" - "$PRUEBA/problemas.jsonl" "$PRUEBA/respuestas.csv" "$((t1 - t0))" <<'EOF'
import csv, json, sys
prob = {(r["id"], r.get("language")): r for r in (json.loads(l) for l in open(sys.argv[1], encoding="utf-8") if l.strip())}
filas = list(csv.DictReader(open(sys.argv[2], encoding="utf-8")))
print(f"\n  {'problema':24s} {'idioma':6s} {'resp':4s} {'bien':5s} {'s':>5s}  vía")
seg, bien = [], 0
for f in filas:
    r = prob.get((f["id"], f.get("language")), {})
    ok = r.get("label") == f["answer"] if r.get("label") else None
    bien += bool(ok)
    s = float(f.get("seconds") or 0)
    seg.append(s)
    print(f"  {f['id']:24s} {f.get('language', ''):6s} {f['answer']:4s} {'sí' if ok else ('no' if ok is not None else '?'):5s} {s:5.1f}  {f.get('status', '')}")
if seg:
    print(f"\n  Aciertos {bien}/{len(filas)} · media {sum(seg) / len(seg):.1f} s · máximo {max(seg):.1f} s · "
          f"{sum(s > 60 for s in seg)} por encima de 60 s · total {sys.argv[3]} s (con el calentamiento)")
    print("  BIEN: ningún problema pasa de 60 s" if max(seg) <= 60 else "  OJO: hay problemas por encima de 60 s; pasa el .log.jsonl")
EOF
echo
echo "  Ficheros: $PRUEBA/  (respuestas.csv y respuestas.csv.log.jsonl, con lo que escribió el modelo)"
echo "  El jurado lo ejecutará así:  cd $RETO && python3 predict.py --input examen.jsonl --output respuestas.csv"
