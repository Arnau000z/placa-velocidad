#!/usr/bin/env bash
# Downloads the two extra models Math Coach uses besides those of setup step 4, pinned in config.env
# (repository, revision, file, SHA-256), into MODELS_DIR, and checks the checksum.
#
#   bash app/math-coach/deploy/get_models.sh bge-m3        0.63 GB: the problem map (laptop or board)
#   bash app/math-coach/deploy/get_models.sh salamandra    4.85 GB: translations (laptop with a GPU only;
#                                                          it doesn't fit in the board's 4 GB of RAM)
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
# shellcheck disable=SC1091
source "$ROOT/config.env"
MODELS_DIR="${MODELS_DIR/#\~/$HOME}"
mkdir -p "$MODELS_DIR"
case "${1:-}" in
  bge-m3)     REPO=$MAP_EMBED_REPO;  REV=$MAP_EMBED_REVISION;  FILE=$MAP_EMBED_FILE;  SHA=$MAP_EMBED_SHA256 ;;
  salamandra) REPO=$TRANSLATE_REPO;  REV=$TRANSLATE_REVISION;  FILE=$TRANSLATE_FILE;  SHA=$TRANSLATE_SHA256 ;;
  *) echo "usage: get_models.sh bge-m3 | salamandra" >&2; exit 2 ;;
esac
OUT="$MODELS_DIR/$FILE"
if [[ ! -f "$OUT" ]]; then
  curl -fL --retry 5 -C - -o "$OUT.part" "https://huggingface.co/$REPO/resolve/$REV/$FILE"
  mv "$OUT.part" "$OUT"
fi
echo "$SHA  $OUT" | sha256sum -c -
