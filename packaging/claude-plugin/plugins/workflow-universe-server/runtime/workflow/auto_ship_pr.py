"""Feature-flagged PR creation for auto-ship attempts.

Phase 2 of the auto-ship canary lane opens a GitHub PR from an existing
``auto-change/*`` branch after ``validate_ship_packet`` has already passed
and written an ``auto_ship_attempts`` row. This module owns only that PR-open
step. It does not apply patches, push branches, poll approvals, or merge.
"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Callable

from workflow.auto_ship_ledger import find_attempt, update_attempt

PR_CREATE_FLAG = "WORKFLOW_AUTO_SHIP_PR_CREATE_ENABLED"
REPO_ENV = "WORKFLOW_AUTO_SHIP_REPO"
DEFAULT_REPO = "Jonnyton/Workflow"
TOKEN_ENV_VARS = ("GH_TOKEN", "GITHUB_TOKEN")

_TRUE_VALUES = {"1", "true", "yes", "on"}
_AUTO_CHANGE_BRANCH_RE = re.compile(r"^auto-change/[A-Za-z0-9._/-]+$")

JsonPost = Callable[[str, str, dict[str, Any]], tuple[int, dict[str, Any]]]
JsonGet = Callable[[str, str], tuple[int, dict[str, Any]]]


def pr_create_enabled(value: str | None = None) -> bool:
    """Return True only for explicit truthy flag values."""
    if value is None:
        value = os.environ.get(PR_CREATE_FLAG, "")
    return value.strip().lower() in _TRUE_VALUES


def _github_token(explicit: str | None = None) -> str:
    if explicit is not None:
        return explicit.strip()
    for name in TOKEN_ENV_VARS:
        token = os.environ.get(name, "").strip()
        if token:
            return token
    return ""


def _repo_slug(explicit: str | None = None) -> str:
    repo = (explicit or os.environ.get(REPO_ENV) or DEFAULT_REPO).strip()
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo):
        raise ValueError(
            f"repo must be owner/name with simple GitHub path parts; got {repo!r}"
        )
    return repo


def _validate_head_branch(head_branch: str) -> str:
    head = head_branch.strip()
    if not head:
        raise ValueError("head_branch is required")
    if ".." in head or head.endswith("/") or not _AUTO_CHANGE_BRANCH_RE.fullmatch(head):
        raise ValueError(
            "head_branch must be an existing same-repo auto-change/* branch"
        )
    return head


def _validate_base_branch(base_branch: str) -> str:
    base = base_branch.strip() or "main"
    if ".." in base or base.endswith("/") or not re.fullmatch(r"[A-Za-z0-9._/-]+", base):
        raise ValueError("base_branch must be a simple same-repo branch ref")
    return base


def _error_result(
    *,
    ship_attempt_id: str,
    ship_status: str,
    error_class: str,
    error_message: str,
    would_open_pr: bool,
    dry_run: bool,
    pr_url: str = "",
    ledger_error: str = "",
) -> dict[str, Any]:
    out: dict[str, Any] = {
        "ship_attempt_id": ship_attempt_id,
        "ship_status": ship_status,
        "would_open_pr": would_open_pr,
        "validation_result": "passed" if would_open_pr else "blocked",
        "pr_url": pr_url,
        "dry_run": dry_run,
        "error_class": error_class,
        "error_message": error_message,
    }
    if ledger_error:
        out["ledger_error"] = ledger_error
    return out


def _mark_attempt(
    universe_path: Path,
    ship_attempt_id: str,
    *,
    ship_status: str,
    error_class: str = "",
    error_message: str = "",
    pr_url: str = "",
    commit_sha: str = "",
    ci_status: str = "",
    rollback_handle: str = "",
) -> str:
    fields: dict[str, Any] = {"ship_status": ship_status}
    if error_class or ship_status == "opened":
        fields["error_class"] = error_class
    if error_message or ship_status == "opened":
        fields["error_message"] = error_message
    if pr_url:
        fields["pr_url"] = pr_url
    if commit_sha:
        fields["commit_sha"] = commit_sha
    if ci_status:
        fields["ci_status"] = ci_status
    if rollback_handle:
        fields["rollback_handle"] = rollback_handle
    try:
        update_attempt(universe_path, ship_attempt_id, **fields)
    except Exception as exc:  # noqa: BLE001 - return observability to caller
        return f"ledger update failed: {exc}"
    return ""


def _post_github_json(url: str, token: str, payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "workflow-auto-ship-pr-create",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read().decode("utf-8")
            return resp.status, json.loads(body) if body else {}
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            parsed: dict[str, Any] = json.loads(body) if body else {}
        except json.JSONDecodeError:
            parsed = {"message": body}
        return exc.code, parsed


def _get_github_json(url: str, token: str) -> tuple[int, dict[str, Any]]:
    req = urllib.request.Request(
        url,
        method="GET",
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "User-Agent": "workflow-auto-ship-pr-create",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read().decode("utf-8")
            return resp.status, json.loads(body) if body else {}
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            parsed: dict[str, Any] = json.loads(body) if body else {}
        except json.JSONDecodeError:
            parsed = {"message": body}
        return exc.code, parsed


def _compare_url(repo_slug: str, base_branch: str, head_branch: str) -> str:
    base = urllib.parse.quote(base_branch, safe="")
    head = urllib.parse.quote(head_branch, safe="")
    return f"https://api.github.com/repos/{repo_slug}/compare/{base}...{head}"


def _head_is_current_with_base(compare: dict[str, Any]) -> bool:
    status = str(compare.get("status") or "")
    try:
        behind_by = int(compare.get("behind_by") or 0)
    except (TypeError, ValueError):
        return False
    return behind_by == 0 and status in {"ahead", "identical"}


def open_auto_ship_pr(
    *,
    universe_path: Path,
    ship_attempt_id: str,
    head_branch: str,
    title: str,
    body: str = "",
    base_branch: str = "main",
    repo: str | None = None,
    create_enabled: bool | None = None,
    token: str | None = None,
    get_json: JsonGet | None = None,
    post_json: JsonPost | None = None,
) -> dict[str, Any]:
    """Open a PR for a passed auto-ship attempt.

    ``create_enabled`` exists for tests; production callers should leave it
    unset and use ``WORKFLOW_AUTO_SHIP_PR_CREATE_ENABLED``. Disabled mode
    never calls GitHub and records ``pr_create_disabled`` on the ledger row so
    the loop can observe that it would have opened a PR.
    """
    attempt_id = ship_attempt_id.strip()
    if not attempt_id:
        return _error_result(
            ship_attempt_id="",
            ship_status="failed",
            error_class="ship_attempt_id_required",
            error_message="ship_attempt_id is required",
            would_open_pr=False,
            dry_run=True,
        )

    attempt = find_attempt(universe_path, attempt_id)
    if attempt is None:
        return _error_result(
            ship_attempt_id=attempt_id,
            ship_status="failed",
            error_class="ship_attempt_not_found",
            error_message=f"ship_attempt_id {attempt_id!r} not found",
            would_open_pr=False,
            dry_run=True,
        )

    if attempt.ship_status == "opened" and attempt.pr_url:
        return {
            "ship_attempt_id": attempt_id,
            "ship_status": "opened",
            "would_open_pr": bool(attempt.would_open_pr),
            "validation_result": "passed" if attempt.would_open_pr else "blocked",
            "pr_url": attempt.pr_url,
            "commit_sha": attempt.commit_sha,
            "ci_status": attempt.ci_status,
            "dry_run": False,
            "already_open": True,
            "error_class": "",
            "error_message": "",
        }

    if attempt.ship_status != "skipped" or not attempt.would_open_pr:
        return _error_result(
            ship_attempt_id=attempt_id,
            ship_status=attempt.ship_status,
            error_class="ship_attempt_not_eligible",
            error_message=(
                "attempt must be ship_status='skipped' with would_open_pr=true "
                "before PR creation"
            ),
            would_open_pr=bool(attempt.would_open_pr),
            dry_run=True,
            pr_url=attempt.pr_url,
        )

    enabled = pr_create_enabled() if create_enabled is None else create_enabled
    if not enabled:
        msg = f"{PR_CREATE_FLAG} is not enabled; PR creation stayed in dry-run mode"
        ledger_error = _mark_attempt(
            universe_path,
            attempt_id,
            ship_status="skipped",
            error_class="pr_create_disabled",
            error_message=msg,
        )
        return _error_result(
            ship_attempt_id=attempt_id,
            ship_status="skipped",
            error_class="pr_create_disabled",
            error_message=msg,
            would_open_pr=True,
            dry_run=True,
            ledger_error=ledger_error,
        )

    try:
        head = _validate_head_branch(head_branch)
        base = _validate_base_branch(base_branch)
        repo_slug = _repo_slug(repo)
    except ValueError as exc:
        msg = str(exc)
        ledger_error = _mark_attempt(
            universe_path,
            attempt_id,
            ship_status="failed",
            error_class="pr_create_invalid_request",
            error_message=msg,
        )
        return _error_result(
            ship_attempt_id=attempt_id,
            ship_status="failed",
            error_class="pr_create_invalid_request",
            error_message=msg,
            would_open_pr=True,
            dry_run=False,
            ledger_error=ledger_error,
        )

    gh_token = _github_token(token)
    if not gh_token:
        msg = "GH_TOKEN or GITHUB_TOKEN is required when PR creation is enabled"
        ledger_error = _mark_attempt(
            universe_path,
            attempt_id,
            ship_status="failed",
            error_class="pr_create_missing_token",
            error_message=msg,
        )
        return _error_result(
            ship_attempt_id=attempt_id,
            ship_status="failed",
            error_class="pr_create_missing_token",
            error_message=msg,
            would_open_pr=True,
            dry_run=False,
            ledger_error=ledger_error,
        )

    get = get_json or _get_github_json
    compare_link = _compare_url(repo_slug, base, head)
    try:
        compare_status, compare_response = get(compare_link, gh_token)
    except Exception as exc:  # noqa: BLE001 - preserve ledger observability
        msg = f"GitHub branch freshness check failed: {type(exc).__name__}: {exc}"
        ledger_error = _mark_attempt(
            universe_path,
            attempt_id,
            ship_status="failed",
            error_class="pr_create_base_check_failed",
            error_message=msg,
        )
        result = _error_result(
            ship_attempt_id=attempt_id,
            ship_status="failed",
            error_class="pr_create_base_check_failed",
            error_message=msg,
            would_open_pr=True,
            dry_run=False,
            ledger_error=ledger_error,
        )
        result["head_branch"] = head
        result["base_branch"] = base
        return result

    if compare_status != 200:
        msg = compare_response.get("message") or json.dumps(compare_response, default=str)
        error_message = (
            f"GitHub branch freshness check failed with HTTP {compare_status}: {msg}"
        )
        ledger_error = _mark_attempt(
            universe_path,
            attempt_id,
            ship_status="failed",
            error_class="pr_create_base_check_failed",
            error_message=error_message,
        )
        result = _error_result(
            ship_attempt_id=attempt_id,
            ship_status="failed",
            error_class="pr_create_base_check_failed",
            error_message=error_message,
            would_open_pr=True,
            dry_run=False,
            ledger_error=ledger_error,
        )
        result["head_branch"] = head
        result["base_branch"] = base
        return result

    if not _head_is_current_with_base(compare_response):
        status_text = str(compare_response.get("status") or "unknown")
        behind_by = compare_response.get("behind_by")
        msg = (
            f"head_branch {head!r} is behind/diverged from base_branch {base!r}; "
            f"compare_status={status_text!r} behind_by={behind_by!r}. "
            "Rebase or recreate the auto-change branch before PR creation."
        )
        ledger_error = _mark_attempt(
            universe_path,
            attempt_id,
            ship_status="failed",
            error_class="pr_create_stale_head",
            error_message=msg,
        )
        result = _error_result(
            ship_attempt_id=attempt_id,
            ship_status="failed",
            error_class="pr_create_stale_head",
            error_message=msg,
            would_open_pr=True,
            dry_run=False,
            ledger_error=ledger_error,
        )
        result["head_branch"] = head
        result["base_branch"] = base
        result["compare_status"] = status_text
        result["behind_by"] = behind_by
        return result

    pr_title = title.strip() or f"[auto-change] {attempt.request_id or attempt_id}"
    payload = {
        "title": pr_title,
        "head": head,
        "base": base,
        "body": body,
        "draft": False,
    }
    post = post_json or _post_github_json
    try:
        status, response = post(
            f"https://api.github.com/repos/{repo_slug}/pulls",
            gh_token,
            payload,
        )
    except Exception as exc:  # noqa: BLE001 - preserve ledger observability
        msg = f"GitHub PR create request failed: {type(exc).__name__}: {exc}"
        ledger_error = _mark_attempt(
            universe_path,
            attempt_id,
            ship_status="failed",
            error_class="pr_create_failed",
            error_message=msg,
        )
        return _error_result(
            ship_attempt_id=attempt_id,
            ship_status="failed",
            error_class="pr_create_failed",
            error_message=msg,
            would_open_pr=True,
            dry_run=False,
            ledger_error=ledger_error,
        )
    if status not in {200, 201}:
        msg = response.get("message") or json.dumps(response, default=str)
        ledger_error = _mark_attempt(
            universe_path,
            attempt_id,
            ship_status="failed",
            error_class="pr_create_failed",
            error_message=f"GitHub PR create failed with HTTP {status}: {msg}",
        )
        return _error_result(
            ship_attempt_id=attempt_id,
            ship_status="failed",
            error_class="pr_create_failed",
            error_message=f"GitHub PR create failed with HTTP {status}: {msg}",
            would_open_pr=True,
            dry_run=False,
            ledger_error=ledger_error,
        )

    pr_url = str(response.get("html_url") or "")
    commit_sha = str((response.get("head") or {}).get("sha") or "")
    ledger_error = _mark_attempt(
        universe_path,
        attempt_id,
        ship_status="opened",
        pr_url=pr_url,
        commit_sha=commit_sha,
        ci_status="pending",
        rollback_handle=f"pr:{pr_url}" if pr_url else "",
    )
    out: dict[str, Any] = {
        "ship_attempt_id": attempt_id,
        "ship_status": "opened",
        "would_open_pr": True,
        "validation_result": "passed",
        "pr_url": pr_url,
        "pr_number": response.get("number"),
        "commit_sha": commit_sha,
        "ci_status": "pending",
        "head_branch": head,
        "base_branch": payload["base"],
        "repo": repo_slug,
        "dry_run": False,
        "error_class": "",
        "error_message": "",
    }
    if ledger_error:
        out["ledger_error"] = ledger_error
    return out
