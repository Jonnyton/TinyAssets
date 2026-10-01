#!/usr/bin/env python3
"""Re-run a REQUIRED check whose latest run on an armed PR was cancelled.

On 2026-10-01 the fd-flake fix (#4204) was stamped and armed but never
entered the merge queue: its newest "PR scope guard" run had been cancelled
as superseded, so the required "Diff scope declared" context read as missing
even though an earlier run had passed. Nothing re-ran it until a person
noticed. This finds that state and re-runs the cancelled run.

Per armed (auto-merge enabled), non-draft open PR, per required check name on
its head commit: if the NEWEST run of that check (highest workflow-run id) is
CANCELLED, re-run its failed/cancelled jobs. A run already on its third
attempt is left alone, so a check that keeps getting cancelled cannot loop.

    rerun_cancelled_required.py --repo OWNER/NAME [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys

MAX_ATTEMPT = 3
GH_TIMEOUT = 60

_PRS = """query($owner:String!,$name:String!){repository(owner:$owner,name:$name){
pullRequests(states:OPEN,first:100,orderBy:{field:UPDATED_AT,direction:DESC}){
nodes{id number isDraft autoMergeRequest{enabledAt}}}}}"""
_CHECKS = """query($id:ID!){node(id:$id){... on PullRequest{commits(last:1){nodes{commit{
statusCheckRollup{contexts(first:100){nodes{... on CheckRun{name conclusion
isRequired(pullRequestId:$id) checkSuite{workflowRun{databaseId}}}}}}}}}}}}"""


def cancelled_required_runs(contexts: list[dict]) -> list[tuple[str, int]]:
    """(check name, workflow run id) for required checks whose newest run was cancelled."""
    newest: dict[str, dict] = {}
    for ctx in contexts:
        run = ((ctx.get("checkSuite") or {}).get("workflowRun") or {}).get("databaseId")
        if not ctx.get("name") or not ctx.get("isRequired") or run is None:
            continue
        if ctx["name"] not in newest or run > newest[ctx["name"]]["run"]:
            newest[ctx["name"]] = {"run": run, "conclusion": ctx.get("conclusion")}
    return sorted((name, v["run"]) for name, v in newest.items()
                  if v["conclusion"] == "CANCELLED")


def _gh(*args: str) -> str:
    return subprocess.run(["gh", *args], capture_output=True, text=True, encoding="utf-8",
                          errors="replace", check=True, timeout=GH_TIMEOUT).stdout


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--repo", required=True)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    owner, name = args.repo.split("/", 1)
    prs = json.loads(_gh("api", "graphql", "-F", f"owner={owner}", "-F", f"name={name}",
                         "-f", f"query={_PRS}"))["data"]["repository"]["pullRequests"]["nodes"]
    for pr in prs:
        if pr["isDraft"] or not pr["autoMergeRequest"]:
            continue
        node = json.loads(_gh("api", "graphql", "-F", f"id={pr['id']}", "-f",
                              f"query={_CHECKS}"))["data"]["node"]
        commits = node["commits"]["nodes"]
        rollup = commits[0]["commit"]["statusCheckRollup"] if commits else None
        contexts = rollup["contexts"]["nodes"] if rollup else []
        for check, run in cancelled_required_runs(contexts):
            attempt = int(_gh("api", f"repos/{args.repo}/actions/runs/{run}",
                              "--jq", ".run_attempt") or 1)
            if attempt >= MAX_ATTEMPT:
                print(f"#{pr['number']} {check}: run {run} is on attempt {attempt}; leaving it.")
                continue
            print(f"#{pr['number']} {check}: newest run {run} was cancelled; re-running.")
            if not args.dry_run:
                try:
                    _gh("run", "rerun", str(run), "-R", args.repo, "--failed")
                except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
                    # One PR's refusal (already re-running, say) must not stop the rest.
                    print(f"  re-run refused: {getattr(exc, 'stderr', exc)}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
