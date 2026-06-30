#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
xcodebuild \
  -project TinyAssets.xcodeproj \
  -scheme TinyAssets \
  -configuration Debug \
  -destination 'platform=iOS Simulator,name=iPhone 16' \
  build
