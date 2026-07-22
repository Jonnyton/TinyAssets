"""Tests for peer_agent's publication audit — the guard against silently
reporting a peer lane as successful when its commits never left the machine.

These drive REAL git repositories and a REAL push to a local bare remote, so
the push path is executed rather than mocked. Only the `unknown` classification
is injected, because its trigger (a worktree owned by another Windows account,
which makes `git -C` fail `dubious ownership`) cannot be created portably.

Loaded by path: scripts/ is outside the importable package tree.
"""

from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _load(rel: str):
    path = ROOT / rel
    spec = importlib.util.spec_from_file_location(path.stem, path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


pa = _load("scripts/peer_agent.py")


def _git(cwd: Path, *argv: str) -> None:
    subprocess.run(["git", "-C", str(cwd), *argv], check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A git repo with one commit and no remote."""
    d = tmp_path / "lane"
    d.mkdir()
    _git(d, "init", "-q", "-b", "claude/lane-work")
    _git(d, "config", "user.email", "t@example.com")
    _git(d, "config", "user.name", "t")
    (d / "f.txt").write_text("work", encoding="utf-8")
    _git(d, "add", "f.txt")
    _git(d, "commit", "-qm", "lane work")
    return d


@pytest.fixture
def origin(tmp_path: Path) -> Path:
    """A bare repo standing in for origin — a real push target, no network."""
    d = tmp_path / "origin.git"
    subprocess.run(["git", "init", "-q", "--bare", str(d)], check=True, capture_output=True)
    return d


# --- publication_state ------------------------------------------------------


def test_non_git_dir_is_skip(tmp_path: Path):
    state, _, detail = pa.publication_state(str(tmp_path))
    assert state == "skip"
    assert "not a git work tree" in detail


def test_repo_without_commits_is_skip(tmp_path: Path):
    d = tmp_path / "empty"
    d.mkdir()
    _git(d, "init", "-q")
    assert pa.publication_state(str(d))[0] == "skip"


def test_committed_but_unpushed_is_blocked(repo: Path):
    state, branch, detail = pa.publication_state(str(repo))
    assert state == "blocked"
    assert branch == "claude/lane-work"
    assert "1 commit(s)" in detail


def test_pushed_work_is_skip(repo: Path, origin: Path):
    _git(repo, "remote", "add", "origin", str(origin))
    _git(repo, "push", "-q", "-u", "origin", "HEAD:refs/heads/claude/lane-work")
    assert pa.publication_state(str(repo))[0] == "skip"


def test_commit_after_push_is_blocked_again(repo: Path, origin: Path):
    """A remote that is merely *configured* must not be mistaken for published."""
    _git(repo, "remote", "add", "origin", str(origin))
    _git(repo, "push", "-q", "-u", "origin", "HEAD:refs/heads/claude/lane-work")
    (repo / "g.txt").write_text("more", encoding="utf-8")
    _git(repo, "add", "g.txt")
    _git(repo, "commit", "-qm", "second")
    state, _, detail = pa.publication_state(str(repo))
    assert state == "blocked"
    assert "1 commit(s)" in detail


def test_uncommitted_work_is_blocked(repo: Path, origin: Path):
    """The sandbox case: the lane produced files but could not write .git.

    Pushed + clean would be `skip`; an untracked file alone must still block,
    or a lane that cannot commit gets reported as a success.
    """
    _git(repo, "remote", "add", "origin", str(origin))
    _git(repo, "push", "-q", "-u", "origin", "HEAD:refs/heads/claude/lane-work")
    (repo / "PROOF.txt").write_text("lane work", encoding="utf-8")
    state, _, detail = pa.publication_state(str(repo))
    assert state == "blocked"
    assert "1 uncommitted change(s)" in detail


def test_uncommitted_work_without_any_commit_is_blocked(tmp_path: Path):
    d = tmp_path / "fresh"
    d.mkdir()
    _git(d, "init", "-q")
    (d / "PROOF.txt").write_text("lane work", encoding="utf-8")
    state, _, detail = pa.publication_state(str(d))
    assert state == "blocked"
    assert "no commit yet" in detail


def test_gitignored_scratch_is_not_unpublished_work(repo: Path, origin: Path):
    """Sandbox test-temp dirs are ignored, not mistaken for the lane's output."""
    _git(repo, "remote", "add", "origin", str(origin))
    (repo / ".gitignore").write_text(".pytest-tmp/\n", encoding="utf-8")
    _git(repo, "add", ".gitignore")
    _git(repo, "commit", "-qm", "ignore scratch")
    _git(repo, "push", "-q", "-u", "origin", "HEAD:refs/heads/claude/lane-work")
    (repo / ".pytest-tmp").mkdir()
    (repo / ".pytest-tmp" / "junk").write_text("x", encoding="utf-8")
    assert pa.publication_state(str(repo))[0] == "skip"


def test_both_reasons_reported_together(repo: Path):
    (repo / "PROOF.txt").write_text("lane work", encoding="utf-8")
    _, _, detail = pa.publication_state(str(repo))
    assert "reachable from no remote" in detail
    assert "uncommitted change(s)" in detail


def test_publish_does_not_rescue_uncommitted_work(repo: Path, origin: Path):
    """--publish pushes commits; it must never claim success over a dirty tree."""
    _git(repo, "remote", "add", "origin", str(origin))
    (repo / "PROOF.txt").write_text("lane work", encoding="utf-8")
    notice, code = pa.settle_publication(str(repo), publish=True)
    assert code == 3
    assert "uncommitted" in notice
    assert "stage + commit" in notice


def test_baseline_excuses_preexisting_scratch(repo: Path, origin: Path):
    """Dirt that was already there is not this lane's unpublished work."""
    _git(repo, "remote", "add", "origin", str(origin))
    _git(repo, "push", "-q", "-u", "origin", "HEAD:refs/heads/claude/lane-work")
    (repo / "fleet_state.json").write_text("{}", encoding="utf-8")
    base = pa.worktree_baseline(str(repo))
    assert pa.publication_state(str(repo), base)[0] == "skip"


def test_baseline_still_catches_new_lane_output(repo: Path, origin: Path):
    """...but anything the lane adds afterwards must still block."""
    _git(repo, "remote", "add", "origin", str(origin))
    _git(repo, "push", "-q", "-u", "origin", "HEAD:refs/heads/claude/lane-work")
    (repo / "fleet_state.json").write_text("{}", encoding="utf-8")
    base = pa.worktree_baseline(str(repo))
    (repo / "PROOF.txt").write_text("lane work", encoding="utf-8")  # the lane's output
    state, _, detail = pa.publication_state(str(repo), base)
    assert state == "blocked"
    assert "1 uncommitted change(s)" in detail


def test_baseline_is_none_when_git_cannot_answer(tmp_path: Path):
    assert pa.worktree_baseline(str(tmp_path)) is None


def test_git_failure_is_unknown_not_skip(repo: Path, monkeypatch: pytest.MonkeyPatch):
    """The dubious-ownership case must never collapse into `skip`."""
    monkeypatch.setattr(
        pa, "git", lambda *a, **k: (128, "fatal: detected dubious ownership in repository")
    )
    state, _, detail = pa.publication_state(str(repo))
    assert state == "unknown"
    assert "dubious ownership" in detail


def test_missing_git_binary_is_skip(repo: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(pa, "git", lambda *a, **k: (-1, "git executable not launchable"))
    assert pa.publication_state(str(repo))[0] == "skip"


# --- publish_branch ---------------------------------------------------------


def test_publish_pushes_to_origin(repo: Path, origin: Path):
    _git(repo, "remote", "add", "origin", str(origin))
    ok, _ = pa.publish_branch(str(repo), "claude/lane-work")
    assert ok
    listed = subprocess.run(
        ["git", "-C", str(origin), "branch", "--list"], capture_output=True, text=True
    ).stdout
    assert "claude/lane-work" in listed


@pytest.mark.parametrize("branch", ["main", "master"])
def test_publish_refuses_default_branches(repo: Path, branch: str):
    ok, msg = pa.publish_branch(str(repo), branch)
    assert not ok
    assert "never push to main" in msg


@pytest.mark.parametrize("branch", ["", "HEAD"])
def test_publish_refuses_detached_head(repo: Path, branch: str):
    ok, msg = pa.publish_branch(str(repo), branch)
    assert not ok
    assert "detached" in msg


def test_publish_failure_is_reported(repo: Path):
    """No origin configured — the push must fail, not silently pass."""
    ok, msg = pa.publish_branch(str(repo), "claude/lane-work")
    assert not ok
    assert msg


# --- settle_publication -----------------------------------------------------


def test_settle_returns_3_and_names_recovery(repo: Path):
    notice, code = pa.settle_publication(str(repo), publish=False)
    assert code == 3
    assert "PUBLICATION BLOCKED" in notice
    assert "claude/lane-work" in notice
    assert "push -u origin" in notice  # the operator's recovery command


def test_settle_is_silent_when_nothing_to_publish(tmp_path: Path):
    assert pa.settle_publication(str(tmp_path), publish=False) == ("", 0)


def test_settle_publishes_and_clears(repo: Path, origin: Path):
    _git(repo, "remote", "add", "origin", str(origin))
    notice, code = pa.settle_publication(str(repo), publish=True)
    assert code == 0
    assert "published claude/lane-work" in notice
    assert pa.publication_state(str(repo))[0] == "skip"


def test_settle_publish_failure_still_returns_3(repo: Path):
    """--publish that cannot reach a remote must NOT downgrade to success."""
    notice, code = pa.settle_publication(str(repo), publish=True)
    assert code == 3
    assert "push:     FAILED" in notice


def test_settle_unknown_returns_3_with_safe_directory_hint(
    repo: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(
        pa, "publication_state", lambda *a: ("unknown", "", "fatal: dubious ownership")
    )
    notice, code = pa.settle_publication(str(repo), publish=False)
    assert code == 3
    assert "safe.directory" in notice
