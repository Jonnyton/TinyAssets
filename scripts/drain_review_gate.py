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


def review_allows_merge(*, branch: str, head: str, body: str) -> bool:
    """Allow ordinary PRs, or drain PRs with one current approval receipt."""
    if not branch.startswith("drain/"):
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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--branch", required=True)
    parser.add_argument("--head", required=True)
    parser.add_argument("--body-file", type=Path, required=True)
    args = parser.parse_args()

    try:
        body = args.body_file.read_text(encoding="utf-8")
    except OSError:
        print("deny")
        return 2

    if review_allows_merge(branch=args.branch, head=args.head, body=body):
        print("allow")
        return 0
    print("deny")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
