"""Tests for scripts/git_squash_merge.py — squash-merge-aware merged detection.

Regression guard: ``git merge-base --is-ancestor`` alone is blind to squash
merges (this repo's default merge style via ``delete_branch_on_merge=true``),
so worktree/branch teardown refused the common case and lanes piled up.
``is_merged_into`` must see through a squash merge while staying conservative
(False) on genuinely unmerged work.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

_SPEC = importlib.util.spec_from_file_location(
    "git_squash_merge",
    Path(__file__).resolve().parent.parent / "scripts" / "git_squash_merge.py",
)
gsm = importlib.util.module_from_spec(_SPEC)
assert _SPEC and _SPEC.loader
sys.modules["git_squash_merge"] = gsm
_SPEC.loader.exec_module(gsm)


class _Proc:
    def __init__(self, returncode: int = 0, stdout: str = "") -> None:
        self.returncode = returncode
        self.stdout = stdout


# --- unit tests with a fake runner (no real git) ---


def test_ancestor_short_circuits_to_merged():
    calls = []

    def run(args):
        calls.append(args)
        return _Proc(0)  # --is-ancestor succeeds

    assert gsm.is_merged_into(run, "feat", "main") is True
    # Should not bother with the squash fallback once ancestry is proven.
    assert calls == [["git", "merge-base", "--is-ancestor", "feat", "main"]]


def _squash_runner(cherry_stdout: str, cherry_rc: int = 0):
    def run(args):
        if args[1:3] == ["merge-base", "--is-ancestor"]:
            return _Proc(1)  # not an ancestor (squash rewrote history)
        if args[1] == "merge-base":
            return _Proc(0, "BASE_SHA\n")
        if args[1] == "rev-parse":
            return _Proc(0, "TREE_SHA\n")
        if args[1] == "commit-tree":
            return _Proc(0, "DANGLING_SHA\n")
        if args[1] == "cherry":
            return _Proc(cherry_rc, cherry_stdout)
        return _Proc(1)

    return run


def test_squash_detected_when_cherry_marks_patch_present():
    assert gsm.is_merged_into(_squash_runner("- deadbeef\n"), "feat", "main") is True


def test_not_merged_when_cherry_marks_patch_missing():
    assert gsm.is_merged_into(_squash_runner("+ deadbeef\n"), "feat", "main") is False


def test_empty_cherry_output_treated_as_merged():
    assert gsm.is_merged_into(_squash_runner(""), "feat", "main") is True


def test_conservative_false_when_merge_base_fails():
    def run(args):
        if args[1:3] == ["merge-base", "--is-ancestor"]:
            return _Proc(1)
        if args[1] == "merge-base":
            return _Proc(128, "")  # no common ancestor / error
        return _Proc(0, "x\n")

    assert gsm.is_merged_into(run, "feat", "main") is False


# --- integration tests against a real temporary git repo ---


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args], cwd=repo, capture_output=True, text=True, encoding="utf-8"
    )


def _runner_for(repo: Path):
    def run(args):
        return subprocess.run(
            args, cwd=repo, capture_output=True, text=True, encoding="utf-8"
        )

    return run


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    r = tmp_path / "repo"
    r.mkdir()
    _git(r, "init", "-q", "-b", "main")
    _git(r, "config", "user.email", "t@example.com")
    _git(r, "config", "user.name", "Test")
    _git(r, "config", "commit.gpgsign", "false")
    (r / "a.txt").write_text("base\n", encoding="utf-8")
    _git(r, "add", "-A")
    _git(r, "commit", "-q", "-m", "base")
    return r


def _make_feature(repo: Path) -> None:
    _git(repo, "checkout", "-q", "-b", "feat")
    (repo / "b.txt").write_text("one\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "feat 1")
    (repo / "b.txt").write_text("one\ntwo\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "feat 2")
    _git(repo, "checkout", "-q", "main")


def test_real_squash_merge_detected(repo: Path):
    _make_feature(repo)
    _git(repo, "merge", "--squash", "feat")
    _git(repo, "commit", "-q", "-m", "squashed feat (#1)")

    run = _runner_for(repo)
    # The old check is blind to the squash:
    assert run(["git", "merge-base", "--is-ancestor", "feat", "main"]).returncode != 0
    # The new check sees the cumulative patch already on main:
    assert gsm.is_merged_into(run, "feat", "main") is True


def test_real_unmerged_branch_not_detected(repo: Path):
    _make_feature(repo)  # nothing merged into main
    assert gsm.is_merged_into(_runner_for(repo), "feat", "main") is False


def test_real_ff_and_merge_commit_detected(repo: Path):
    _make_feature(repo)
    _git(repo, "merge", "--no-ff", "-m", "merge feat", "feat")
    assert gsm.is_merged_into(_runner_for(repo), "feat", "main") is True


def test_real_squash_then_extra_commit_not_fully_merged(repo: Path):
    _make_feature(repo)
    _git(repo, "merge", "--squash", "feat")
    _git(repo, "commit", "-q", "-m", "squashed feat (#1)")
    # New work lands on feat after the squash — branch is no longer fully merged.
    _git(repo, "checkout", "-q", "feat")
    (repo / "c.txt").write_text("post-merge work\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "feat 3")
    _git(repo, "checkout", "-q", "main")
    assert gsm.is_merged_into(_runner_for(repo), "feat", "main") is False
