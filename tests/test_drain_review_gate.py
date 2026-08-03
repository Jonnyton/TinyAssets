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


_BASE_LEDGER = (
    "# header\ntests/a.py::test_one\ntests/b.py::test_two\nflaky tests/c.py::test_three\n"
)


def _run_ledger_gate(
    tmp_path: Path, *, base: str | None, head: bytes | None
) -> subprocess.CompletedProcess[str]:
    base_path = tmp_path / "base-ledger.txt"
    head_path = tmp_path / "head-ledger.txt"
    if base is not None:
        base_path.write_text(base, encoding="utf-8")
    # Bytes, not text: a "binary" ledger is one of the bypasses under test.
    head_path.write_bytes(head if head is not None else b"")
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--ledger-base-file",
            str(base_path),
            "--ledger-head-file",
            str(head_path),
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
            0,
            "re-labelling an existing entry flaky is not a new entry",
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
