#!/usr/bin/env bash
set -euo pipefail

: "${SOURCE_DATE_EPOCH:?SOURCE_DATE_EPOCH must be provisioned}"
: "${LINUX_SIGNING_KEY_BASE64:?signing identity not provisioned: Linux package signing key}"
: "${LINUX_SIGNING_IDENTITY:?signing identity not provisioned: Linux key fingerprint}"
: "${ARTIFACT:?ARTIFACT must be provisioned}"

if [[ ! -f "$ARTIFACT" ]]; then
  echo "artifact does not exist: $ARTIFACT" >&2
  exit 1
fi
gpg_home="$(mktemp -d)"
trap 'rm -rf "$gpg_home"' EXIT
chmod 700 "$gpg_home"
printf '%s' "$LINUX_SIGNING_KEY_BASE64" | base64 --decode |
  gpg --homedir "$gpg_home" --batch --import
actual_fingerprint="$(
  gpg --homedir "$gpg_home" --batch --with-colons --fingerprint |
    awk -F: '$1 == "fpr" { print $10; exit }'
)"
expected_fingerprint="${LINUX_SIGNING_IDENTITY// /}"
if [[ "${actual_fingerprint^^}" != "${expected_fingerprint^^}" ]]; then
  echo "provisioned Linux key does not match LINUX_SIGNING_IDENTITY" >&2
  exit 1
fi
gpg --homedir "$gpg_home" --batch --yes --armor \
  --local-user "$actual_fingerprint" \
  --detach-sign --output "${ARTIFACT}.asc" "$ARTIFACT"
gpg --homedir "$gpg_home" --verify "${ARTIFACT}.asc" "$ARTIFACT"
