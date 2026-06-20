#!/usr/bin/env bash
# Configure GitHub branch protection so main merges require a founder
# code-owner review on the current head plus green CI.

set -euo pipefail

REPO="${REPO:-Jonnyton/Workflow}"
BRANCH="${BRANCH:-main}"
REQUIRED_STATUS_CONTEXTS="${REQUIRED_STATUS_CONTEXTS:-actionlint,Docker build smoke,Daemon request policy}"

if ! command -v gh >/dev/null 2>&1; then
    echo "gh CLI is required" >&2
    exit 1
fi

IFS=',' read -r -a contexts <<< "$REQUIRED_STATUS_CONTEXTS"
contexts_json="$(printf '%s\n' "${contexts[@]}" | python3 -c 'import json,sys; print(json.dumps([line.strip() for line in sys.stdin if line.strip()]))')"
protection_url="repos/${REPO}/branches/${BRANCH}/protection"

printf 'Enabling auto-merge for %s...\n' "$REPO"
gh api --method PATCH "repos/${REPO}" \
    -H 'Accept: application/vnd.github+json' \
    -f allow_auto_merge=true >/dev/null

printf 'Applying branch protection to %s/%s...\n' "$REPO" "$BRANCH"
python3 - "$contexts_json" <<'PY' | gh api --method PUT "$protection_url" \
    -H 'Accept: application/vnd.github+json' \
    --input - >/dev/null
import json
import sys

contexts = json.loads(sys.argv[1])
print(json.dumps({
    "required_status_checks": {
        "strict": True,
        "contexts": contexts,
    },
    "enforce_admins": True,
    "required_pull_request_reviews": {
        "dismiss_stale_reviews": True,
        "require_code_owner_reviews": True,
        "required_approving_review_count": 1,
        "require_last_push_approval": True,
    },
    "restrictions": None,
    "required_linear_history": False,
    "allow_force_pushes": False,
    "allow_deletions": False,
    "block_creations": False,
    "required_conversation_resolution": True,
    "lock_branch": False,
    "allow_fork_syncing": True,
}))
PY

printf 'Secure merge gate applied. Verify CODEOWNERS includes @Jonnyton and that the bot is not an admin.\n'
