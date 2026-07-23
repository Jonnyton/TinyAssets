#!/usr/bin/env python3
"""Detect commits built from a stale snapshot of the tree.

The failure mode
----------------
A commit is written with a *current* parent pointer but a *stale* tree — the
author's index/checkout was behind ``origin/main`` when the tree was built. Git
records this as a normal commit; nothing in the diff says "revert". But every
file that landed between the stale snapshot and the real parent is silently
reset to its old content.

The 2026-05-04 incident (720 files) and 2026-07-21 ``0bc841aa`` (15 files, 4
merged PRs reverted, one of them a safety guard) are both this class.

The signature
-------------
A healthy commit is *closest to its own parent*: it adds a few files' worth of
change on top of ``P``. A stale-tree commit is closest to some **ancestor** of
``P`` instead, because that ancestor is the snapshot it was really built from.

So for commit ``C`` with parent ``P``::

    n_parent   = |diff(P, C)|
    n_ancestor = |diff(A, C)|   for each ancestor A of P

If any ``n_ancestor < n_parent``, ``C`` was built from ``A``'s snapshot and
reverts everything merged in ``A..P``. That inequality is the whole test — it
needs no heuristic about commit messages, deletion counts, or file types.

Why this is needed when a guard already exists
----------------------------------------------
``scripts/fuse_safe_commit.py`` would have *caught* ``0bc841aa`` had it been
used (verified by cross-family review, 2026-07-22): it ``read-tree``s from the
base ref it is handed, so a fresh ``--base-ref origin/main`` never admits stale
content in the first place, and its post-build scope check counts 15 paths
against ``--max-files 1`` and rejects the 14 undeclared ones.

The gap is not strength, it is **enforceability**: the wrapper is opt-in and
was bypassed. Nothing observes a commit that was made some other way. So the
ratchet has to run on commits that *already exist* — a pre-push hook or CI —
where it cannot be skipped by choosing a different tool.

Usage
-----
    python scripts/check_stale_base_commit.py                 # HEAD vs @{upstream}
    python scripts/check_stale_base_commit.py --range origin/main..HEAD
    python scripts/check_stale_base_commit.py --commit 0bc841aa

Exit codes: 0 clean, 1 usage/git error, 2 stale-base commit found.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys

# How far back to look for a better-matching ancestor. The stale window is
# bounded in practice by how long a session holds an index; 50 covers a busy
# day on this repo with room to spare.
DEFAULT_DEPTH = 50

# A deliberate revert legitimately resembles an ancestor more than its parent --
# that is what a revert *is*. Recognise the forms this repo actually uses:
# git's own `Revert "..."`, its `This reverts commit <sha>` trailer, and the
# conventional-commits `revert:` / `revert(scope):` type (found on 575c7059 in
# the 400-commit calibration sweep).
REVERT_TRAILER = "this reverts commit"
REVERT_RE = re.compile(r"^revert(\([^)]*\))?[:\s\"]", re.IGNORECASE)

# An author may knowingly supersede an approach introduced by a recent commit,
# which legitimately makes the tree resemble the pre-approach ancestor (5e50cc06
# in the same sweep). There is no way to distinguish that from a stale tree by
# shape alone, so it is an explicit opt-out rather than a guess.
OVERRIDE_TRAILER = "stale-base-check: intentional"


def _git(*args: str) -> str:
    proc = subprocess.run(
        ["git", *args], capture_output=True, text=True, encoding="utf-8", errors="replace"
    )
    if proc.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {proc.stderr.strip()}")
    return proc.stdout


def _changed_count(a: str, b: str) -> int:
    """Number of paths differing between two trees."""
    out = _git("diff", "--name-only", "-z", a, b)
    return len([p for p in out.split("\0") if p])


def _is_exempt(sha: str) -> bool:
    """True if the commit declares itself a revert or an intentional supersession."""
    body = _git("log", "-1", "--pretty=%B", sha).strip()
    lowered = body.lower()
    return bool(
        REVERT_RE.match(lowered)
        or REVERT_TRAILER in lowered
        or OVERRIDE_TRAILER in lowered
    )


def check_commit(sha: str, depth: int) -> dict | None:
    """Return a finding dict if `sha` looks built from a stale snapshot."""
    parents = _git("log", "-1", "--pretty=%P", sha).split()
    # Merge commits legitimately differ from each parent by the other side's
    # whole history. The heuristic does not apply.
    if len(parents) != 1:
        return None
    parent = parents[0]

    n_parent = _changed_count(parent, sha)
    if n_parent == 0:
        return None

    ancestors = _git(
        "log", "--first-parent", f"--max-count={depth}", "--pretty=%H", parent
    ).split()

    # Walking back from the parent, the difference count falls until it reaches
    # the snapshot the tree was really built from, then rises again as older
    # ancestors diverge. Track the minimum and stop once it has been rising for
    # RISE_PATIENCE steps — checking all `depth` ancestors on every commit costs
    # a git diff each and makes the whole check unusably slow on real history.
    RISE_PATIENCE = 3
    best = None
    rising = 0
    lowest = n_parent
    for anc in ancestors[1:]:  # ancestors[0] is `parent` itself
        n_anc = _changed_count(anc, sha)
        if n_anc < n_parent and (best is None or n_anc < best[1]):
            best = (anc, n_anc)
        if n_anc < lowest:
            lowest = n_anc
            rising = 0
        else:
            rising += 1
            if rising >= RISE_PATIENCE:
                break

    if best is None:
        return None
    if _is_exempt(sha):
        return None

    stale_base, n_base = best
    reverted = _git(
        "log", "--oneline", "--first-parent", f"{stale_base}..{parent}"
    ).strip().splitlines()

    return {
        "sha": sha,
        "subject": _git("log", "-1", "--pretty=%s", sha).strip(),
        "author": _git("log", "-1", "--pretty=%an", sha).strip(),
        "parent": parent,
        "n_parent": n_parent,
        "stale_base": stale_base,
        "n_base": n_base,
        "reverted": reverted,
    }


def _report(f: dict) -> None:
    print(f"\n  STALE-BASE COMMIT: {f['sha'][:8]}  {f['subject']}")
    print(f"    author            {f['author']}")
    print(f"    parent            {f['parent'][:8]}  -> {f['n_parent']} files differ")
    print(f"    real (stale) base {f['stale_base'][:8]}  -> {f['n_base']} files differ")
    print(
        f"    The tree is closer to {f['stale_base'][:8]} than to its own parent, so it "
        f"was built from that\n    snapshot and silently reverts the "
        f"{len(f['reverted'])} commit(s) merged in between:"
    )
    for line in f["reverted"]:
        print(f"      - {line}")
    print(
        "\n    Fix: rebuild the change on top of the real parent "
        "(fetch first, then re-apply your\n    edit) rather than pushing this tree. "
        "See CLAUDE.md 'FUSE git plumbing rule' and\n    scripts/fuse_safe_commit.py."
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--range", dest="rev_range", help="e.g. origin/main..HEAD")
    ap.add_argument("--commit", help="check a single commit")
    ap.add_argument("--depth", type=int, default=DEFAULT_DEPTH)
    args = ap.parse_args()

    try:
        if args.commit:
            shas = [_git("rev-parse", args.commit).strip()]
        else:
            rev_range = args.rev_range
            if not rev_range:
                upstream = _git(
                    "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}"
                ).strip()
                rev_range = f"{upstream}..HEAD"
            shas = _git("rev-list", rev_range).split()
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if not shas:
        print("check_stale_base_commit: no commits to check")
        return 0

    findings = []
    for sha in shas:
        try:
            found = check_commit(sha, args.depth)
        except RuntimeError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        if found:
            findings.append(found)

    if not findings:
        print(f"check_stale_base_commit: {len(shas)} commit(s) checked, none stale-based")
        return 0

    print(f"check_stale_base_commit: {len(findings)} stale-based commit(s) found")
    for f in findings:
        _report(f)
    return 2


if __name__ == "__main__":
    sys.exit(main())
