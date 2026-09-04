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

echo "=== set aside any previously generated platform ==="
# This runs against a BIND-MOUNTED repo, so anything removed here is removed on
# the host. `mobile/android/` is generated and gitignored, but gitignored is not
# the same as disposable: a developer may hold uncommitted manifest or Java
# customization there, and it exists on no remote and in no history. Hard Rule
# 13 says inventory before destroying, and a script cannot inventory for you.
# So move it aside rather than delete it, and say where it went.
if [ -e android ]; then
  superseded="android.superseded.$(date -u +%Y%m%dT%H%M%SZ)"
  mv android "$superseded"
  echo "previous android/ preserved as mobile/$superseded"
  echo "it is gitignored; delete it yourself once you have checked it holds nothing you want"
fi

echo "=== cap add/sync android ==="
npx --no-install cap add android
npx --no-install cap sync android

echo "=== deep-link scheme ==="
python3 scripts/add_app_scheme.py
grep -n 'android:scheme="tinyassets"' android/app/src/main/AndroidManifest.xml

echo "=== launcher icon + splash ==="
python3 scripts/add_app_icons.py

echo "=== release identity, version, manifest + artwork gate ==="
python3 scripts/configure_android_release.py
python3 scripts/verify_android_release.py --artwork-only
python3 scripts/verify_android_release.py

echo "=== declared SDK levels ==="
cat android/variables.gradle

echo "=== version code / name ==="
grep -nE "versionCode|versionName" android/app/build.gradle

echo "=== gradle lintRelease + bundleRelease ==="
cd android
./gradlew lintRelease bundleRelease --no-daemon --stacktrace
cd ..
python3 scripts/verify_android_release.py --merged
cd android

echo "=== locate bundle ==="
# android-release.yml asserts the located path is non-empty before it signs
# (see its "Locate the bundle" step). Mirror that, or a Gradle run that exits 0
# without producing a bundle reports success here and fails later in sign.sh.
aab="$(find app/build/outputs/bundle/release -type f -name '*.aab' -print -quit)"
[ -n "$aab" ] || { echo "no .aab produced by bundleRelease"; exit 1; }
ls -la "$aab"
