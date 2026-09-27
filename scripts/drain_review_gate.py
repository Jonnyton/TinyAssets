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
import hashlib
import json
import re
import subprocess
import sys
from collections.abc import Iterable
from pathlib import Path

_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_DIFF_KEY_RE = re.compile(r"^[0-9a-f]{64}$")
# One `git diff --raw` record header with FULL object ids (SHA-1 or SHA-256).
_RAW_META_RE = re.compile(
    rb":[0-7]{6} [0-7]{6} ([0-9a-f]{40}|[0-9a-f]{64}) ([0-9a-f]{40}|[0-9a-f]{64}) [A-Z][0-9]*"
)
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
    diff_key: str | None = None,
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

    lines = leading_lines(body, 3)
    if not (_attests_approval(lines, head, diff_key) and len(lines) == 3):
        return False
    artifact = lines[2]
    if _ARTIFACT_RE.fullmatch(artifact) is None:
        return False
    if artifact_must_be_comment_on is None:
        return True
    repo, pr = artifact_must_be_comment_on
    return artifact_names_trusted_comment(
        artifact, repo=repo, pr=pr, trusted_comment_urls=trusted_comment_urls
    )


def leading_lines(text: str, count: int) -> list[str]:
    """The first `count` non-blank lines, trailing whitespace removed.

    **A receipt is only read at the TOP of the text**, and that is the whole
    anti-hiding rule. Nothing can precede the first line of a document, so no
    construct can be open when it is read: an HTML comment, a fence, a
    `<details>`, a blockquote or a list all have to START somewhere, and if one
    does, the first non-blank line is its opener and not the verdict.

    This replaced a markdown scanner, and the reason is worth keeping. Three
    cross-family review rounds each found defects in that scanner, in BOTH
    directions -- approvals hidden in a nested `<details>`, in an HTML comment, in
    a lazily-continued blockquote, in a list-nested quote; and honest receipts
    wrongly refused after a heading, after a fence marker inside an HTML block,
    after a literal `<!--` in a code example. Each fix created the next round's
    findings, which `AGENTS.md` names as a loop rather than progress, and says to
    answer with a redesign: recurring findings in one area mean the shape is
    wrong. Modelling GitHub's renderer was the wrong shape. A position that
    cannot have anything in front of it needs no renderer.

    Trailing whitespace is stripped because an editor adding a space must not
    void a receipt, and trailing whitespace can hide nothing. Leading blank
    lines are skipped for the same reason.
    """
    lines: list[str] = []
    for raw in text.splitlines():
        line = raw.rstrip()
        if not line:
            continue
        lines.append(line)
        if len(lines) == count:
            break
    return lines


def _attests_approval(lines: list[str], head: str, diff_key: str | None = None) -> bool:
    """Do these leading lines OPEN with an approval of `head`, or of its diff?

    ONE definition of what an approval looks like, used for the PR body and for
    the cited comment alike. Exact string equality on the first two non-blank
    lines, in order, so `BLOCK`, a lower-case verdict, trailing prose, or a head
    line for any other commit all refuse.

    The second line binds the approval to what was reviewed, in one of two ways:

    * `Drain-Review-Head: <sha>` — this exact commit. Any push voids it.
    * `Drain-Review-Diff: <key>` — this exact CHANGE, as `diff_key` computes it
      for the current head. Merging main in or rebasing leaves the key alone
      unless the PR's own change moves with it, so it survives the catch-ups
      that voided receipts on 2026-09-26 without accepting any content the
      reviewer did not see. Only honoured when the caller computed a key.
    """
    bindings = [f"Drain-Review-Head: {head}"]
    if diff_key is not None and _DIFF_KEY_RE.fullmatch(diff_key):
        bindings.append(f"Drain-Review-Diff: {diff_key}")
    return len(lines) >= 2 and lines[0] == "Drain-Review-Verdict: APPROVE" and lines[1] in bindings


def comment_attests_approval(comment_body: str, head: str, diff_key: str | None = None) -> bool:
    """Does this comment OPEN by publishing an approval of `head`?

    Comment identity was not enough. Cross-family review 2026-09-26, finding 6:
    the gate accepted any trusted-author comment as the artifact, so a body
    receipt citing an OWNER comment that said `VERDICT: BLOCK` for this exact
    head passed. Checking the comment's own attestation is what makes the
    artifact evidence rather than a bookmark — and it closes the stale-comment
    gap too (finding 7), because the comment must name the CURRENT head, which
    needs no clock.
    """
    return _attests_approval(leading_lines(comment_body, 2), head, diff_key)


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


