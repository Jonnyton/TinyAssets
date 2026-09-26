from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "drain_review_gate.py"
WORKFLOW = (
    Path(__file__).resolve().parents[1]
    / ".github"
    / "workflows"
    / "auto-enroll-merge.yml"
)
POLICY_WORKFLOW = (
    Path(__file__).resolve().parents[1]
    / ".github"
    / "workflows"
    / "pr-scope-guard.yml"
)
HEAD = "a" * 40


def _run_gate(
    tmp_path: Path,
    *,
    branch: str,
    head: str = HEAD,
    body: str = "",
    require_receipt: bool = False,
) -> subprocess.CompletedProcess[str]:
    body_path = tmp_path / "body.md"
    body_path.write_text(body, encoding="utf-8")
    cmd = [
        sys.executable,
        str(SCRIPT),
        "--branch",
        branch,
        "--head",
        head,
        "--body-file",
        str(body_path),
    ]
    if require_receipt:
        cmd.append("--require-receipt")
    return subprocess.run(cmd, text=True, capture_output=True, check=False)


def _valid_body(*, head: str = HEAD) -> str:
    return (
        "## Review\n\n"
        "Drain-Review-Verdict: APPROVE\n"
        f"Drain-Review-Head: {head}\n"
        "Drain-Review-Artifact: docs/audits/drain-review.md\n"
    )


def test_non_drain_branch_preserves_existing_enrollment(tmp_path: Path) -> None:
    completed = _run_gate(tmp_path, branch="fix/ordinary")

    assert completed.returncode == 0
    assert completed.stdout.strip() == "allow"


def test_require_receipt_denies_ordinary_branch_without_receipt(tmp_path: Path) -> None:
    # Gate-defining file edits force the receipt regardless of branch name.
    completed = _run_gate(tmp_path, branch="fix/ordinary", require_receipt=True)

    assert completed.returncode == 2
    assert completed.stdout.strip() == "deny"


_BASE_LEDGER = (
    "# header\ntests/a.py::test_one\ntests/b.py::test_two\nflaky tests/c.py::test_three\n"
)


def _run_ledger_gate(
    tmp_path: Path,
    *,
    base: str | None,
    head: bytes | None,
    mode: str = "100644",
    size: str | None = None,
    head_path_override: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    base_path = tmp_path / "base-ledger.txt"
    head_path = tmp_path / "head-ledger.txt"
    if base is not None:
        base_path.write_text(base, encoding="utf-8")
    # Bytes, not text: a "binary" ledger is one of the bypasses under test.
    payload = head if head is not None else b""
    head_path.write_bytes(payload)
    # Default: the tree's size agrees with what was fetched (an honest fetch).
    declared = str(len(payload)) if size is None else size
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--ledger-base-file",
            str(base_path),
            "--ledger-head-file",
            str(head_path_override or head_path),
            "--ledger-head-mode",
            mode,
            "--ledger-head-size",
            declared,
            "--branch",
            "fix/ordinary",
            "--head",
            HEAD,
            "--body-file",
            str(head_path),
        ],
        text=True,
        capture_output=True,
        check=False,
    )


@pytest.mark.parametrize(
    "mode,size,why",
    [
        ("120000", None, "symlink: Contents API dereferences it; target path is unprotected"),
        ("160000", None, "submodule/gitlink"),
        ("040000", None, "tree, not a file"),
        ("", None, "tree lookup failed entirely"),
        ("100644", "999999", "declared size > bytes fetched: truncated (>1MB blobs)"),
        ("100644", "0", "declared 0 but bytes present: response did not match the blob"),
        ("100644", "not-a-number", "unparseable size"),
        ("100644", "", "size missing"),
    ],
)
def test_untrustworthy_head_blob_always_requires_receipt(
    tmp_path: Path, mode: str, size: str | None, why: str
) -> None:
    # A deletion-only edit — the one shape that WOULD be exempt — must still be
    # refused when the fetch itself cannot be trusted.
    deletion_only = b"# header\ntests/a.py::test_one\n"
    completed = _run_ledger_gate(
        tmp_path, base=_BASE_LEDGER, head=deletion_only, mode=mode, size=size
    )

    assert completed.returncode == 2, why
    assert completed.stdout.strip() == "receipt-required"


