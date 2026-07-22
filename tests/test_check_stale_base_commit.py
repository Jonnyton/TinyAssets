"""Tests for scripts/check_stale_base_commit.py.

Each test builds a real throwaway git repo and exercises the detector against
it, so the assertions cover actual git behaviour rather than a mocked model of
it. The stale-tree case is constructed the way the 2026-07-22 incident happened:
`read-tree` from an old commit, `commit-tree` onto a current parent.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "check_stale_base_commit.py"


def _git(repo: Path, *args: str, env_extra: dict | None = None) -> str:
    import os

    env = os.environ.copy()
    env.update(
        {
            "GIT_AUTHOR_NAME": "t",
            "GIT_AUTHOR_EMAIL": "t@e",
            "GIT_COMMITTER_NAME": "t",
            "GIT_COMMITTER_EMAIL": "t@e",
        }
    )
    if env_extra:
        env.update(env_extra)
    proc = subprocess.run(
        ["git", *args], cwd=repo, capture_output=True, text=True, env=env
    )
    assert proc.returncode == 0, f"git {' '.join(args)}: {proc.stderr}"
    return proc.stdout.strip()


def _run_check(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=repo,
        capture_output=True,
        text=True,
    )


def _commit(repo: Path, name: str, content: str, message: str) -> str:
    (repo / name).write_text(content, encoding="utf-8")
    _git(repo, "add", name)
    _git(repo, "commit", "-q", "-m", message)
    return _git(repo, "rev-parse", "HEAD")


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    """A repo with a linear 4-commit history: base -> a -> b -> c."""
    r = tmp_path / "r"
    r.mkdir()
    _git(r, "init", "-q", "-b", "main")
    _commit(r, "shared.txt", "v1\n", "base")
    _commit(r, "a.txt", "a\n", "add a")
    _commit(r, "b.txt", "b\n", "add b")
    _commit(r, "c.txt", "c\n", "add c")
    return r


def test_clean_linear_history_has_no_findings(repo: Path) -> None:
    base = _git(repo, "rev-parse", "HEAD~3")
    res = _run_check(repo, "--range", f"{base}..HEAD")
    assert res.returncode == 0, res.stdout + res.stderr
    assert "none stale-based" in res.stdout


def test_detects_tree_built_from_stale_snapshot(repo: Path) -> None:
    """The incident shape: old tree, current parent pointer."""
    stale_base = _git(repo, "rev-parse", "HEAD~2")  # before b and c landed
    parent = _git(repo, "rev-parse", "HEAD")

    # Build a tree from the stale snapshot plus one intended edit, then commit
    # it onto the *current* parent -- exactly what a stale index produces.
    index = repo / ".git" / "tmp-index"
    env = {"GIT_INDEX_FILE": str(index)}
    _git(repo, "read-tree", stale_base, env_extra=env)
    (repo / "shared.txt").write_text("v2\n", encoding="utf-8")
    blob = _git(repo, "hash-object", "-w", "shared.txt")
    _git(
        repo, "update-index", "--add", "--cacheinfo",
        f"100644,{blob},shared.txt", env_extra=env,
    )
    tree = _git(repo, "write-tree", env_extra=env)
    bad = _git(repo, "commit-tree", tree, "-p", parent, "-m", "tweak shared.txt")

    res = _run_check(repo, "--commit", bad)
    assert res.returncode == 2, res.stdout + res.stderr
    assert "STALE-BASE COMMIT" in res.stdout
    assert stale_base[:8] in res.stdout, "should name the real stale base"
    # Both commits lost in the window must be reported.
    assert "add b" in res.stdout and "add c" in res.stdout


def test_declared_revert_is_not_flagged(repo: Path) -> None:
    """A deliberate revert resembles an ancestor by design -- not a finding."""
    _git(repo, "revert", "--no-edit", "HEAD")
    res = _run_check(repo, "--commit", "HEAD")
    assert res.returncode == 0, res.stdout + res.stderr
    assert "none stale-based" in res.stdout


def _make_stale_commit(repo: Path, message: str) -> str:
    """Build the incident shape and return the bad sha, without committing to a ref."""
    stale_base = _git(repo, "rev-parse", "HEAD~2")
    parent = _git(repo, "rev-parse", "HEAD")
    index = repo / ".git" / f"tmp-index-{abs(hash(message))}"
    env = {"GIT_INDEX_FILE": str(index)}
    _git(repo, "read-tree", stale_base, env_extra=env)
    (repo / "shared.txt").write_text("v2\n", encoding="utf-8")
    blob = _git(repo, "hash-object", "-w", "shared.txt")
    _git(
        repo, "update-index", "--add", "--cacheinfo",
        f"100644,{blob},shared.txt", env_extra=env,
    )
    tree = _git(repo, "write-tree", env_extra=env)
    return _git(repo, "commit-tree", tree, "-p", parent, "-m", message)


def test_conventional_commits_revert_form_is_exempt(repo: Path) -> None:
    """`revert(scope): ...` is a declared revert -- 575c7059 was flagged by an
    earlier matcher that only understood git's own `Revert "..."` form."""
    bad = _make_stale_commit(repo, "revert(backfill): remove the thing")
    res = _run_check(repo, "--commit", bad)
    assert res.returncode == 0, res.stdout + res.stderr


def test_explicit_override_trailer_is_exempt(repo: Path) -> None:
    """Deliberate supersession is indistinguishable by shape, so it opts out."""
    bad = _make_stale_commit(
        repo, "swap approach\n\nStale-base-check: intentional supersession\n"
    )
    res = _run_check(repo, "--commit", bad)
    assert res.returncode == 0, res.stdout + res.stderr


def test_override_trailer_is_required_to_exempt(repo: Path) -> None:
    """Red-green guard: the same commit without the trailer must still fire."""
    bad = _make_stale_commit(repo, "swap approach")
    res = _run_check(repo, "--commit", bad)
    assert res.returncode == 2, res.stdout + res.stderr


def test_merge_commit_is_skipped(repo: Path) -> None:
    """Differing from each parent by the other side's history is normal."""
    _git(repo, "checkout", "-q", "-b", "side", "HEAD~2")
    _commit(repo, "side.txt", "s\n", "side work")
    _git(repo, "checkout", "-q", "main")
    _git(repo, "merge", "-q", "--no-ff", "side", "-m", "merge side")
    res = _run_check(repo, "--commit", "HEAD")
    assert res.returncode == 0, res.stdout + res.stderr


def test_root_commit_is_handled(repo: Path) -> None:
    """A commit with no parent must not crash the walk."""
    root = _git(repo, "rev-list", "--max-parents=0", "HEAD")
    res = _run_check(repo, "--commit", root)
    assert res.returncode == 0, res.stdout + res.stderr
