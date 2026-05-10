"""Community loop watch - cloud-visible health for the change loop.

This is not the MCP uptime canary. It answers the higher-level question:
is the community-driven change loop actually moving requests from intake to
writer/release/observation, or is it blocked behind a successful-looking
workflow?

The script is read-only. It queries public GitHub state (optionally with
GITHUB_TOKEN or the local gh CLI for higher rate limits) and exits non-zero
only when the loop is red. Yellow states are surfaced in output but do not
fail the workflow.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

DEFAULT_REPO = "Jonnyton/Workflow"
DEFAULT_API = "https://api.github.com"
DEFAULT_TIMEOUT = 20.0

WORKFLOWS = {
    "intake": "wiki-bug-sync.yml",
    "writer": "auto-fix-bug.yml",
    "observation": "uptime-canary.yml",
    "tier3": "tier3-oss-clone-nightly.yml",
    "deploy_prod": "deploy-prod.yml",
    "deploy_site": "deploy-site.yml",
}

REQUEST_LABELS = ("daemon-request", "auto-change", "auto-bug")
LEGACY_PRIORITY_LABEL_MAP = {
    "loop-discipline": "priority:loop-discipline",
    "primitive-layer": "priority:primitive-layer",
    "primitive-surface": "priority:primitive-surface",
}
BLOCKED_LABEL = "needs-human"
AWAIT_PRIMITIVE_LAYER_LABEL = "await-primitive-layer"
ATTEMPTED_LABEL = "auto-fix-attempted"
STALE_GATE_LABEL = "auto-fix-stale-gate"
COMPLETE_LABEL = "complete"
P0_OUTAGE_LABEL = "p0-outage"
TIER3_BROKEN_LABEL = "tier3-broken"
AUTH_MISSING_LABEL = "auto-fix-auth-missing"
CLAUDE_SUBSCRIPTION_MISSING_LABEL = "auto-fix-claude-subscription-missing"
CODEX_SUBSCRIPTION_MISSING_LABEL = "auto-fix-codex-subscription-missing"
PROVIDER_EXHAUSTED_LABEL = "auto-fix-provider-exhausted"
READY_FOR_CHECKER_LABEL = "ready_for_checker"
CHECKER_CODEX_LABEL = "checker:codex"
CHECKER_CLAUDE_LABEL = "checker:claude"
AUTO_CHECKER_DISPATCHED_LABEL = "auto-checker-dispatched"
AUTO_CHECKER_FAILED_LABEL = "auto-checker-failed"
AUTO_CHECK_PR_WORKFLOW = "auto-check-pr.yml"
REVIEWED_LABEL = "auto-fix-reviewed"
ALREADY_FIXED_LABEL = "auto-fix-already-fixed"
BLOCKED_REVIEWED_LABEL = "auto-fix-blocked"
PR_BLOCKED_LABEL = "auto-fix-pr-blocked"
BRANCH_PUSH_BLOCKED_LABEL = "auto-fix-branch-push-blocked"
TERMINAL_REVIEW_LABELS = frozenset(
    {
        REVIEWED_LABEL,
        ALREADY_FIXED_LABEL,
        BLOCKED_REVIEWED_LABEL,
        PR_BLOCKED_LABEL,
        BRANCH_PUSH_BLOCKED_LABEL,
    }
)

STATUS_RANK = {"green": 0, "yellow": 1, "red": 2}
CLOSING_ISSUE_RE = re.compile(
    r"\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\s+#(?P<number>\d+)\b",
    re.IGNORECASE,
)
WRITER_ELIGIBLE_QUEUE_DETAIL_KEYS = (
    "needs_human",
    "old_pending",
    "stale_gate",
    "attempted_with_open_pr",
    "pending",
)


class WatchError(Exception):
    """Raised when the watch cannot read its evidence source."""

    def __init__(self, msg: str, *, code: int = 3) -> None:
        super().__init__(msg)
        self.msg = msg
        self.code = code


def _utc_now() -> dt.datetime:
    return dt.datetime.now(tz=dt.timezone.utc)


def _gh_cli_token(timeout: float = 5.0) -> str | None:
    try:
        result = subprocess.run(
            ["gh", "auth", "token"],
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (FileNotFoundError, OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    token = result.stdout.strip()
    return token or None


def _github_token(args: argparse.Namespace) -> str | None:
    return args.token or os.environ.get("GITHUB_TOKEN") or _gh_cli_token()


def _parse_time(value: str | None) -> dt.datetime | None:
    if not value:
        return None
    text = value.replace("Z", "+00:00") if value.endswith("Z") else value
    try:
        parsed = dt.datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def _age_min(value: str | None, now: dt.datetime) -> float | None:
    parsed = _parse_time(value)
    if parsed is None:
        return None
    return max(0.0, (now - parsed).total_seconds() / 60.0)


def _gh_get(
    path: str,
    *,
    api: str,
    token: str | None,
    timeout: float,
    params: dict[str, str | int] | None = None,
) -> Any:
    query = f"?{urllib.parse.urlencode(params)}" if params else ""
    url = f"{api.rstrip('/')}{path}{query}"
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "workflow-community-loop-watch/1.0",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:400]
        raise WatchError(f"GitHub HTTP {exc.code} for {path}: {body}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise WatchError(f"GitHub request failed for {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise WatchError(f"GitHub response was not JSON for {path}: {exc}") from exc


def _gh_get_paginated(
    path: str,
    *,
    api: str,
    token: str | None,
    timeout: float,
    params: dict[str, str | int] | None = None,
    max_pages: int = 10,
) -> list[dict[str, Any]]:
    base_params: dict[str, str | int] = dict(params or {})
    per_page = int(base_params.get("per_page", 100))
    items: list[dict[str, Any]] = []
    for page in range(1, max_pages + 1):
        data = _gh_get(
            path,
            api=api,
            token=token,
            timeout=timeout,
            params={**base_params, "page": page},
        )
        if not isinstance(data, list):
            raise WatchError(f"GitHub paginated response for {path} was not a list")
        items.extend(data)
        if len(data) < per_page:
            break
    return items


def _labels(issue: dict[str, Any]) -> set[str]:
    result = set()
    for label in issue.get("labels", []):
        if isinstance(label, str):
            result.add(label)
        elif isinstance(label, dict) and label.get("name"):
            result.add(str(label["name"]))
    return result


def _is_pr(issue: dict[str, Any]) -> bool:
    return "pull_request" in issue


def _closing_issue_numbers(text: str | None) -> set[int]:
    if not text:
        return set()
    return {int(match.group("number")) for match in CLOSING_ISSUE_RE.finditer(text)}


def _stage(
    name: str,
    status: str,
    summary: str,
    *,
    evidence: str | None = None,
    url: str | None = None,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "name": name,
        "status": status,
        "summary": summary,
        "evidence": evidence,
        "url": url,
        "details": details or {},
    }


def _recent_workflow_runs(
    repo: str,
    workflow_id: str,
    *,
    api: str,
    token: str | None,
    timeout: float,
    per_page: int = 20,
    event: str | None = None,
) -> list[dict[str, Any]]:
    params: dict[str, Any] = {"per_page": per_page}
    if event is not None:
        params["event"] = event
    data = _gh_get(
        f"/repos/{repo}/actions/workflows/{workflow_id}/runs",
        api=api,
        token=token,
        timeout=timeout,
        params=params,
    )
    runs = data.get("workflow_runs", []) if isinstance(data, dict) else []
    return runs if isinstance(runs, list) else []


def _is_neutral_skipped_run(run: dict[str, Any]) -> bool:
    return run.get("status") == "completed" and run.get("conclusion") == "skipped"


def _latest_workflow_run(
    repo: str,
    workflow_id: str,
    *,
    api: str,
    token: str | None,
    timeout: float,
) -> dict[str, Any] | None:
    runs = _recent_workflow_runs(repo, workflow_id, api=api, token=token, timeout=timeout)
    for run in runs:
        if not _is_neutral_skipped_run(run):
            return run
    return runs[0] if runs else None


def workflow_stage(
    label: str,
    repo: str,
    workflow_id: str,
    *,
    api: str,
    token: str | None,
    timeout: float,
    now: dt.datetime,
    max_age_min: int | None,
    stale_status: str = "red",
    required_success_event: str | None = None,
    fallback_success_events: tuple[str, ...] = (),
    per_page: int = 20,
) -> dict[str, Any]:
    runs = _recent_workflow_runs(
        repo,
        workflow_id,
        api=api,
        token=token,
        timeout=timeout,
        per_page=per_page,
    )
    skipped_runs = [candidate for candidate in runs if _is_neutral_skipped_run(candidate)]
    candidates = [candidate for candidate in runs if not _is_neutral_skipped_run(candidate)]
    fallback_candidates: list[dict[str, Any]] = []
    if required_success_event is not None:
        event_runs = _recent_workflow_runs(
            repo,
            workflow_id,
            api=api,
            token=token,
            timeout=timeout,
            per_page=per_page,
            event=required_success_event,
        )
        skipped_event_runs = [
            candidate
            for candidate in event_runs
            if _is_neutral_skipped_run(candidate)
            and candidate.get("event") == required_success_event
        ]
        candidates = [
            candidate
            for candidate in event_runs
            if not _is_neutral_skipped_run(candidate)
            and candidate.get("event") == required_success_event
        ]
        skipped_runs = skipped_event_runs
        fallback_candidates = [
            candidate
            for candidate in runs
            if not _is_neutral_skipped_run(candidate)
            and candidate.get("event") in fallback_success_events
            and candidate.get("status") == "completed"
            and candidate.get("conclusion") == "success"
        ]
        fallback_in_progress_candidates = [
            candidate
            for candidate in runs
            if not _is_neutral_skipped_run(candidate)
            and candidate.get("event") in fallback_success_events
            and candidate.get("status") != "completed"
        ]
    else:
        fallback_in_progress_candidates = []
    run = next(iter(candidates), None)
    if run is None and runs:
        if required_success_event is not None:
            latest = runs[0]
            latest_event = latest.get("event") or "unknown event"
            details = {
                "workflow_id": workflow_id,
                "required_success_event": required_success_event,
                "latest_run_id": latest.get("id"),
                "latest_event": latest_event,
                "latest_status": latest.get("status"),
                "latest_conclusion": latest.get("conclusion"),
                "latest_created_at": latest.get("created_at"),
                "checked_run_count": len(runs),
                "checked_required_event_run_count": len(event_runs),
                "ignored_skipped_run_ids": [skipped.get("id") for skipped in skipped_runs],
            }
            return _stage(
                label,
                "red",
                f"{workflow_id} has no visible {required_success_event} backfill runs",
                evidence=(
                    f"latest visible run was {latest_event} "
                    f"{latest.get('status')}/{latest.get('conclusion')}"
                ),
                url=latest.get("html_url"),
                details=details,
            )
        run = runs[0]
    if not run:
        return _stage(label, "red", f"{workflow_id} has no visible runs")

    conclusion = run.get("conclusion")
    status = run.get("status")
    age = _age_min(run.get("created_at"), now)
    age_text = "unknown age" if age is None else f"{age:.1f} min ago"
    evidence = f"{workflow_id} latest {status}/{conclusion} ({age_text})"

    details = {
        "workflow_id": workflow_id,
        "run_id": run.get("id"),
        "event": run.get("event"),
        "status": status,
        "conclusion": conclusion,
        "created_at": run.get("created_at"),
        "updated_at": run.get("updated_at"),
        "ignored_skipped_run_ids": [
            skipped.get("id") for skipped in skipped_runs if skipped is not run
        ],
    }
    if required_success_event is not None:
        details["required_success_event"] = required_success_event

    if status != "completed":
        return _stage(
            label,
            "yellow",
            f"{workflow_id} is still {status}",
            evidence=evidence,
            url=run.get("html_url"),
            details=details,
        )
    if conclusion != "success":
        fallback_run = next(iter(fallback_candidates), None)
        fallback_age = _age_min(fallback_run.get("created_at"), now) if fallback_run else None
        if (
            fallback_run is not None
            and max_age_min is not None
            and fallback_age is not None
            and fallback_age <= max_age_min
        ):
            fallback_event = fallback_run.get("event") or "unknown event"
            return _stage(
                label,
                "yellow",
                (
                    f"{workflow_id} {required_success_event} run concluded {conclusion}, "
                    f"but recent {fallback_event} success proves the workflow is dispatchable"
                ),
                evidence=(
                    f"required {required_success_event} run was {status}/{conclusion}; "
                    f"fallback {fallback_event} success was {fallback_age:.1f} min ago"
                ),
                url=fallback_run.get("html_url") or run.get("html_url"),
                details={
                    **details,
                    "fallback_run_id": fallback_run.get("id"),
                    "fallback_event": fallback_event,
                    "fallback_created_at": fallback_run.get("created_at"),
                    "fallback_age_min": round(fallback_age, 1),
                },
            )
        return _stage(
            label,
            "red",
            f"{workflow_id} latest run concluded {conclusion}",
            evidence=evidence,
            url=run.get("html_url"),
            details=details,
        )
    if max_age_min is not None and (age is None or age > max_age_min):
        fallback_run = next(iter(fallback_candidates), None)
        fallback_age = _age_min(fallback_run.get("created_at"), now) if fallback_run else None
        if fallback_run is not None and fallback_age is not None and fallback_age <= max_age_min:
            fallback_event = fallback_run.get("event") or "unknown event"
            return _stage(
                label,
                "yellow",
                (
                    f"{workflow_id} {required_success_event} success is stale, "
                    f"but recent {fallback_event} success proves the workflow is productive"
                ),
                evidence=(
                    f"required {required_success_event} success was {age_text}; "
                    f"fallback {fallback_event} success was {fallback_age:.1f} min ago"
                ),
                url=fallback_run.get("html_url") or run.get("html_url"),
                details={
                    **details,
                    "max_age_min": max_age_min,
                    "fallback_run_id": fallback_run.get("id"),
                    "fallback_event": fallback_event,
                    "fallback_created_at": fallback_run.get("created_at"),
                    "fallback_age_min": round(fallback_age, 1),
                },
            )
        fallback_run = next(iter(fallback_in_progress_candidates), None)
        fallback_age = _age_min(fallback_run.get("created_at"), now) if fallback_run else None
        if fallback_run is not None and fallback_age is not None and fallback_age <= max_age_min:
            fallback_event = fallback_run.get("event") or "unknown event"
            fallback_status = fallback_run.get("status") or "unknown"
            return _stage(
                label,
                "yellow",
                (
                    f"{workflow_id} {required_success_event} success is stale, "
                    f"but recent {fallback_event} run is {fallback_status}"
                ),
                evidence=(
                    f"required {required_success_event} success was {age_text}; "
                    f"fallback {fallback_event} run started {fallback_age:.1f} min ago"
                ),
                url=fallback_run.get("html_url") or run.get("html_url"),
                details={
                    **details,
                    "max_age_min": max_age_min,
                    "fallback_run_id": fallback_run.get("id"),
                    "fallback_event": fallback_event,
                    "fallback_status": fallback_status,
                    "fallback_created_at": fallback_run.get("created_at"),
                    "fallback_age_min": round(fallback_age, 1),
                },
            )
        return _stage(
            label,
            stale_status,
            f"{workflow_id} has not run successfully within {max_age_min} min",
            evidence=evidence,
            url=run.get("html_url"),
            details={**details, "max_age_min": max_age_min},
        )
    return _stage(
        label,
        "green",
        f"{workflow_id} latest run is successful",
        evidence=evidence,
        url=run.get("html_url"),
        details=details,
    )


def list_open_issues_by_label(
    repo: str,
    label: str,
    *,
    api: str,
    token: str | None,
    timeout: float,
    include_prs: bool = False,
) -> list[dict[str, Any]]:
    data = _gh_get_paginated(
        f"/repos/{repo}/issues",
        api=api,
        token=token,
        timeout=timeout,
        params={"state": "open", "labels": label, "per_page": 100},
    )
    if not isinstance(data, list):
        raise WatchError(f"GitHub issues response for {label!r} was not a list")
    return [issue for issue in data if include_prs or not _is_pr(issue)]


def _pull_comments(
    repo: str,
    number: int,
    *,
    api: str,
    token: str | None,
    timeout: float,
) -> list[dict[str, Any]]:
    return _gh_get_paginated(
        f"/repos/{repo}/issues/{number}/comments",
        api=api,
        token=token,
        timeout=timeout,
        params={"per_page": 100},
    )


def list_ready_for_checker_prs(
    repo: str,
    *,
    api: str,
    token: str | None,
    timeout: float,
) -> list[dict[str, Any]]:
    issues = list_open_issues_by_label(
        repo,
        READY_FOR_CHECKER_LABEL,
        api=api,
        token=token,
        timeout=timeout,
        include_prs=True,
    )
    prs: list[dict[str, Any]] = []
    for issue in issues:
        if not _is_pr(issue) or not isinstance(issue.get("number"), int):
            continue
        number = int(issue["number"])
        labels = _labels(issue)
        should_hydrate_comments = CHECKER_CODEX_LABEL in labels or "priority:urgent" in labels
        prs.append(
            {
                "number": number,
                "title": issue.get("title") or "",
                "state": str(issue.get("state") or "open").upper(),
                # ready_for_checker is added only after stale-base pre-checks.
                # Keep this watch stage cheap and checker-focused; hydrated
                # merge-state proof remains in scripts/merge_readiness.py.
                "mergeStateStatus": "CLEAN",
                "labels": issue.get("labels", []),
                "comments": (
                    _pull_comments(repo, number, api=api, token=token, timeout=timeout)
                    if should_hydrate_comments
                    else []
                ),
                "reviews": [],
                "html_url": issue.get("html_url"),
            }
        )
    return prs


def checker_queue_stage(
    repo: str,
    *,
    api: str,
    token: str | None,
    timeout: float,
) -> dict[str, Any]:
    from scripts.merge_readiness import PullRequestFacts, classify_pr

    prs = list_ready_for_checker_prs(repo, api=api, token=token, timeout=timeout)
    results = [classify_pr(PullRequestFacts.from_mapping(pr)) for pr in prs]
    by_state: dict[str, list[int]] = {}
    for result in results:
        by_state.setdefault(result.state, []).append(result.number)
    independent_blockers = [
        result for result in results if result.state.startswith("needs_independent_")
    ]
    prs_by_number = {int(pr["number"]): pr for pr in prs if isinstance(pr.get("number"), int)}
    self_heal_dispatches: list[dict[str, Any]] = []
    already_dispatched: list[int] = []
    failed_dispatches: list[int] = []
    for blocker in independent_blockers:
        pr = prs_by_number.get(blocker.number, {})
        labels = _labels(pr)
        if AUTO_CHECKER_FAILED_LABEL in labels:
            failed_dispatches.append(blocker.number)
            continue
        if AUTO_CHECKER_DISPATCHED_LABEL in labels:
            already_dispatched.append(blocker.number)
            continue
        checker_family = _checker_family_from_state(blocker.state)
        if not checker_family:
            continue
        reason = blocker.merge_executor_state
        self_heal_dispatches.append(
            {
                "workflow_id": AUTO_CHECK_PR_WORKFLOW,
                "pr_number": blocker.number,
                "checker_family": checker_family,
                "reason": reason,
                "inputs": {
                    "pr_number": str(blocker.number),
                    "checker_family": checker_family,
                    "reason": reason,
                },
            }
        )
    checker_waiting = [
        result
        for result in results
        if result.state in {"needs_codex_checker", "needs_claude_checker"}
    ]
    details = {
        "ready_for_checker_prs": [pr.get("number") for pr in prs],
        "by_state": by_state,
        "items": [result.as_dict() for result in results],
        "self_heal_dispatches": self_heal_dispatches,
        "already_dispatched_independent_checkers": already_dispatched,
        "failed_independent_checker_dispatches": failed_dispatches,
    }
    if self_heal_dispatches:
        first = independent_blockers[0]
        first_pr = next((pr for pr in prs if pr.get("number") == first.number), {})
        return _stage(
            "Checker queue",
            "yellow",
            (
                f"{len(independent_blockers)} ready PR(s) need an independent "
                "checker because the current executor is ineligible"
            ),
            evidence=f"PR #{first.number}: {first.next_action}",
            url=first_pr.get("html_url"),
            details=details,
        )
    if failed_dispatches:
        first = independent_blockers[0]
        first_pr = next((pr for pr in prs if pr.get("number") == first.number), {})
        return _stage(
            "Checker queue",
            "yellow",
            f"{len(failed_dispatches)} ready PR(s) have failed independent checker dispatch",
            evidence=f"PR #{failed_dispatches[0]}: repair checker worker/auth and redispatch",
            url=first_pr.get("html_url"),
            details=details,
        )
    if independent_blockers:
        first = independent_blockers[0]
        first_pr = next((pr for pr in prs if pr.get("number") == first.number), {})
        return _stage(
            "Checker queue",
            "yellow",
            (
                f"{len(independent_blockers)} ready PR(s) already dispatched "
                "to independent checker workers"
            ),
            evidence=f"PR #{first.number}: waiting on dispatched independent checker",
            url=first_pr.get("html_url"),
            details=details,
        )
    if checker_waiting:
        first = checker_waiting[0]
        first_pr = next((pr for pr in prs if pr.get("number") == first.number), {})
        return _stage(
            "Checker queue",
            "yellow",
            f"{len(checker_waiting)} ready PR(s) are waiting on checker keys",
            evidence=f"PR #{first.number}: {first.next_action}",
            url=first_pr.get("html_url"),
            details=details,
        )
    return _stage(
        "Checker queue",
        "green",
        "no ready_for_checker PRs are waiting on independent checker routing",
        details=details,
    )


def _checker_family_from_state(state: str) -> str | None:
    prefix = "needs_independent_"
    suffix = "_checker"
    if not state.startswith(prefix) or not state.endswith(suffix):
        return None
    return state[len(prefix) : -len(suffix)]


def list_open_prs_by_closing_issue(
    repo: str,
    issue_numbers: set[int],
    *,
    api: str,
    token: str | None,
    timeout: float,
) -> dict[int, list[dict[str, Any]]]:
    if not issue_numbers:
        return {}
    data = _gh_get_paginated(
        f"/repos/{repo}/pulls",
        api=api,
        token=token,
        timeout=timeout,
        params={"state": "open", "per_page": 100},
    )
    result: dict[int, list[dict[str, Any]]] = {number: [] for number in issue_numbers}
    for item in data:
        for issue_number in _closing_issue_numbers(str(item.get("body") or "")):
            if issue_number in result:
                result[issue_number].append(item)
    return {number: prs for number, prs in result.items() if prs}


def list_loop_issues(
    repo: str,
    *,
    api: str,
    token: str | None,
    timeout: float,
) -> list[dict[str, Any]]:
    by_number: dict[int, dict[str, Any]] = {}
    for label in REQUEST_LABELS:
        for issue in list_open_issues_by_label(repo, label, api=api, token=token, timeout=timeout):
            number = issue.get("number")
            if isinstance(number, int):
                by_number[number] = issue
    return [by_number[number] for number in sorted(by_number, reverse=True)]


def queue_stage(
    repo: str,
    *,
    api: str,
    token: str | None,
    timeout: float,
    now: dt.datetime,
    max_pending_age_min: int,
) -> dict[str, Any]:
    issues = list_loop_issues(repo, api=api, token=token, timeout=timeout)
    attempted_issue_numbers = {
        issue["number"]
        for issue in issues
        if isinstance(issue.get("number"), int)
        and ATTEMPTED_LABEL in _labels(issue)
        and COMPLETE_LABEL not in _labels(issue)
        and _labels(issue).isdisjoint(TERMINAL_REVIEW_LABELS)
        and AWAIT_PRIMITIVE_LAYER_LABEL not in _labels(issue)
    }
    linked_open_prs_by_issue = list_open_prs_by_closing_issue(
        repo,
        attempted_issue_numbers,
        api=api,
        token=token,
        timeout=timeout,
    )
    needs_human: list[dict[str, Any]] = []
    missing_subscription: list[dict[str, Any]] = []
    missing_codex_subscription: list[dict[str, Any]] = []
    auth_missing: list[dict[str, Any]] = []
    provider_exhausted: list[dict[str, Any]] = []
    pr_blocked: list[dict[str, Any]] = []
    branch_push_blocked: list[dict[str, Any]] = []
    reviewed_terminal: list[dict[str, Any]] = []
    stale_gate: list[dict[str, Any]] = []
    attempted_with_open_pr: list[dict[str, Any]] = []
    attempted: list[dict[str, Any]] = []
    pending: list[dict[str, Any]] = []
    old_pending: list[dict[str, Any]] = []
    await_primitive_layer: list[dict[str, Any]] = []
    legacy_priority_migrations: list[dict[str, Any]] = []

    for issue in issues:
        labels = _labels(issue)
        legacy_priority_labels = [
            legacy
            for legacy, mapped in LEGACY_PRIORITY_LABEL_MAP.items()
            if legacy in labels and mapped not in labels
        ]
        if BLOCKED_LABEL in labels and (
            labels.isdisjoint(TERMINAL_REVIEW_LABELS)
            or PR_BLOCKED_LABEL in labels
            or BRANCH_PUSH_BLOCKED_LABEL in labels
        ):
            needs_human.append(issue)
            if CLAUDE_SUBSCRIPTION_MISSING_LABEL in labels:
                missing_subscription.append(issue)
            if CODEX_SUBSCRIPTION_MISSING_LABEL in labels:
                missing_codex_subscription.append(issue)
            if AUTH_MISSING_LABEL in labels:
                auth_missing.append(issue)
            if PR_BLOCKED_LABEL in labels:
                pr_blocked.append(issue)
            if BRANCH_PUSH_BLOCKED_LABEL in labels:
                branch_push_blocked.append(issue)
            if PROVIDER_EXHAUSTED_LABEL in labels:
                provider_exhausted.append(issue)
        elif COMPLETE_LABEL in labels or not labels.isdisjoint(TERMINAL_REVIEW_LABELS):
            reviewed_terminal.append(issue)
        elif AWAIT_PRIMITIVE_LAYER_LABEL in labels:
            await_primitive_layer.append(issue)
        elif ATTEMPTED_LABEL in labels:
            attempted.append(issue)
            linked_prs = linked_open_prs_by_issue.get(issue.get("number"), [])
            if linked_prs:
                attempted_with_open_pr.append(
                    {
                        "issue": issue,
                        "prs": linked_prs,
                    }
                )
                continue
            age = _age_min(issue.get("created_at"), now)
            if STALE_GATE_LABEL in labels or age is None or age > max_pending_age_min:
                stale_gate.append(issue)
        else:
            pending.append(issue)
            age = _age_min(issue.get("created_at"), now)
            if age is None or age > max_pending_age_min:
                if legacy_priority_labels:
                    for legacy_label in legacy_priority_labels:
                        legacy_priority_migrations.append(
                            {
                                "issue": issue.get("number"),
                                "legacy_label": legacy_label,
                                "mapped_label": LEGACY_PRIORITY_LABEL_MAP[legacy_label],
                            }
                        )
                else:
                    old_pending.append(issue)

    details = {
        "open_loop_issues": len(issues),
        "needs_human": [issue.get("number") for issue in needs_human],
        "missing_claude_subscription": [issue.get("number") for issue in missing_subscription],
        "missing_codex_subscription": [issue.get("number") for issue in missing_codex_subscription],
        "auth_missing": [issue.get("number") for issue in auth_missing],
        "branch_push_blocked": [issue.get("number") for issue in branch_push_blocked],
        "pr_blocked": [issue.get("number") for issue in pr_blocked],
        "provider_exhausted": [issue.get("number") for issue in provider_exhausted],
        "pending": [issue.get("number") for issue in pending],
        "old_pending": [issue.get("number") for issue in old_pending],
        "await_primitive_layer": [issue.get("number") for issue in await_primitive_layer],
        "legacy_priority_migrations": legacy_priority_migrations,
        "reviewed_terminal": [issue.get("number") for issue in reviewed_terminal],
        "stale_gate": [issue.get("number") for issue in stale_gate],
        "attempted": [issue.get("number") for issue in attempted],
        "attempted_with_open_pr": [
            {
                "issue": item["issue"].get("number"),
                "prs": [pr.get("number") for pr in item["prs"]],
                "ready_for_checker": [
                    pr.get("number") for pr in item["prs"] if READY_FOR_CHECKER_LABEL in _labels(pr)
                ],
            }
            for item in attempted_with_open_pr
        ],
        "request_labels": list(REQUEST_LABELS),
    }

    if needs_human:
        first = needs_human[0]
        root_cause = "automated writer is blocked"
        if branch_push_blocked and pr_blocked:
            root_cause = "automated writer hit branch-push and PR-creation permission blocks"
        elif branch_push_blocked:
            root_cause = "automated writer produced a patch but branch push was blocked"
        elif pr_blocked:
            root_cause = "automated writer pushed a branch but PR creation was blocked"
        elif missing_subscription and missing_codex_subscription:
            root_cause = (
                "Claude subscription OAuth and Codex subscription auth bundle "
                "are not visible to GitHub Actions"
            )
        elif missing_subscription:
            root_cause = "Claude subscription OAuth is not visible to GitHub Actions"
        elif missing_codex_subscription:
            root_cause = "Codex subscription auth bundle is not visible to GitHub Actions"
        elif auth_missing:
            root_cause = "approved subscription-backed writer auth is missing"
        elif provider_exhausted:
            root_cause = "approved writer provider returned quota/capacity exhaustion"
        pending_clause = (
            f" and {len(old_pending)} pending request(s) are older than {max_pending_age_min} min"
            if old_pending
            else ""
        )
        return _stage(
            "Writer queue",
            "red",
            (
                f"{len(needs_human)} open loop request(s) are marked "
                f"{BLOCKED_LABEL}{pending_clause}; {root_cause}"
            ),
            evidence=f"first blocked issue #{first.get('number')}: {first.get('title')}",
            url=first.get("html_url"),
            details=details,
        )
    if old_pending:
        first = old_pending[0]
        return _stage(
            "Writer queue",
            "red",
            (
                f"{len(old_pending)} pending loop request(s) are older than "
                f"{max_pending_age_min} min"
            ),
            evidence=f"oldest visible pending issue #{first.get('number')}: {first.get('title')}",
            url=first.get("html_url"),
            details=details,
        )
    if stale_gate:
        first = stale_gate[0]
        return _stage(
            "Writer queue",
            "red",
            (
                f"{len(stale_gate)} attempted loop request(s) have no terminal "
                f"review label after {max_pending_age_min} min"
            ),
            evidence=(
                f"stale attempted issue #{first.get('number')}: {first.get('title')} "
                f"(apply {STALE_GATE_LABEL} while triaging)"
            ),
            url=first.get("html_url"),
            details=details,
        )
    if attempted_with_open_pr:
        first = attempted_with_open_pr[0]
        first_issue = first["issue"]
        first_prs = first["prs"]
        ready_prs = [
            pr.get("number")
            for item in attempted_with_open_pr
            for pr in item["prs"]
            if READY_FOR_CHECKER_LABEL in _labels(pr)
        ]
        ready_clause = (
            f"; {len(ready_prs)} PR(s) are {READY_FOR_CHECKER_LABEL}" if ready_prs else ""
        )
        return _stage(
            "Writer queue",
            "yellow",
            (
                f"{len(attempted_with_open_pr)} attempted loop request(s) "
                f"already have linked open PRs awaiting review/precheck"
                f"{ready_clause}"
            ),
            evidence=(
                f"issue #{first_issue.get('number')} is linked to open PR(s) "
                f"{', '.join('#' + str(pr.get('number')) for pr in first_prs)}"
            ),
            url=first_prs[0].get("html_url") or first_issue.get("html_url"),
            details=details,
        )
    if legacy_priority_migrations:
        first = legacy_priority_migrations[0]
        issue_number = first.get("issue")
        mapped_label = first.get("mapped_label")
        return _stage(
            "Writer queue",
            "yellow",
            (
                f"{len(legacy_priority_migrations)} legacy unprefixed priority "
                "label(s) need migration before pending-age escalation"
            ),
            evidence=f"issue #{issue_number} should use {mapped_label}",
            url=next(
                (issue.get("html_url") for issue in pending if issue.get("number") == issue_number),
                None,
            ),
            details=details,
        )
    if pending:
        first = pending[0]
        return _stage(
            "Writer queue",
            "yellow",
            f"{len(pending)} fresh loop request(s) are waiting for the next writer pass",
            evidence=f"newest pending issue #{first.get('number')}: {first.get('title')}",
            url=first.get("html_url"),
            details=details,
        )
    if await_primitive_layer:
        first = await_primitive_layer[0]
        return _stage(
            "Writer queue",
            "yellow",
            (
                f"{len(await_primitive_layer)} loop request(s) are intentionally "
                f"waiting on {AWAIT_PRIMITIVE_LAYER_LABEL}"
            ),
            evidence=(f"first deferred issue #{first.get('number')}: {first.get('title')}"),
            url=first.get("html_url"),
            details=details,
        )
    return _stage(
        "Writer queue",
        "green",
        "no open daemon-request/auto-change/auto-bug requests are waiting on the writer",
        details=details,
    )


def _has_no_writer_eligible_queue(stage: dict[str, Any]) -> bool:
    if stage.get("name") != "Writer queue":
        return False
    details = stage.get("details")
    if not isinstance(details, dict):
        return False
    return all(not details.get(key) for key in WRITER_ELIGIBLE_QUEUE_DETAIL_KEYS)


def _writer_queue_downgrade_reason(stage: dict[str, Any]) -> str:
    details = stage.get("details")
    if not isinstance(details, dict):
        return "no writer-eligible queue"
    deferred = details.get("await_primitive_layer")
    if isinstance(deferred, list) and deferred:
        return f"no writer-eligible queue ({len(deferred)} await-primitive-layer deferrals)"
    return "no writer-eligible queue"


def _is_stale_writer_schedule_stage(stage: dict[str, Any]) -> bool:
    if stage.get("name") != "Writer workflow":
        return False
    details = stage.get("details")
    if not isinstance(details, dict):
        return False
    return (
        stage.get("status") == "red"
        and details.get("required_success_event") == "schedule"
        and "max_age_min" in details
    )


def incident_stage(
    repo: str,
    *,
    api: str,
    token: str | None,
    timeout: float,
) -> dict[str, Any]:
    issues = list_open_issues_by_label(repo, P0_OUTAGE_LABEL, api=api, token=token, timeout=timeout)
    if issues:
        issue = issues[0]
        return _stage(
            "Observation incidents",
            "red",
            f"{len(issues)} open {P0_OUTAGE_LABEL} issue(s)",
            evidence=f"#{issue.get('number')}: {issue.get('title')}",
            url=issue.get("html_url"),
            details={"open_p0_outages": [i.get("number") for i in issues]},
        )
    return _stage(
        "Observation incidents",
        "green",
        f"no open {P0_OUTAGE_LABEL} issues",
        details={"open_p0_outages": []},
    )


def tier3_clone_smoke_stage(
    repo: str,
    *,
    api: str,
    token: str | None,
    timeout: float,
) -> dict[str, Any]:
    issues = list_open_issues_by_label(
        repo, TIER3_BROKEN_LABEL, api=api, token=token, timeout=timeout
    )
    if issues:
        issue = issues[0]
        latest_run = _latest_workflow_run(
            repo,
            WORKFLOWS["tier3"],
            api=api,
            token=token,
            timeout=timeout,
        )
        latest_run_time = _parse_time(latest_run.get("created_at")) if latest_run else None
        issue_times = [
            parsed
            for parsed in (
                _parse_time(item.get("created_at") or item.get("updated_at")) for item in issues
            )
            if parsed is not None
        ]
        newest_issue_time = max(issue_times) if issue_times else None
        if (
            latest_run is not None
            and latest_run.get("status") == "completed"
            and latest_run.get("conclusion") == "success"
            and latest_run_time is not None
            and newest_issue_time is not None
            and latest_run_time > newest_issue_time
        ):
            return _stage(
                "Tier-3 clone smoke",
                "yellow",
                (
                    f"latest {WORKFLOWS['tier3']} success is newer than "
                    f"{len(issues)} open {TIER3_BROKEN_LABEL} issue(s)"
                ),
                evidence=(
                    f"latest successful tier-3 run {latest_run.get('id')} at "
                    f"{latest_run.get('created_at')}; newest open issue "
                    f"#{issue.get('number')}: {issue.get('title')}"
                ),
                url=latest_run.get("html_url") or issue.get("html_url"),
                details={
                    "open_tier3_broken": [i.get("number") for i in issues],
                    "latest_run_id": latest_run.get("id"),
                    "latest_run_conclusion": latest_run.get("conclusion"),
                    "latest_run_created_at": latest_run.get("created_at"),
                    "newest_issue_at": newest_issue_time.isoformat().replace("+00:00", "Z"),
                },
            )
        return _stage(
            "Tier-3 clone smoke",
            "red",
            (
                f"{len(issues)} open {TIER3_BROKEN_LABEL} issue(s); "
                "Forever Rule tier-3 clone/run surface is red"
            ),
            evidence=f"#{issue.get('number')}: {issue.get('title')}",
            url=issue.get("html_url"),
            details={"open_tier3_broken": [i.get("number") for i in issues]},
        )
    return _stage(
        "Tier-3 clone smoke",
        "green",
        f"no open {TIER3_BROKEN_LABEL} issues",
        details={"open_tier3_broken": []},
    )


def classify(stages: list[dict[str, Any]]) -> str:
    return max((stage["status"] for stage in stages), key=lambda s: STATUS_RANK[s])


def build_status(args: argparse.Namespace, now: dt.datetime | None = None) -> dict[str, Any]:
    current_now = now or _utc_now()
    token = _github_token(args)
    repo = args.repo
    api = args.api
    timeout = args.timeout

    stages = [
        workflow_stage(
            "Intake sync",
            repo,
            WORKFLOWS["intake"],
            api=api,
            token=token,
            timeout=timeout,
            now=current_now,
            max_age_min=args.max_sync_age_min,
        ),
        workflow_stage(
            "Writer workflow",
            repo,
            WORKFLOWS["writer"],
            api=api,
            token=token,
            timeout=timeout,
            now=current_now,
            max_age_min=args.max_writer_age_min,
            required_success_event="schedule",
            fallback_success_events=("workflow_dispatch", "issues", "workflow_run"),
            per_page=100,
        ),
        queue_stage(
            repo,
            api=api,
            token=token,
            timeout=timeout,
            now=current_now,
            max_pending_age_min=args.max_pending_age_min,
        ),
        checker_queue_stage(repo, api=api, token=token, timeout=timeout),
        workflow_stage(
            "Observation canary",
            repo,
            WORKFLOWS["observation"],
            api=api,
            token=token,
            timeout=timeout,
            now=current_now,
            max_age_min=args.max_observation_age_min,
        ),
        incident_stage(repo, api=api, token=token, timeout=timeout),
        tier3_clone_smoke_stage(repo, api=api, token=token, timeout=timeout),
        workflow_stage(
            "Production deploy",
            repo,
            WORKFLOWS["deploy_prod"],
            api=api,
            token=token,
            timeout=timeout,
            now=current_now,
            max_age_min=None,
        ),
        workflow_stage(
            "Website deploy",
            repo,
            WORKFLOWS["deploy_site"],
            api=api,
            token=token,
            timeout=timeout,
            now=current_now,
            max_age_min=None,
        ),
    ]
    writer_workflow = next(
        (stage for stage in stages if stage.get("name") == "Writer workflow"),
        None,
    )
    writer_queue = next(
        (stage for stage in stages if stage.get("name") == "Writer queue"),
        None,
    )
    if (
        writer_workflow is not None
        and writer_queue is not None
        and _is_stale_writer_schedule_stage(writer_workflow)
        and _has_no_writer_eligible_queue(writer_queue)
    ):
        downgrade_reason = _writer_queue_downgrade_reason(writer_queue)
        writer_workflow["status"] = "yellow"
        writer_workflow["summary"] = f"{writer_workflow.get('summary')}; {downgrade_reason}"
        existing_evidence = writer_workflow.get("evidence")
        writer_workflow["evidence"] = (
            f"{existing_evidence}; {downgrade_reason}" if existing_evidence else downgrade_reason
        )
        details = writer_workflow.get("details")
        if isinstance(details, dict):
            details["queue_downgrade"] = downgrade_reason
    overall = classify(stages)
    return {
        "version": 1,
        "checked_at": current_now.isoformat().replace("+00:00", "Z"),
        "repo": repo,
        "overall": overall,
        "exit_code": 2 if overall == "red" else 0,
        "stages": stages,
    }


def error_status(exc: WatchError, now: dt.datetime | None = None) -> dict[str, Any]:
    current_now = now or _utc_now()
    return {
        "version": 1,
        "checked_at": current_now.isoformat().replace("+00:00", "Z"),
        "repo": None,
        "overall": "red",
        "exit_code": exc.code,
        "stages": [
            _stage(
                "GitHub evidence read",
                "red",
                "community loop watch could not read GitHub evidence",
                evidence=exc.msg,
            )
        ],
    }


def format_human(status: dict[str, Any]) -> str:
    lines = [
        f"Community loop status: {status['overall'].upper()}",
        f"Checked: {status['checked_at']}",
        f"Repo: {status.get('repo') or '(unknown)'}",
        "",
    ]
    for stage in status["stages"]:
        lines.append(f"- {stage['status'].upper()} {stage['name']}: {stage['summary']}")
        if stage.get("evidence"):
            lines.append(f"  evidence: {stage['evidence']}")
        if stage.get("url"):
            lines.append(f"  url: {stage['url']}")
    return "\n".join(lines)


def make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Report cloud-visible health of the community change loop.",
    )
    parser.add_argument("--repo", default=DEFAULT_REPO)
    parser.add_argument("--api", default=DEFAULT_API)
    parser.add_argument(
        "--token",
        default=None,
        help="GitHub token; defaults to GITHUB_TOKEN or `gh auth token`.",
    )
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT)
    parser.add_argument(
        "--max-sync-age-min",
        type=int,
        default=90,
        help="Red if wiki-bug-sync latest success is older than this.",
    )
    parser.add_argument(
        "--max-writer-age-min",
        type=int,
        default=90,
        help="Red if auto-fix latest success is older than this.",
    )
    parser.add_argument(
        "--max-observation-age-min",
        type=int,
        default=90,
        help="Red if uptime-canary latest success is older than this.",
    )
    parser.add_argument(
        "--max-pending-age-min",
        type=int,
        default=45,
        help="Red if an unattempted loop issue is older than this.",
    )
    parser.add_argument("--json", action="store_true", help="Print JSON instead of text.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = make_parser().parse_args(argv)
    try:
        status = build_status(args)
    except WatchError as exc:
        status = error_status(exc)

    if args.json:
        print(json.dumps(status, indent=2, sort_keys=True))
    else:
        print(format_human(status))
    return int(status["exit_code"])


if __name__ == "__main__":
    sys.exit(main())
