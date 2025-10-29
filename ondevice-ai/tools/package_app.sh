#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
VENV_PATH="${VENV_PATH:-$ROOT_DIR/.venv}"
PYTHON_BIN="$VENV_PATH/bin/python3"
PIP_BIN="$VENV_PATH/bin/pip"
PYINSTALLER_BIN="$VENV_PATH/bin/pyinstaller"

BUILD_DIR="$ROOT_DIR/build"
PY_DIST="$BUILD_DIR/python-dist"
PY_WORK="$BUILD_DIR/python-build"
BACKEND_STAGE="$BUILD_DIR/backend"
SWIFT_PACKAGE_DIR="$ROOT_DIR/swift/OnDeviceAIApp"
TARGET_DIST_DIR="$ROOT_DIR/dist"
TARGET_APP="$TARGET_DIST_DIR/OnDeviceAI.app"
BACKEND_RESOURCE_DIR="$TARGET_APP/Contents/Resources/backend"
DMG_PATH="$TARGET_DIST_DIR/OnDeviceAI.dmg"
ARTIFACT_DMG="$ROOT_DIR/artifacts/OnDeviceAIApp.dmg"
PYINSTALLER_OUTPUT_NAME="${PYINSTALLER_OUTPUT_NAME:-mahi_backend}"
PYINSTALLER_APP_BUNDLE="${PYINSTALLER_APP_BUNDLE:-MahiBackend.app}"

APP_DISPLAY_NAME="${APP_DISPLAY_NAME:-OnDeviceAI}"
APP_EXECUTABLE_NAME="${APP_EXECUTABLE_NAME:-OnDeviceAIApp}"
APP_VERSION="${APP_VERSION:-1.0.0}"
APP_BUILD="${APP_BUILD:-1}"
BUNDLE_IDENTIFIER="${BUNDLE_IDENTIFIER:-ai.ondevice.app}"
APP_ICON_SOURCE="${APP_ICON_SOURCE:-$ROOT_DIR/assets/icon.icns}"

mkdir -p "$BUILD_DIR" "$TARGET_DIST_DIR" "$ROOT_DIR/artifacts"

if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "Creating virtual environment at $VENV_PATH"
  python3 -m venv "$VENV_PATH"
fi

if [[ ! -x "$PYINSTALLER_BIN" ]]; then
  echo "Installing Python packaging dependencies"
  "$PIP_BIN" install -r "$ROOT_DIR/requirements.txt"
fi

echo "Cleaning previous build artifacts"
rm -rf "$PY_DIST" "$PY_WORK" "$BACKEND_STAGE"
rm -rf "$TARGET_APP" "$DMG_PATH"

if [[ -d "$TARGET_DIST_DIR/OnDeviceAI" ]]; then
  rm -rf "$TARGET_DIST_DIR/OnDeviceAI"
fi

echo "Building backend with PyInstaller"
"$PYINSTALLER_BIN" "$ROOT_DIR/packaging/OnDeviceAI.spec" --noconfirm --distpath "$PY_DIST" --workpath "$PY_WORK"

BACKEND_DIST_PATH="$PY_DIST/$PYINSTALLER_OUTPUT_NAME"

if [[ ! -d "$BACKEND_DIST_PATH" ]]; then
  echo "PyInstaller output missing expected directory at $BACKEND_DIST_PATH" >&2
  exit 1
fi

mkdir -p "$BACKEND_STAGE"
cp -R "$BACKEND_DIST_PATH"/. "$BACKEND_STAGE"/

# Drop any auxiliary PyInstaller app bundle to avoid shipping duplicate UIs
if [[ -d "$PY_DIST/$PYINSTALLER_APP_BUNDLE" ]]; then
  rm -rf "$PY_DIST/$PYINSTALLER_APP_BUNDLE"
fi

echo "Building Swift UI app"
SWIFT_BIN_PATH=$(cd "$SWIFT_PACKAGE_DIR" && swift build -c release --show-bin-path | tail -n 1)
SWIFT_BINARY="$SWIFT_BIN_PATH/$APP_EXECUTABLE_NAME"

if [[ ! -x "$SWIFT_BINARY" ]]; then
  echo "Swift build did not produce expected binary at $SWIFT_BINARY" >&2
  exit 1
fi

echo "Assembling Swift app bundle"
rm -rf "$TARGET_APP"
mkdir -p "$TARGET_APP/Contents/MacOS" "$TARGET_APP/Contents/Resources"

cp "$SWIFT_BINARY" "$TARGET_APP/Contents/MacOS/$APP_EXECUTABLE_NAME"
chmod +x "$TARGET_APP/Contents/MacOS/$APP_EXECUTABLE_NAME"

if [[ -f "$APP_ICON_SOURCE" ]]; then
  cp "$APP_ICON_SOURCE" "$TARGET_APP/Contents/Resources/icon.icns"
fi

cat > "$TARGET_APP/Contents/Info.plist" <<EOPLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleDisplayName</key>
  <string>$APP_DISPLAY_NAME</string>
  <key>CFBundleExecutable</key>
  <string>$APP_EXECUTABLE_NAME</string>
  <key>CFBundleIconFile</key>
  <string>icon.icns</string>
  <key>CFBundleIdentifier</key>
  <string>$BUNDLE_IDENTIFIER</string>
  <key>CFBundleInfoDictionaryVersion</key>
  <string>6.0</string>
  <key>CFBundleName</key>
  <string>$APP_DISPLAY_NAME</string>
  <key>CFBundlePackageType</key>
  <string>APPL</string>
  <key>CFBundleShortVersionString</key>
  <string>$APP_VERSION</string>
  <key>CFBundleVersion</key>
  <string>$APP_BUILD</string>
  <key>LSBackgroundOnly</key>
  <false/>
  <key>LSUIElement</key>
  <false/>
  <key>NSHighResolutionCapable</key>
  <true/>
</dict>
</plist>
EOPLIST

mkdir -p "$BACKEND_RESOURCE_DIR"
rsync -a "$BACKEND_STAGE"/ "$BACKEND_RESOURCE_DIR"/

# Ensure backend binary is executable after copy
if [[ -f "$BACKEND_RESOURCE_DIR/$PYINSTALLER_OUTPUT_NAME" ]]; then
  chmod +x "$BACKEND_RESOURCE_DIR/$PYINSTALLER_OUTPUT_NAME"
fi

echo "Packaging DMG"
if [[ -f "$DMG_PATH" ]]; then
  rm -f "$DMG_PATH"
fi
APP_EXECUTABLE_NAME="$APP_EXECUTABLE_NAME" bash "$ROOT_DIR/tools/build_dmg.sh"

echo "Copying DMG to artifacts"
cp "$DMG_PATH" "$ARTIFACT_DMG"

# Provide checksum for convenience
shasum -a 256 "$ARTIFACT_DMG" > "$ARTIFACT_DMG.sha256"

cat <<EOM
Swift UI app packaged successfully.
  App Bundle: $TARGET_APP
  Backend Resources: $BACKEND_RESOURCE_DIR
  DMG: $ARTIFACT_DMG
  SHA256: $(cut -d' ' -f1 "$ARTIFACT_DMG.sha256")
EOM
