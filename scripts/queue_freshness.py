#!/usr/bin/env python3
"""Catch a queued or armed PR that went stale against main BEFORE it poisons a group.

Measured over the 24 hours to 2026-10-02: 241 merge-group Tests runs for 76
merges, 99 of them failed. A large share were semantic conflicts. The PR was
green on its own head, but main had since merged something it collides with
(a shrink-only pin list against a merged deletion, a workspace-mask test
against newly added provider views). Its group failed, it was ejected, and
every group cumulatively built behind it was rebuilt, costing 20-30 minutes a
cycle.

When main moves, this runs for every queued or armed PR:

1. **Textual conflict.** GitHub reports the PR CONFLICTING, or a local merge
   onto new main fails. It is stale.
2. **Semantic conflict.** Only the tests that BOTH sides can affect run on the
   merged tree: the PR's selection (scripts/affected_tests.py over its diff)
   intersected with main's selection (over what main changed since the PR's
   base). A PR whose base IS main is fresh by definition. Disjoint selections
   cannot conflict in a test. A huge intersection is left to the queue rather
   than duplicating it.

The run is split in two on purpose: `probe` executes PR code with a read-only
token and writes a verdict file; `act` holds the write token, never touches PR
code, and dequeues/disarms/comments only for a head that has not moved.

    queue_freshness.py probe --repo R --out verdicts.json
    queue_freshness.py act   --repo R --verdicts verdicts.json
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

MAX_CANDIDATES = 60
# Queue order first, so the PRs about to enter a group are probed before the
# budget runs out; the rest wait for the next push to main.
BUDGET_SECONDS = 30 * 60
LABEL = "stale-vs-main"
MARKER = "<!-- queue-freshness:{head}:{main} -->"
GH_TIMEOUT = 60

_CANDIDATES_Q = """query($owner:String!,$name:String!){repository(owner:$owner,name:$name){
mergeQueue(branch:"main"){entries(first:100){nodes{pullRequest{number}}}}
pullRequests(states:OPEN,first:100){nodes{id number isDraft headRefOid baseRefOid
mergeable author{login} autoMergeRequest{enabledAt}}}}}"""


# ---- the decision (pure) -----------------------------------------------------


def probe_set(pr_selection: list[str] | None, main_selection: list[str] | None,
              cap: int = MAX_CANDIDATES) -> tuple[list[str] | None, str]:
    """(test files to run on the merged tree, why). ``None`` means don't run."""
    if pr_selection is None and main_selection is None:
        return None, "both sides select the whole suite; left to the queue"
    if pr_selection is None:
        candidates = list(main_selection or [])
    elif main_selection is None:
        candidates = list(pr_selection)
    else:
        candidates = sorted(set(pr_selection) & set(main_selection))
    if not candidates:
        return [], "no test is reachable from both sides"
    if len(candidates) > cap:
        return None, f"{len(candidates)} shared test files exceed the cap {cap}; left to the queue"
    return sorted(candidates), f"{len(candidates)} shared test file(s)"


def render_comment(pr: dict, verdict: dict, main: str) -> str:
    who = f"@{pr['author']} " if pr.get("author") else ""
    lines = [
        MARKER.format(head=verdict["head"], main=main),
        "### Stale against main: taken out of the queue before it reached a group",
        "",
        f"{who}main moved to `{main[:12]}`, and this head (`{verdict['head'][:12]}`) no "
        "longer merges cleanly with it, so it was dequeued and auto-merge disabled "
        "(scripts/queue_freshness.py). Merge or rebase onto main and push; a "
        "`Drain-Review-Diff:` receipt survives that if the change itself is unchanged.",
        "",
        f"**{verdict['verdict']}**: {verdict['why']}",
    ]
    if verdict.get("failures"):
        lines += ["", "Failing on the merged tree:"]
        lines += [f"- `{t}`" for t in verdict["failures"][:30]]
    return "\n".join(lines) + "\n"


# ---- I/O ---------------------------------------------------------------------


def _run(*cmd: str, cwd: Path | None = None, check: bool = True,
         timeout: int | None = None, untrusted: bool = False) -> subprocess.CompletedProcess[str]:
    # `untrusted` runs PR code: it gets no GitHub token, even the read-only one.
    env = None
    if untrusted:
        env = {k: v for k, v in os.environ.items() if k not in ("GH_TOKEN", "GITHUB_TOKEN")}
    return subprocess.run(cmd, cwd=cwd or REPO_ROOT, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", check=check, timeout=timeout,
                          env=env)


