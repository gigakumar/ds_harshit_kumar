#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

APP_PATH="${APP_PATH:-$ROOT_DIR/dist/OnDeviceAI.app}"
DMG_PATH="${DMG_PATH:-$ROOT_DIR/dist/OnDeviceAI.dmg}"
VOLNAME="${DMG_VOLNAME:-OnDeviceAI}"
APP_EXECUTABLE_NAME="${APP_EXECUTABLE_NAME:-OnDeviceAIApp}"
DMG_TMP_DIR="${DMG_TMP_DIR:-$(mktemp -d /tmp/ondeviceai-dmg.XXXXXX)}"
DMG_STAGE_DIR="$DMG_TMP_DIR/stage"
DMG_RW_IMAGE="$DMG_TMP_DIR/${VOLNAME}.rw.dmg"
DMG_COMPRESSED_BASENAME="$DMG_TMP_DIR/${VOLNAME}.compressed"
DMG_APPLICATIONS_SYMLINK="${DMG_APPLICATIONS_SYMLINK:-true}"
DMG_BACKGROUND_IMAGE="${DMG_BACKGROUND_IMAGE:-$ROOT_DIR/assets/dmg-background.png}"
DMG_BACKGROUND_DEST="$DMG_STAGE_DIR/.background"
DMG_BACKGROUND_NAME="${DMG_BACKGROUND_NAME:-dmg-background.png}"
DMG_README_SOURCE="${DMG_README_SOURCE:-}" # optional external README to copy
DMG_EMBED_README="${DMG_EMBED_README:-true}"
DMG_EMBED_README_NAME="${DMG_EMBED_README_NAME:-README.txt}"
DMG_VOLUME_ICON="${DMG_VOLUME_ICON:-}" # optional .icns for the mounted volume icon

cleanup() {
  if [[ -n "${DMG_RW_ATTACHED:-}" ]]; then
    hdiutil detach "$DMG_RW_ATTACHED" -quiet || true
  fi
  rm -rf "$DMG_TMP_DIR"
}

trap cleanup EXIT

if [[ ! -d "$APP_PATH" ]]; then
  echo "App bundle not found at $APP_PATH" >&2
  exit 1
fi

# Ensure the bundled executable is present and executable
EXEC="$APP_PATH/Contents/MacOS/$APP_EXECUTABLE_NAME"
if [[ -f "$EXEC" ]]; then
  echo "Found executable: $EXEC"
  chmod +x "$EXEC" || true
else
  echo "Warning: expected executable not found at $EXEC" >&2
fi

# Optional codesign (set CODESIGN_ID in environment to sign)
if [[ -n "${CODESIGN_ID:-}" ]]; then
  echo "Codesigning app with identity: $CODESIGN_ID"
  # --deep to sign nested frameworks/bundles; --options runtime for hardened runtime
  codesign --deep --force --options runtime --sign "$CODESIGN_ID" "$APP_PATH" || {
    echo "codesign failed" >&2
  }
fi

echo "Creating DMG at $DMG_PATH..."

mkdir -p "$DMG_STAGE_DIR"

APP_NAME="$(basename "$APP_PATH")"

echo "Staging DMG layout in $DMG_STAGE_DIR"
rsync -a "$APP_PATH" "$DMG_STAGE_DIR/"

if [[ "$DMG_APPLICATIONS_SYMLINK" == "true" ]]; then
  ln -sfn /Applications "$DMG_STAGE_DIR/Applications"
fi

if [[ -n "$DMG_README_SOURCE" && -f "$DMG_README_SOURCE" ]]; then
  cp "$DMG_README_SOURCE" "$DMG_STAGE_DIR/$DMG_EMBED_README_NAME"
elif [[ "$DMG_EMBED_README" == "true" ]]; then
  cat > "$DMG_STAGE_DIR/$DMG_EMBED_README_NAME" <<'EOF'
OnDeviceAI macOS bundle
========================

Drag **OnDeviceAI.app** into the Applications folder to install.

Troubleshooting:
- If macOS cannot open the app, right-click it and choose **Open** to bypass Gatekeeper prompts.
- The automation daemon expects bundled models and configuration inside the app Resources directory.
- For latest notes visit https://github.com/gigakumar/MahiLLM_app

Enjoy a fully local-first automation stack!
EOF
fi

if [[ -n "$DMG_BACKGROUND_IMAGE" && -f "$DMG_BACKGROUND_IMAGE" ]]; then
  mkdir -p "$DMG_BACKGROUND_DEST"
  cp "$DMG_BACKGROUND_IMAGE" "$DMG_BACKGROUND_DEST/$DMG_BACKGROUND_NAME"
fi

# Compute an appropriate size (in MB) with headroom
DMG_SIZE_MB=$(du -sm "$DMG_STAGE_DIR" | awk '{print $1 + 40}')

if [[ -f "$DMG_RW_IMAGE" ]]; then
  rm -f "$DMG_RW_IMAGE"
fi

echo "Creating read-write DMG image ($DMG_SIZE_MB MB)"
hdiutil create -megabytes "$DMG_SIZE_MB" -fs HFS+J -volname "$VOLNAME" -ov "$DMG_RW_IMAGE"

echo "Mounting read-write DMG"
ATTACH_OUTPUT=$(hdiutil attach -nobrowse -noautoopen "$DMG_RW_IMAGE")
DMG_RW_ATTACHED=$(echo "$ATTACH_OUTPUT" | tail -n 1 | awk '{print $3}')

if [[ -z "$DMG_RW_ATTACHED" ]]; then
  echo "Failed to mount DMG image" >&2
  exit 1
fi

echo "Copying staged content into mounted DMG"
rsync -a "$DMG_STAGE_DIR"/ "$DMG_RW_ATTACHED"/

if [[ -n "$DMG_VOLUME_ICON" && -f "$DMG_VOLUME_ICON" ]]; then
  cp "$DMG_VOLUME_ICON" "$DMG_RW_ATTACHED/.VolumeIcon.icns"
  if command -v SetFile >/dev/null 2>&1; then
    SetFile -a C "$DMG_RW_ATTACHED"
  fi
fi

sync

echo "Detaching read-write DMG"
hdiutil detach "$DMG_RW_ATTACHED"
unset DMG_RW_ATTACHED

echo "Compressing image"
hdiutil convert "$DMG_RW_IMAGE" -format UDZO -imagekey zlib-level=9 -o "$DMG_COMPRESSED_BASENAME" >/dev/null

rm -f "$DMG_PATH"
mv "$DMG_COMPRESSED_BASENAME.dmg" "$DMG_PATH"

echo "DMG created: $DMG_PATH"
