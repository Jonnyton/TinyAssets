#!/usr/bin/env python3
"""Decide whether a pull request may use trusted auto-merge enrollment.

Two callers, one receipt format:

* `auto-enroll-merge.yml` asks whether a drain PR may be enrolled at all;
* `pr-scope-guard.yml` — a REQUIRED check — asks, via `--blocking-review`,
  whether a release-critical / authority / `infra-change` / Tier 2 PR carries
  the exact-head `Drain-Review-Verdict: APPROVE` receipt it now needs. That is
  what makes a blocking review verdict enforceable: before 2026-09-26 the
  verdict was a PR comment, and PR #3989 auto-merged at the exact head its
  reviewer had BLOCKED.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Iterable
from pathlib import Path

_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_ARTIFACT_RE = re.compile(
    r"Drain-Review-Artifact: "
    r"(docs/[A-Za-z0-9_./-]+\.md|https://github\.com/\S+)"
)

# A comment ON THIS PR, by URL. The three anchors are the three places a review
# verdict can live on a pull request: a top-level issue comment, a submitted
# review, and an inline review comment. Anything else — a docs path, a link to
# another PR, another repository, a bare commit URL — is not the durable,
# timestamped artifact this receipt is supposed to point at.
_COMMENT_ARTIFACT_RE = re.compile(
    r"Drain-Review-Artifact: (?P<url>https://github\.com/"
    r"(?P<repo>[A-Za-z0-9._-]+/[A-Za-z0-9._-]+)/pull/(?P<pr>[1-9][0-9]*)"
    r"#(?:issuecomment-[0-9]+|pullrequestreview-[0-9]+|discussion_r[0-9]+))"
)

_INFRA_LABEL = "infra-change"

# `Tier 2` anywhere in the title, however spaced or hyphenated. `(?![0-9])`
# keeps a hypothetical `Tier 20` out; the leading class stops `subtier2`.
_TIER2_TITLE_RE = re.compile(r"(?:^|[^0-9A-Za-z])tier[ _-]?2(?![0-9])", re.IGNORECASE)

# `author_association` as GitHub computes it at read time — trusted metadata,
# not something a comment body can claim. CONTRIBUTOR and NONE are excluded:
# anyone can comment on a public repo's PR, and the receipt must not be
# satisfiable by a drive-by comment.
_TRUSTED_ASSOCIATIONS = frozenset({"OWNER", "MEMBER", "COLLABORATOR"})


def review_allows_merge(
    *,
    branch: str,
    head: str,
    body: str,
    force: bool = False,
    artifact_must_be_comment_on: tuple[str, int] | None = None,
    trusted_comment_urls: frozenset[str] | None = None,
) -> bool:
    """Allow ordinary PRs; drain PRs — and force-flagged calls — need a receipt.

    `force=True` is used by the scope guard for PRs that need a blocking
    review verdict before they may merge: release-critical or authority paths,
    the `infra-change` declaration, or a Tier 2 title. Those can neuter the
    checks that judge them or escalate a privilege, so a label (declaration)
    is not authorization — an exact-head review receipt is required regardless
    of branch name.

    With `artifact_must_be_comment_on=(repo, pr)` the receipt's artifact must
    additionally name a comment on THAT pull request, present in
    `trusted_comment_urls`. A missing inventory (the API read failed) denies:
    a receipt we cannot corroborate is not a receipt.
    """
    if not force and not branch.startswith("drain/"):
        return True
    if not _SHA_RE.fullmatch(head):
        return False

    lines = body.splitlines()
    verdicts = [line for line in lines if line.startswith("Drain-Review-Verdict:")]
    reviewed_heads = [line for line in lines if line.startswith("Drain-Review-Head:")]
    artifacts = [line for line in lines if line.startswith("Drain-Review-Artifact:")]
    if not (
        verdicts == ["Drain-Review-Verdict: APPROVE"]
        and reviewed_heads == [f"Drain-Review-Head: {head}"]
        and len(artifacts) == 1
        and _ARTIFACT_RE.fullmatch(artifacts[0]) is not None
    ):
        return False
    if artifact_must_be_comment_on is None:
        return True
    repo, pr = artifact_must_be_comment_on
    return artifact_names_trusted_comment(
        artifacts[0], repo=repo, pr=pr, trusted_comment_urls=trusted_comment_urls
    )


def artifact_names_trusted_comment(
    artifact_line: str,
    *,
    repo: str,
    pr: int,
    trusted_comment_urls: frozenset[str] | None,
) -> bool:
    """Does this artifact line name a trusted comment on THIS pull request?

    Three independent conditions, all required:

    * the URL is shaped like a comment anchor on `repo`'s PR `pr` — not a docs
      path, not another PR, not another repository;
    * that exact URL is in the inventory read from the API, so the comment
      actually EXISTS (a receipt can otherwise cite an invented comment id);
    * the inventory only ever contains comments whose `author_association` is
      trusted, so a drive-by commenter cannot supply the artifact.

    Fails closed when the inventory is unavailable.
    """
    if trusted_comment_urls is None:
        return False
    match = _COMMENT_ARTIFACT_RE.fullmatch(artifact_line)
    if match is None:
        return False
    # GitHub resolves owner/repo case-insensitively, so a stamper who types a
    # different casing must not be refused; the PR number is compared as the
    # canonical decimal string the regex already constrained.
    if match["repo"].lower() != repo.lower() or match["pr"] != str(pr):
        return False
    return match["url"].lower() in trusted_comment_urls


def parse_trusted_comments(stream: str) -> frozenset[str] | None:
    """URLs of trusted-author comments, from a stream of JSON objects.

    The workflow reads the PR's issue comments, reviews and review comments and
    appends each object to one file (`gh api --jq '.[] | {...}'` emits one
    compact object per line). Filtering happens HERE, not in a jq expression,
    so the trust list is unit tested rather than buried in a shell string.

    Returns `None` on anything unparseable — a partially understood inventory
    must deny, never silently shrink to a set that a receipt cannot match and
    also never grow past what was actually read.
    """
    decoder = json.JSONDecoder()
    urls: set[str] = set()
    index = 0
    length = len(stream)
    while index < length:
        while index < length and stream[index].isspace():
            index += 1
        if index >= length:
            break
        try:
            obj, end = decoder.raw_decode(stream, index)
        except ValueError:
            return None
        index = end
        if not isinstance(obj, dict):
            return None
        url = obj.get("url")
        association = obj.get("association")
        if not isinstance(url, str) or not isinstance(association, str):
            return None
        if association in _TRUSTED_ASSOCIATIONS:
            urls.add(url.lower())
    return frozenset(urls)


def blocking_review_reason(
    *,
    labels: str,
    title: str,
    hits: Iterable[str],
    footprint_exempt: bool = False,
) -> str | None:
    """Why this PR needs a blocking-review receipt, or `None` if it does not.

    PR #3989 auto-merged at the exact head its Tier 2 reviewer had BLOCKED: a
    verdict posted as a comment is advisory, and only a failing REQUIRED check
    holds a PR. These three triggers are what that PR would have matched.

    `footprint_exempt` says the gate PROVED the PR's entire release-critical /
    authority footprint cannot change behaviour — a deletion-only quarantine
    ledger edit, or an authority file whose AST is unchanged. A content proof
    outranks the `infra-change` label, which is only a declaration ABOUT those
    paths. It does NOT outrank a Tier 2 title: that is the author declaring the
    change as a whole needs a blocking review, which no path proof can answer.
    """
    if _TIER2_TITLE_RE.search(title):
        return "the title declares Tier 2"
    if footprint_exempt:
        return None
    listed = sorted({hit.strip() for hit in hits if hit.strip()})
    if listed:
        return "it touches release-critical or authority paths: " + ", ".join(listed)
    if _INFRA_LABEL in {label.strip() for label in labels.split(",")}:
        return f"it carries the `{_INFRA_LABEL}` label"
    return None


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


def _read_text(path: Path | None) -> str | None:
    if path is None:
        return None
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def _blocking_review(args: argparse.Namespace) -> int:
    """`--blocking-review`: is a receipt due, and does the body carry one?"""
    hits_text = _read_text(args.review_hits_file)
    if hits_text is None:
        # The gate could not see its own path list. Refuse rather than read an
        # unreadable file as "no release-critical paths touched".
        print("deny")
        print("the release-critical/authority path list could not be read", file=sys.stderr)
        return 2

    reason = blocking_review_reason(
        labels=args.review_labels,
        title=args.review_title,
        hits=hits_text.splitlines(),
        footprint_exempt=args.review_footprint_exempt,
    )
    if reason is None:
        print("receipt-not-required")
        return 0
    print(f"a blocking-review receipt is required because {reason}", file=sys.stderr)

    body = _read_text(args.body_file)
    comments = _read_text(args.review_comments_file)
    trusted = None if comments is None else parse_trusted_comments(comments)
    if body is not None and review_allows_merge(
        branch=args.branch,
        head=args.head,
        body=body,
        force=True,
        artifact_must_be_comment_on=(args.review_repo, args.review_pr),
        trusted_comment_urls=trusted,
    ):
        print("allow")
        return 0
    print("deny")
    return 2


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
    parser.add_argument(
        "--blocking-review",
        action="store_true",
        help="Decide the blocking-review receipt requirement for a PR: prints "
        "receipt-not-required / allow (exit 0) or deny (exit 2), with the "
        "reason on stderr. Requires --review-*.",
    )
    parser.add_argument("--review-title", default="", help="PR title, for the Tier 2 declaration.")
    parser.add_argument(
        "--review-labels", default="", help="Comma-joined PR label names."
    )
    parser.add_argument(
        "--review-hits-file",
        type=Path,
        help="One release-critical or authority path per line, after exemptions.",
    )
    parser.add_argument(
        "--review-footprint-exempt",
        action="store_true",
        help="The gate PROVED the whole release-critical/authority footprint is "
        "behaviourally inert (deletion-only ledger edit, AST-identical "
        "authority file).",
    )
    parser.add_argument("--review-repo", default="", help="owner/repo of this PR.")
    parser.add_argument("--review-pr", type=int, help="This PR's number.")
    parser.add_argument(
        "--review-comments-file",
        type=Path,
        help="JSON objects ({url, association}) for this PR's comments, "
        "reviews and review comments. Unreadable => deny when a receipt is due.",
    )
    args = parser.parse_args()

    if args.blocking_review:
        if args.review_hits_file is None or args.review_pr is None or not args.review_repo:
            parser.error("--blocking-review needs --review-hits-file, --review-pr, --review-repo")
        return _blocking_review(args)

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
