#!/usr/bin/env python3
"""Cap blind merge-queue retries: two failed attempts on one head, then hand off.

Measured 2026-09-27..10-01: 39 of 65 queue removals were `failed_checks`, and
one PR (#4164) was removed for failed checks six times on the way to merging.
Each retry costs a full merge-group run and holds every PR queued behind it.
After the second failure the same head is not re-queued. The PR is labelled
`queue-handoff`, auto-merge is disabled, and one comment records what failed,
classified. Pushing a new head resets the count.

ONE definition of an attempt, used by both callers: a `failed_checks` removal
in the PR's timeline after the count last reset. It resets when the head
changes (the newest commit's committed date, or a force-push) and when
someone removes the `queue-handoff` label: removing it is how a person says
"I read the record, retry this head" (a flake, say).

    queue_attempts.py check   --repo R --pr N   # exit 3 when capped (auto-enroll)
    queue_attempts.py handoff --repo R --pr N   # label + disable + record (on dequeue)
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

CAP = 2
LABEL = "queue-handoff"
CAPPED_EXIT = 3
MARKER = "<!-- queue-handoff:{head}:{since} -->"
REPO_ROOT = Path(__file__).resolve().parent.parent
QUARANTINE = REPO_ROOT / ".github" / "known-failing-tests.txt"

_TIMELINE = """query($owner:String!,$name:String!,$number:Int!){repository(owner:$owner,name:$name){
pullRequest(number:$number){headRefOid labels(first:50){nodes{name}}
commits(last:1){nodes{commit{committedDate}}}
timelineItems(last:100,itemTypes:[REMOVED_FROM_MERGE_QUEUE_EVENT,HEAD_REF_FORCE_PUSHED_EVENT,UNLABELED_EVENT]){
nodes{__typename ... on RemovedFromMergeQueueEvent{createdAt reason}
... on HeadRefForcePushedEvent{createdAt}
... on UnlabeledEvent{createdAt label{name}}}}}}}"""
_NEW_FAILURE = re.compile(r"- `(tests/[^`]+::[^`]+)`")


def _ts(raw: str) -> datetime:
    return datetime.fromisoformat(raw.replace("Z", "+00:00"))


# ---- the decision (pure) -----------------------------------------------------


def head_changed_at(pr: dict) -> datetime:
    """When the PR's current head arrived: last commit or last force-push."""
    times = [_ts(n["commit"]["committedDate"]) for n in pr["commits"]["nodes"]]
    times += [
        _ts(n["createdAt"])
        for n in pr["timelineItems"]["nodes"]
        if n["__typename"] == "HeadRefForcePushedEvent"
    ]
    return max(times)


def count_reset_at(pr: dict) -> datetime:
    """The head change, or a later removal of the handoff label."""
    times = [head_changed_at(pr)]
    times += [
        _ts(n["createdAt"])
        for n in pr["timelineItems"]["nodes"]
        if n["__typename"] == "UnlabeledEvent" and (n.get("label") or {}).get("name") == LABEL
    ]
    return max(times)


def failed_attempts(pr: dict) -> list[datetime]:
    """`failed_checks` queue removals since the count last reset, oldest first."""
    since = count_reset_at(pr)
    return sorted(
        _ts(n["createdAt"])
        for n in pr["timelineItems"]["nodes"]
        if n["__typename"] == "RemovedFromMergeQueueEvent"
        and n.get("reason") == "failed_checks"
        and _ts(n["createdAt"]) > since
    )


def is_capped(pr: dict) -> bool:
    return len(failed_attempts(pr)) >= CAP


def new_failures(log: str) -> list[str]:
    """The node ids a failed run names as new failures (the gate's summary)."""
    return sorted(set(_NEW_FAILURE.findall(log)))


def flaky_entries(text: str) -> set[str]:
    out = set()
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if line.startswith("flaky "):
            out.add(line[len("flaky "):].strip())
    return out


def classify(test_id: str, *, on_pr_run: set[str], other_prs: Counter, flaky: set[str]) -> str:
    """One line on what a failing test most likely means. Evidence, not a verdict."""
    if test_id in flaky:
        return "quarantined as flaky"
    if test_id in on_pr_run:
        return "also failed on this PR's own Linux run: a defect in this PR"
    if other_prs[test_id]:
        return (f"also failed for {other_prs[test_id]} other PR(s) in the queue in "
                "the last 24h: main drift or a flake, not this PR alone")
    return ("did not fail on this PR's own Linux run and no other PR hit it: a "
            "batch interaction, a test the PR run did not select, or a flake")


def render_record(pr: int, head: str, since: str, attempts: list[tuple[int, list[str]]],
                  classes: dict[str, str]) -> str:
    lines = [
        MARKER.format(head=head, since=since),
        f"### Queue handoff: {len(attempts)} failed merge-queue runs on `{head[:12]}`",
        "",
        f"This head failed the merge queue {len(attempts)} times, so it will not be "
        "re-queued as it is (`scripts/queue_attempts.py`). Fix it and push; a new "
        "head starts a fresh count. If the record shows a flake or main drift, "
        f"removing the `{LABEL}` label grants this head a fresh count.",
        "",
        "| Failing test | Classification |",
        "|---|---|",
    ]
    for test_id in sorted(classes):
        lines.append(f"| `{test_id}` | {classes[test_id]} |")
    if not classes:
        lines.append("| (no test ids in the failed runs; a non-test check failed) | |")
    lines += ["", "Runs: " + ", ".join(f"`{run}`" for run, _ in attempts)]
    return "\n".join(lines) + "\n"