def _gh(*args: str) -> str:
    return _run("gh", *args, timeout=GH_TIMEOUT).stdout


def candidates(repo: str) -> list[dict]:
    owner, name = repo.split("/", 1)
    data = json.loads(_gh("api", "graphql", "-F", f"owner={owner}", "-F", f"name={name}",
                          "-f", f"query={_CANDIDATES_Q}"))["data"]["repository"]
    order = [n["pullRequest"]["number"] for n in data["mergeQueue"]["entries"]["nodes"]]
    queued = set(order)
    out = []
    for pr in data["pullRequests"]["nodes"]:
        if pr["isDraft"]:
            continue
        if pr["number"] in queued or pr["autoMergeRequest"]:
            out.append({
                "id": pr["id"], "number": pr["number"], "head": pr["headRefOid"],
                "base": pr["baseRefOid"], "mergeable": pr["mergeable"],
                "author": (pr.get("author") or {}).get("login", ""),
                "queued": pr["number"] in queued,
            })
    return sorted(out, key=lambda p: order.index(p["number"]) if p["queued"] else len(order))


def _selection(files: list[str], root: Path) -> list[str] | None:
    import affected_tests

    try:
        selected, _ = affected_tests.select(files, root)
    except RuntimeError:
        return None
    return selected


def _new_failures(junit: Path) -> list[str]:
    import ci_required_tests as gate

    failing, _ = gate.collect_outcomes(junit)
    tolerated, flaky, _ = gate.parse_quarantine(gate.QUARANTINE)
    return sorted(failing - tolerated - flaky)


def _still_failing(tree: Path, node_ids: list[str], tmp: str, tag: str) -> set[str]:
    """Re-run just these node ids in ``tree``; the ones that fail again."""
    junit = Path(tmp) / f"confirm-{tag}.xml"
    _run(sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-o", "addopts=",
         f"--basetemp={tmp}/c-{tag}", f"--junitxml={junit}", *node_ids,
         cwd=tree, check=False, timeout=900, untrusted=True)
    if not junit.exists():
        return set(node_ids)
    import ci_required_tests as gate

    failing, ran = gate.collect_outcomes(junit)
    return (failing | (set(node_ids) - ran)) & set(node_ids)


def blame(first_run: list[str], merged_again: set[str], main_alone: set[str]) -> list[str]:
    """Failures the PR is responsible for: fail twice merged, pass on main alone.

    A dequeue costs a builder a rebase, so a flake (passes on the re-run) or a
    test already broken on main (fails without the PR) never causes one.
    """
    return sorted(t for t in first_run if t in merged_again and t not in main_alone)


def probe_one(pr: dict, main: str) -> dict:
    verdict = {"number": pr["number"], "head": pr["head"]}
    if pr["mergeable"] == "CONFLICTING":
        return {**verdict, "verdict": "conflict",
                "why": "GitHub reports a merge conflict with main"}
    _run("git", "fetch", "-q", "--no-tags", "origin", f"+refs/pull/{pr['number']}/head")
    merge_base = _run("git", "merge-base", pr["head"], main).stdout.strip()
    if merge_base == main:
        return {**verdict, "verdict": "fresh", "why": "already based on current main"}
    main_delta = _run("git", "diff", "--name-only", merge_base, main).stdout.split()
    pr_files = _run("git", "diff", "--name-only", merge_base, pr["head"]).stdout.split()
    with tempfile.TemporaryDirectory(prefix="ta-fresh-") as tmp:
        tree = Path(tmp) / "w"
        _run("git", "worktree", "add", "-q", "--detach", str(tree), main)
        try:
            merged = _run("git", "-c", "user.name=freshness", "-c", "user.email=f@localhost",
                          "merge", "-q", "--no-edit", pr["head"], cwd=tree, check=False)
            if merged.returncode != 0:
                return {**verdict, "verdict": "conflict", "why": "merging onto main conflicts"}
            run_files, why = probe_set(_selection(pr_files, tree), _selection(main_delta, tree))
            if not run_files:
                state = "fresh" if run_files == [] else "unchecked"
                return {**verdict, "verdict": state, "why": why}
            selection = Path(tmp) / "affected.txt"
            selection.write_text("".join(f"{f}\n" for f in run_files), encoding="utf-8")
            junit = Path(tmp) / "junit.xml"
            _run(sys.executable, "scripts/ci_required_tests.py", "--junit", str(junit),
                 "--exclude-from", ".github/heavy-test-files.txt", "--affected", str(selection),
                 "--profile", "affected", "--pytest-arg", f"--basetemp={tmp}/b",
                 cwd=tree, check=False, timeout=1500, untrusted=True)
            failures = _new_failures(junit) if junit.exists() else []
            if failures:
                again = _still_failing(tree, failures, tmp, "merged")
                _run("git", "checkout", "-q", "--detach", main, cwd=tree)
                failures = blame(failures, again, _still_failing(tree, failures, tmp, "main"))
            if failures:
                return {**verdict, "verdict": "semantic-conflict", "why": why, "failures": failures}
            return {**verdict, "verdict": "fresh", "why": f"{why} pass on the merged tree"}
        finally:
            _run("git", "worktree", "remove", "--force", str(tree), check=False)


