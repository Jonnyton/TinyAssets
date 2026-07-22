"""Regression tests for the squash-aware branch liveness report."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

_SPEC = importlib.util.spec_from_file_location(
    "branch_janitor_liveness",
    Path(__file__).resolve().parent.parent / "scripts" / "branch_janitor.py",
)
bj = importlib.util.module_from_spec(_SPEC)
assert _SPEC and _SPEC.loader
sys.modules[_SPEC.name] = bj
_SPEC.loader.exec_module(bj)


def _pr_index(
    *, open_prs: dict[str, int] | None = None, all_prs: dict[str, int] | None = None
):
    return bj.PullRequestIndex(open_prs or {}, all_prs or {})


def _verdict(verdicts, name: str):
    return next(verdict for verdict in verdicts if verdict.name == name)


def test_squash_merged_branch_is_merged_not_stranded(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(command: list[str], **_kwargs):
        key = tuple(command[1:])
        answers = {
            ("merge-base", "--is-ancestor", "refs/remotes/origin/fix/squashed", "origin/main"):
                (1, ""),
            ("merge-base", "refs/remotes/origin/fix/squashed", "origin/main"):
                (0, "base-sha\n"),
            ("rev-parse", "refs/remotes/origin/fix/squashed^{tree}"):
                (0, "tree-sha\n"),
            ("commit-tree", "tree-sha", "-p", "base-sha", "-m", "_"):
                (0, "synthetic-sha\n"),
            ("cherry", "origin/main", "synthetic-sha"):
                (0, "- synthetic-sha\n"),
        }
        returncode, stdout = answers[key]
        return subprocess.CompletedProcess(command, returncode, stdout, "")

    monkeypatch.setattr(bj, "_run", fake_run)

    verdicts = bj.classify_liveness(
        "origin",
        "origin/main",
        ["fix/squashed"],
        pr_index=_pr_index(all_prs={"fix/squashed": 1480}),
    )

    verdict = _verdict(verdicts, "fix/squashed")
    assert verdict.category == "MERGED"
    assert verdict.pr_number == 1480


def test_ancestor_success_without_stdout_is_not_undetermined(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        bj,
        "_run",
        lambda command: subprocess.CompletedProcess(command, 0, "", ""),
    )

    merged, error = bj.merge_status("refs/remotes/origin/base", "origin/main")

    assert merged is True
    assert error is None


def test_contained_branch_reports_absorbing_ref(monkeypatch: pytest.MonkeyPatch) -> None:
    child = "refs/remotes/origin/feature/child"
    stack = "refs/remotes/origin/feature/stack"

    def merge_status(ref: str, base_ref: str):
        if (ref, base_ref) == (child, stack):
            return True, None
        return False, None

    monkeypatch.setattr(bj, "merge_status", merge_status)

    verdicts = bj.classify_liveness(
        "origin",
        "origin/main",
        ["feature/child", "feature/stack"],
        pr_index=_pr_index(),
    )

    verdict = _verdict(verdicts, "feature/child")
    assert verdict.category == "CONTAINED"
    assert verdict.contained_by == "origin/feature/stack"


def test_ancestry_container_finds_live_stack_ref(monkeypatch: pytest.MonkeyPatch) -> None:
    output = "\n".join(
        [
            "origin/feature/child",
            "origin/feature/stack",
            "origin/main",
        ]
    )
    monkeypatch.setattr(
        bj,
        "_run",
        lambda command: subprocess.CompletedProcess(command, 0, output, ""),
    )

    contained_by, error = bj.ancestry_container(
        "origin",
        "feature/child",
        "origin/main",
    )

    assert contained_by == "origin/feature/stack"
    assert error is None


def test_unreachable_branch_without_open_pr_is_stranded(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(bj, "merge_status", lambda _ref, _base: (False, None))

    verdicts = bj.classify_liveness(
        "origin",
        "origin/main",
        ["claude/brain-scratch-root-cleanup"],
        pr_index=_pr_index(),
    )

    verdict = _verdict(verdicts, "claude/brain-scratch-root-cleanup")
    assert verdict.category == "STRANDED"
    assert bj.liveness_exit_code(verdicts, exit_on_stranded=False) == 0
    assert bj.liveness_exit_code(verdicts, exit_on_stranded=True) == 1


def test_git_failure_is_undetermined_and_never_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        bj,
        "merge_status",
        lambda _ref, _base: (None, "git merge-base failed (exit 128)"),
    )

    verdicts = bj.classify_liveness(
        "origin",
        "origin/main",
        ["feature/ambiguous"],
        pr_index=_pr_index(),
    )

    verdict = _verdict(verdicts, "feature/ambiguous")
    assert verdict.category == "UNDETERMINED"
    assert "merge-base" in verdict.reason
    assert bj.liveness_exit_code(verdicts, exit_on_stranded=False) == 2
    assert bj.liveness_exit_code(verdicts, exit_on_stranded=True) == 2


def test_missing_gh_suppresses_unsafe_stranded_bucket(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(bj, "merge_status", lambda _ref, _base: (False, None))
    monkeypatch.setattr(bj, "ancestry_container", lambda _remote, _name, _base: (None, None))

    verdicts = bj.classify_liveness(
        "origin",
        "origin/main",
        ["feature/maybe-open"],
        pr_index=None,
        pr_error="gh unavailable",
    )

    verdict = _verdict(verdicts, "feature/maybe-open")
    assert verdict.category == "UNDETERMINED"
    assert "PR attribution unavailable" in verdict.reason
    report = bj.render_liveness_report(verdicts, pr_error="gh unavailable")
    assert "PR attribution: unavailable" in report


def test_missing_gh_executable_is_reported_not_raised(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        bj,
        "_run",
        lambda _command: (_ for _ in ()).throw(FileNotFoundError("gh not found")),
    )

    pr_index, error = bj.pull_request_index()

    assert pr_index is None
    assert error == "gh pr list failed: gh not found"


def test_open_pr_bucket_has_priority(monkeypatch: pytest.MonkeyPatch) -> None:
    def unexpected_merge(_ref: str, _base: str):
        raise AssertionError("OPEN-PR should not need git merge classification")

    monkeypatch.setattr(bj, "merge_status", unexpected_merge)

    verdicts = bj.classify_liveness(
        "origin",
        "origin/main",
        ["feature/live"],
        pr_index=_pr_index(open_prs={"feature/live": 1482}),
    )

    verdict = _verdict(verdicts, "feature/live")
    assert verdict.category == "OPEN-PR"
    assert verdict.pr_number == 1482
