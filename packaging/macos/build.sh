#!/usr/bin/env bash
set -euo pipefail

: "${SOURCE_DATE_EPOCH:?SOURCE_DATE_EPOCH must be provisioned for reproducible builds}"
: "${VERSION:?VERSION must be provisioned}"
: "${ARCHITECTURE:?ARCHITECTURE must be provisioned}"

repo="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$repo"
python -m PyInstaller --noconfirm --clean \
  --distpath packaging/dist/macos \
  --workpath packaging/build/macos \
  packaging/macos/TinyAssets.spec

touch -t "$(date -u -r "$SOURCE_DATE_EPOCH" +%Y%m%d%H%M.%S)" \
  packaging/dist/macos/TinyAssets.app
hdiutil create \
  -volname TinyAssets \
  -srcfolder packaging/dist/macos/TinyAssets.app \
  -ov -format UDZO \
  "packaging/dist/macos/TinyAssets-${VERSION}-${ARCHITECTURE}.dmg"
