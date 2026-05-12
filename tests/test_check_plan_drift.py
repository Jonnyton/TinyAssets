# ruff: noqa: E402, I001

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import check_plan_drift as cpd  # noqa: E402


PLAN = """# Workflow - Plan

## Module Layout (target shape)

| Subpackage | Responsibility |
|---|---|
| `workflow/api/` | MCP tool surfaces. Landed today: `api/wiki.py`. |
| `workflow/storage/` | Schema layers (`storage/accounts.py`). |
| `workflow/runtime/` | Run scheduling primitives. |

Correctly-flat modules at root (small typed surfaces with no clear sibling):
`protocols.py`, `config.py`, `__init__.py`, `__main__.py`.

**Migration policy.** When a flat module crosses ~500 LOC OR overlaps a
sibling's responsibility, it gets a subpackage.
"""


def write_repo(root: Path, plan: str = PLAN) -> None:
    (root / "PLAN.md").write_text(plan, encoding="utf-8")
    workflow = root / "workflow"
    workflow.mkdir()
    (workflow / "__init__.py").write_text("", encoding="utf-8")


def test_parse_plan_commitments_extracts_mechanical_targets():
    commitments = cpd.parse_plan_commitments(PLAN)

    assert commitments.canonical_subpackages == ("api", "runtime", "storage")
    assert commitments.correctly_flat_modules == (
        "__init__.py",
        "__main__.py",
        "config.py",
        "protocols.py",
    )
    assert commitments.mentioned_workflow_files == (
        "workflow/api/wiki.py",
        "workflow/storage/accounts.py",
    )


def test_detect_plan_drift_clean_when_targets_exist(tmp_path: Path):
    write_repo(tmp_path)
    for directory in ("api", "runtime", "storage"):
        (tmp_path / "workflow" / directory).mkdir()
        (tmp_path / "workflow" / directory / "__init__.py").write_text(
            "",
            encoding="utf-8",
        )
    (tmp_path / "workflow" / "api" / "wiki.py").write_text("", encoding="utf-8")
    (tmp_path / "workflow" / "storage" / "accounts.py").write_text(
        "",
        encoding="utf-8",
    )
    (tmp_path / "workflow" / "config.py").write_text("VALUE = 1\n", encoding="utf-8")

    assert cpd.detect_plan_drift(tmp_path) == []


def test_detect_plan_drift_reports_missing_and_oversized_root_modules(tmp_path: Path):
    write_repo(tmp_path)
    (tmp_path / "workflow" / "api").mkdir()
    (tmp_path / "workflow" / "api" / "wiki.py").write_text("", encoding="utf-8")
    (tmp_path / "workflow" / "runs.py").write_text(
        "\n".join("pass" for _ in range(4)),
        encoding="utf-8",
    )

    issues = cpd.detect_plan_drift(tmp_path, root_module_loc_threshold=3)
    issue_keys = {(issue.code, issue.path) for issue in issues}

    assert ("missing-canonical-subpackage", "workflow/runtime/") in issue_keys
    assert ("missing-canonical-subpackage", "workflow/storage/") in issue_keys
    assert ("missing-plan-mentioned-file", "workflow/storage/accounts.py") in issue_keys
    assert ("oversized-root-module", "workflow/runs.py") in issue_keys


def test_cli_emits_report_and_nonzero_on_drift(tmp_path: Path):
    write_repo(tmp_path)

    result = subprocess.run(
        [
            sys.executable,
            str(_SCRIPTS / "check_plan_drift.py"),
            "--root",
            str(tmp_path),
        ],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    assert result.returncode == cpd.EXIT_DRIFT
    assert "PLAN.md drift report" in result.stdout
    assert "missing-canonical-subpackage" in result.stdout


def test_cli_no_fail_allows_inventory_mode(tmp_path: Path):
    write_repo(tmp_path)

    result = subprocess.run(
        [
            sys.executable,
            str(_SCRIPTS / "check_plan_drift.py"),
            "--root",
            str(tmp_path),
            "--no-fail",
        ],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    assert result.returncode == cpd.EXIT_CLEAN
    assert "Issues:" in result.stdout
