"""Tests for scripts/wt.py teardown helpers.

Guards the branch-delete flag selection: ``git branch -d`` is ancestor-based
and refuses squash-merged branches (this repo's default merge style), which
would strand the local branch after ``wt.py done``. Once the merge is proven
squash-aware, teardown must force-delete with ``-D``.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(_SCRIPTS))  # so wt.py's sibling import (git_squash_merge) resolves
_SPEC = importlib.util.spec_from_file_location("wt", _SCRIPTS / "wt.py")
wt = importlib.util.module_from_spec(_SPEC)
assert _SPEC and _SPEC.loader
sys.modules["wt"] = wt
_SPEC.loader.exec_module(wt)


def test_proven_merged_uses_force_delete():
    # Squash-merged branch: proven merged but NOT an ancestor -> -d would refuse.
    assert wt._branch_delete_flag(merged=True, force=False) == "-D"


def test_force_uses_force_delete():
    assert wt._branch_delete_flag(merged=False, force=True) == "-D"


def test_unmerged_unforced_stays_safe_delete():
    # Unreachable in cmd_done (it bails first), but the helper stays conservative.
    assert wt._branch_delete_flag(merged=False, force=False) == "-d"


def test_sweep_candidate_accepts_merged_clean():
    assert wt._is_sweep_candidate({"state": "READY_TO_REMOVE", "dirty": False}) is True


def test_sweep_candidate_rejects_dirty():
    assert wt._is_sweep_candidate({"state": "READY_TO_REMOVE", "dirty": True}) is False


def test_sweep_candidate_rejects_non_ready_states():
    for state in ("IN_FLIGHT", "ORPHANED", "PARKED_DRAFT", "NEEDS_PURPOSE", "MISSING"):
        assert wt._is_sweep_candidate({"state": state, "dirty": False}) is False


def test_sweep_candidate_defaults_conservative_on_missing_fields():
    # Missing dirty flag must default to "treat as dirty" (skip).
    assert wt._is_sweep_candidate({"state": "READY_TO_REMOVE"}) is False
    assert wt._is_sweep_candidate({}) is False


def test_path_contains_excludes_current_tree(tmp_path):
    parent = tmp_path / "wt"
    (parent / "sub").mkdir(parents=True)
    assert wt._path_contains(parent.resolve(), parent.resolve()) is True
    assert wt._path_contains(parent.resolve(), (parent / "sub").resolve()) is True
    assert wt._path_contains(parent.resolve(), tmp_path.resolve()) is False
    assert wt._path_contains(parent.resolve(), (tmp_path / "other").resolve()) is False


# --- _PURPOSE.md is a local draft; the PR body is the record (2026-08-29) -------
#
# A tracked _PURPOSE.md at the repo root was edited by every lane, so the first
# PR to land turned every other open PR DIRTY and auto-merge never fired: five
# times in one afternoon (#2676, #2680 x2, #2682 x2). GitHub ignores
# .gitattributes merge drivers, so the file simply must not be tracked.


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], capture_output=True, text=True, encoding="utf-8",
        cwd=str(_SCRIPTS.parent),
    ).stdout


def test_purpose_file_is_ignored_and_never_tracked():
    assert _git("ls-files", "--", "_PURPOSE.md").strip() == "", "_PURPOSE.md is tracked again"
    assert _git("check-ignore", "_PURPOSE.md").strip() == "_PURPOSE.md"
    local_log = ".agents/worktrees.local.log"
    assert _git("check-ignore", local_log).strip() == local_log


def test_the_hand_edited_worktree_index_is_retired():
    assert _git("ls-files", "--", ".agents/worktrees.md").strip() == ""
    assert wt.EVENT_LOG.as_posix() == ".agents/worktrees.local.log"


def test_log_event_writes_the_local_log_not_a_tracked_file(tmp_path):
    wt.log_event(tmp_path, "CREATE wf-x branch=claude/x")
    assert (tmp_path / ".agents" / "worktrees.local.log").read_text(encoding="utf-8").endswith(
        "CREATE wf-x branch=claude/x\n"
    )
    assert not (tmp_path / ".agents" / "worktrees.md").exists()


def test_purpose_title_comes_from_the_purpose_line():
    text = ("# Worktree purpose\n\nPurpose: the reader treats silence as generation\n"
            "Provider: claude-code\n")
    assert wt._purpose_title(text) == "the reader treats silence as generation"


def test_purpose_title_refuses_a_todo_or_empty_line():
    assert wt._purpose_title("Purpose: TODO - fill me\n") == ""
    assert wt._purpose_title("Purpose:\nProvider: codex\n") == ""
    assert wt._purpose_title("no purpose line at all\n") == ""


def test_pr_command_publishes_the_purpose_as_the_body(tmp_path):
    body = tmp_path / "_PURPOSE.md"
    cmd = wt.pr_command(branch="claude/x", base="main", title="x lands", body_path=body)
    assert cmd == [
        "gh", "pr", "create", "--base", "main", "--head", "claude/x",
        "--title", "x lands", "--body-file", str(body),
    ]
    draft = wt.pr_command(branch="b", base="main", title="t", body_path=body, draft=True)
    assert draft[-1] == "--draft"

