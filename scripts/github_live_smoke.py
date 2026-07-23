#!/usr/bin/env python3
"""Env-gated LIVE GitHub smoke — S4 / E4.

Exercises the live ``HttpGitHubApi`` READ path (``verify_review_gate_active`` on
a real repo/branch) against real credentials, to confirm the HTTP wiring works
end to end when credentials exist. It is READ-ONLY: it never creates a PR,
submits a review, or merges.

**Refuses to run without explicit opt-in.** Set ``TINYASSETS_GITHUB_LIVE_SMOKE=1``
AND supply a target + a credential, or it exits non-zero without touching the
network. Credentials are read from env for this manual check ONLY — production
credential storage is the vault lane's job, not this script's.

Env:
  TINYASSETS_GITHUB_LIVE_SMOKE=1                (required opt-in)
  TINYASSETS_GITHUB_SMOKE_REPO=owner/repo       (required)
  TINYASSETS_GITHUB_SMOKE_BRANCH=main           (default: main)
  # one credential path:
  TINYASSETS_GITHUB_SMOKE_PAT=github_pat_...     (fine-grained PAT), OR
  TINYASSETS_GITHUB_APP_ID / _INSTALLATION_ID / _PEM_PATH  (GitHub App)
  TINYASSETS_GITHUB_SMOKE_APP_ACTOR_ID=<int>    (optional; App integration id
                                                 for the bypass-actor check)

Exit 0 = probe ran (whether or not the repo is gated — it prints the summary).
Exit 2 = refused (no opt-in / missing target / missing credential).
Exit 3 = the live call raised.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tinyassets import github_auth as ga  # noqa: E402
from tinyassets import github_http as gh  # noqa: E402
from tinyassets import github_native as gn  # noqa: E402


def _refuse(msg: str) -> int:
    print(f"REFUSED: {msg}", file=sys.stderr)
    return 2


def _build_installation_provider():
    pat = os.environ.get("TINYASSETS_GITHUB_SMOKE_PAT", "").strip()
    if pat:
        return ga.StaticTokenProvider(pat, purposes={ga.PURPOSE_INSTALLATION})
    app_id = os.environ.get("TINYASSETS_GITHUB_APP_ID", "").strip()
    inst_id = os.environ.get("TINYASSETS_GITHUB_INSTALLATION_ID", "").strip()
    pem_path = os.environ.get("TINYASSETS_GITHUB_PEM_PATH", "").strip()
    if app_id and inst_id and pem_path:
        pem = Path(pem_path).read_text(encoding="utf-8")
        return ga.GitHubAppTokenProvider(
            app_id=app_id, private_key_pem=pem, installation_id=inst_id,
            token_exchange=gh.installation_token_exchange(),
        )
    return None


def main() -> int:
    if os.environ.get("TINYASSETS_GITHUB_LIVE_SMOKE", "").strip() not in {"1", "true", "yes"}:
        return _refuse(
            "set TINYASSETS_GITHUB_LIVE_SMOKE=1 to allow a live GitHub call"
        )
    repo = os.environ.get("TINYASSETS_GITHUB_SMOKE_REPO", "").strip()
    if not repo or "/" not in repo:
        return _refuse("set TINYASSETS_GITHUB_SMOKE_REPO=owner/repo")
    branch = os.environ.get("TINYASSETS_GITHUB_SMOKE_BRANCH", "main").strip() or "main"
    provider = _build_installation_provider()
    if provider is None:
        return _refuse(
            "supply TINYASSETS_GITHUB_SMOKE_PAT or the App triple "
            "(TINYASSETS_GITHUB_APP_ID / _INSTALLATION_ID / _PEM_PATH)"
        )
    app_actor_id = os.environ.get("TINYASSETS_GITHUB_SMOKE_APP_ACTOR_ID", "").strip() or None

    api = gh.HttpGitHubApi(provider)
    print(f"LIVE read-only smoke: verify_review_gate_active({repo}@{branch}) …")
    try:
        gated, summary = gn.verify_review_gate_active(
            api, destination=repo, branch=branch, app_actor_id=app_actor_id
        )
    except gh.GitHubHttpError as exc:
        print("LIVE CALL RAISED:", json.dumps(exc.to_dict(), indent=2), file=sys.stderr)
        return 3
    print(json.dumps({"gated": gated, "summary": summary}, indent=2))
    print("OK: live read path works (no writes performed).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
