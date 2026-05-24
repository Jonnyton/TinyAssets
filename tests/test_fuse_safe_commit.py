from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "fuse_safe_commit.py"


def _git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=check,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def _init_repo(repo: Path) -> None:
    _git(repo, "init")
    _git(repo, "config", "user.name", "Test User")
    _git(repo, "config", "user.email", "test@example.invalid")


def _commit_all(repo: Path, message: str) -> str:
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", message)
    return _git(repo, "rev-parse", "HEAD").stdout.strip()


def _run_script(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.setdefault("PYTHONUTF8", "1")
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=repo,
        check=check,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
    )


def test_creates_commit_from_base_ref_without_copying_stale_index(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    (repo / "a.txt").write_text("base\n", encoding="utf-8")
    (repo / "b.txt").write_text("keep\n", encoding="utf-8")
    base = _commit_all(repo, "base")

    # Simulate the incident shape: the worktree index has unrelated staged
    # drift. The wrapper must read from base, not copy .git/index.
    (repo / "b.txt").write_text("staged drift\n", encoding="utf-8")
    _git(repo, "add", "b.txt")

    content = tmp_path / "new-a.txt"
    content.write_text("changed by safe commit\n", encoding="utf-8")
    result = _run_script(
        repo,
        "--base-ref",
        base,
        "--file",
        f"a.txt:{content}",
        "--message",
        "safe commit",
        "--max-files",
        "1",
    )

    new_commit = result.stdout.strip()
    assert new_commit
    assert _git(repo, "diff", "--name-only", f"{base}..{new_commit}").stdout.splitlines() == [
        "a.txt"
    ]
    assert _git(repo, "show", f"{new_commit}:a.txt").stdout == "changed by safe commit\n"
    assert _git(repo, "show", f"{new_commit}:b.txt").stdout == "keep\n"


def test_refuses_when_diff_exceeds_max_files(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    (repo / "a.txt").write_text("base a\n", encoding="utf-8")
    (repo / "b.txt").write_text("base b\n", encoding="utf-8")
    base = _commit_all(repo, "base")

    content_a = tmp_path / "new-a.txt"
    content_b = tmp_path / "new-b.txt"
    content_a.write_text("new a\n", encoding="utf-8")
    content_b.write_text("new b\n", encoding="utf-8")
    result = _run_script(
        repo,
        "--base-ref",
        base,
        "--file",
        f"a.txt:{content_a}",
        "--file",
        f"b.txt:{content_b}",
        "--message",
        "too broad",
        "--max-files",
        "1",
        check=False,
    )

    assert result.returncode == 1
    assert "diff touches 2 files, exceeds --max-files 1" in result.stderr


def test_update_ref_accepts_dot_git_ref_path(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    (repo / "a.txt").write_text("base\n", encoding="utf-8")
    base = _commit_all(repo, "base")

    content = tmp_path / "new-a.txt"
    content.write_text("new\n", encoding="utf-8")
    result = _run_script(
        repo,
        "--base-ref",
        base,
        "--file",
        f"a.txt:{content}",
        "--message",
        "update ref",
        "--max-files",
        "1",
        "--update-ref",
        ".git/refs/heads/main",
    )

    new_commit = result.stdout.strip()
    assert _git(repo, "rev-parse", "main").stdout.strip() == new_commit


def test_rejects_unsafe_repo_paths(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    (repo / "a.txt").write_text("base\n", encoding="utf-8")
    base = _commit_all(repo, "base")
    content = tmp_path / "new-a.txt"
    content.write_text("new\n", encoding="utf-8")

    result = _run_script(
        repo,
        "--base-ref",
        base,
        "--file",
        f"../a.txt:{content}",
        "--message",
        "unsafe",
        check=False,
    )

    assert result.returncode == 2
    assert "repo path must stay inside the repository" in result.stderr