def published_approval_urls(
    stream: str, *, head: str, diff_key: str | None = None
) -> frozenset[str] | None:
    """URLs of comments that PUBLISH a trusted approval of `head`.

    The workflow reads the PR's issue comments, reviews and review comments and
    appends each object to one file (`gh api --jq '.[] | {...}'` emits one
    compact object per line, with the body's newlines JSON-escaped). Both
    filters happen HERE, not in a jq expression, so they are unit tested rather
    than buried in a shell string:

    * `author_association` must be trusted — GitHub computes it at read time, so
      it is not something a comment body can claim about itself;
    * the comment must itself attest `APPROVE` at this exact head. A trusted
      author's comment saying `VERDICT: BLOCK` is not an approval, and before
      this filter existed the gate accepted one as the artifact.

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
        body = obj.get("body")
        if not isinstance(url, str) or not isinstance(association, str):
            return None
        if not isinstance(body, str):
            # The projection uses `(.body // "")`, so an absent body means the
            # inventory is not the shape this gate reads. Refuse it.
            return None
        if association in _TRUSTED_ASSOCIATIONS and comment_attests_approval(
            body, head, diff_key
        ):
            urls.add(url.lower())
    return frozenset(urls)


def diff_key(base: str, head: str, *, cwd: Path | None = None) -> str:
    """The identity of the CHANGE a PR makes, independent of its commit history.

    sha256 over every path in `git diff merge-base(base, head)..head`, each
    with both modes and both FULL blob ids (`--raw --no-abbrev`, no rename
    detection). Blob ids are content hashes, so this pins exactly which bytes
    the PR replaces and with what, including binary files, and nothing else:

    * merge main in, or rebase, where main did not touch the PR's files: the
      merge base moves, but every path's before/after blob is unchanged -> SAME
      key;
    * any edit to the PR's own change, or a catch-up where main DID touch a
      file the PR changes (the "before" blob or the merged "after" blob moves)
      -> DIFFERENT key, so the reviewer re-reviews exactly when the reviewed
      change is no longer the change being merged.

    Deliberately not `git patch-id`: it hashes only textual hunk lines, so two
    different binary changes to the same path would share an id.

    Raises on any git failure; callers must treat that as "no key" (deny).
    """
    def git(*args: str) -> bytes:
        return subprocess.run(
            ["git", *args], cwd=cwd, capture_output=True, check=True
        ).stdout

    merge_base = git("merge-base", base, head).strip().decode("ascii")
    # `--no-abbrev` is what makes the ids full: `--full-index` alone still
    # prints abbreviated ids in --raw output, and two different blobs can share
    # an abbreviation (cross-family review 2026-09-27 built such a pair).
    raw = git(
        "diff", "--raw", "--no-renames", "--full-index", "--no-abbrev", "-z", merge_base, head
    )
    return diff_key_from_raw(raw)


def diff_key_from_raw(raw: bytes) -> str:
    """Hash `git diff --raw -z --no-abbrev` output; refuse anything else."""
    fields = raw.split(b"\0")
    if fields and fields[-1] == b"":
        fields.pop()
    if len(fields) % 2:
        raise ValueError("unexpected `git diff --raw -z` output")
    pairs = sorted(zip(fields[1::2], fields[0::2]))
    digest = hashlib.sha256()
    for path, meta in pairs:
        if _RAW_META_RE.fullmatch(meta) is None:
            raise ValueError(f"unexpected `git diff --raw` record: {meta!r}")
        # Length-prefixed, never delimiter-joined: a path may contain a tab or
        # a newline, and joining would let one path spell two entries.
        for part in (path, meta):
            digest.update(len(part).to_bytes(8, "big"))
            digest.update(part)
    return digest.hexdigest()


def blocking_review_reason(
    *,
    hits: Iterable[str],
    footprint_exempt: bool = False,
) -> str | None:
    """Why this PR needs a blocking-review receipt, or `None` if it does not.

    Gate-defining and authority paths only — **exactly the set that already
    needed one**. A Tier 2 title and the `infra-change` label were built as
    additional triggers and then CUT: measured against the 60 most recently
    merged PRs they would have made 29 of them wait for a stamp, and the founder's
    direction is that the process is already bloated. PR #3989's fix does not need
    a wider net; it needs a receipt that cannot be satisfied by a refusal, which
    is `comment_attests_approval`.

    `footprint_exempt` says the gate PROVED the whole footprint cannot change
    behaviour — a deletion-only quarantine ledger edit, or an authority file whose
    AST is unchanged.
    """
    if footprint_exempt:
        return None
    listed = sorted({hit.strip() for hit in hits if hit.strip()})
    if listed:
        return "it edits gate-defining or authority-critical files: " + ", ".join(listed)
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
        hits=hits_text.splitlines(),
        footprint_exempt=args.review_footprint_exempt,
    )
    if reason is None:
        print("receipt-not-required")
        return 0
    print(f"a blocking-review receipt is required because {reason}", file=sys.stderr)

    body = _read_text(args.body_file)
    comments = _read_text(args.review_comments_file)
    key = args.diff_key or None
    trusted = (
        None
        if comments is None
        else published_approval_urls(comments, head=args.head, diff_key=key)
    )
    if body is not None and review_allows_merge(
        branch=args.branch,
        head=args.head,
        body=body,
        force=True,
        artifact_must_be_comment_on=(args.review_repo, args.review_pr),
        trusted_comment_urls=trusted,
        diff_key=key,
    ):
        print("allow")
        return 0
    print("deny")
    return 2


def _print_diff_key(argv: list[str]) -> int:
    """`--print-diff-key BASE HEAD`: the value a reviewer stamps as Drain-Review-Diff."""
    parser = argparse.ArgumentParser(prog="drain_review_gate.py --print-diff-key")
    parser.add_argument("base", help="the PR's base, e.g. origin/main")
    parser.add_argument("head", nargs="?", default="HEAD")
    args = parser.parse_args(argv)
    try:
        print(diff_key(args.base, args.head))
    except (subprocess.CalledProcessError, ValueError) as exc:
        print(f"could not compute the diff key: {exc}", file=sys.stderr)
        return 2
    return 0


def main() -> int:
    if sys.argv[1:2] == ["--print-diff-key"]:
        return _print_diff_key(sys.argv[2:])
    parser = argparse.ArgumentParser()
    parser.add_argument("--branch", required=True)
    parser.add_argument("--head", required=True)
    parser.add_argument("--body-file", type=Path, required=True)
    parser.add_argument(
        "--diff-key",
        default="",
        help="The PR's diff key as computed by the workflow (diff_key), which "
        "lets a `Drain-Review-Diff:` receipt match. Empty or malformed means "
        "only `Drain-Review-Head:` receipts can match.",
    )
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
        branch=args.branch,
        head=args.head,
        body=body,
        force=args.require_receipt,
        diff_key=args.diff_key or None,
    ):
        print("allow")
        return 0
    print("deny")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
