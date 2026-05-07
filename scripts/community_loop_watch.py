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
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

DEFAULT_REPO = "Jonnyton/Workflow"
DEFAULT_API = "https://api.github.com"
DEFAULT_TIMEOUT = 20.0

WORKFLOWS = {
    "intake": "wiki-bug-sync.yml",
    "writer": "auto-fix-bug.yml",
    "observation": "uptime-canary.yml",
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
P0_OUTAGE_LABEL = "p0-outage"
AUTH_MISSING_LABEL = "auto-fix-auth-missing"
CLAUDE_SUBSCRIPTION_MISSING_LABEL = "auto-fix-claude-subscription-missing"
CODEX_SUBSCRIPTION_MISSING_LABEL = "auto-fix-codex-subscription-missing"
PROVIDER_EXHAUSTED_LABEL = "auto-fix-provider-exhausted"
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
) -> list[dict[str, Any]]:
    data = _gh_get(
        f"/repos/{repo}/actions/workflows/{workflow_id}/runs",
        api=api,
        token=token,
        timeout=timeout,
        params={"per_page": per_page},
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
    runs = _recent_workflow_runs(
        repo, workflow_id, api=api, token=token, timeout=timeout
    )
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
        candidates = [
            candidate
            for candidate in candidates
            if candidate.get("event") == required_success_event
        ]
        fallback_candidates = [
            candidate
            for candidate in runs
            if not _is_neutral_skipped_run(candidate)
            and candidate.get("event") in fallback_success_events
            and candidate.get("status") == "completed"
            and candidate.get("conclusion") == "success"
        ]
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
                "ignored_skipped_run_ids": [
                    skipped.get("id") for skipped in skipped_runs
                ],
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
) -> list[dict[str, Any]]:
    data = _gh_get(
        f"/repos/{repo}/issues",
        api=api,
        token=token,
        timeout=timeout,
        params={"state": "open", "labels": label, "per_page": 100},
    )
    if not isinstance(data, list):
        raise WatchError(f"GitHub issues response for {label!r} was not a list")
    return [issue for issue in data if not _is_pr(issue)]


def list_loop_issues(
    repo: str,
    *,
    api: str,
    token: str | None,
    timeout: float,
) -> list[dict[str, Any]]:
    by_number: dict[int, dict[str, Any]] = {}
    for label in REQUEST_LABELS:
        for issue in list_open_issues_by_label(
            repo, label, api=api, token=token, timeout=timeout
        ):
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
    needs_human: list[dict[str, Any]] = []
    missing_subscription: list[dict[str, Any]] = []
    missing_codex_subscription: list[dict[str, Any]] = []
    auth_missing: list[dict[str, Any]] = []
    provider_exhausted: list[dict[str, Any]] = []
    pr_blocked: list[dict[str, Any]] = []
    branch_push_blocked: list[dict[str, Any]] = []
    reviewed_terminal: list[dict[str, Any]] = []
    stale_gate: list[dict[str, Any]] = []
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
        elif not labels.isdisjoint(TERMINAL_REVIEW_LABELS):
            reviewed_terminal.append(issue)
        elif ATTEMPTED_LABEL in labels:
            attempted.append(issue)
            age = _age_min(issue.get("created_at"), now)
            if STALE_GATE_LABEL in labels or age is None or age > max_pending_age_min:
                stale_gate.append(issue)
        elif AWAIT_PRIMITIVE_LAYER_LABEL in labels:
            await_primitive_layer.append(issue)
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
        "missing_claude_subscription": [
            issue.get("number") for issue in missing_subscription
        ],
        "missing_codex_subscription": [
            issue.get("number") for issue in missing_codex_subscription
        ],
        "auth_missing": [issue.get("number") for issue in auth_missing],
        "branch_push_blocked": [
            issue.get("number") for issue in branch_push_blocked
        ],
        "pr_blocked": [issue.get("number") for issue in pr_blocked],
        "provider_exhausted": [issue.get("number") for issue in provider_exhausted],
        "pending": [issue.get("number") for issue in pending],
        "old_pending": [issue.get("number") for issue in old_pending],
        "await_primitive_layer": [
            issue.get("number") for issue in await_primitive_layer
        ],
        "legacy_priority_migrations": legacy_priority_migrations,
        "reviewed_terminal": [issue.get("number") for issue in reviewed_terminal],
        "stale_gate": [issue.get("number") for issue in stale_gate],
        "attempted": [issue.get("number") for issue in attempted],
        "request_labels": list(REQUEST_LABELS),
    }

    if needs_human:
        first = needs_human[0]
        root_cause = "automated writer is blocked"
        if branch_push_blocked and pr_blocked:
            root_cause = (
                "automated writer hit branch-push and PR-creation permission blocks"
            )
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
            root_cause = (
                "Claude subscription OAuth is not visible to GitHub Actions"
            )
        elif missing_codex_subscription:
            root_cause = (
                "Codex subscription auth bundle is not visible to GitHub Actions"
            )
        elif auth_missing:
            root_cause = "approved subscription-backed writer auth is missing"
        elif provider_exhausted:
            root_cause = "approved writer provider returned quota/capacity exhaustion"
        pending_clause = (
            f" and {len(old_pending)} pending request(s) are older than "
            f"{max_pending_age_min} min"
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
                (
                    issue.get("html_url")
                    for issue in pending
                    if issue.get("number") == issue_number
                ),
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
            evidence=(
                f"first deferred issue #{first.get('number')}: "
                f"{first.get('title')}"
            ),
            url=first.get("html_url"),
            details=details,
        )
    return _stage(
        "Writer queue",
        "green",
        "no open daemon-request/auto-change/auto-bug requests are waiting on the writer",
        details=details,
    )


def incident_stage(
    repo: str,
    *,
    api: str,
    token: str | None,
    timeout: float,
) -> dict[str, Any]:
    issues = list_open_issues_by_label(
        repo, P0_OUTAGE_LABEL, api=api, token=token, timeout=timeout
    )
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
            fallback_success_events=("workflow_dispatch", "issues"),
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