def test_genuinely_unreadable_head_file_requires_receipt(tmp_path: Path) -> None:
    # Not merely empty — absent. The earlier version of this test wrote an
    # empty file, which never exercised the unreadable path at all.
    completed = _run_ledger_gate(
        tmp_path,
        base=_BASE_LEDGER,
        head=b"# header\n",
        head_path_override=tmp_path / "does-not-exist.txt",
    )

    assert completed.returncode == 2
    assert completed.stdout.strip() == "receipt-required"


@pytest.mark.parametrize(
    "head_bytes,expected_rc,why",
    [
        # Deletion-only: the maintenance the ratchet itself forces.
        (b"# header\ntests/a.py::test_one\n", 0, "removed two entries"),
        (_BASE_LEDGER.encode(), 0, "unchanged"),
        (b"# header\ntests/a.py::test_one\ntests/b.py::test_two\n", 0, "dropped flaky entry"),
        # Additions in any dress -> receipt required.
        (_BASE_LEDGER.encode() + b"tests/d.py::test_new\n", 2, "plain addition"),
        (
            b"# header\x00poisoned\ntests/a.py::test_one\ntests/b.py::test_two\n"
            b"flaky tests/c.py::test_three\ntests/d.py::test_new\n",
            2,
            "NUL-poisoned 'binary' file still parses as an addition (additions:0 bypass)",
        ),
        (b"# planted\ntests/evil.py::test_smuggled\n", 2, "file renamed into place"),
        (b"", 2, "rename-out / deleted / unreadable head -> fail closed"),
        (b"# comments only\n", 2, "every entry wiped at once needs a human"),
        (
            b"# header\ntests/a.py::test_one\nflaky tests/b.py::test_two\n"
            b"flaky tests/c.py::test_three\n",
            2,
            "plain -> flaky exempts an entry from stale detection: weakens the ratchet",
        ),
        (
            b"# header\ntests/a.py::test_one  # still broken\ntests/b.py::test_two\n"
            b"flaky tests/c.py::test_three\n",
            0,
            "trailing comment is stripped by BOTH parsers, so this is not a new entry",
        ),
        (
            _BASE_LEDGER.encode() + b"tests/d.py::test_new  # looks like a comment\n",
            2,
            "trailing comment cannot disguise an addition",
        ),
    ],
)
def test_ledger_edit_receipt_policy_fails_closed(
    tmp_path: Path, head_bytes: bytes, expected_rc: int, why: str
) -> None:
    # Regressions for two verified bypasses: GitHub reports additions:0 for
    # BOTH binary files and pure renames, so any metadata-based check waves
    # those through. Content comparison is immune to how the change is dressed.
    completed = _run_ledger_gate(tmp_path, base=_BASE_LEDGER, head=head_bytes)

    assert completed.returncode == expected_rc, why
    assert completed.stdout.strip() == ("exempt" if expected_rc == 0 else "receipt-required")


def test_ledger_parsers_have_no_seam(tmp_path: Path) -> None:
    """Every entry the GATE honours must be visible to the EXEMPTION check.

    The two live in different files; if they ever disagree on a line shape,
    an entry could count as "not new" for the exemption while still being
    honoured as quarantine — a smuggling seam. This pins them together.
    """
    import importlib.util

    def _load(rel: str, name: str):
        spec = importlib.util.spec_from_file_location(
            name, Path(__file__).resolve().parents[1] / rel
        )
        assert spec and spec.loader
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    gate = _load("scripts/drain_review_gate.py", "gate_policy")
    aggregator = _load("scripts/ci_required_tests.py", "aggregator")

    text = "\n".join(
        [
            "tests/a.py::t",
            "flaky tests/b.py::t",
            "tests/c.py::t # trailing note",
            "  tests/d.py::t  ",
            "# whole-line comment",
            "",
            "flaky tests/e.py::t  # both",
            "tests/f.py::t\x00",  # NUL-poisoned, still an entry
        ]
    )
    ledger = tmp_path / "ledger.txt"
    ledger.write_text(text, encoding="utf-8")

    tolerated, flaky, _ = aggregator.parse_quarantine(ledger)
    honoured = tolerated | flaky
    seen = {
        e[len("flaky ") :] if e.startswith("flaky ") else e
        for e in gate.ledger_entries(text)
    }

    assert honoured, "fixture must produce entries or the test proves nothing"
    assert not (honoured - seen), "gate honours entries the exemption cannot see"


