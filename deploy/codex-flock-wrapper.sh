#!/usr/bin/env bash
# Codex CLI cross-container serialization wrapper.
#
# Every codex launch is a universe's provider child, started with that
# universe's own CODEX_HOME (tinyassets/providers/base.py
# subprocess_env_for_provider); the platform holds no Codex login of its own
# (AGENTS.md Hard Rule 15). Codex's official CI/CD auth guide warns that one
# auth.json must NOT be shared across concurrent runners -- concurrent
# refresh attempts race the rotation and trigger `refresh_token_reused`
# (OpenAI Codex issue #10332) -- and two turns of one universe can launch
# against the same home.
#
# Mitigation: every `codex` invocation goes through this wrapper, which
# takes an exclusive flock on a sentinel file inside the shared auth
# directory. The lock file lives next to auth.json so containers that
# bind the same host directory see the same lock and serialize their
# `codex exec` calls. Per-invocation lock, not held across calls —
# refresh + write happen inside one `codex exec` process, so the
# serialization window matches the rotation window exactly.
#
# When CODEX_HOME is not present (local dev), the wrapper falls back to
# HOME/.codex and then a per-process lock in /tmp.

set -euo pipefail

CODEX_BIN="/opt/codex-install/node_modules/.bin/codex"
CODEX_LOCK_DIR="${CODEX_HOME:-${HOME:-/app}/.codex}"
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
