"""Loop consent digest - batch the loop's autonomous abandonment decisions into a PR.

The auto-fix loop applies several terminal labels when it decides an issue cannot be
progressed autonomously: `auto-fix-exhausted` (retry budget burned, Slice B), `auto-fix-blocked`
(writer rejected the design), `auto-fix-already-fixed`, `auto-fix-pr-blocked`,
`auto-fix-branch-push-blocked`. Each is a decision the loop made without the host in the
loop. Slice C makes those decisions auditable + reversible by surfacing them through the
same merge-key gesture the host already uses for code PRs.

This script:
- Lists open issues currently carrying a terminal-abandonment label.
- Filters to those whose terminal label landed *since* the most recently merged loop-consent
  PR (or all of them, on first run).
- Emits an append-only audit log file at `docs/loop-decisions/<UTC-date>.md`.
- Prints a PR-body markdown summary to stdout.

The caller (the GitHub Actions workflow) is responsible for committing the file, pushing the
branch, and opening the PR. Keeping the script reasoning separate from the git plumbing
keeps the unit-testable surface small.

The output deliberately does NOT include workflow-state mutations. Reopen-on-comment is a
separate workflow (`loop-consent-reopen.yml`) so this script can stay read-only and idempotent.
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
CONSENT_PR_LABEL = "loop-consent"
CONSENT_PR_BRANCH_PREFIX = "loop-consent/"
DECISIONS_DIR = Path("docs/loop-decisions")

# Labels the loop applies when it decides an issue cannot be progressed autonomously. Order
# matters only for display grouping.
TERMINAL_DECISION_LABELS: tuple[str, ...] = (
    "auto-fix-exhausted",
    "auto-fix-blocked",
    "auto-fix-pr-blocked",
    "auto-fix-branch-push-blocked",
    "auto-fix-already-fixed",
)

# Human-readable summary of each terminal category for the digest.
DECISION_LABEL_SUMMARY: dict[str, str] = {
    "auto-fix-exhausted": "retry budget burned (Slice B)",
    "auto-fix-blocked": "writer rejected the design as unbuildable",
    "auto-fix-pr-blocked": "branch pushed but PR creation blocked",
    "auto-fix-branch-push-blocked": "patch produced but branch push blocked",
    "auto-fix-already-fixed": "request already addressed, no PR needed",
}


def _utc_now() -> dt.datetime:
    return dt.datetime.now(tz=dt.timezone.utc)


def _gh_request(
    url: str,
    *,
    token: str | None,
    timeout: float,
    method: str = "GET",
) -> Any:
    req = urllib.request.Request(url, method=method)
    req.add_header("Accept", "application/vnd.github+json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"GitHub API error {exc.code} for {url}: {exc.reason}") from exc


def _gh_paginate(url: str, *, token: str | None, timeout: float) -> list[dict[str, Any]]:
    """Paginate over GitHub API responses; cap at 10 pages to bound runtime cost."""
    results: list[dict[str, Any]] = []
    next_url: str | None = url
    pages = 0
    while next_url and pages < 10:
        req = urllib.request.Request(next_url)
        req.add_header("Accept", "application/vnd.github+json")
        if token:
            req.add_header("Authorization", f"Bearer {token}")
        with urllib.request.urlopen(req, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
            if isinstance(payload, list):
                results.extend(payload)
            else:
                results.append(payload)
            link = response.headers.get("Link", "")
        next_url = _parse_next_link(link)
        pages += 1
    return results


def _parse_next_link(link_header: str) -> str | None:
    if not link_header:
        return None
    for piece in link_header.split(","):
        match = re.search(r'<([^>]+)>;\s*rel="next"', piece.strip())
        if match:
            return match.group(1)
    return None


def _github_token(args: argparse.Namespace) -> str | None:
    if getattr(args, "token", None):
        return args.token
    env_token = os.environ.get("GITHUB_TOKEN")
    if env_token:
        return env_token
    try:
        result = subprocess.run(
            ["gh", "auth", "token"],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
        candidate = (result.stdout or "").strip()
        if result.returncode == 0 and candidate:
            return candidate
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    return None


def list_open_issues_with_any_label(
    repo: str,
    labels: tuple[str, ...],
    *,
    api: str,
    token: str | None,
    timeout: float,
) -> list[dict[str, Any]]:
    """Open issues with at least one of the terminal-decision labels.

    GitHub's `labels=a,b` parameter does AND, not OR, so we issue one paginated request per
    label and dedupe by issue number.
    """
    by_number: dict[int, dict[str, Any]] = {}
    for label in labels:
        params = urllib.parse.urlencode(
            {"state": "open", "labels": label, "per_page": 100}
        )
        url = f"{api}/repos/{repo}/issues?{params}"
        for issue in _gh_paginate(url, token=token, timeout=timeout):
            # filter out pull requests masquerading as issues in the same endpoint
            if isinstance(issue, dict) and "pull_request" not in issue:
                number = issue.get("number")
                if isinstance(number, int):
                    by_number[number] = issue
    return sorted(by_number.values(), key=lambda issue: issue.get("number", 0))


def find_last_merged_consent_pr(
    repo: str,
    *,
    api: str,
    token: str | None,
    timeout: float,
) -> dict[str, Any] | None:
    """Most recently merged PR carrying the loop-consent label, for the digest cutoff."""
    params = urllib.parse.urlencode(
        {
            "state": "closed",
            "labels": CONSENT_PR_LABEL,
            "per_page": 30,
            "sort": "updated",
            "direction": "desc",
        }
    )
    url = f"{api}/repos/{repo}/issues?{params}"
    candidates = _gh_paginate(url, token=token, timeout=timeout)
    for candidate in candidates:
        # only PRs (issue endpoint returns both)
        if "pull_request" not in candidate:
            continue
        # Was it merged (not just closed)? Need to fetch the PR object.
        pr_number = candidate.get("number")
        if not isinstance(pr_number, int):
            continue
        pr = _gh_request(
            f"{api}/repos/{repo}/pulls/{pr_number}",
            token=token,
            timeout=timeout,
        )
        if pr.get("merged_at"):
            return pr
    return None


def find_open_consent_pr(
    repo: str,
    *,
    api: str,
    token: str | None,
    timeout: float,
) -> dict[str, Any] | None:
    """Any currently-open loop-consent PR. If one exists, the workflow should skip filing a
    new one and instead update the existing diff (handled by the workflow caller)."""
    params = urllib.parse.urlencode(
        {"state": "open", "labels": CONSENT_PR_LABEL, "per_page": 5}
    )
    url = f"{api}/repos/{repo}/issues?{params}"
    for candidate in _gh_paginate(url, token=token, timeout=timeout):
        if "pull_request" in candidate:
            return candidate
    return None


def _classify_decision(labels: set[str]) -> str:
    """First-match-wins; auto-fix-exhausted is most specific so it wins over generic blocked."""
    for label in TERMINAL_DECISION_LABELS:
        if label in labels:
            return label
    return "unknown"


def _issue_labels(issue: dict[str, Any]) -> set[str]:
    raw = issue.get("labels") or []
    out: set[str] = set()
    for item in raw:
        name = item.get("name") if isinstance(item, dict) else str(item)
        if name:
            out.add(name)
    return out


def _retry_count_from_labels(labels: set[str]) -> int:
    retry_re = re.compile(r"^auto-fix-retries-(\d+)$")
    counts = [int(match.group(1)) for label in labels if (match := retry_re.match(label))]
    return max(counts) if counts else 0


def build_digest(
    repo: str,
    *,
    api: str,
    token: str | None,
    timeout: float,
    cutoff: dt.datetime | None,
    now: dt.datetime,
) -> dict[str, Any]:
    """Build a digest payload describing all loop decisions since cutoff.

    Returns a dict with keys:
      - `decisions`: list of per-issue dicts
      - `summary_counts`: count per terminal label
      - `cutoff`: ISO string or None
      - `generated_at`: ISO string
      - `should_open_pr`: True if there are any decisions to surface
    """
    issues = list_open_issues_with_any_label(
        repo,
        TERMINAL_DECISION_LABELS,
        api=api,
        token=token,
        timeout=timeout,
    )
    decisions: list[dict[str, Any]] = []
    summary_counts: dict[str, int] = {label: 0 for label in TERMINAL_DECISION_LABELS}
    for issue in issues:
        labels = _issue_labels(issue)
        decision = _classify_decision(labels)
        if decision == "unknown":
            continue
        updated_at = issue.get("updated_at")
        # Cutoff filter: skip issues whose terminal label landed *before* the last consent PR
        # merged. updated_at is a coarse proxy — refining it would require iterating events.
        if cutoff is not None and updated_at:
            try:
                updated_dt = dt.datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
                if updated_dt < cutoff:
                    continue
            except ValueError:
                pass
        summary_counts[decision] += 1
        decisions.append(
            {
                "number": issue.get("number"),
                "title": issue.get("title", ""),
                "url": issue.get("html_url", ""),
                "decision": decision,
                "labels": sorted(labels),
                "updated_at": updated_at,
                "retry_count": _retry_count_from_labels(labels),
            }
        )
    return {
        "decisions": decisions,
        "summary_counts": summary_counts,
        "cutoff": cutoff.isoformat().replace("+00:00", "Z") if cutoff else None,
        "generated_at": now.isoformat().replace("+00:00", "Z"),
        "should_open_pr": bool(decisions),
    }


def render_audit_log(digest: dict[str, Any]) -> str:
    """Render the digest as the markdown that will land at docs/loop-decisions/<date>.md."""
    lines: list[str] = []
    date_label = digest["generated_at"][:10]
    lines.append(f"# Loop decisions consent — {date_label}")
    lines.append("")
    lines.append(f"Generated: {digest['generated_at']}")
    if digest.get("cutoff"):
        lines.append(f"Decisions since: {digest['cutoff']}")
    else:
        lines.append(
            "Decisions since: (no prior consent PR; covering all currently-terminal issues)"
        )
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    for label in TERMINAL_DECISION_LABELS:
        count = digest["summary_counts"].get(label, 0)
        descriptor = DECISION_LABEL_SUMMARY.get(label, label)
        lines.append(f"- {count} {label} ({descriptor})")
    lines.append("")
    if not digest["decisions"]:
        lines.append("No decisions to record.")
        return "\n".join(lines) + "\n"
    lines.append("## Decisions")
    lines.append("")
    for decision in digest["decisions"]:
        lines.append(f"### #{decision['number']} — {decision['decision']}")
        lines.append("")
        lines.append(f"**Title:** {decision['title']}")
        lines.append(f"**URL:** {decision['url']}")
        lines.append(f"**Last touch:** {decision.get('updated_at') or 'unknown'}")
        if decision.get("retry_count"):
            lines.append(f"**Retry count:** {decision['retry_count']}")
        lines.append(f"**Labels:** {', '.join(decision['labels'])}")
        lines.append("")
        lines.append(
            "To dissent: comment `reopen #" + str(decision["number"])
            + "` on the consent PR before merging."
        )
        lines.append("")
    lines.append("---")
    lines.append("")
    lines.append(
        "Merging this PR records host consent for all decisions above. To dissent on "
        "specific items, comment `reopen #N1 #N2 ...` on this PR and close-without-merge; "
        "the next digest will include unreopened decisions."
    )
    return "\n".join(lines) + "\n"


def parse_reopen_numbers(comment_body: str) -> list[int]:
    """Extract `reopen #N #M ...` numbers from a host comment on the consent PR.

    Used by the reopen-on-comment workflow to strip terminal labels from the named issues.
    Accepts `reopen #123`, `reopen #123, #456`, `reopen #123 #456`. Whitespace and commas
    tolerated. Case-insensitive. Other text in the comment is ignored.
    """
    lower = comment_body.lower()
    out: list[int] = []
    for match in re.finditer(r"reopen\s+((?:#\d+[\s,]*)+)", lower):
        chunk = match.group(1)
        for number_match in re.finditer(r"#(\d+)", chunk):
            try:
                value = int(number_match.group(1))
            except ValueError:
                continue
            if value > 0 and value not in out:
                out.append(value)
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=DEFAULT_REPO)
    parser.add_argument("--api", default=DEFAULT_API)
    parser.add_argument("--token", default=None)
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT)
    parser.add_argument(
        "--out",
        default=None,
        help="Path to write the audit log file (default: docs/loop-decisions/<date>.md).",
    )
    parser.add_argument(
        "--print-pr-body",
        action="store_true",
        help="Print a PR-body markdown summary to stdout after writing the audit log.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the audit log to stdout instead of writing.",
    )
    args = parser.parse_args(argv)

    token = _github_token(args)
    now = _utc_now()

    open_consent_pr = find_open_consent_pr(
        args.repo, api=args.api, token=token, timeout=args.timeout
    )
    if open_consent_pr is not None:
        sys.stderr.write(
            f"open consent PR already exists: #{open_consent_pr.get('number')} — "
            "skipping new digest\n"
        )
        return 0

    last_merged = find_last_merged_consent_pr(
        args.repo, api=args.api, token=token, timeout=args.timeout
    )
    cutoff: dt.datetime | None = None
    if last_merged and last_merged.get("merged_at"):
        try:
            cutoff = dt.datetime.fromisoformat(
                last_merged["merged_at"].replace("Z", "+00:00")
            )
        except ValueError:
            cutoff = None

    digest = build_digest(
        args.repo,
        api=args.api,
        token=token,
        timeout=args.timeout,
        cutoff=cutoff,
        now=now,
    )

    if not digest["should_open_pr"]:
        sys.stderr.write("no new loop decisions since cutoff; nothing to consent to\n")
        return 0

    audit_log = render_audit_log(digest)

    if args.dry_run:
        sys.stdout.write(audit_log)
        return 0

    out_path = Path(args.out) if args.out else (
        REPO_ROOT / DECISIONS_DIR / f"{now.date().isoformat()}.md"
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(audit_log, encoding="utf-8")
    sys.stderr.write(f"wrote audit log: {out_path}\n")

    if args.print_pr_body:
        sys.stdout.write(audit_log)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
