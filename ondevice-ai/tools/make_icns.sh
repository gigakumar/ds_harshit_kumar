#!/usr/bin/env bash
set -euo pipefail

PNG="assets/icon.png"
ICONSET_DIR="assets/icon.iconset"
ICNS="assets/icon.icns"

if [[ ! -f "$PNG" ]]; then
  echo "Icon PNG not found at $PNG; skipping .icns generation" >&2
  exit 0
fi

mkdir -p "$ICONSET_DIR"
sizes=(16 32 64 128 256 512 1024)
for s in "${sizes[@]}"; do
  /usr/bin/sips -z "$s" "$s" "$PNG" --out "$ICONSET_DIR/icon_${s}x${s}.png" >/dev/null
done
/usr/bin/iconutil -c icns "$ICONSET_DIR" -o "$ICNS"
echo "Created $ICNS"
