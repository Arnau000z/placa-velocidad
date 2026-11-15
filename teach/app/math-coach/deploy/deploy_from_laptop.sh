#!/usr/bin/env bash
# Sends the Math Coach app from a laptop (Linux, macOS or WSL) to the UNO Q and installs it there.
# Run it from the repository folder, after building python/data/bank.json (README, step 2):
#
#   bash app/math-coach/deploy/deploy_from_laptop.sh arduino@<board-ip>    over SSH (setup step 0.3)
#   bash app/math-coach/deploy/deploy_from_laptop.sh adb                   over USB with adb (setup step 0.4)
#
# It packs app/math-coach (without the laptop's own databases and reports), copies it to
# ~/math-coach-src on the board and runs deploy/install_on_board.sh there. The class data on the board
# (python/data/profiles.db, teacher_pin.txt) is never overwritten.
set -euo pipefail
TARGET="${1:?usage: deploy_from_laptop.sh arduino@<board-ip> | adb}"
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
[[ -f "$SRC/python/data/bank.json" ]] || { echo "Missing python/data/bank.json: build it first (README, step 2)." >&2; exit 1; }

PKG="$(mktemp -t math-coach-XXXX.tgz)"
trap 'rm -f "$PKG"' EXIT
tar czf "$PKG" -C "$SRC" \
  --exclude='python/data/profiles*.db' --exclude='python/data/teacher_pin.txt' \
  --exclude='python/data/translation_report.json' --exclude='python/data/translation_review.csv' \
  --exclude='__pycache__' .
echo "Package: $(du -h "$PKG" | cut -f1)"

REMOTE='rm -rf "$HOME/math-coach-src" && mkdir -p "$HOME/math-coach-src" && tar xzf /tmp/math-coach.tgz -C "$HOME/math-coach-src" && rm /tmp/math-coach.tgz && bash "$HOME/math-coach-src/deploy/install_on_board.sh"'
if [[ "$TARGET" == "adb" ]]; then
  adb push "$PKG" /tmp/math-coach.tgz
  adb shell "$REMOTE"
  adb forward tcp:7000 tcp:7000
  echo "Over USB: http://127.0.0.1:7000 on this laptop"
else
  scp "$PKG" "$TARGET:/tmp/math-coach.tgz"
  ssh "$TARGET" "$REMOTE"
fi
