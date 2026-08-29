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

_REPO = _SCRIPTS.parent


def _git(*args: str) -> tuple[int, str]:
    proc = subprocess.run(
        ["git", *args], capture_output=True, text=True, encoding="utf-8", cwd=str(_REPO),
    )
    return proc.returncode, proc.stdout.strip()


def test_purpose_file_is_ignored_by_this_repos_gitignore_and_never_tracked():
    code, out = _git("ls-files", "--", "_PURPOSE.md")
    assert code == 0 and out == "", "_PURPOSE.md is tracked again"
    # -v names the rule's source: it must be THIS repo's .gitignore, not a
    # global exclude that happens to be set on the machine (Codex round 1, P2).
    code, out = _git("check-ignore", "-v", "_PURPOSE.md")
    assert code == 0, "_PURPOSE.md is not ignored"
    source = out.split(":", 1)[0].replace("\\", "/")
    assert source.endswith(".gitignore") and "/" not in source.strip("./"), out


def test_the_hand_edited_worktree_index_is_retired():
    code, out = _git("ls-files", "--", ".agents/worktrees.md")
    assert code == 0 and out == ""


def test_the_event_log_lives_inside_the_git_dir():
    """Inside .git it is never tracked and needs no ignore rule — a primary
    checkout behind main would not have had one (Codex round 1, P1)."""
    path = wt._event_log_path(_REPO)
    code, common = _git("rev-parse", "--git-common-dir")
    assert code == 0
    assert path.name == wt.EVENT_LOG_NAME
    assert path.parent == Path(common if Path(common).is_absolute() else _REPO / common).resolve()


def test_log_event_falls_back_to_a_dot_git_path_outside_a_repo(tmp_path):
    wt.log_event(tmp_path, "CREATE wf-x branch=claude/x")
    log = tmp_path / ".git" / wt.EVENT_LOG_NAME
    assert log.read_text(encoding="utf-8").endswith("CREATE wf-x branch=claude/x\n")
    assert not (tmp_path / ".agents").exists()


def test_purpose_title_comes_from_the_purpose_line():
    text = ("# Worktree purpose\n\nPurpose: the reader treats silence as generation\n"
            "Provider: claude-code\n")
    assert wt._purpose_title(text) == "the reader treats silence as generation"


def test_purpose_title_refuses_a_todo_or_empty_line():
    assert wt._purpose_title("Purpose: TODO - fill me\n") == ""
    assert wt._purpose_title("Purpose:\nProvider: codex\n") == ""
    assert wt._purpose_title("no purpose line at all\n") == ""


def test_scaffold_title_is_refused_for_slash_and_no_slash_branches():
    assert wt._title_is_scaffold("x", "claude/x") is True
    assert wt._title_is_scaffold("demo", "demo") is True          # Codex round 1, P2
    assert wt._title_is_scaffold("", "claude/x") is True
    assert wt._title_is_scaffold("x lands cleanly", "claude/x") is False


def test_base_normalization_strips_exactly_the_remote_prefix():
    assert wt._normalize_base("origin/main", "origin") == "main"
    assert wt._normalize_base("release/1.x", "origin") == "release/1.x"   # Codex round 1, P1
    assert wt._normalize_base("origin/release/1.x", "origin") == "release/1.x"
    assert wt._normalize_base("main", "origin") == "main"


def test_pr_command_publishes_the_purpose_as_the_body(tmp_path):
    body = tmp_path / "_PURPOSE.md"
    cmd = wt.pr_command(branch="claude/x", base="main", title="x lands", body_path=body)
    assert cmd == [
        "gh", "pr", "create", "--base", "main", "--head", "claude/x",
        "--title", "x lands", "--body-file", str(body),
    ]
    draft = wt.pr_command(branch="b", base="main", title="t", body_path=body, draft=True)
    assert draft[-1] == "--draft"


def test_pr_update_command_republishes_an_existing_pr(tmp_path):
    body = tmp_path / "_PURPOSE.md"
    assert wt.pr_update_command(number=42, title=None, body_path=body) == [
        "gh", "pr", "edit", "42", "--body-file", str(body),
    ]
    assert wt.pr_update_command(number=42, title="new", body_path=body)[-2:] == ["--title", "new"]


def test_unpublished_purpose_is_detected_against_the_pr_body():
    assert wt._purpose_unpublished("a\nb\n", "a\nb") is False          # whitespace-insensitive
    assert wt._purpose_unpublished("a\nb\nc", "a\nb") is True
    assert wt._purpose_unpublished("anything", None) is False        # no PR: nothing to compare


def test_pr_lookup_distinguishes_no_pr_from_could_not_ask(monkeypatch):
    """`done`/`sweep` must not need gh, and a failed lookup must not be
    recorded as "never published" (Codex round 2, P1 + P2)."""
    import types

    def fake_run(args, *, cwd=None):
        return fake_run.result

    monkeypatch.setattr(wt, "_run", fake_run)
    fake_run.result = types.SimpleNamespace(
        returncode=1, stdout="", stderr="no pull requests found for branch",
    )
    found = wt._existing_pr("claude/x", Path("."))
    assert found.known is True and found.number is None

    fake_run.result = types.SimpleNamespace(
        returncode=1, stdout="",
        stderr="gh: To get started with GitHub CLI, please run: gh auth login",
    )
    found = wt._existing_pr("claude/x", Path("."))
    assert found.known is False and "auth" in found.detail

    def missing_gh(args, *, cwd=None):
        raise FileNotFoundError("gh")

    monkeypatch.setattr(wt, "_run", missing_gh)
    found = wt._existing_pr("claude/x", Path("."))
    assert found.known is False and "unavailable" in found.detail

    monkeypatch.setattr(wt, "_run", fake_run)
    fake_run.result = types.SimpleNamespace(
        returncode=0, stdout='{"number": 7, "state": "MERGED", "body": "b"}', stderr="",
    )
    found = wt._existing_pr("claude/x", Path("."))
    assert (found.number, found.state, found.body, found.known) == (7, "MERGED", "b", True)


def test_archive_writes_header_and_text_in_one_append(tmp_path, monkeypatch):
    lane = tmp_path / "wf-x"
    lane.mkdir()
    (lane / "_PURPOSE.md").write_text("Purpose: keep me\nShip condition: x\n", encoding="utf-8")
    offline = wt._PrLookup(known=False, detail="offline")
    monkeypatch.setattr(wt, "_existing_pr", lambda branch, cwd: offline)
    calls = []
    monkeypatch.setattr(wt, "log_event", lambda root, line: calls.append(line))
    note = wt._archive_purpose(tmp_path, lane, "claude/x", "testing")
    assert len(calls) == 1 and calls[0].startswith("PURPOSE-ARCHIVE wf-x branch=claude/x pr=?")
    assert "    Purpose: keep me" in calls[0] and "    Ship condition: x" in calls[0]
    assert "unknown" in note and "archived" in note
