#!/usr/bin/env bash
# Wire Cowork's git push + gh CLI access on session start.
# Reads GH_TOKEN from the environment or .cowork-bootstrap/github.token
# (gitignored) and configures ~/.git-credentials so Cowork's Linux
# sandbox can push.
set -euo pipefail
SECRETS="$(cd "$(dirname "$0")/.." && pwd)/.cowork-bootstrap"
tok="${GH_TOKEN:-}"
if [ -z "$tok" ] && [ -f "$SECRETS/github.token" ]; then
  tok="$(cat "$SECRETS/github.token")"
fi
if [ -z "$tok" ]; then
  echo "::warning::no GH_TOKEN or $SECRETS/github.token — Cowork stays read-only"
  exit 0
fi
git config --global credential.helper store
printf 'https://Jonnyton:%s@github.com\n' "$tok" > "$HOME/.git-credentials"
chmod 600 "$HOME/.git-credentials"
echo "GH_TOKEN=$tok" > "$HOME/.cowork-env"
chmod 600 "$HOME/.cowork-env"
echo "Cowork creds wired. To use gh, source ~/.cowork-env first."
if ! command -v gh >/dev/null 2>&1; then
  (curl -sSL https://github.com/cli/cli/releases/latest/download/gh_2.61.0_linux_amd64.tar.gz \
    | tar xz -C /tmp \
    && cp /tmp/gh_2.61.0_linux_amd64/bin/gh "$HOME/.local/bin/gh" 2>/dev/null) \
    || echo "gh CLI install skipped (not critical — git push works without it)"
fi
if [ -f "$SECRETS/ssh/do_deploy" ]; then
  mkdir -p "$HOME/.ssh"
  cp "$SECRETS/ssh/do_deploy" "$HOME/.ssh/do_deploy"
  chmod 600 "$HOME/.ssh/do_deploy"
  echo "SSH key installed for droplet access."
fi
