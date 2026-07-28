from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "openspec_flow.py"
SPEC = importlib.util.spec_from_file_location("openspec_flow", SCRIPT)
assert SPEC is not None
openspec_flow = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = openspec_flow
SPEC.loader.exec_module(openspec_flow)


def _change(
    repo: Path,
    name: str,
    *,
    complete: int = 0,
    remaining: int = 1,
    proposal: str = "One focused intent.",
) -> None:
    change = repo / "openspec" / "changes" / name
    change.mkdir(parents=True)
    tasks = ["# Tasks", ""]
    tasks.extend(f"- [x] done {index}" for index in range(complete))
    tasks.extend(f"- [ ] todo {index}" for index in range(remaining))
    (change / "tasks.md").write_text("\n".join(tasks) + "\n", encoding="utf-8")
    (change / "proposal.md").write_text(proposal + "\n", encoding="utf-8")


def _status(repo: Path, *rows: str) -> None:
    content = [
        "# Status",
        "",
        "## Work",
        "",
        "| Task | Files | Depends | Status |",
        "|---|---|---|---|",
        *rows,
        "",
    ]
    (repo / "STATUS.md").write_text("\n".join(content), encoding="utf-8")


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


@pytest.fixture
def flow_repo(tmp_path: Path) -> Path:
    _change(tmp_path, "complete-change", complete=2, remaining=0)
    _change(tmp_path, "claimed-small", complete=1, remaining=1)
    _change(tmp_path, "claimed-large", remaining=3)
    _change(tmp_path, "queued-change", remaining=2)
    _change(tmp_path, "untracked-change", remaining=4)
    _status(
        tmp_path,
        "| Complete complete-change | a | - | pending |",
        "| Small claimed-small | b | - | claimed:codex-desktop ACTIVE 2026-07-28 |",
        "| Large claimed-large | c | - | claimed:claude-code-2 |",
        "| Queue queued-change | d | - | dev-ready |",
    )
    return tmp_path


def test_inventory_maps_status_and_ranks_finish_first(flow_repo: Path) -> None:
    report = openspec_flow.build_report(flow_repo)
    changes = {change["name"]: change for change in report["changes"]}

    assert report["summary"] == {
        "active_changes": 5,
        "completed_tasks": 3,
        "remaining_tasks": 10,
        "delivery_wip": 2,
        "untracked_changes": 1,
        "oversized_changes": 0,
        "complete_unarchived": 1,
        "invalid_changes": 0,
    }
    assert changes["claimed-small"]["classification"] == "in-flight"
    assert changes["claimed-small"]["owner"] == "codex-desktop"
    assert changes["queued-change"]["classification"] == "queued"
    assert changes["untracked-change"]["classification"] == "untracked"
    assert report["provider_wip"] == {
        "claude-code-2": ["claimed-large"],
        "codex-desktop": ["claimed-small"],
    }
    assert report["recommendations"] == [
        "complete-change",
        "claimed-small",
        "claimed-large",
        "queued-change",
    ]


def test_text_and_json_expose_the_same_core_information(flow_repo: Path) -> None:
    report = openspec_flow.build_report(flow_repo)
    text = openspec_flow.render_text(report)
    encoded = json.dumps(report, sort_keys=True)
    decoded = json.loads(encoded)

    assert "Active changes: 5" in text
    assert "Delivery WIP: 2" in text
    assert "complete-change" in text
    assert "untracked-change | untracked | 0/4" in text
    assert "Provider WIP uses exact STATUS identities" in text
    assert decoded["summary"] == report["summary"]
    assert decoded["recommendations"] == report["recommendations"]
    assert decoded["provider_wip"] == report["provider_wip"]


def test_audit_is_read_only_and_legacy_oversize_is_advisory(
    tmp_path: Path,
) -> None:
    _change(tmp_path, "legacy-umbrella", remaining=13)
    _status(tmp_path)
    before = {
        path.relative_to(tmp_path): path.read_bytes()
        for path in tmp_path.rglob("*")
        if path.is_file()
    }

    report = openspec_flow.build_report(tmp_path)
    after = {
        path.relative_to(tmp_path): path.read_bytes()
        for path in tmp_path.rglob("*")
        if path.is_file()
    }

    assert report["summary"]["oversized_changes"] == 1
    assert report["changes"][0]["oversized"] is True
    assert before == after


def test_admission_rejects_more_than_twelve_total_tasks(tmp_path: Path) -> None:
    _change(tmp_path, "too-large", complete=12, remaining=1)
    _status(tmp_path)

    result = openspec_flow.check_admission(
        openspec_flow.build_report(tmp_path),
        change_name="too-large",
        provider="codex-desktop",
    )

    assert result["allowed"] is False
    assert any("12-task ceiling" in error for error in result["errors"])


