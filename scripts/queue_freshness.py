#!/usr/bin/env python3
"""Catch a queued or armed PR that went stale against main BEFORE it poisons a group.

Measured over the 24 hours to 2026-10-02: 241 merge-group Tests runs for 76
merges, 99 of them failed. A large share were semantic conflicts. The PR was
green on its own head, but main had since merged something it collides with
(a shrink-only pin list against a merged deletion, a workspace-mask test
against newly added provider views). Its group failed, it was ejected, and
every group cumulatively built behind it was rebuilt, costing 20-30 minutes a
cycle.

When main moves, the first few queued or armed PRs (queue order) are checked:

1. **Textual conflict.** A merge onto new main leaves unmerged paths.
2. **Semantic conflict.** Only the tests that both sides can affect run on the
   merged tree: the PR's selection (scripts/affected_tests.py over its diff)
   intersected with main's selection (over what main changed since the PR's
   merge base). A failure counts only if it fails again on a re-run AND passes
   on main alone, so a flake or a test already broken on main never costs a
   builder a rebase. A huge intersection is left to the queue.

Three commands, three trust levels (.github/workflows/queue-freshness.yml):

    list   trusted: picks the candidates; its output is the matrix.
    probe  untrusted: runs ONE PR's code with no GitHub token at all and writes
           a verdict about that PR only. The workflow names its artifact from
           the trusted matrix, and `act` ignores any PR number inside it, so a
           malicious PR can at worst dequeue itself (Codex on #4293).
    act    trusted: never runs PR code. Re-derives a textual conflict itself
           (`git merge-tree`), takes a semantic verdict only from that PR's own
           artifact, acts only while main and the head are both unchanged, and
           re-reads the PR right before each mutation.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

MAX_SHARED_TESTS = 60
# Probes per push to main, in queue order. The PRs about to enter a group come
# first; anything further back is checked on a later push.
MAX_PROBES = 6
FIRST_RUN_TIMEOUT = 900
CONFIRM_TIMEOUT = 300
LABEL = "stale-vs-main"
MARKER = "<!-- queue-freshness:{head}:{main} -->"
GH_TIMEOUT = 60
STALE = ("conflict", "semantic-conflict")
# Never handed to PR code (Codex on #4293: the conftest import inherited them).
_SECRET_ENV = (
    "GH_TOKEN", "GITHUB_TOKEN", "ACTIONS_RUNTIME_TOKEN", "ACTIONS_ID_TOKEN_REQUEST_TOKEN",
)

_CANDIDATES_Q = """query($owner:String!,$name:String!,$after:String){
repository(owner:$owner,name:$name){
mergeQueue(branch:"main"){entries(first:100){nodes{pullRequest{number}}}}
pullRequests(states:OPEN,first:100,after:$after){pageInfo{hasNextPage endCursor}
nodes{id number isDraft headRefOid baseRefName author{login}
autoMergeRequest{enabledAt}}}}}"""

_ONE_Q = """query($owner:String!,$name:String!,$n:Int!){repository(owner:$owner,name:$name){
pullRequest(number:$n){id state isDraft headRefOid baseRefName isInMergeQueue
author{login} autoMergeRequest{enabledAt}}}}"""


# ---- the decision (pure) -----------------------------------------------------


def probe_set(pr_selection: list[str] | None, main_selection: list[str] | None,
              cap: int = MAX_SHARED_TESTS) -> tuple[list[str] | None, str]:
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


def blame(first_run: list[str], merged_again: set[str], main_alone: set[str]) -> list[str]:
    """Failures the PR is responsible for: fail twice merged, pass on main alone."""
    return sorted(t for t in first_run if t in merged_again and t not in main_alone)


def actionable(trusted: dict, verdict: dict | None) -> dict | None:
    """The verdict ``act`` may use for the PR the trusted matrix named, else None.

    The PR number and head come from ``trusted``; the artifact only contributes
    its verdict, and only if it is about that same head.
    """
    if not verdict or verdict.get("head") != trusted["head"]:
        return None
    if verdict.get("verdict") not in STALE:
        return None
    return {**verdict, "number": trusted["number"]}


def render_comment(author: str, verdict: dict, main: str) -> str:
    who = f"@{author} " if author else ""
    lines = [
        MARKER.format(head=verdict["head"], main=main),
        "### Stale against main: taken out of the queue before it reached a group",
        "",
        f"{who}main moved to `{main[:12]}`, and this head (`{verdict['head'][:12]}`) no "
        "longer merges cleanly with it, so it was taken out of the merge queue and "
        "auto-merge was disabled (scripts/queue_freshness.py). Merge or rebase onto "
        "main and push; a `Drain-Review-Diff:` receipt survives that if the change "
        "itself is unchanged.",
        "",
        f"**{verdict['verdict']}**: {verdict['why']}",
    ]
    if verdict.get("failures"):
        lines += ["", "Failing on the merged tree (twice), passing on main alone:"]
        lines += [f"- `{t}`" for t in verdict["failures"][:30]]
    return "\n".join(lines) + "\n"


# ---- I/O ---------------------------------------------------------------------


def _untrusted_env() -> dict[str, str]:
    return {k: v for k, v in os.environ.items() if k not in _SECRET_ENV}


def _run(*cmd: str, cwd: Path | None = None, check: bool = True,
         timeout: int | None = None, untrusted: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=cwd or REPO_ROOT, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", check=check, timeout=timeout,
                          env=_untrusted_env() if untrusted else None)


def _gh(*args: str) -> str:
    return _run("gh", *args, timeout=GH_TIMEOUT).stdout


def _graphql(query: str, **variables: object) -> dict:
    args = ["api", "graphql", "-f", f"query={query}"]
    for key, value in variables.items():
        if value is not None:
            args += ["-F", f"{key}={value}"]
    return json.loads(_gh(*args))["data"]


def candidates(repo: str) -> list[dict]:
    """Open, non-draft PRs into main that are queued or armed: queue order, then armed."""
    owner, name = repo.split("/", 1)
    order: list[int] = []
    prs: list[dict] = []
    after = None
    while True:
        data = _graphql(_CANDIDATES_Q, owner=owner, name=name, after=after)["repository"]
        if not order:
            order = [n["pullRequest"]["number"] for n in data["mergeQueue"]["entries"]["nodes"]]
        page = data["pullRequests"]
        prs += page["nodes"]
        if not page["pageInfo"]["hasNextPage"]:
            break
        after = page["pageInfo"]["endCursor"]
    queued = set(order)
    out = []
    for pr in prs:
        if pr["isDraft"] or pr["baseRefName"] != "main":
            continue
        if pr["number"] in queued or pr["autoMergeRequest"]:
            out.append({"number": pr["number"], "head": pr["headRefOid"],
                        "author": (pr.get("author") or {}).get("login", "")})
    return sorted(out, key=lambda p: order.index(p["number"]) if p["number"] in queued
                  else len(order))


def _selection(files: list[str], root: Path) -> list[str] | None:
    # affected_tests imports the merged tree's conftests: PR code. The probe job
    # carries no token, and _SECRET_ENV is dropped here as well.
    import affected_tests

    saved = {k: os.environ.pop(k) for k in _SECRET_ENV if k in os.environ}
    try:
        selected, _ = affected_tests.select(files, root)
    except RuntimeError:
        return None
    finally:
        os.environ.update(saved)
    return selected


def _junit_failures(junit: Path, asked: list[str] | None = None) -> set[str] | None:
    """Failing node ids, or None if the report is missing or unreadable.

    With ``asked``, an asked-for id that did not run counts as failing.
    """
    import ci_required_tests as gate

    if not junit.exists():
        return None
    try:
        failing, ran = gate.collect_outcomes(junit)
    except Exception:  # noqa: BLE001 - a broken report is "unchecked", never "fresh"
        return None
    if asked is None:
        return failing
    return (failing | (set(asked) - ran)) & set(asked)


def _still_failing(tree: Path, node_ids: list[str], tmp: str, tag: str) -> set[str]:
    """Re-run just these node ids in ``tree``; the ones that fail again."""
    junit = Path(tmp) / f"confirm-{tag}.xml"
    # Same junit family as the gate run: under the default xunit2 the report
    # loses `file` and every id reads as "did not run" (Codex on #4293).
    try:
        _run(sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
             "-o", "junit_family=xunit1", f"--basetemp={tmp}/c-{tag}",
             f"--junitxml={junit}", *node_ids,
             cwd=tree, check=False, timeout=CONFIRM_TIMEOUT, untrusted=True)
    except subprocess.TimeoutExpired:
        return set(node_ids)
    failing = _junit_failures(junit, node_ids)
    return set(node_ids) if failing is None else failing


def probe_one(number: int, head: str, main: str) -> dict:
    verdict = {"number": number, "head": head}
    _run("git", "fetch", "-q", "--no-tags", "origin", f"+refs/pull/{number}/head")
    if _run("git", "rev-parse", "FETCH_HEAD").stdout.strip() != head:
        return {**verdict, "verdict": "unchecked", "why": "the head moved since it was listed"}
    merge_base = _run("git", "merge-base", head, main).stdout.strip()
    if merge_base == main:
        return {**verdict, "verdict": "fresh", "why": "already based on current main"}
    main_delta = _run("git", "diff", "--name-only", merge_base, main).stdout.split()
    pr_files = _run("git", "diff", "--name-only", merge_base, head).stdout.split()
    with tempfile.TemporaryDirectory(prefix="ta-fresh-") as tmp:
        tree = Path(tmp) / "w"
        _run("git", "worktree", "add", "-q", "--detach", str(tree), main)
        try:
            merged = _run("git", "-c", "user.name=freshness", "-c", "user.email=f@localhost",
                          "merge", "-q", "--no-edit", head, cwd=tree, check=False)
            if merged.returncode != 0:
                unmerged = _run("git", "diff", "--name-only", "--diff-filter=U",
                                cwd=tree).stdout.split()
                if unmerged:
                    return {**verdict, "verdict": "conflict",
                            "why": f"merging onto main conflicts in {len(unmerged)} file(s)"}
                return {**verdict, "verdict": "unchecked", "why": "the local merge failed"}
            run_files, why = probe_set(_selection(pr_files, tree), _selection(main_delta, tree))
            if not run_files:
                state = "fresh" if run_files == [] else "unchecked"
                return {**verdict, "verdict": state, "why": why}
            selection = Path(tmp) / "affected.txt"
            selection.write_text("".join(f"{f}\n" for f in run_files), encoding="utf-8")
            junit = Path(tmp) / "junit.xml"
            try:
                _run(sys.executable, "scripts/ci_required_tests.py", "--junit", str(junit),
                     "--exclude-from", ".github/heavy-test-files.txt",
                     "--affected", str(selection), "--profile", "affected",
                     "--pytest-arg", f"--basetemp={tmp}/b",
                     cwd=tree, check=False, timeout=FIRST_RUN_TIMEOUT, untrusted=True)
            except subprocess.TimeoutExpired:
                return {**verdict, "verdict": "unchecked", "why": f"{why}; the run timed out"}
            failing = _junit_failures(junit)
            if failing is None:
                return {**verdict, "verdict": "unchecked", "why": f"{why}; no readable report"}
            import ci_required_tests as gate

            tolerated, flaky, _ = gate.parse_quarantine(tree / ".github/known-failing-tests.txt")
            failures = sorted(failing - tolerated - flaky)
            if failures:
                again = _still_failing(tree, failures, tmp, "merged")
                _run("git", "checkout", "-q", "--detach", main, cwd=tree)
                failures = blame(failures, again, _still_failing(tree, failures, tmp, "main"))
            if failures:
                return {**verdict, "verdict": "semantic-conflict", "why": why,
                        "failures": failures}
            return {**verdict, "verdict": "fresh", "why": f"{why} pass on the merged tree"}
        finally:
            _run("git", "worktree", "remove", "--force", str(tree), check=False)


def _live(repo: str, number: int) -> dict:
    owner, name = repo.split("/", 1)
    return _graphql(_ONE_Q, owner=owner, name=name, n=number)["repository"]["pullRequest"]


def _main_sha(repo: str) -> str:
    return _gh("api", f"repos/{repo}/commits/main", "--jq", ".sha").strip()


def _really_conflicts(head: str, main: str, number: int) -> bool:
    """Trusted re-derivation of a textual conflict: no PR code runs."""
    _run("git", "fetch", "-q", "--no-tags", "origin", main, f"+refs/pull/{number}/head")
    out = _run("git", "merge-tree", "--write-tree", main, head, check=False)
    return out.returncode == 1


def act(repo: str, main: str, matrix: list[dict], verdict_dir: Path) -> int:
    # A textual conflict is re-derived against main as it is NOW. A semantic
    # verdict holds only for the main it was probed on, so a moved main drops
    # it; the run already pending for the new main probes again.
    current = _main_sha(repo)
    for trusted in matrix:
        n = trusted["number"]
        path = verdict_dir / f"verdict-{n}" / "verdict.json"
        raw = json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
        v = actionable(trusted, raw)
        if v is None:
            print(f"#{n}: {(raw or {}).get('verdict', 'no verdict')}; nothing to do.")
            continue
        if v["verdict"] == "semantic-conflict" and current != main:
            print(f"#{n}: semantic verdict was for {main[:12]}; main moved, leaving it.")
            continue
        if v["verdict"] == "conflict" and not _really_conflicts(v["head"], current, n):
            print(f"#{n}: no textual conflict with current main {current[:12]}; leaving it.")
            continue
        pr = _live(repo, n)
        if (pr["state"] != "OPEN" or pr["isDraft"] or pr["baseRefName"] != "main"
                or pr["headRefOid"] != v["head"]
                or not (pr["isInMergeQueue"] or pr["autoMergeRequest"])):
            print(f"#{n}: changed since the probe (head, state or queue); leaving it.")
            continue
        _remove(repo, pr)
        after = _live(repo, n)
        if after["isInMergeQueue"] or after["autoMergeRequest"]:
            print(f"::warning::#{n}: still queued or armed after removal; not commenting.")
            continue
        marker = MARKER.format(head=v["head"], main=current)
        comments = _gh("api", "--paginate", f"repos/{repo}/issues/{n}/comments", "--jq", ".[].body")
        if marker not in comments:
            author = (pr.get("author") or {}).get("login", "")
            _gh("pr", "comment", str(n), "-R", repo, "--body", render_comment(author, v, current))
        _gh("label", "create", LABEL, "-R", repo, "--force", "--color", "FBCA04",
            "--description", "Stale against current main; rebase before re-queueing")
        _gh("pr", "edit", str(n), "-R", repo, "--add-label", LABEL)
        print(f"#{n}: {v['verdict']}; removed from the queue and disarmed, author pinged.")
    return 0


def _remove(repo: str, pr: dict) -> None:
    for wanted, mutation in (
        (pr["isInMergeQueue"], "dequeuePullRequest"),
        (pr["autoMergeRequest"], "disablePullRequestAutoMerge"),
    ):
        if not wanted:
            continue
        query = (f"mutation($id:ID!){{{mutation}(input:{{"
                 f"{'id' if mutation == 'dequeuePullRequest' else 'pullRequestId'}:$id}})"
                 "{clientMutationId}}")
        try:
            _graphql(query, id=pr["id"])
        except subprocess.CalledProcessError as exc:
            print(f"::warning::#{pr.get('number', '?')}: {mutation} refused: "
                  f"{exc.stderr.strip()[:200]}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="command", required=True)
    ls = sub.add_parser("list")
    ls.add_argument("--repo", required=True)
    pr = sub.add_parser("probe")
    pr.add_argument("--number", type=int, required=True)
    pr.add_argument("--head", required=True)
    pr.add_argument("--main", required=True)
    pr.add_argument("--out", type=Path, required=True)
    ac = sub.add_parser("act")
    ac.add_argument("--repo", required=True)
    ac.add_argument("--main", required=True)
    ac.add_argument("--matrix", required=True, help="the list job's JSON output")
    ac.add_argument("--verdict-dir", type=Path, required=True)
    args = ap.parse_args()
    os.environ.setdefault("GIT_TERMINAL_PROMPT", "0")
    if args.command == "list":
        print(json.dumps(candidates(args.repo)[:MAX_PROBES]))
        return 0
    if args.command == "probe":
        try:
            verdict = probe_one(args.number, args.head, args.main)
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
            verdict = {"number": args.number, "head": args.head, "verdict": "unchecked",
                       "why": f"probe failed: {type(exc).__name__}"}
        print(f"#{args.number}: {verdict['verdict']} - {verdict['why']}")
        args.out.write_text(json.dumps(verdict, indent=1), encoding="utf-8")
        return 0
    return act(args.repo, args.main, json.loads(args.matrix), args.verdict_dir)


if __name__ == "__main__":
    raise SystemExit(main())
