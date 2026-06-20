"""GitHub merge effector for owner-controlled PR merge authorization.

This is the first PR-175 adapter: GitHub branch protection is the
authorization surface, and the effector binds the merge request to the exact
current PR head SHA. Wiki position records may describe review context, but
they are not accepted as merge authorization.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from typing import Any

from workflow.effectors.github_pr import (
    _DRY_RUN_ENV,
    _GH_PR_TIMEOUT_S,
    _GITHUB_API,
    _env_truthy,
    _read_capability,
    _resolve_universe_dir,
)

EXTERNAL_WRITE_SINK_GITHUB_MERGE = "github_merge"
AUTHORIZATION_MODE_GITHUB_BRANCH_PROTECTION = "github_branch_protection"

_REPO_RE = re.compile(r"[\w.-]+/[\w.-]+")
_SHA_RE = re.compile(r"[0-9a-fA-F]{40}")
_MERGE_METHODS = frozenset({"merge", "squash", "rebase"})


def _parse_packet(value: Any) -> dict[str, Any] | None:
    if isinstance(value, dict):
        packet = value
    elif isinstance(value, str):
        stripped = value.strip()
        if not stripped or not stripped.startswith("{"):
            return None
        try:
            packet = json.loads(stripped)
        except (TypeError, ValueError):
            return None
        if not isinstance(packet, dict):
            return None
    else:
        return None
    if packet.get("sink") != EXTERNAL_WRITE_SINK_GITHUB_MERGE:
        return None
    return packet


def _error(kind: str, message: str, **extra: Any) -> dict[str, Any]:
    result: dict[str, Any] = {"error": message, "error_kind": kind, **extra}
    return result


def _github_api(
    *,
    method: str,
    path: str,
    capability_token: str,
    body: dict[str, Any] | None = None,
) -> tuple[Any, dict[str, Any] | None]:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(
        f"{_GITHUB_API}{path}",
        data=data,
        method=method,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {capability_token}",
            "Content-Type": "application/json",
            "User-Agent": "workflow-github-merge-effector/1.0",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=_GH_PR_TIMEOUT_S) as resp:
            raw = resp.read().decode("utf-8")
            return (json.loads(raw) if raw.strip() else {}), None
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        return None, {"http_status": exc.code, "detail": detail}
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return None, {"http_status": None, "detail": str(exc)}
    except (TypeError, ValueError) as exc:
        return None, {"http_status": None, "detail": f"parse error: {exc}"}


def _merge_error_kind(error: dict[str, Any]) -> str:
    status = error.get("http_status")
    if status == 404:
        return "github_pr_not_found"
    if status in (401, 403):
        return "github_merge_denied"
    if status in (405, 409, 422):
        return "github_merge_blocked"
    return "github_api_error"


def _payload_authorization_mode(packet: dict[str, Any], payload: dict[str, Any]) -> str:
    raw = payload.get("authorization_mode") or packet.get("authorization_mode")
    if isinstance(raw, str):
        return raw.strip()
    authorization = payload.get("authorization")
    if authorization is None:
        authorization = packet.get("authorization")
    if isinstance(authorization, dict):
        mode = authorization.get("mode")
        if isinstance(mode, str):
            return mode.strip()
    return ""


def _payload_pr_number(payload: dict[str, Any]) -> int | None:
    raw = payload.get("pr_number")
    if isinstance(raw, int) and raw > 0:
        return raw
    if isinstance(raw, str) and raw.strip().isdigit():
        value = int(raw.strip())
        return value if value > 0 else None
    return None


def _payload_expected_head_sha(payload: dict[str, Any]) -> str:
    raw = payload.get("expected_head_sha") or payload.get("head_sha") or ""
    if not isinstance(raw, str):
        return ""
    value = raw.strip()
    return value if _SHA_RE.fullmatch(value) else ""


def run_github_merge_effector(
    *,
    node_id: str,
    output_keys: list[str],
    run_state: dict[str, Any],
    base_path: str | None = None,
    run_id: str = "",
    dry_run: bool = True,
) -> dict[str, Any]:
    """Merge a GitHub PR only through head-SHA-bound server authorization.

    The initial authorization adapter is GitHub branch protection. The packet
    must explicitly opt into that mode, the effector verifies the current head
    SHA before attempting the merge, and GitHub enforces founder review/status
    checks on the merge endpoint. Missing or stale authorization fails closed.
    """
    del run_id, dry_run
    universe_dir = _resolve_universe_dir(base_path)

    matched_key: str | None = None
    packet: dict[str, Any] | None = None
    for key in output_keys or []:
        if not isinstance(key, str) or key not in run_state:
            continue
        candidate = _parse_packet(run_state.get(key))
        if candidate is None:
            continue
        matched_key = key
        packet = candidate
        break
    if packet is None:
        return _error(
            "no_matching_packet",
            (
                f"node '{node_id}' declared effects=[github_merge] but no output_key "
                "held a parseable external_write_packet with sink='github_merge'"
            ),
        )

    if _env_truthy(_DRY_RUN_ENV):
        return {
            "dry_run": True,
            "phase": "phase_2",
            "reason": "operator_kill_switch_active",
            "kill_switch_env": _DRY_RUN_ENV,
            "intent": packet,
            "matched_output_key": matched_key,
        }

    destination_raw = packet.get("destination", "")
    destination = destination_raw.strip().strip("/") if isinstance(destination_raw, str) else ""
    if not destination or not _REPO_RE.fullmatch(destination):
        return _error(
            "invalid_destination",
            f"packet.destination must be an owner/repo GitHub repository, got {destination_raw!r}",
            matched_output_key=matched_key,
        )

    payload = packet.get("payload")
    if not isinstance(payload, dict):
        return _error(
            "invalid_payload",
            "packet.payload must be a JSON object",
            destination=destination,
            matched_output_key=matched_key,
        )

    authorization_mode = _payload_authorization_mode(packet, payload)
    if authorization_mode != AUTHORIZATION_MODE_GITHUB_BRANCH_PROTECTION:
        return _error(
            "missing_merge_authorization",
            (
                "github_merge requires authorization.mode="
                f"{AUTHORIZATION_MODE_GITHUB_BRANCH_PROTECTION!r}; wiki position records "
                "are audit context only and cannot authorize a merge"
            ),
            destination=destination,
            authorization_mode=authorization_mode,
            matched_output_key=matched_key,
        )

    pr_number = _payload_pr_number(payload)
    if pr_number is None:
        return _error(
            "invalid_pr_number",
            "packet.payload.pr_number must be a positive integer",
            destination=destination,
            matched_output_key=matched_key,
        )

    expected_head_sha = _payload_expected_head_sha(payload)
    if not expected_head_sha:
        return _error(
            "missing_expected_head_sha",
            "packet.payload.expected_head_sha must be a 40-character commit SHA",
            destination=destination,
            pr_number=pr_number,
            matched_output_key=matched_key,
        )

    merge_method = payload.get("merge_method") or "squash"
    if not isinstance(merge_method, str) or merge_method not in _MERGE_METHODS:
        return _error(
            "invalid_merge_method",
            "packet.payload.merge_method must be one of merge, squash, or rebase",
            destination=destination,
            pr_number=pr_number,
            matched_output_key=matched_key,
        )

    capability = _read_capability(destination, universe_dir)
    if not capability:
        return {
            "dry_run": True,
            "phase": "phase_2",
            "reason": "missing_capability",
            "destination": destination,
            "matched_output_key": matched_key,
            "hint": (
                "Add a vcs/github/write credential to this universe's "
                f'per-universe credential vault under destination "{destination}".'
            ),
            "intent": packet,
        }

    pr_obj, err = _github_api(
        method="GET",
        path=f"/repos/{destination}/pulls/{pr_number}",
        capability_token=capability,
    )
    if err is not None:
        return _error(
            _merge_error_kind(err),
            f"GitHub PR lookup failed: {err.get('detail')}",
            destination=destination,
            pr_number=pr_number,
            http_status=err.get("http_status"),
            matched_output_key=matched_key,
        )
    if not isinstance(pr_obj, dict):
        return _error(
            "github_api_error",
            "GitHub PR lookup returned a non-object response",
            destination=destination,
            pr_number=pr_number,
            matched_output_key=matched_key,
        )

    if pr_obj.get("state") != "open":
        return _error(
            "pr_not_open",
            f"PR #{pr_number} is not open",
            destination=destination,
            pr_number=pr_number,
            matched_output_key=matched_key,
        )
    if bool(pr_obj.get("draft")):
        return _error(
            "pr_is_draft",
            f"PR #{pr_number} is still draft",
            destination=destination,
            pr_number=pr_number,
            matched_output_key=matched_key,
        )

    actual_head_sha = ((pr_obj.get("head") or {}).get("sha") or "").strip()
    if actual_head_sha != expected_head_sha:
        return _error(
            "head_sha_mismatch",
            (
                f"PR #{pr_number} head SHA is {actual_head_sha or '(missing)'}, "
                f"not expected {expected_head_sha}; refusing stale authorization"
            ),
            destination=destination,
            pr_number=pr_number,
            expected_head_sha=expected_head_sha,
            actual_head_sha=actual_head_sha,
            matched_output_key=matched_key,
        )

    merge_body: dict[str, Any] = {
        "sha": expected_head_sha,
        "merge_method": merge_method,
    }
    for source_key, api_key in (
        ("commit_title", "commit_title"),
        ("commit_message", "commit_message"),
    ):
        value = payload.get(source_key)
        if isinstance(value, str) and value.strip():
            merge_body[api_key] = value

    merge_obj, err = _github_api(
        method="PUT",
        path=f"/repos/{destination}/pulls/{pr_number}/merge",
        capability_token=capability,
        body=merge_body,
    )
    if err is not None:
        return _error(
            _merge_error_kind(err),
            f"GitHub merge refused: {err.get('detail')}",
            destination=destination,
            pr_number=pr_number,
            expected_head_sha=expected_head_sha,
            http_status=err.get("http_status"),
            matched_output_key=matched_key,
        )
    if not isinstance(merge_obj, dict) or merge_obj.get("merged") is not True:
        return _error(
            "github_merge_blocked",
            f"GitHub merge response did not confirm merged=true: {merge_obj!r}",
            destination=destination,
            pr_number=pr_number,
            expected_head_sha=expected_head_sha,
            matched_output_key=matched_key,
        )

    merge_commit_sha = merge_obj.get("sha") if isinstance(merge_obj.get("sha"), str) else ""
    return {
        "phase": "phase_2",
        "destination": destination,
        "matched_output_key": matched_key,
        "authorization_mode": AUTHORIZATION_MODE_GITHUB_BRANCH_PROTECTION,
        "pr_number": pr_number,
        "head_sha": expected_head_sha,
        "merge_method": merge_method,
        "merged": True,
        "merge_commit_sha": merge_commit_sha,
        "message": merge_obj.get("message") if isinstance(merge_obj.get("message"), str) else "",
    }
