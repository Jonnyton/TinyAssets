#!/usr/bin/env bash
set -euo pipefail

: "${SOURCE_DATE_EPOCH:?SOURCE_DATE_EPOCH must be provisioned}"
: "${APPLE_DEVELOPER_ID_APPLICATION:?signing identity not provisioned: Apple Developer ID}"
: "${APPLE_ID:?signing identity not provisioned: Apple notarization account}"
: "${APPLE_TEAM_ID:?signing identity not provisioned: Apple team identifier}"
: "${APPLE_APP_PASSWORD:?signing identity not provisioned: Apple notarization password}"
: "${VERSION:?VERSION must be provisioned}"
: "${ARCHITECTURE:?ARCHITECTURE must be provisioned}"

app="packaging/dist/macos/TinyAssets.app"
dmg="packaging/dist/macos/TinyAssets-${VERSION}-${ARCHITECTURE}.dmg"
codesign --force --deep --options runtime --timestamp \
  --sign "$APPLE_DEVELOPER_ID_APPLICATION" "$app"
codesign --verify --deep --strict --verbose=2 "$app"
rm -f "$dmg"
hdiutil create -volname TinyAssets -srcfolder "$app" -ov -format UDZO "$dmg"
codesign --force --timestamp --sign "$APPLE_DEVELOPER_ID_APPLICATION" "$dmg"
xcrun notarytool submit "$dmg" \
  --apple-id "$APPLE_ID" \
  --team-id "$APPLE_TEAM_ID" \
  --password "$APPLE_APP_PASSWORD" \
  --wait
xcrun stapler staple "$dmg"
xcrun stapler validate "$dmg"
spctl --assess --type open --context context:primary-signature --verbose=2 "$dmg"
