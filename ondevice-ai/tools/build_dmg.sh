#!/usr/bin/env bash
set -euo pipefail

APP_PATH="dist/OnDeviceAI.app"
DMG_PATH="dist/OnDeviceAI.dmg"
VOLNAME="OnDeviceAI"

if [[ ! -d "$APP_PATH" ]]; then
  echo "App bundle not found at $APP_PATH" >&2
  exit 1
fi

# Ensure the bundled executable is present and executable
EXEC="$APP_PATH/Contents/MacOS/OnDeviceAI"
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
hdiutil create -volname "$VOLNAME" -srcfolder "$APP_PATH" -ov -format UDZO "$DMG_PATH"
echo "DMG created: $DMG_PATH"
