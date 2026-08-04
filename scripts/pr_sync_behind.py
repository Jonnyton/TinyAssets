"""Re-sync your open PRs that branch protection has left BEHIND.

Why this exists
---------------
``main`` is protected with ``strict: true`` — a PR must be up to date with the
base before it can merge. With several providers landing PRs concurrently, an
open PR goes ``BEHIND`` faster than its checks finish, and **GitHub's
auto-merge does not update the branch for you**. The PR then sits at
``mergeStateStatus: BEHIND`` indefinitely while its author assumes auto-merge
is handling it. Observed 2026-08-04: two PRs each needed two manual re-syncs.

The obvious fix — a scheduled workflow calling the ``update-branch`` API — is
a trap in THIS repo, and the reason is narrower than "GITHUB_TOKEN suppresses
everything" (that formulation is wrong; corrected by cross-family review
2026-08-04). What GitHub actually does with a default-``GITHUB_TOKEN``-caused
event:

* ``pull_request`` ``opened`` / ``synchronize`` / ``reopened`` **do** create
  runs — but they land in an **approval-required** state.
* ``push``, ``pull_request_target``, and other ``pull_request`` activity types
  create **no** run at all.

So an updater using the default token wedges the PR in two different ways at
once. ``required-tests`` (``tests.yml``, ``pull_request: synchronize``) would
sit waiting for a human to approve it, and ``Diff scope declared``
(``pull_request_target``) would never run at all — and required checks must
pass for the LATEST sha, so the earlier results cannot carry over. Net: up to
date, still blocked, now needing two manual interventions instead of one.

Fixing it *in CI* needs a credential that is not the default token — a
dedicated GitHub App installation token (best fit) or a fine-grained PAT. A
merge queue is the better long-term model but is not available here: merge
queues need an organization-owned repository and this one is personal-account
owned. All of those are repo-owner decisions.

So this is a local helper, not CI. It runs under YOUR ``gh`` credentials, so
the push is attributed to a real user and the PR's checks re-run normally.

That last part is **verified, not assumed** (2026-08-04, PR #2263): after an
``--update`` run the head moved ``adefd32b -> 841e8f36`` and
``gh run list`` showed ``Tests event=pull_request`` queued against the new
sha. A user-token update-branch triggers the checks; that is precisely what
the ``GITHUB_TOKEN`` variant could not be relied on to do.

Usage::

    python scripts/pr_sync_behind.py                 # report only (default)
    python scripts/pr_sync_behind.py --update        # actually update them
    python scripts/pr_sync_behind.py --update --mine # only PRs you authored

After ``--update`` touches a PR you have checked out locally, your local
branch is **behind its own remote** — the update-branch merge lands on the
remote only. Your next ``git push`` will be rejected until you
``git fetch && git merge origin/<branch>``. Hit on the first real use of this
script, on its own PR.

``--mine`` filters by ``--author @me``, which does NOT isolate your lane in
this repo: every provider session authenticates as the same GitHub account,
so ``@me`` matches the whole fleet's PRs. Read the report before running
``--update`` — you can and will update other lanes' branches. That is benign
(the merge from ``main`` is what they need to land anyway, and it is
non-destructive), but it should be a choice rather than a surprise.

Advisory by default and never touches your working tree: the update is done
through the GitHub API on the PR branch, not by checking anything out, so it
cannot disturb a dirty worktree (hard rule 13).
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys

# Only BEHIND. Deliberately NOT `UNKNOWN`: GitHub reports UNKNOWN while it is
# still computing mergeability, so acting on it would fire update-branch at
# PRs that may not need it and burn a CI cycle each. UNKNOWN resolves on its
# own within seconds — re-run instead. Also not BLOCKED/DIRTY: those need a
# failing check fixed or a conflict resolved, and a re-sync changes neither.
_SYNCABLE = {"BEHIND"}


def _force_utf8_stdio() -> None:
    """Print UTF-8 regardless of the Windows console codepage.

    Same helper as `session_sync_gate.py`. Without it a PR title containing an
    em dash renders as mojibake on cp1252 — which this repo's pre-commit
    explicitly scans files for, so emitting it to the console is the same
    class of defect. Observed in this script's own first live run.
    """
    for name in ("stdout", "stderr"):
        stream = getattr(sys, name)
        enc = (getattr(stream, "encoding", None) or "").lower().replace("_", "-")
        if enc == "utf-8":
            continue
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
            except (AttributeError, ValueError, OSError):
                pass


def _gh(*args: str) -> str:
    proc = subprocess.run(
        ["gh", *args],
        capture_output=True,
        # bytes + explicit decode: `text=True` decodes with the Windows locale
        # (cp1252), which mangles any non-ASCII in a PR title.
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"gh {' '.join(args)} failed ({proc.returncode}): "
            f"{proc.stderr.decode('utf-8', 'replace').strip()}"
        )
    return proc.stdout.decode("utf-8", "replace")


def _open_prs(mine: bool) -> list[dict]:
    args = [
        "pr", "list", "--state", "open", "--limit", "100",
        "--json", "number,title,mergeStateStatus,autoMergeRequest,isDraft,author,headRefName",
    ]
    if mine:
        args += ["--author", "@me"]
    return json.loads(_gh(*args))


def _update(number: int) -> tuple[bool, str]:
    """Ask GitHub to merge the base into the PR branch.

    Returns (ok, detail). A 422 here is normal and means a real conflict the
    author has to resolve by hand — reported, never retried.
    """
    try:
        _gh("api", "--method", "PUT",
            f"repos/{{owner}}/{{repo}}/pulls/{number}/update-branch",
            "-H", "Accept: application/vnd.github+json")
        return True, "updated"
    except RuntimeError as exc:
        detail = str(exc)
        if "422" in detail:
            return False, "conflict — resolve by hand"
        return False, detail.splitlines()[0][:120]


def main() -> int:
    _force_utf8_stdio()
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--update", action="store_true",
                    help="actually update; default is report-only")
    ap.add_argument("--mine", action="store_true",
                    help="only PRs you authored")
    ap.add_argument("--limit", type=int, default=10,
                    help="max PRs to update in one run (default 10). A cap "
                         "exists so a mass event cannot flood CI.")
    args = ap.parse_args()

    try:
        prs = _open_prs(args.mine)
    except RuntimeError as exc:
        print(f"[pr-sync] {exc}", file=sys.stderr)
        return 1

    behind = [
        p for p in prs
        if p.get("mergeStateStatus") in _SYNCABLE and not p.get("isDraft")
    ]
    if not behind:
        print(f"[pr-sync] no open PRs are BEHIND ({len(prs)} open)")
        return 0

    print(f"[pr-sync] {len(behind)} of {len(prs)} open PRs are BEHIND:")
    for p in behind:
        auto = "auto-merge" if p.get("autoMergeRequest") else "no auto-merge"
        print(f"  #{p['number']:<6} {auto:<13} {p['title'][:70]}")

    if not args.update:
        print("\n[pr-sync] report only. Re-run with --update to sync them.")
        return 0

    todo = behind[: args.limit]
    if len(behind) > args.limit:
        # Never truncate silently — a capped run that looks complete is how a
        # backlog hides.
        print(f"\n[pr-sync] capped at {args.limit}; "
              f"{len(behind) - args.limit} left for the next run")

    print()
    failures = 0
    for p in todo:
        ok, detail = _update(p["number"])
        print(f"  #{p['number']:<6} {'OK ' if ok else 'FAIL'} {detail}")
        failures += 0 if ok else 1

    # Non-zero when something could not be synced, so a caller can notice.
    return 1 if failures else 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