def probe(repo: str, out: Path) -> int:
    main = _run("git", "rev-parse", "origin/main").stdout.strip()
    verdicts = []
    deadline = time.monotonic() + BUDGET_SECONDS
    for pr in candidates(repo):
        if time.monotonic() > deadline:
            print(f"#{pr['number']}: budget spent; next push to main probes it.")
            continue
        try:
            verdicts.append(probe_one(pr, main))
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
            verdicts.append({"number": pr["number"], "head": pr["head"], "verdict": "unchecked",
                             "why": f"probe failed: {type(exc).__name__}"})
        print(f"#{pr['number']}: {verdicts[-1]['verdict']} - {verdicts[-1]['why']}")
    out.write_text(json.dumps({"main": main, "verdicts": verdicts}, indent=1), encoding="utf-8")
    return 0


def act(repo: str, verdicts_file: Path) -> int:
    data = json.loads(verdicts_file.read_text(encoding="utf-8"))
    main, live = data["main"], {p["number"]: p for p in candidates(repo)}
    for v in data["verdicts"]:
        if v["verdict"] not in ("conflict", "semantic-conflict"):
            continue
        pr = live.get(v["number"])
        if pr is None or pr["head"] != v["head"]:
            print(f"#{v['number']}: head moved or no longer queued/armed; leaving it.")
            continue
        n = str(pr["number"])
        if pr["queued"]:
            try:
                _gh("api", "graphql", "-F", f"id={pr['id']}", "-f",
                    "query=mutation($id:ID!){dequeuePullRequest(input:{id:$id})"
                    "{clientMutationId}}")
            except subprocess.CalledProcessError as exc:
                # Still disarm and comment: a person can dequeue by hand.
                print(f"::warning::#{n}: dequeue refused: {exc.stderr.strip()[:200]}")
        subprocess.run(["gh", "pr", "merge", n, "-R", repo, "--disable-auto"],
                       capture_output=True, timeout=GH_TIMEOUT)
        marker = MARKER.format(head=v["head"], main=main)
        comments = _gh("api", "--paginate", f"repos/{repo}/issues/{n}/comments", "--jq", ".[].body")
        if marker not in comments:
            _gh("pr", "comment", n, "-R", repo, "--body", render_comment(pr, v, main))
        _gh("label", "create", LABEL, "-R", repo, "--force", "--color", "FBCA04",
            "--description", "Stale against current main; rebase before re-queueing")
        _gh("pr", "edit", n, "-R", repo, "--add-label", LABEL)
        print(f"#{n}: {v['verdict']}; dequeued, disarmed, commented.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("command", choices=["probe", "act"])
    ap.add_argument("--repo", required=True)
    ap.add_argument("--out", type=Path)
    ap.add_argument("--verdicts", type=Path)
    args = ap.parse_args()
    os.environ.setdefault("GIT_TERMINAL_PROMPT", "0")
    if args.command == "probe":
        if not args.out:
            ap.error("probe needs --out")
        return probe(args.repo, args.out)
    if not args.verdicts:
        ap.error("act needs --verdicts")
    return act(args.repo, args.verdicts)


if __name__ == "__main__":
    raise SystemExit(main())
