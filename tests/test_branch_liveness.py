"""Regression tests for the squash-aware branch liveness report."""

from __future__ import annotations

import importlib.util
import json
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
    monkeypatch.setattr(bj, "merge_status", lambda _ref, _base, **_kwargs: (False, None))
    monkeypatch.setattr(
        bj,
        "ancestry_container",
        lambda _remote, name, _base: (
            ("origin/feature/stack", None)
            if name == "feature/child"
            else (None, None)
        ),
    )

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


@pytest.mark.parametrize("pr_index", [None, _pr_index()])
def test_squash_containment_is_independent_of_gh(
    monkeypatch: pytest.MonkeyPatch,
    pr_index,
) -> None:
    child = "refs/remotes/origin/feature/child"
    stack = "refs/remotes/origin/feature/stack"
    monkeypatch.setattr(bj, "ancestry_container", lambda _remote, _name, _base: (None, None))
    monkeypatch.setattr(
        bj,
        "merge_status",
        lambda ref, base, **_kwargs: (
            (True, None) if (ref, base) == (child, stack) else (False, None)
        ),
    )

    verdicts = bj.classify_liveness(
        "origin",
        "origin/main",
        ["feature/child", "feature/stack"],
        pr_index=pr_index,
        pr_error="gh unavailable" if pr_index is None else None,
    )

    assert _verdict(verdicts, "feature/child").category == "CONTAINED"


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


def test_history_lookup_failure_keeps_open_pr_coverage(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(command: list[str]):
        state = command[command.index("--state") + 1]
        if state == "open":
            stdout = json.dumps(
                [{"headRefName": "feature/live", "number": 42, "state": "OPEN"}]
            )
            return subprocess.CompletedProcess(command, 0, stdout, "")
        return subprocess.CompletedProcess(command, 1, "", "history unavailable")

    monkeypatch.setattr(bj, "_run", fake_run)

    pr_index, error = bj.pull_request_index()

    assert error is None
    assert pr_index is not None
    assert pr_index.open_by_branch == {"feature/live": 42}
    assert pr_index.history_error == "gh pr list failed (exit 1): history unavailable"


def test_open_query_with_non_open_row_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    row = [{"headRefName": "feature/missing", "number": 9, "state": "CLOSED"}]
    monkeypatch.setattr(
        bj,
        "_run",
        lambda command: subprocess.CompletedProcess(command, 0, json.dumps(row), ""),
    )

    pr_index, error = bj.pull_request_index()

    assert pr_index is None
    assert error == "gh pr list --state open returned a non-open row"


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


def test_main_json_reports_fetch_failure_and_never_mutates(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        bj,
        "_run",
        lambda command: subprocess.CompletedProcess(command, 1, "", "offline"),
    )
    monkeypatch.setattr(bj, "liveness_branches", lambda _remote: ([], None))
    monkeypatch.setattr(bj, "pull_request_index", lambda: (_pr_index(), None))
    monkeypatch.setattr(
        bj,
        "delete_branch",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("mutation reached")),
    )
    monkeypatch.setattr(
        bj,
        "upsert_issue",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("mutation reached")),
    )

    exit_code = bj.main(["--liveness", "--json", "--fetch"])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 2
    assert payload["branches"] == []
    assert "git fetch --prune failed" in payload["errors"][0]


def test_main_exit_code_gates_stranded_human_report(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(bj, "liveness_branches", lambda _remote: (["feature/lost"], None))
    monkeypatch.setattr(bj, "pull_request_index", lambda: (_pr_index(), None))
    monkeypatch.setattr(bj, "merge_status", lambda _ref, _base: (False, None))
    monkeypatch.setattr(bj, "ancestry_container", lambda _remote, _name, _base: (None, None))

    exit_code = bj.main(["--liveness", "--exit-code"])

    assert exit_code == 1
    assert "| `feature/lost` | STRANDED |" in capsys.readouterr().out


def test_main_rejects_liveness_apply_combination() -> None:
    with pytest.raises(SystemExit) as excinfo:
        bj.main(["--liveness", "--apply"])

    assert excinfo.value.code == 2