def test_ledger_gate_missing_base_treats_every_entry_as_new(tmp_path: Path) -> None:
    # No ledger on base (as on `main` before this lands) -> nothing is exempt.
    completed = _run_ledger_gate(tmp_path, base=None, head=_BASE_LEDGER.encode())

    assert completed.returncode == 2
    assert completed.stdout.strip() == "receipt-required"


def test_require_receipt_allows_ordinary_branch_with_receipt(tmp_path: Path) -> None:
    completed = _run_gate(
        tmp_path, branch="fix/ordinary", body=_valid_body(), require_receipt=True
    )

    assert completed.returncode == 0
    assert completed.stdout.strip() == "allow"


def test_drain_branch_allows_one_matching_approval_receipt(tmp_path: Path) -> None:
    completed = _run_gate(
        tmp_path,
        branch="drain/run/target-001",
        body=_valid_body(),
    )

    assert completed.returncode == 0
    assert completed.stdout.strip() == "allow"


def test_drain_branch_denies_missing_or_stale_receipt(tmp_path: Path) -> None:
    missing = _run_gate(tmp_path, branch="drain/run/target-001")
    stale = _run_gate(
        tmp_path,
        branch="drain/run/target-001",
        body=_valid_body(head="b" * 40),
    )

    assert missing.returncode == 2
    assert stale.returncode == 2
    assert missing.stdout.strip() == "deny"
    assert stale.stdout.strip() == "deny"


def test_drain_branch_denies_duplicate_or_malformed_receipt(
    tmp_path: Path,
) -> None:
    duplicate = _run_gate(
        tmp_path,
        branch="drain/run/target-001",
        body=_valid_body() + f"Drain-Review-Head: {HEAD}\n",
    )
    malformed = _run_gate(
        tmp_path,
        branch="drain/run/target-001",
        body=(
            "Drain-Review-Verdict: approve\n"
            f"Drain-Review-Head: {HEAD.upper()}\n"
            "Drain-Review-Artifact: local/private.txt\n"
        ),
    )
    valid_plus_malformed = _run_gate(
        tmp_path,
        branch="drain/run/target-001",
        body=(
            _valid_body()
            + "Drain-Review-Verdict: DENY\n"
            + "Drain-Review-Head: malformed\n"
        ),
    )

    assert duplicate.returncode == 2
    assert malformed.returncode == 2
    assert valid_plus_malformed.returncode == 2


def test_auto_enroll_reconciles_drain_review_on_head_and_body_changes() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")

    assert "edited" in text
    assert "scripts/drain_review_gate.py" in text
    assert "headRefName" in text
    assert "headRefOid" in text
    assert "gh pr merge \"$PR\" --repo \"$REPO\" --disable-auto" in text
    assert "--match-head-commit \"$HEAD_OID\"" in text
    assert (
        "actions/checkout@11d5960a326750d5838078e36cf38b85af677262"
        in text
    )


def test_required_scope_check_fails_closed_on_unreviewed_drain_head() -> None:
    text = POLICY_WORKFLOW.read_text(encoding="utf-8")

    assert "pull_request_target:" in text
    assert "edited" in text
    assert (
        "actions/checkout@11d5960a326750d5838078e36cf38b85af677262"
        in text
    )
    assert "scripts/drain_review_gate.py" in text
    assert "--branch \"${HEAD_REF}\"" in text
    assert "--head \"${HEAD_OID}\"" in text
    assert "--body-file \"$RUNNER_TEMP/pr-body.md\"" in text


