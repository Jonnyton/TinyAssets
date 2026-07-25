#!/usr/bin/env bash
set -euo pipefail

: "${SOURCE_DATE_EPOCH:?SOURCE_DATE_EPOCH must be provisioned}"
: "${LINUX_SIGNING_KEY_BASE64:?signing identity not provisioned: Linux package signing key}"
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
gpg --homedir "$gpg_home" --batch --yes --armor \
  --detach-sign --output "${ARTIFACT}.asc" "$ARTIFACT"
gpg --homedir "$gpg_home" --verify "${ARTIFACT}.asc" "$ARTIFACT"
