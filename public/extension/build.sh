#!/usr/bin/env bash
# Build script — produces thronos-wallet-extension.zip for Chrome/Brave
set -e

cd "$(dirname "$0")"

echo "Building Thronos Wallet Extension..."

ZIP_NAME="thronos-wallet-extension.zip"
rm -f "$ZIP_NAME"

zip -r "$ZIP_NAME" \
  manifest.json \
  popup.html popup.js popup.css \
  background.js content.js inject.js \
  lib/secp256k1.js lib/qrcode.min.js \
  icons/icon16.png icons/icon48.png icons/icon128.png

echo "✅ Built: $ZIP_NAME ($(du -sh $ZIP_NAME | cut -f1))"
echo ""
echo "To install in Chrome/Brave:"
echo "  1. Go to chrome://extensions/"
echo "  2. Enable 'Developer mode'"
echo "  3. Click 'Load unpacked' → select this directory"
echo "  OR"
echo "  3. Click 'Load packed extension' → select $ZIP_NAME"