# ---------------------------------------------------------------------------
# Blocking-review receipt (2026-09-26). PR #3989 auto-merged at the exact head
# its Tier 2 reviewer had BLOCKED: the verdict was a PR comment, and only a
# failing REQUIRED check holds a PR.
# ---------------------------------------------------------------------------

REPO = "Jonnyton/TinyAssets"
PR = 4242
ARTIFACT_URL = f"https://github.com/{REPO}/pull/{PR}#issuecomment-5841421637"
TRUSTED_COMMENTS = ((ARTIFACT_URL, "OWNER"),)


def _receipt_body(*, head: str = HEAD, url: str = ARTIFACT_URL, verdict: str = "APPROVE") -> str:
    return (
        "## Review\n\n"
        f"Drain-Review-Verdict: {verdict}\n"
        f"Drain-Review-Head: {head}\n"
        f"Drain-Review-Artifact: {url}\n"
    )


def _run_blocking(
    tmp_path: Path,
    *,
    title: str = "fix: a thing",
    labels: str = "",
    hits: tuple[str, ...] = (),
    body: str = "",
    head: str = HEAD,
    repo: str = REPO,
    pr: int = PR,
    comments: tuple[tuple[str, str], ...] | None = TRUSTED_COMMENTS,
    comments_raw: str | None = None,
    footprint_exempt: bool = False,
    branch: str = "fix/ordinary",
    hits_file_missing: bool = False,
) -> subprocess.CompletedProcess[str]:
    body_path = tmp_path / "body.md"
    body_path.write_text(body, encoding="utf-8")
    hits_path = tmp_path / "hits.txt"
    if not hits_file_missing:
        hits_path.write_text("".join(f"{h}\n" for h in hits), encoding="utf-8")
    comments_path = tmp_path / "comments.ndjson"
    if comments_raw is not None:
        comments_path.write_text(comments_raw, encoding="utf-8")
    elif comments is not None:
        # Exactly what `gh api --jq '.[] | {url, association}'` emits: one
        # compact JSON object per line.
        comments_path.write_text(
            "".join(
                json.dumps({"url": url, "association": assoc}) + "\n" for url, assoc in comments
            ),
            encoding="utf-8",
        )
    cmd = [
        sys.executable,
        str(SCRIPT),
        "--blocking-review",
        "--branch",
        branch,
        "--head",
        head,
        "--body-file",
        str(body_path),
        "--review-title",
        title,
        "--review-labels",
        labels,
        "--review-hits-file",
        str(hits_path),
        "--review-repo",
        repo,
        "--review-pr",
        str(pr),
        "--review-comments-file",
        str(comments_path),
    ]
    if footprint_exempt:
        cmd.append("--review-footprint-exempt")
    return subprocess.run(cmd, text=True, capture_output=True, check=False)


@pytest.mark.parametrize(
    "kwargs,why",
    [
        ({"title": "deploy: rotate the image tag (Tier 2)"}, "Tier 2 in the title"),
        ({"title": "Tier 2: harness the provider"}, "Tier 2 leading the title"),
        ({"title": "a tier-2 change"}, "hyphenated"),
        ({"title": "a TIER 2 change"}, "upper case"),
        ({"labels": "bug,infra-change"}, "the infra-change declaration"),
        ({"hits": (".github/workflows/deploy-prod.yml",)}, "a release-critical path"),
        ({"hits": ("tinyassets/auth/provider.py",)}, "an authority path"),
    ],
)
def test_receipt_is_required_for_every_trigger(
    tmp_path: Path, kwargs: dict[str, object], why: str
) -> None:
    # The PR #3989 shape: no receipt in the body, so the required check fails.
    completed = _run_blocking(tmp_path, **kwargs)  # type: ignore[arg-type]

    assert completed.returncode == 2, why
    assert completed.stdout.strip() == "deny"
    assert "blocking-review receipt is required" in completed.stderr


