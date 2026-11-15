#!/usr/bin/env bash
# Installs (or updates) the Math Coach App Lab app on the Arduino UNO Q and starts it.
# Run it ON THE BOARD, from a copy of app/math-coach (the repository clone of step 8, or the folder
# that deploy_from_laptop.sh sends):
#
#   bash app/math-coach/deploy/install_on_board.sh             install or update, then (re)start
#   bash app/math-coach/deploy/install_on_board.sh --restart   only restart the app (e.g. after a reboot)
#
# What it does:
#   1. copies the app (app.yaml, sketch, Python, web page, problem map) to ~/ArduinoApps/math-coach,
#      keeping the class data already on the board (python/data/profiles.db and teacher_pin.txt)
#   2. installs the model bridge as a user service (no sudo): App Lab runs the app in Docker, where
#      127.0.0.1 is the container; the bridge listens on 172.17.0.1:8081 (docker0, never Wi-Fi) and
#      relays to the language model of step 7 on 127.0.0.1:8081
#   3. (re)starts the app with arduino-app-cli and prints the address to open
set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DST="${MATHCOACH_DST:-$HOME/ArduinoApps/math-coach}"
DRY="${MATHCOACH_DRY_RUN:-0}"      # 1: copy files only (for testing off the board)
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
say() { printf '\n== %s\n' "$*"; }

start_app() {
  say "Starting the app (the sketch compiles first: about a minute)"
  arduino-app-cli app stop "$DST" >/dev/null 2>&1 || true
  arduino-app-cli app start "$DST" || arduino-app-cli app start "$DST" --no-prepare
  arduino-app-cli app ps || true
  local ip
  ip="$(hostname -I | awk '{print $1}')"
  say "Ready"
  echo "Students and teacher:   http://${ip}:7000      (same Wi-Fi as the board)"
  echo "How it works (jury):    http://${ip}:7000/como-funciona.html"
  echo "Teacher PIN:            cat $DST/python/data/teacher_pin.txt   (created on the first start)"
  echo "App log:                arduino-app-cli app logs $DST"
}

if [[ "${1:-}" == "--restart" ]]; then
  [[ "$DRY" == 1 ]] || start_app
  exit 0
fi

say "Checking the source: $SRC"
if [[ ! -f "$SRC/python/data/bank.json" ]]; then
  echo "Missing $SRC/python/data/bank.json (the problem map). Build it first: README, 'How to replicate', step 2." >&2
  exit 1
fi
[[ -f "$SRC/python/data/explanations_i18n.json" ]] || echo "Note: no translations of the written solutions (optional): lessons show them in English."

say "Copying the app to $DST"
mkdir -p "$DST/python/data" "$DST/sketch"
rm -rf "$DST/assets"                       # the page is replaced as a whole (drops removed files)
cp -r "$SRC/assets" "$DST/assets"
cp "$SRC/app.yaml" "$DST/"
cp "$SRC/sketch/sketch.ino" "$SRC/sketch/sketch.yaml" "$DST/sketch/"
cp "$SRC"/python/*.py "$DST/python/"
cp "$SRC/python/data/bank.json" "$DST/python/data/"
[[ -f "$SRC/python/data/explanations_i18n.json" ]] && cp "$SRC/python/data/explanations_i18n.json" "$DST/python/data/"
# files edited on Windows may carry CRLF line endings: strip them from the text files (never from the fonts)
find "$DST" -type f \( -name '*.py' -o -name '*.js' -o -name '*.css' -o -name '*.html' -o -name '*.yaml' -o -name '*.ino' -o -name '*.txt' \) \
  -exec sed -i 's/\r$//' {} +
echo "Class data kept: $(ls "$DST/python/data" | tr '\n' ' ')"

if [[ "$DRY" == 1 ]]; then echo "(dry run: no services, no start)"; exit 0; fi

say "Model bridge (user service, no sudo)"
mkdir -p "$HOME/math-coach-bridge" "$HOME/.config/systemd/user"
cp "$SRC/board/llm_bridge.py" "$HOME/math-coach-bridge/llm_bridge.py"
sed "s#/home/arduino#$HOME#g" "$SRC/board/math-llm-bridge.service" > "$HOME/.config/systemd/user/math-llm-bridge.service"
sed -i 's/\r$//' "$HOME/math-coach-bridge/llm_bridge.py" "$HOME/.config/systemd/user/math-llm-bridge.service"
systemctl --user daemon-reload
systemctl --user enable --now math-llm-bridge
systemctl --user restart math-llm-bridge
sleep 2
systemctl --user is-active math-llm-bridge
if ! loginctl show-user "$USER" -p Linger 2>/dev/null | grep -q yes; then
  echo "Note: to start the bridge at boot without logging in, run once: sudo loginctl enable-linger $USER"
fi
if ! systemctl is-active --quiet math-llm; then
  echo "Warning: the language model service (step 7, math-llm) is not running. The app works, but hint 3 falls back to the method."
fi
curl -s --max-time 3 http://172.17.0.1:8081/health && echo "  <- the model answers through the bridge" || echo "Warning: no answer on 172.17.0.1:8081 yet"

start_app
