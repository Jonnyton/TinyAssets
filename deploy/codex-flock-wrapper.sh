#!/usr/bin/env bash
# Codex CLI cross-container serialization wrapper.
#
# PR #965 binds /var/lib/workflow-codex -> /app/.codex into both the
# workflow-daemon and workflow-worker containers so Codex's in-place
# refresh chain survives container restarts. Codex's official CI/CD
# auth guide warns that one auth.json must NOT be shared across
# concurrent runners — concurrent refresh attempts race the rotation
# and trigger the exact `refresh_token_reused` class we are fixing
# (see OpenAI Codex issue #10332).
#
# Mitigation: every `codex` invocation goes through this wrapper, which
# takes an exclusive flock on a sentinel file inside the shared auth
# directory. The lock file lives next to auth.json so containers that
# bind the same host directory see the same lock and serialize their
# `codex exec` calls. Per-invocation lock, not held across calls —
# refresh + write happen inside one `codex exec` process, so the
# serialization window matches the rotation window exactly.
#
# When /app/.codex is not present (local dev, Docker run without the
# compose bind mount), the wrapper falls back to a per-process lock in
# /tmp. Single-container correctness is not at risk because there's no
# second container competing for the auth file.

set -euo pipefail

CODEX_BIN="/opt/codex-install/node_modules/.bin/codex"
CODEX_LOCK_DIR="${HOME:-/app}/.codex"
CODEX_LOCK_FALLBACK_DIR="/tmp"

if [[ -d "${CODEX_LOCK_DIR}" ]]; then
    LOCK_FILE="${CODEX_LOCK_DIR}/.lock"
else
    LOCK_FILE="${CODEX_LOCK_FALLBACK_DIR}/codex.lock"
fi

# Create the lock sentinel if missing. Use a tight chmod so the file
# doesn't leak readability beyond the codex auth dir's own posture
# (mode 700 on the dir + 600 on auth.json).
if [[ ! -e "${LOCK_FILE}" ]]; then
    # touch may race with a concurrent invocation; ignore the race —
    # whichever process wins still ends up with a valid lock target.
    touch "${LOCK_FILE}" 2>/dev/null || true
    chmod 600 "${LOCK_FILE}" 2>/dev/null || true
fi

# Pass the lock fd through flock; -x = exclusive, no timeout (codex
# refresh + write completes in well under a second; if codex itself
# hangs that's an unrelated problem and the call timeout handles it).
exec flock -x "${LOCK_FILE}" "${CODEX_BIN}" "$@"