@pytest.mark.parametrize(
    "kwargs,why",
    [
        ({}, "ordinary PR: no label, no hits, no Tier 2 title"),
        ({"title": "Tier 0: docs"}, "Tier 0 is unaffected"),
        ({"title": "C27: tier 3 rollout"}, "Tier 3 is unaffected"),
        ({"title": "subtier2 naming"}, "'tier2' inside a word is not a declaration"),
        ({"title": "Tier 20 of 30"}, "Tier 20 is not Tier 2"),
        ({"labels": "bug,documentation"}, "unrelated labels"),
        # The workflow seds blank lines out, but an empty footprint must read as
        # empty however it is spelled — never as one unnamed hit.
        ({"hits": ("", "   ")}, "a blank hits file is not a hit"),
    ],
)
def test_tier0_and_tier1_prs_outside_the_paths_are_unaffected(
    tmp_path: Path, kwargs: dict[str, object], why: str
) -> None:
    completed = _run_blocking(tmp_path, **kwargs)  # type: ignore[arg-type]

    assert completed.returncode == 0, why
    assert completed.stdout.strip() == "receipt-not-required"


def test_valid_receipt_unblocks_a_tier2_pr(tmp_path: Path) -> None:
    completed = _run_blocking(
        tmp_path, title="deploy: a thing (Tier 2)", body=_receipt_body()
    )

    assert completed.returncode == 0
    assert completed.stdout.strip() == "allow"
    # The reason is still reported, so the PR says WHY a receipt was needed.
    assert "the title declares Tier 2" in completed.stderr


@pytest.mark.parametrize(
    "body,why",
    [
        (_receipt_body(verdict="BLOCK"), "a BLOCK verdict can never satisfy the gate"),
        (_receipt_body(verdict="DENY"), "nor any other word"),
        (_receipt_body(verdict="approve"), "nor lower-case approve"),
        (_receipt_body(verdict="APPROVE with reservations"), "nor APPROVE plus prose"),
        (_receipt_body(head="b" * 40), "a receipt for another head is stale"),
        (_receipt_body(head=HEAD.upper()), "the head must be lower-case hex"),
        ("", "no receipt at all"),
        (
            _receipt_body() + f"Drain-Review-Verdict: BLOCK\nDrain-Review-Head: {HEAD}\n",
            "an APPROVE cannot be stacked next to a BLOCK",
        ),
    ],
)
def test_mutating_the_verdict_or_head_fails_closed(tmp_path: Path, body: str, why: str) -> None:
    completed = _run_blocking(tmp_path, title="deploy: a thing (Tier 2)", body=body)

    assert completed.returncode == 2, why
    assert completed.stdout.strip() == "deny"


@pytest.mark.parametrize(
    "url,why",
    [
        ("docs/audits/drain-review.md", "a docs path is not a comment on this PR"),
        (
            f"https://github.com/{REPO}/pull/{PR + 1}#issuecomment-5841421637",
            "a comment on a DIFFERENT PR",
        ),
        (
            f"https://github.com/someone/else/pull/{PR}#issuecomment-5841421637",
            "a comment in a different repository",
        ),
        (f"https://github.com/{REPO}/pull/{PR}#issuecomment-1", "a comment id that does not exist"),
        (f"https://github.com/{REPO}/pull/{PR}", "the PR itself, with no comment anchor"),
        (
            f"https://github.com/{REPO}/commit/{'c' * 40}",
            "a commit URL",
        ),
        (
            f"https://github.com/{REPO}/pull/{PR}#issuecomment-5841421637 (approved)",
            "trailing prose on the artifact line",
        ),
        (
            f"https://evil.example/{REPO}/pull/{PR}#issuecomment-5841421637",
            "a look-alike host",
        ),
    ],
)
def test_artifact_must_name_a_real_comment_on_this_pr(tmp_path: Path, url: str, why: str) -> None:
    completed = _run_blocking(
        tmp_path, title="deploy: a thing (Tier 2)", body=_receipt_body(url=url)
    )

    assert completed.returncode == 2, why
    assert completed.stdout.strip() == "deny"