# ---- GitHub I/O (thin) ---------------------------------------------------------


def _gh(*args: str) -> str:
    return subprocess.run(
        ["gh", *args], capture_output=True, text=True, encoding="utf-8",
        errors="replace", check=True,
    ).stdout


def fetch_pr(repo: str, number: int) -> dict:
    owner, name = repo.split("/", 1)
    raw = _gh("api", "graphql", "-F", f"owner={owner}", "-F", f"name={name}",
              "-F", f"number={number}", "-f", f"query={_TIMELINE}")
    return json.loads(raw)["data"]["repository"]["pullRequest"]


def _runs(repo: str, event: str, since: datetime) -> list[dict]:
    raw = _gh("api", "--paginate",
              f"repos/{repo}/actions/workflows/tests.yml/runs?event={event}"
              f"&created=>={since:%Y-%m-%dT%H:%M:%SZ}&per_page=100",
              "--jq", ".workflow_runs[]")
    return [json.loads(line) for line in raw.splitlines() if line.strip()]


def _failed_ids(repo: str, run_id: int) -> list[str]:
    try:
        return new_failures(_gh("run", "view", str(run_id), "-R", repo, "--log-failed"))
    except subprocess.CalledProcessError:
        return []


def handoff(repo: str, number: int, settle_seconds: float = 20.0) -> int:
    pr = fetch_pr(repo, number)
    if not is_capped(pr) and settle_seconds:
        # The dequeue event can arrive before its timeline entry is readable.
        time.sleep(settle_seconds)
        pr = fetch_pr(repo, number)
    if not is_capped(pr):
        print(f"PR #{number}: {len(failed_attempts(pr))} failed attempt(s) on this head; "
              f"cap is {CAP}. Nothing to do.")
        return 0
    head, since = pr["headRefOid"], count_reset_at(pr)
    prefix = f"gh-readonly-queue/main/pr-{number}-"
    window = _runs(repo, "merge_group", since - timedelta(hours=24))
    attempts = [
        (r["id"], _failed_ids(repo, r["id"]))
        for r in window
        if r["head_branch"].startswith(prefix) and r["conclusion"] == "failure"
        and _ts(r["created_at"]) > since
    ]
    others: Counter = Counter()
    for r in window:
        if r["conclusion"] == "failure" and not r["head_branch"].startswith(prefix):
            for test_id in _failed_ids(repo, r["id"]):
                others[test_id] += 1
    on_pr_run: set[str] = set()
    for r in _runs(repo, "pull_request", since - timedelta(hours=1)):
        if r["head_sha"] == head and r["conclusion"] == "failure":
            on_pr_run |= set(_failed_ids(repo, r["id"]))
    flaky = flaky_entries(QUARANTINE.read_text(encoding="utf-8")) if QUARANTINE.exists() else set()
    classes = {
        t: classify(t, on_pr_run=on_pr_run, other_prs=others, flaky=flaky)
        for _, ids in attempts for t in ids
    }
    stamp = f"{since:%Y-%m-%dT%H:%M:%SZ}"
    body = render_record(number, head, stamp, attempts, classes)
    comments = _gh("api", "--paginate", f"repos/{repo}/issues/{number}/comments",
                   "--jq", ".[].body")
    if MARKER.format(head=head, since=stamp) in comments:
        print(f"PR #{number}: handoff for {head[:12]} already recorded.")
    else:
        _gh("pr", "comment", str(number), "-R", repo, "--body", body)
    _gh("label", "create", LABEL, "-R", repo, "--force", "--color", "B60205",
        "--description", "Failed the merge queue twice on one head; not re-queued")
    _gh("pr", "edit", str(number), "-R", repo, "--add-label", LABEL)
    try:
        _gh("pr", "merge", str(number), "-R", repo, "--disable-auto")
    except subprocess.CalledProcessError:
        pass  # Not armed: the removal already disarmed it.
    print(body)
    return 0


def check(repo: str, number: int) -> int:
    pr = fetch_pr(repo, number)
    if is_capped(pr):
        print(f"PR #{number} is capped: {len(failed_attempts(pr))} failed merge-queue "
              f"runs on head {pr['headRefOid'][:12]}. Push a fix to re-arm.")
        return CAPPED_EXIT
    if any(n["name"] == LABEL for n in pr["labels"]["nodes"]):
        # A new head reset the count; the label no longer describes it.
        _gh("pr", "edit", str(number), "-R", repo, "--remove-label", LABEL)
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("command", choices=["check", "handoff"])
    ap.add_argument("--repo", required=True)
    ap.add_argument("--pr", type=int, required=True)
    args = ap.parse_args(argv)
    return (check if args.command == "check" else handoff)(args.repo, args.pr)


if __name__ == "__main__":
    sys.exit(main())
