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


def ledger_entries(text: str) -> set[str]:
    """Quarantine node ids in a ledger file, ignoring comments and blanks.

    Mirrors `ci_required_tests.parse_quarantine`'s view of a line so this
    decision sees exactly what the gate itself would honour.
    """
    entries: set[str] = set()
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("flaky "):
            line = line[len("flaky ") :].strip()
        if line:
            entries.add(line)
    return entries


def ledger_edit_needs_receipt(base_text: str | None, head_text: str | None) -> bool:
    """Does a `known-failing-tests.txt` edit need an exact-head review receipt?

    Only a provably deletion-only edit is exempt: removing quarantine lines is
    the maintenance the gate itself forces and only tightens the ratchet.
    ADDING an entry is the bypass direction.

    Decided by COMPARING CONTENT, never by trusting diff metadata. GitHub
    reports `additions: 0` for binary files AND for pure renames, so both a
    NUL-poisoned ledger and a pre-planted file renamed into place read as
    "no additions" and sail through a metadata check (Codex review
    2026-08-02, verified against PRs #2041 and #2172). Comparing the parsed
    entry sets is immune to how the change is dressed up.

    Fail closed: unreadable head content requires a receipt, unless base was
    empty too (nothing could have been smuggled in).
    """
    if head_text is None:
        return True
    base_entries = ledger_entries(base_text or "")
    head_entries = ledger_entries(head_text)
    if not head_entries and base_entries:
        # Wiping every entry at once is indistinguishable from a truncated or
        # unreadable fetch — make a human vouch for it either way.
        return True
    return bool(head_entries - base_entries)


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
        "--ledger-base-file",
        type=Path,
        help="Trusted base-checkout copy of known-failing-tests.txt.",
    )
    parser.add_argument(
        "--ledger-head-file",
        type=Path,
        help="Head copy of known-failing-tests.txt. With --ledger-base-file, "
        "asks only whether that edit needs a receipt: prints "
        "exempt/receipt-required and exits 0/2.",
    )
    args = parser.parse_args()

    if args.ledger_head_file is not None:
        def _read(path: Path | None) -> str | None:
            if path is None:
                return None
            try:
                # errors="replace": a NUL-poisoned "binary" ledger must still be
                # parsed and compared, never treated as unreadable.
                return path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                return None

        base_text = _read(args.ledger_base_file) or ""
        if ledger_edit_needs_receipt(base_text, _read(args.ledger_head_file)):
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