@pytest.mark.parametrize(
    "anchor",
    ["issuecomment-5841421637", "pullrequestreview-991234", "discussion_r778899"],
)
def test_a_verdict_may_live_in_a_comment_review_or_review_comment(
    tmp_path: Path, anchor: str
) -> None:
    url = f"https://github.com/{REPO}/pull/{PR}#{anchor}"
    completed = _run_blocking(
        tmp_path,
        title="deploy: a thing (Tier 2)",
        body=_receipt_body(url=url),
        comments=((url, "OWNER"),),
    )

    assert completed.returncode == 0
    assert completed.stdout.strip() == "allow"


def test_repo_casing_in_the_artifact_url_is_tolerated(tmp_path: Path) -> None:
    # GitHub resolves owner/repo case-insensitively; refusing a stamper who
    # typed a different casing would be a wall, not a gate.
    url = f"https://github.com/jonnyton/tinyassets/pull/{PR}#issuecomment-5841421637"
    completed = _run_blocking(
        tmp_path,
        title="deploy: a thing (Tier 2)",
        body=_receipt_body(url=url),
        comments=((url.replace("jonnyton/tinyassets", REPO), "OWNER"),),
    )

    assert completed.returncode == 0
    assert completed.stdout.strip() == "allow"


@pytest.mark.parametrize(
    "association",
    ["CONTRIBUTOR", "FIRST_TIME_CONTRIBUTOR", "NONE", "MANNEQUIN", ""],
)
def test_an_untrusted_commenter_cannot_supply_the_artifact(
    tmp_path: Path, association: str
) -> None:
    # Anyone can comment on a public repo's PR. Trust comes from GitHub's
    # author_association, read from the API, never from the comment body.
    completed = _run_blocking(
        tmp_path,
        title="deploy: a thing (Tier 2)",
        body=_receipt_body(),
        comments=((ARTIFACT_URL, association),),
    )

    assert completed.returncode == 2
    assert completed.stdout.strip() == "deny"


@pytest.mark.parametrize("association", ["OWNER", "MEMBER", "COLLABORATOR"])
def test_write_side_associations_may_supply_the_artifact(
    tmp_path: Path, association: str
) -> None:
    completed = _run_blocking(
        tmp_path,
        title="deploy: a thing (Tier 2)",
        body=_receipt_body(),
        comments=((ARTIFACT_URL, association),),
    )

    assert completed.returncode == 0
    assert completed.stdout.strip() == "allow"


@pytest.mark.parametrize(
    "comments_raw,why",
    [
        (None, "the comment API read failed, so the workflow removed the file"),
        ("", "an empty inventory cannot corroborate anything"),
        ("not json at all\n", "unparseable inventory"),
        (
            json.dumps({"url": ARTIFACT_URL, "association": "OWNER"}) + "\n{oops",
            "a trailing partial object means we did not read the whole inventory",
        ),
        (
            json.dumps({"url": ARTIFACT_URL}) + "\n",
            "a row with no association cannot be trusted",
        ),
        (
            json.dumps([{"url": ARTIFACT_URL, "association": "OWNER"}]) + "\n",
            "an array where objects were expected",
        ),
    ],
)
def test_an_uncorroborated_receipt_fails_closed(
    tmp_path: Path, comments_raw: str | None, why: str
) -> None:
    completed = _run_blocking(
        tmp_path,
        title="deploy: a thing (Tier 2)",
        body=_receipt_body(),
        comments=None,
        comments_raw=comments_raw,
    )

    assert completed.returncode == 2, why
    assert completed.stdout.strip() == "deny"


def test_pretty_printed_inventory_still_parses(tmp_path: Path) -> None:
    # raw_decode, not a line split: if gh ever stops emitting compact objects
    # the gate must keep reading them rather than silently see an empty set.
    completed = _run_blocking(
        tmp_path,
        title="deploy: a thing (Tier 2)",
        body=_receipt_body(),
        comments=None,
        comments_raw=json.dumps({"url": ARTIFACT_URL, "association": "OWNER"}, indent=2) + "\n",
    )

    assert completed.returncode == 0
    assert completed.stdout.strip() == "allow"


def test_an_unreadable_hits_file_fails_closed(tmp_path: Path) -> None:
    # The gate could not see its own path list. That must not read as "no
    # release-critical paths touched".
    completed = _run_blocking(tmp_path, hits_file_missing=True)

    assert completed.returncode == 2
    assert completed.stdout.strip() == "deny"
    assert "could not be read" in completed.stderr