def test_admission_rejects_second_change_for_exact_session_identity(
    tmp_path: Path,
) -> None:
    _change(tmp_path, "existing-change")
    _change(tmp_path, "candidate-change")
    _status(
        tmp_path,
        "| Existing existing-change | a | - | claimed:codex-desktop |",
    )
    report = openspec_flow.build_report(tmp_path)

    blocked = openspec_flow.check_admission(
        report,
        change_name="candidate-change",
        provider="codex-desktop",
    )
    other_session = openspec_flow.check_admission(
        report,
        change_name="candidate-change",
        provider="codex-cli-2",
    )

    assert blocked["allowed"] is False
    assert "existing-change" in blocked["errors"][0]
    assert blocked["global_delivery_wip"] == 1
    assert other_session["allowed"] is True
    assert other_session["global_delivery_wip"] == 1
    assert any("suffix" in warning for warning in other_session["warnings"])


def test_all_matching_claimed_owners_count_toward_wip(tmp_path: Path) -> None:
    _change(tmp_path, "shared-change")
    _change(tmp_path, "candidate-change")
    _status(
        tmp_path,
        "| B depends on shared-change | a | shared-change | claimed:provider-b |",
        "| A owns shared-change | openspec/changes/shared-change | - | claimed:provider-a |",
    )
    report = openspec_flow.build_report(tmp_path)
    shared = next(
        change for change in report["changes"] if change["name"] == "shared-change"
    )

    assert shared["owners"] == ["provider-a", "provider-b"]
    assert report["provider_wip"]["provider-a"] == ["shared-change"]
    assert report["provider_wip"]["provider-b"] == ["shared-change"]
    assert (
        openspec_flow.check_admission(
            report,
            change_name="candidate-change",
            provider="provider-a",
        )["allowed"]
        is False
    )


def test_umbrella_language_warns_but_does_not_decide_scope(tmp_path: Path) -> None:
    _change(
        tmp_path,
        "candidate",
        proposal="Complete the full platform vision in one change.",
    )
    _status(tmp_path)

    result = openspec_flow.check_admission(
        openspec_flow.build_report(tmp_path),
        change_name="candidate",
        provider="codex-desktop",
    )

    assert result["allowed"] is True
    assert any("semantic scope review" in warning for warning in result["warnings"])


def test_change_without_tasks_is_reported_for_triage(tmp_path: Path) -> None:
    change = tmp_path / "openspec" / "changes" / "missing-tasks"
    change.mkdir(parents=True)
    (change / "proposal.md").write_text("Focused change.\n", encoding="utf-8")
    _status(tmp_path)

    report = openspec_flow.build_report(tmp_path)

    assert report["summary"]["invalid_changes"] == 1
    assert report["changes"][0]["classification"] == "invalid-artifacts"
    assert any("missing tasks.md" in warning for warning in report["warnings"])


def test_git_window_counts_unique_admissions_and_archives(tmp_path: Path) -> None:
    _git(tmp_path, "init", "-q", "-b", "main")
    _git(tmp_path, "config", "user.email", "test@example.com")
    _git(tmp_path, "config", "user.name", "Test User")
    _status(tmp_path)
    _git(tmp_path, "add", "STATUS.md")
    _git(tmp_path, "commit", "-q", "-m", "base")
    base = _git(tmp_path, "rev-parse", "HEAD")
    _change(tmp_path, "new-change", remaining=2)
    archive = tmp_path / "openspec" / "changes" / "archive" / "old-change"
    archive.mkdir(parents=True)
    (archive / "tasks.md").write_text("- [x] done\n", encoding="utf-8")
    _git(tmp_path, "add", "openspec")
    _git(tmp_path, "commit", "-q", "-m", "change flow")

    flow = openspec_flow.build_report(tmp_path, since=base)["git_flow"]

    assert flow == {
        "since": base,
        "admitted_changes": 1,
        "archived_changes": 1,
        "net_active_arrival": 0,
    }


def test_git_window_rejects_option_shaped_revision(tmp_path: Path) -> None:
    _status(tmp_path)

    flow = openspec_flow.build_report(tmp_path, since="--output=unsafe")["git_flow"]

    assert flow == {
        "since": "--output=unsafe",
        "error": "git revision must not start with '-'",
    }


def test_cli_returns_two_for_blocked_admission(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _change(tmp_path, "too-large", remaining=13)
    _status(tmp_path)

    exit_code = openspec_flow.main(
        [
            "--repo",
            str(tmp_path),
            "check-change",
            "too-large",
            "--provider",
            "codex-desktop",
        ]
    )

    assert exit_code == 2
    assert "BLOCKED" in capsys.readouterr().out
