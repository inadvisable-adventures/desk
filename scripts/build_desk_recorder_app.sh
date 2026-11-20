#!/bin/bash
# Builds DeskRecorder.app (TODO b9689cd, plans/desk-recorder-app.md) from desk_recorder/launcher.m.
#
#   scripts/build_desk_recorder_app.sh [--output DIR] [--no-install]
#
# Default: build into build/ and install to ~/Applications/DeskRecorder.app, which is where Desk looks
# (also /Applications, or DESK_RECORDER_APP). The checkout's path and .venv python are baked into the app,
# so rebuild after moving the checkout. DESK_RECORDER_PYTHON overrides the python baked in (used by tests).
#
# The bundle is signed ad hoc with the designated requirement `identifier "local.desk.recorder"`, so
# macOS keeps its Screen Recording / Camera / Microphone grants across rebuilds (not verified; if a
# rebuild loses one, grant it again in System Settings > Privacy & Security).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUTPUT="$ROOT/build"
INSTALL=1
while [ $# -gt 0 ]; do
  case "$1" in
    --output) OUTPUT="$2"; shift 2 ;;
    --no-install) INSTALL=0; shift ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done
PYTHON="${DESK_RECORDER_PYTHON:-$ROOT/.venv/bin/python}"
LOG="${DESK_RECORDER_LOG:-$HOME/Library/Logs/DeskRecorder.log}"
BUNDLE_ID="local.desk.recorder"
APP="$OUTPUT/DeskRecorder.app"

rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$(dirname "$LOG")"
clang -O1 -fobjc-arc -framework AVFoundation -framework CoreGraphics -framework Foundation \
  -o "$APP/Contents/MacOS/DeskRecorder" "$ROOT/desk_recorder/launcher.m" \
  -DPROJECT_DIR="\"$ROOT\"" -DPYTHON_BIN="\"$PYTHON\"" -DLOG_FILE="\"$LOG\""
cat > "$APP/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>CFBundleName</key><string>DeskRecorder</string>
<key>CFBundleDisplayName</key><string>DeskRecorder</string>
<key>CFBundleIdentifier</key><string>$BUNDLE_ID</string>
<key>CFBundleExecutable</key><string>DeskRecorder</string>
<key>CFBundlePackageType</key><string>APPL</string>
<key>CFBundleVersion</key><string>1</string>
<key>LSUIElement</key><true/>
<key>NSCameraUsageDescription</key><string>DeskRecorder records video from your camera when you turn on camera recording in Desk.</string>
<key>NSMicrophoneUsageDescription</key><string>DeskRecorder listens to your microphone for transcription and screen-recording audio when you turn them on in Desk.</string>
<key>NSCameraUseContinuityCameraDeviceType</key><true/>
</dict></plist>
PLIST
codesign --force --sign - --identifier "$BUNDLE_ID" -r="designated => identifier \"$BUNDLE_ID\"" "$APP"
echo "built $APP"
if [ "$INSTALL" = 1 ]; then
  mkdir -p "$HOME/Applications"
  rm -rf "$HOME/Applications/DeskRecorder.app"
  cp -R "$APP" "$HOME/Applications/DeskRecorder.app"
  echo "installed ~/Applications/DeskRecorder.app"
fi
