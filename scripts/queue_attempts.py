#!/usr/bin/env python3
"""Cap blind merge-queue retries: two failed attempts on one head, then hand off.

Measured 2026-09-27..10-01: 39 of 65 queue removals were `failed_checks`, and
one PR (#4164) was removed for failed checks six times on the way to merging.
Each retry costs a full merge-group run and holds every PR queued behind it.

Everything is keyed by the head SHA, never by a timestamp:

- On each `failed_checks` dequeue, `handoff` records that removal against the
  dequeued head SHA in one ledger comment on the PR (idempotent per removal).
- On the second removal of the same SHA it posts a classified failure record
  (marker `queue-handoff:<sha>`), adds the `queue-handoff` label and disables
  auto-merge, after re-checking that the head has not moved.
- `check` (auto-enroll) reports capped only while BOTH hold: the record for
  the CURRENT head exists and the label is on the PR. A new head is never
  capped; removing the label is how a person retries a head (a flake, say);
  and nothing is blocked unless the record was actually delivered.

    queue_attempts.py check   --repo R --pr N             # exit 3 when capped
    queue_attempts.py handoff --repo R --pr N --head SHA  # on dequeue
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

CAP = 2
LABEL = "queue-handoff"
CAPPED_EXIT = 3
LEDGER_MARKER = "<!-- queue-attempts-ledger -->"
RECORD_MARKER = "<!-- queue-handoff:{head} -->"
REPO_ROOT = Path(__file__).resolve().parent.parent
QUARANTINE = REPO_ROOT / ".github" / "known-failing-tests.txt"
GH_TIMEOUT = 60

_PR_QUERY = """query($owner:String!,$name:String!,$number:Int!){repository(owner:$owner,name:$name){
pullRequest(number:$number){headRefOid labels(first:50){nodes{name}}
timelineItems(last:5,itemTypes:[REMOVED_FROM_MERGE_QUEUE_EVENT]){
nodes{... on RemovedFromMergeQueueEvent{createdAt reason}}}}}}"""
_LEDGER_LINE = re.compile(r"^<!-- attempt (?P<sha>[0-9a-f]{40}) (?P<at>\S+) -->$", re.M)
_FAILED_HEADER = "**FAILED — this PR introduces test failures"
_BULLET = re.compile(r"`(tests/[^`]+::[^`]+)`")


# ---- the decision (pure) -----------------------------------------------------


def parse_ledger(body: str) -> dict[str, set[str]]:
    """{head sha: removal timestamps recorded against it}."""
    ledger: dict[str, set[str]] = {}
    for m in _LEDGER_LINE.finditer(body):
        ledger.setdefault(m["sha"], set()).add(m["at"])
    return ledger


def render_ledger(ledger: dict[str, set[str]]) -> str:
    lines = [LEDGER_MARKER,
             "Merge-queue attempts that failed checks, per head "
             f"(`scripts/queue_attempts.py`; a head is handed off after {CAP})."]
    for sha in sorted(ledger):
        lines += [f"<!-- attempt {sha} {at} -->" for at in sorted(ledger[sha])]
        lines.append(f"- `{sha[:12]}`: {len(ledger[sha])}")
    return "\n".join(lines) + "\n"


def is_capped(head: str, labels: set[str], comment_bodies: list[str]) -> bool:
    record = RECORD_MARKER.format(head=head)
    return LABEL in labels and any(record in body for body in comment_bodies)


def new_failures(log: str) -> list[str]:
    """Node ids under the gate's NEW-failures heading only.

    The same summary also lists stale quarantine entries, which are PASSING
    tests; reading every backticked id would name those as failures.
    """
    found: set[str] = set()
    for block in log.split(_FAILED_HEADER)[1:]:
        for line in block.splitlines()[1:]:
            text = re.sub(r"^.*?(?=- `|\*\*|$)", "", line).strip()
            if text.startswith("**"):
                break  # the next section (e.g. stale entries) starts here
            found.update(_BULLET.findall(text))
    return sorted(found)


def flaky_entries(text: str) -> set[str]:
    out = set()
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if line.startswith("flaky "):
            out.add(line[len("flaky "):].strip())
    return out


def classify(test_id: str, *, pr_run: set[str] | None, other_prs: Counter,
             flaky: set[str]) -> str:
    """What the evidence says about one failing test. Evidence, not a verdict.

    `pr_run` is None when the PR's own Linux run gave no usable evidence (not
    run, still running, or its log unreadable), which is not the same as the
    test passing there.
    """
    if test_id in flaky:
        return "quarantined as flaky"
    if pr_run is not None and test_id in pr_run:
        return "also failed on this PR's own Linux run: most likely this PR"
    if other_prs[test_id]:
        return (f"also failed for {other_prs[test_id]} other PR(s) in the queue in "
                "the last 24h: main drift or a flake, not this PR alone")
    if pr_run is None:
        return "no usable evidence from this PR's own Linux run; no other PR hit it"
    return ("did not fail on this PR's own Linux run (it may not have been "
            "selected there) and no other PR hit it: a batch interaction or a flake")


def render_record(head: str, attempts: list[tuple[int, list[str] | None]],
                  classes: dict[str, str]) -> str:
    lines = [
        RECORD_MARKER.format(head=head),
        f"### Queue handoff: {CAP} failed merge-queue attempts on `{head[:12]}`",
        "",
        "This head will not be re-armed as it is (`scripts/queue_attempts.py`). Push "
        f"a fix (a new head is never capped), or remove the `{LABEL}` label to retry "
        "this head if the record shows a flake or main drift.",
        "",
        "| Failing test | Evidence |",
        "|---|---|",
    ]
    lines += [f"| `{t}` | {classes[t]} |" for t in sorted(classes)]
    if not classes:
        lines.append("| (no test ids read from the failed runs) | see the runs below |")
    unreadable = [run for run, ids in attempts if ids is None]
    lines += ["", "Runs: " + (", ".join(f"`{run}`" for run, _ in attempts) or "none found")]
    if unreadable:
        lines.append("Logs unreadable for: " + ", ".join(f"`{r}`" for r in unreadable))
    return "\n".join(lines) + "\n"


# ---- GitHub I/O (thin) ---------------------------------------------------------


def _gh(*args: str) -> str:
    return subprocess.run(
        ["gh", *args], capture_output=True, text=True, encoding="utf-8",
        errors="replace", check=True, timeout=GH_TIMEOUT,
    ).stdout


def fetch_pr(repo: str, number: int) -> dict:
    owner, name = repo.split("/", 1)
    raw = _gh("api", "graphql", "-F", f"owner={owner}", "-F", f"name={name}",
              "-F", f"number={number}", "-f", f"query={_PR_QUERY}")
    return json.loads(raw)["data"]["repository"]["pullRequest"]


def _comments(repo: str, number: int) -> list[dict]:
    raw = _gh("api", "--paginate", f"repos/{repo}/issues/{number}/comments",
              "--jq", ".[] | {id, body}")
    return [json.loads(line) for line in raw.splitlines() if line.strip()]


def _runs(repo: str, event: str, since: datetime) -> list[dict]:
    raw = _gh("api", "--paginate",
              f"repos/{repo}/actions/workflows/tests.yml/runs?event={event}"
              f"&created=>={since:%Y-%m-%dT%H:%M:%SZ}&per_page=100",
              "--jq", ".workflow_runs[]")
    return [json.loads(line) for line in raw.splitlines() if line.strip()]


def _failed_ids(repo: str, run_id: int) -> list[str] | None:
    try:
        return new_failures(_gh("run", "view", str(run_id), "-R", repo, "--log-failed"))
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return None


def _queue_pr(head_branch: str) -> int | None:
    m = re.match(r"gh-readonly-queue/[^/]+/pr-(\d+)-", head_branch or "")
    return int(m.group(1)) if m else None


def handoff(repo: str, number: int, head: str, settle_seconds: float = 20.0) -> int:
    pr = fetch_pr(repo, number)
    removals = pr["timelineItems"]["nodes"]
    if pr["headRefOid"] != head:
        print(f"PR #{number} moved past {head[:12]}; this dequeue is stale.")
        return 0
    if not removals or removals[-1].get("reason") != "failed_checks":
        print(f"PR #{number}: latest removal is not failed_checks; not an attempt.")
        return 0
    removal_at = removals[-1]["createdAt"]

    comments = _comments(repo, number)
    ledger_comment = next((c for c in comments if LEDGER_MARKER in c["body"]), None)
    ledger = parse_ledger(ledger_comment["body"]) if ledger_comment else {}
    if removal_at in ledger.get(head, set()):
        # Either a re-delivered event, or this removal's timeline entry is not
        # readable yet and the latest one is the previous removal. Look once more.
        time.sleep(settle_seconds)
        latest = fetch_pr(repo, number)["timelineItems"]["nodes"]
        if not latest or latest[-1].get("reason") != "failed_checks":
            return 0
        removal_at = latest[-1]["createdAt"]
    ledger.setdefault(head, set()).add(removal_at)
    body = render_ledger(ledger)
    if ledger_comment is None:
        _gh("pr", "comment", str(number), "-R", repo, "--body", body)
    elif ledger_comment["body"] != body:
        _gh("api", "-X", "PATCH", f"repos/{repo}/issues/comments/{ledger_comment['id']}",
            "-f", f"body={body}")
    if len(ledger[head]) < CAP:
        print(f"PR #{number}: {len(ledger[head])} failed attempt(s) on {head[:12]}; cap {CAP}.")
        return 0

    now = datetime.now(timezone.utc)
    window = _runs(repo, "merge_group", now - timedelta(hours=24))
    own = [r for r in window if _queue_pr(r["head_branch"]) == number
           and r["conclusion"] == "failure"]
    attempts = [(r["id"], _failed_ids(repo, r["id"])) for r in own[:CAP + 2]]
    other_prs: dict[str, set[int]] = {}
    for r in window:
        other = _queue_pr(r["head_branch"])
        if r["conclusion"] == "failure" and other not in (None, number):
            for test_id in _failed_ids(repo, r["id"]) or []:
                other_prs.setdefault(test_id, set()).add(other)
    others = Counter({t: len(prs) for t, prs in other_prs.items()})
    pr_runs = [r for r in _runs(repo, "pull_request", now - timedelta(days=7))
               if r["head_sha"] == head and r["status"] == "completed"]
    pr_run: set[str] | None = None
    if pr_runs:
        ids = [_failed_ids(repo, r["id"]) if r["conclusion"] == "failure" else []
               for r in pr_runs]
        if all(i is not None for i in ids):
            pr_run = {t for i in ids for t in i}
    flaky = flaky_entries(QUARANTINE.read_text(encoding="utf-8")) if QUARANTINE.exists() else set()
    classes = {t: classify(t, pr_run=pr_run, other_prs=others, flaky=flaky)
               for _, ids in attempts for t in (ids or [])}
    record = render_record(head, attempts, classes)

    # Re-check right before acting: a push during the reads above must not be
    # disabled by a handoff that was about the previous head.
    if fetch_pr(repo, number)["headRefOid"] != head:
        print(f"PR #{number} moved while the record was built; not handing off.")
        return 0
    if not any(RECORD_MARKER.format(head=head) in c["body"] for c in _comments(repo, number)):
        _gh("pr", "comment", str(number), "-R", repo, "--body", record)
    _gh("label", "create", LABEL, "-R", repo, "--force", "--color", "B60205",
        "--description", "Failed the merge queue twice on one head; not re-armed")
    _gh("pr", "edit", str(number), "-R", repo, "--add-label", LABEL)
    try:
        _gh("pr", "merge", str(number), "-R", repo, "--disable-auto")
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        pass  # Not armed: the removal already disarmed it.
    print(record)
    return 0


def check(repo: str, number: int) -> int:
    pr = fetch_pr(repo, number)
    head = pr["headRefOid"]
    labels = {n["name"] for n in pr["labels"]["nodes"]}
    if LABEL not in labels:
        return 0
    if is_capped(head, labels, [c["body"] for c in _comments(repo, number)]):
        print(f"PR #{number} is handed off on head {head[:12]}: push a fix, or remove "
              f"the {LABEL} label to retry this head.")
        return CAPPED_EXIT
    # The label belongs to an earlier head; it no longer describes this one.
    _gh("pr", "edit", str(number), "-R", repo, "--remove-label", LABEL)
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("command", choices=["check", "handoff"])
    ap.add_argument("--repo", required=True)
    ap.add_argument("--pr", type=int, required=True)
    ap.add_argument("--head", help="handoff: the dequeued head SHA (from the event)")
    args = ap.parse_args(argv)
    if args.command == "check":
        return check(args.repo, args.pr)
    if not args.head or not re.fullmatch(r"[0-9a-f]{40}", args.head):
        ap.error("handoff needs --head <40-hex sha>")
    return handoff(args.repo, args.pr, args.head)


if __name__ == "__main__":
    sys.exit(main())
