#!/usr/bin/env bash
# Mirrors .github/workflows/android-release.yml's build half, minus signing.
# CI always starts from a clean checkout; this scratch tree does not, and
# `cap add android` refuses to overwrite an existing platform, so drop the
# generated project first. Everything under android/ is regenerated below.
set -euo pipefail

cd /work/mobile

echo "=== versions ==="
node --version
java -version 2>&1 | head -1

echo "=== npm ci ==="
npm ci --ignore-scripts --no-audit --no-fund

echo "=== drop any previously generated platform ==="
rm -rf android

echo "=== cap add/sync android ==="
npx --no-install cap add android
npx --no-install cap sync android

echo "=== deep-link scheme ==="
python3 scripts/add_app_scheme.py
grep -n 'android:scheme="tinyassets"' android/app/src/main/AndroidManifest.xml

echo "=== launcher icon + splash ==="
python3 scripts/add_app_icons.py

echo "=== declared SDK levels ==="
cat android/variables.gradle

echo "=== version code / name ==="
grep -nE "versionCode|versionName" android/app/build.gradle

echo "=== gradle bundleRelease ==="
cd android
./gradlew bundleRelease --no-daemon --stacktrace

echo "=== locate bundle ==="
find app/build/outputs/bundle/release -name '*.aab' -exec ls -la {} +