def test_a_proven_inert_footprint_outranks_the_label_but_not_a_tier2_title(
    tmp_path: Path,
) -> None:
    # A deletion-only quarantine ledger edit, or an AST-identical authority
    # file, must stay label-exempt: the gate itself forces that maintenance and
    # a content proof beats a declaration ABOUT those paths. A Tier 2 title is
    # the author declaring the whole change needs review, which no path proof
    # can answer.
    exempt = _run_blocking(tmp_path, labels="infra-change", footprint_exempt=True)
    still_tier2 = _run_blocking(
        tmp_path,
        title="tests: drop a stale quarantine entry (Tier 2)",
        labels="infra-change",
        footprint_exempt=True,
    )
    unproven_leftover = _run_blocking(
        tmp_path,
        labels="infra-change",
        hits=("deploy/install-host-uptime-services.sh",),
        footprint_exempt=False,
    )

    assert exempt.returncode == 0
    assert exempt.stdout.strip() == "receipt-not-required"
    assert still_tier2.returncode == 2
    assert unproven_leftover.returncode == 2


def test_receipt_requirement_survives_a_rename_duplicated_hit(tmp_path: Path) -> None:
    # The file list projects both the new and previous name, so the same path
    # can appear twice. That must read as one reason, not crash or double-count.
    completed = _run_blocking(
        tmp_path,
        hits=("tinyassets/auth/provider.py", "tinyassets/auth/provider.py", ""),
    )

    assert completed.returncode == 2
    assert completed.stderr.count("tinyassets/auth/provider.py") == 1


# The exact list the workflow's GATE_RE protected before 2026-09-26, when the
# receipt requirement widened to every release-critical path. Each of these can
# neuter the check that judges it, so losing the receipt on any of them is a
# silent regression — SENSITIVE_RE must keep covering all of them.
_FORMER_GATE_PATHS = (
    ".github/workflows/tests.yml",
    ".github/workflows/pr-scope-guard.yml",
    ".github/known-failing-tests.txt",
    ".github/heavy-test-files.txt",
    "scripts/ci_required_tests.py",
    "scripts/drain_review_gate.py",
)


def _workflow_regex(name: str) -> str:
    text = POLICY_WORKFLOW.read_text(encoding="utf-8")
    match = re.search(rf"^\s*{name}='(?P<pattern>.+)'\s*$", text, re.MULTILINE)
    assert match, f"{name} is gone from {POLICY_WORKFLOW.name}"
    return match.group("pattern")


def test_every_formerly_gate_defining_path_still_demands_a_receipt() -> None:
    sensitive = re.compile(_workflow_regex("SENSITIVE_RE"))

    for path in _FORMER_GATE_PATHS:
        assert sensitive.match(path), f"{path} lost its receipt requirement"


def test_authority_paths_still_demand_a_receipt() -> None:
    authority = re.compile(_workflow_regex("AUTHORITY_RE"), re.IGNORECASE)

    for path in (
        "tinyassets/auth/provider.py",
        "tinyassets/credential_vault.py",
        "tinyassets/providers/router.py",
        "tinyassets/api/permissions.py",
        "packaging/claude-plugin/plugins/tinyassets-universe-server/runtime/tinyassets/auth/x.py",
    ):
        assert authority.match(path), f"{path} lost its receipt requirement"


def _extract(pattern: str) -> str:
    """The workflow's own lines, so this test cannot drift from what runs."""
    text = POLICY_WORKFLOW.read_text(encoding="utf-8")
    match = re.search(pattern, text, re.MULTILINE)
    assert match, f"{pattern!r} is gone from {POLICY_WORKFLOW.name}"
    return match.group(0).strip()


