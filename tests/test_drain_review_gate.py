from __future__ import annotations

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


@pytest.mark.parametrize(
    "additions,expected_rc",
    [
        ("0", 0),  # provably deletion-only: the ratchet's own maintenance
        ("1", 2),
        ("483", 2),
        ("", 2),  # API failure / field absent -> fail CLOSED
        ("null", 2),  # jq emitted null (patch omitted on large/binary diffs)
        ("  0  ", 0),  # whitespace tolerated, still provably zero
        ("0x0", 2),  # not a clean numeric zero
    ],
)
def test_ledger_edit_receipt_policy_fails_closed(
    tmp_path: Path, additions: str, expected_rc: int
) -> None:
    # Regression for the fail-open Codex found: deciding from `.patch` text made
    # an unreadable diff look like "no additions" and waved the edit through.
    # Exercised through the CLI the workflow actually calls, exit codes included.
    body = tmp_path / "empty.md"
    body.write_text("", encoding="utf-8")
    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--ledger-additions",
            additions,
            "--branch",
            "fix/ordinary",
            "--head",
            HEAD,
            "--body-file",
            str(body),
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == expected_rc
    assert completed.stdout.strip() == ("exempt" if expected_rc == 0 else "receipt-required")


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
