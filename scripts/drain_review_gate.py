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
        # `split("#", 1)[0]` exactly as parse_quarantine does — it strips
        # TRAILING comments too, so `X  # note` and `X` are one entry there and
        # must be one entry here. Any divergence between the two parsers is a
        # seam where an entry counts as "not new" for the exemption while the
        # gate honours it as quarantine.
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        # The `flaky ` label is kept as PART of the token, deliberately: moving
        # an entry plain -> flaky exempts it from stale detection, which weakens
        # the ratchet, so a human vouches for that too.
        entries.add(line)
    return entries


_REGULAR_BLOB_MODES = frozenset({"100644", "100755"})


def ledger_fetch_is_trustworthy(mode: str, expected_size: str, actual_bytes: int) -> bool:
    """Is the fetched head ledger the real, complete, regular file?

    Three ways the fetch lies, all found in cross-family review:

    * **symlink / submodule** — the Contents API dereferences a symlink, so
      swapping the ledger for a link to identical content looks like a no-op
      edit. A later PR then edits the *link target*, whose path is not
      gate-protected, and adds effective quarantine entries with no receipt.
      Only a regular blob (`100644`/`100755`) is accepted; `120000` (symlink)
      and `160000` (submodule) are refused.
    * **truncation** — GitHub returns empty content for some blobs over 1 MB.
      A partial decode is a SUBSET of base, which reads as a deletion.
    * **failed fetch** — 404/oversize yields nothing, which against an empty
      base also reads as a deletion.

    Comparing the decoded byte count against the tree's own `size` catches the
    last two; anything unparseable is refused.
    """
    if mode not in _REGULAR_BLOB_MODES:
        return False
    size = expected_size.strip()
    if not size.isdigit():
        return False
    return int(size) == actual_bytes


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
    parser.add_argument(
        "--ledger-head-mode",
        default="",
        help="Git tree mode of the head ledger blob. Only a regular blob is "
        "trusted; a symlink or submodule is refused.",
    )
    parser.add_argument(
        "--ledger-head-size",
        default="",
        help="Git tree size of the head ledger blob, compared against the "
        "bytes actually fetched to catch truncation and failed fetches.",
    )
    args = parser.parse_args()

    if args.ledger_head_file is not None:
        def _read_bytes(path: Path | None) -> bytes | None:
            if path is None:
                return None
            try:
                return path.read_bytes()
            except OSError:
                return None

        head_bytes = _read_bytes(args.ledger_head_file)
        if head_bytes is None or not ledger_fetch_is_trustworthy(
            args.ledger_head_mode, args.ledger_head_size, len(head_bytes)
        ):
            print("receipt-required")
            return 2

        base_bytes = _read_bytes(args.ledger_base_file) or b""
        # errors="replace": a NUL-poisoned "binary" ledger must still be parsed
        # and compared, never treated as unreadable.
        if ledger_edit_needs_receipt(
            base_bytes.decode("utf-8", errors="replace"),
            head_bytes.decode("utf-8", errors="replace"),
        ):
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
