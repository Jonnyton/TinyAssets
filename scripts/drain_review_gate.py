#!/usr/bin/env python3
"""Decide whether a pull request may use trusted auto-merge enrollment."""

from __future__ import annotations

import argparse
import re
from pathlib import Path

_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_ARTIFACT_RE = re.compile(
    r"Drain-Review-Artifact: "
    r"(docs/[A-Za-z0-9_./-]+\.md|https://github\.com/\S+)"
)


def review_allows_merge(*, branch: str, head: str, body: str, force: bool = False) -> bool:
    """Allow ordinary PRs; drain PRs — and force-flagged calls — need a receipt.

    `force=True` is used by the scope guard for PRs that edit the files
    DEFINING the required-tests gate: those can neuter the check from the
    PR's own checkout, so a label (declaration) is not authorization — an
    exact-head review receipt is required regardless of branch name.
    """
    if not force and not branch.startswith("drain/"):
        return True
    if not _SHA_RE.fullmatch(head):
        return False

    lines = body.splitlines()
    verdicts = [line for line in lines if line.startswith("Drain-Review-Verdict:")]
    reviewed_heads = [line for line in lines if line.startswith("Drain-Review-Head:")]
    artifacts = [line for line in lines if line.startswith("Drain-Review-Artifact:")]
    return (
        verdicts == ["Drain-Review-Verdict: APPROVE"]
        and reviewed_heads == [f"Drain-Review-Head: {head}"]
        and len(artifacts) == 1
        and _ARTIFACT_RE.fullmatch(artifacts[0]) is not None
    )


def ledger_edit_needs_receipt(additions: str) -> bool:
    """Does a `known-failing-tests.txt` edit need an exact-head review receipt?

    Only a provably deletion-only edit is exempt: removing quarantine lines is
    the maintenance the gate itself forces and only tightens the ratchet.
    ADDING a line is the bypass direction.

    Decided on the API's `additions` COUNT, never on the diff text: GitHub
    omits `patch` for binary files and drops it on large diffs, so a
    patch-grep reads "no additions" and fails OPEN (Codex review 2026-08-02).
    Anything that is not a clean numeric zero keeps the requirement.
    """
    return additions.strip() != "0"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--branch", required=True)
    parser.add_argument("--head", required=True)
    parser.add_argument("--body-file", type=Path, required=True)
    parser.add_argument(
        "--require-receipt",
        action="store_true",
        help="Demand the exact-head review receipt regardless of branch name "
        "(used for PRs touching gate-defining files).",
    )
    parser.add_argument(
        "--ledger-additions",
        metavar="COUNT",
        help="Ask only whether a known-failing-tests.txt edit with this many "
        "added lines needs a receipt. Prints exempt/receipt-required and "
        "exits 0/2. Ignores every other argument's policy.",
    )
    args = parser.parse_args()

    if args.ledger_additions is not None:
        if ledger_edit_needs_receipt(args.ledger_additions):
            print("receipt-required")
            return 2
        print("exempt")
        return 0

    try:
        body = args.body_file.read_text(encoding="utf-8")
    except OSError:
        print("deny")
        return 2

    if review_allows_merge(
        branch=args.branch, head=args.head, body=body, force=args.require_receipt
    ):
        print("allow")
        return 0
    print("deny")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
