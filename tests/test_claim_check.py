from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "claim_check.py"
SPEC = importlib.util.spec_from_file_location("claim_check_ref_contract", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
claim_check = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = claim_check
SPEC.loader.exec_module(claim_check)


STATUS_TEXT = """# Status

## Work
| Task | Files | Depends | Status |
|---|---|---|---|
| **current-main task** | `current.py` | - | pending |
"""


def test_load_status_text_defaults_to_working_tree(
    tmp_path: Path,
    monkeypatch,
) -> None:
    status_path = tmp_path / "STATUS.md"
    status_path.write_text(STATUS_TEXT, encoding="utf-8")
    monkeypatch.setattr(claim_check, "STATUS_PATH", status_path)

    def runner(*_args, **_kwargs):
        raise AssertionError("working-tree status must not invoke git")

    text = claim_check.load_status_text(runner=runner)

    assert text == STATUS_TEXT
    assert claim_check.parse_status(text)[0].task_label == "current-main task"


def test_task_label_preserves_full_bolded_identity() -> None:
    label = ("same task identity " * 8) + "distinct ending"
    text = STATUS_TEXT.replace("current-main task", label)

    row = claim_check.parse_status(text)[0]

    assert row.task_label == label


def test_load_status_text_reads_explicit_git_ref(tmp_path: Path) -> None:
    commands: list[list[str]] = []

    def runner(command: list[str], **kwargs: object):
        commands.append(command)
        assert kwargs["cwd"] == tmp_path
        assert kwargs["encoding"] == "utf-8"
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=STATUS_TEXT,
            stderr="",
        )

    text = claim_check.load_status_text(
        status_ref="origin/main",
        repo_root=tmp_path,
        runner=runner,
    )

    assert text == STATUS_TEXT
    assert commands == [["git", "show", "origin/main:STATUS.md"]]


def test_load_status_text_fails_closed_for_unreadable_ref(tmp_path: Path) -> None:
    def runner(command: list[str], **_kwargs: object):
        return subprocess.CompletedProcess(
            command,
            128,
            stdout="",
            stderr="fatal: bad revision",
        )

    try:
        claim_check.load_status_text(
            status_ref="missing",
            repo_root=tmp_path,
            runner=runner,
        )
    except RuntimeError as exc:
        assert "cannot read missing:STATUS.md" in str(exc)
    else:
        raise AssertionError("unreadable ref must fail closed")


def test_load_status_text_rejects_option_like_ref(tmp_path: Path) -> None:
    def runner(*_args, **_kwargs):
        raise AssertionError("invalid ref must be rejected before git")

    try:
        claim_check.load_status_text(
            status_ref="--help",
            repo_root=tmp_path,
            runner=runner,
        )
    except RuntimeError as exc:
        assert "invalid STATUS ref" in str(exc)
    else:
        raise AssertionError("option-like ref must fail closed")


def test_stale_activity_uses_same_explicit_history_ref() -> None:
    row = claim_check.Row(
        raw_task="**claimed task**",
        files=["claimed.py"],
        depends_raw="-",
        status="claimed:old-provider",
        line_no=7,
    )
    commands: list[list[str]] = []

    def runner(command: list[str], **_kwargs: object):
        commands.append(command)
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    stale = claim_check.find_stale_claims(
        [row],
        history_ref="origin/main",
        runner=runner,
    )

    assert stale
    assert commands
    assert "origin/main" in commands[0]
    assert commands[0].index("origin/main") < commands[0].index("--")


def test_status_row_lifecycle_atom_does_not_create_global_overlap() -> None:
    hits = claim_check.files_overlap(
        ["STATUS.md", "tinyassets/api/runs.py"],
        ["STATUS.md", "tinyassets/api/branches.py"],
    )

    assert hits == []


def test_status_exemption_preserves_every_non_coordination_overlap() -> None:
    hits = claim_check.files_overlap(
        ["./STATUS.md", "tests/test_claim_check.py"],
        ["STATUS.md", "tests/"],
    )

    assert hits == ["tests/test_claim_check.py"]


def test_nested_status_named_file_remains_an_ordinary_collision() -> None:
    hits = claim_check.files_overlap(
        ["docs/STATUS.md"],
        ["docs/"],
    )

    assert hits == ["docs/STATUS.md"]