@pytest.mark.parametrize(
    "hits,authority,exempt_fired,expected_hits,expected_exempt",
    [
        ("", "", "0", [], "0"),
        ("deploy/x.sh", "", "0", ["deploy/x.sh"], "0"),
        # The file list projects both the new and the previous name on a rename,
        # so the same path arrives twice and must collapse to one.
        ("deploy/x.sh\ndeploy/x.sh", "", "0", ["deploy/x.sh"], "0"),
        (
            "deploy/x.sh",
            "tinyassets/auth/p.py",
            "0",
            ["deploy/x.sh", "tinyassets/auth/p.py"],
            "0",
        ),
        # AST proof cleared AUTHORITY_HITS and nothing else was release-critical.
        ("", "", "1", [], "1"),
        # AST proof cleared one authority file but a release-critical path
        # remains: the proof does not cover the footprint, so no exemption.
        ("deploy/x.sh", "", "1", ["deploy/x.sh"], "0"),
    ],
)
def test_receipt_footprint_is_the_deduplicated_union(
    tmp_path: Path,
    hits: str,
    authority: str,
    exempt_fired: str,
    expected_hits: list[str],
    expected_exempt: str,
) -> None:
    bash = shutil.which("bash")
    if bash is None:  # pragma: no cover - CI runners all have bash
        pytest.skip("bash is required to exercise the workflow's own lines")

    script = "\n".join(
        [
            "set -euo pipefail",
            # Inputs arrive through the environment: a hits list is multi-line,
            # and Windows argv quoting mangles an embedded newline.
            _extract(r'^\s*RECEIPT_HITS="\$\(printf .*$'),
            _extract(r"^\s*FOOTPRINT_EXEMPT=0\n(?:.*\n)*?\s*fi$"),
            _extract(r"^\s*printf '%s\\n' \"\$RECEIPT_HITS\" \| sed .*receipt-hits\.txt\"$"),
            'echo "FOOTPRINT_EXEMPT=${FOOTPRINT_EXEMPT}"',
        ]
    )
    script_path = tmp_path / "fragment.sh"
    script_path.write_text(script, encoding="utf-8")

    completed = subprocess.run(
        [bash, str(script_path)],
        text=True,
        capture_output=True,
        check=False,
        env={
            **os.environ,
            "HITS": hits,
            "AUTHORITY_HITS": authority,
            "EXEMPT_FIRED": exempt_fired,
            "RUNNER_TEMP": str(tmp_path),
        },
    )

    assert completed.returncode == 0, completed.stderr
    written = (tmp_path / "receipt-hits.txt").read_text(encoding="utf-8").splitlines()
    assert written == expected_hits
    assert completed.stdout.strip() == f"FOOTPRINT_EXEMPT={expected_exempt}"


def test_scope_guard_wires_the_blocking_review_decision() -> None:
    text = POLICY_WORKFLOW.read_text(encoding="utf-8")

    # Re-trigger events: stamping the BODY must re-run the check without a push,
    # and labelling must too.
    for event in ("edited", "labeled", "unlabeled", "synchronize", "opened", "reopened"):
        assert event in text, event
    assert "PR_TITLE: ${{ github.event.pull_request.title }}" in text
    assert "--blocking-review" in text
    for flag in (
        '--review-title "${PR_TITLE:-}"',
        '--review-labels "${LABELS:-}"',
        '--review-hits-file "$RUNNER_TEMP/receipt-hits.txt"',
        '--review-repo "${REPO}"',
        '--review-pr "${PR}"',
        '--review-comments-file "$COMMENTS_FILE"',
    ):
        assert flag in text, flag
    # The inventory is read from the API, for all three places a verdict lands.
    for endpoint in ('"issues/${PR}/comments"', '"pulls/${PR}/comments"', '"pulls/${PR}/reviews"'):
        assert endpoint in text, endpoint
    assert "author_association" in text
    # A failed comment read must not fail an unrelated PR, but must leave no
    # inventory behind for one that needs a receipt. Asserted as the ORDERED
    # sequence inside the loop: the bare string also appears before the loop,
    # so a looser check stayed green when the in-loop removal was deleted.
    assert re.search(
        r'rm -f "\$COMMENTS_FILE"\s*\n\s*break\s*\n\s*fi\s*\n\s*done',
        text,
    ), "a partial inventory must be discarded, not read as the complete one"
