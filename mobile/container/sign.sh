#!/usr/bin/env bash
# Mirrors the "Sign the bundle with the upload key" step of
# .github/workflows/android-release.yml, including the fail-closed
# certificate pin. Passwords reach keytool/jarsigner via `:env` only —
# never argv, never stdout.
set -euo pipefail

EXPECTED_SHA256="D0:BC:F2:FB:EA:4E:11:6D:87:DD:DD:BD:B2:4C:1E:28:53:7A:CA:77:BE:8E:69:BE:AD:52:C7:C1:C1:03:B2:11"

# /keys is mounted read-only from ~/.tinyassets/android.
#
# The env file was written on Windows and has CRLF endings, so sourcing it
# directly leaves a trailing carriage return on every value and keytool fails
# with "Keystore was tampered with, or password was incorrect" — a message that
# blames the keystore for what is really a line-ending bug. Strip CR first.
env_clean="$(mktemp)"
trap 'rm -f "$env_clean" /tmp/upload.jks' EXIT
tr -d '\r' < /keys/upload-keystore.env > "$env_clean"

set -a
# shellcheck disable=SC1090
. "$env_clean"
set +a

KEYSTORE_PASSWORD="${ANDROID_UPLOAD_KEYSTORE_PASSWORD:?missing}"
KEY_PASSWORD="${ANDROID_UPLOAD_KEY_PASSWORD:?missing}"
KEY_ALIAS="${ANDROID_UPLOAD_KEY_ALIAS:?missing}"
export KEYSTORE_PASSWORD KEY_PASSWORD

ks=/tmp/upload.jks
cp /keys/tinyassets-upload.jks "$ks"

actual="$(keytool -list -v -keystore "$ks" -storepass:env KEYSTORE_PASSWORD -alias "$KEY_ALIAS" | awk '/SHA256:/ {print $2; exit}')"
if [ "$actual" != "$EXPECTED_SHA256" ]; then
  echo "FINGERPRINT MISMATCH"
  echo "  expected $EXPECTED_SHA256"
  echo "  actual   $actual"
  echo "refusing to sign"
  exit 1
fi
echo "upload certificate fingerprint verified"

# `|| true` matters: under `set -e -o pipefail` a failing find would abort the
# script at this assignment, so the friendly message below would never print.
AAB="$(find /work/mobile/android/app/build/outputs/bundle/release -name '*.aab' 2>/dev/null | head -1 || true)"
if [ -z "$AAB" ]; then
  echo "no .aab under mobile/android/app/build/outputs/bundle/release — run build.sh first"
  exit 1
fi
echo "bundle: $AAB"

jarsigner -sigalg SHA256withRSA -digestalg SHA-256 \
  -keystore "$ks" -storepass:env KEYSTORE_PASSWORD -keypass:env KEY_PASSWORD \
  "$AAB" "$KEY_ALIAS"

jarsigner -verify "$AAB"
# mobile/ is gitignored for *.aab, so the artifact cannot be committed by accident.
cp "$AAB" /work/mobile/tinyassets-release.aab
ls -la /work/mobile/tinyassets-release.aab
echo "SIGNED OK"
