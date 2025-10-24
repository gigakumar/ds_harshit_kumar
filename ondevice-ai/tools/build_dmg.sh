#!/usr/bin/env bash
set -euo pipefail

APP_PATH="dist/OnDeviceAI.app"
DMG_PATH="dist/OnDeviceAI.dmg"
VOLNAME="OnDeviceAI"

if [[ ! -d "$APP_PATH" ]]; then
  echo "App bundle not found at $APP_PATH" >&2
  exit 1
fi

echo "Creating DMG at $DMG_PATH..."
hdiutil create -volname "$VOLNAME" -srcfolder "$APP_PATH" -ov -format UDZO "$DMG_PATH"
echo "DMG created: $DMG_PATH"
