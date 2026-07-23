from __future__ import annotations

import importlib.util
import io
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "check_stranded_lanes.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("check_stranded_lanes", SCRIPT)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def stranded_fixture(tmp_path: Path) -> tuple[Path, Path, str]:
    remote = tmp_path / "origin.git"
    root = tmp_path / "TinyAssets"
    scratch = root / ".codex-scratch-finished-work"

    _git(tmp_path, "init", "--bare", "-q", str(remote))
    root.mkdir()
    _git(root, "init", "-q", "-b", "main")
    _configure_author(root)
    (root / "README.md").write_text("base\n", encoding="utf-8")
    _git(root, "add", "README.md")
    _git(root, "commit", "-q", "-m", "base")
    _git(root, "remote", "add", "origin", str(remote))
    _git(root, "push", "-q", "-u", "origin", "main")
    _git(tmp_path, "--git-dir", str(remote), "symbolic-ref", "HEAD", "refs/heads/main")

    _git(root, "clone", "-q", str(remote), str(scratch))
    _configure_author(scratch)
    _git(scratch, "checkout", "-q", "-b", "feat/finished-work")
    (scratch / "finished.txt").write_text("valuable\n", encoding="utf-8")
    _git(scratch, "add", "finished.txt")
    _git(scratch, "commit", "-q", "-m", "finished locally")
    return root, scratch, "feat/finished-work"


def test_scratch_clone_without_pushed_branch_is_stranded_and_exit_2(
    stranded_fixture: tuple[Path, Path, str],
) -> None:
    check_stranded_lanes = _load_module()
    root, scratch, _branch = stranded_fixture
    output = io.StringIO()

    exit_code = check_stranded_lanes.run_detector(
        root,
        output=output,
        pr_exists=lambda _path, _branch: True,
    )

    rendered = output.getvalue()
    assert exit_code == 2
    assert "STRANDED" in rendered
    assert str(scratch.resolve()) in rendered
    assert "branch=feat/finished-work" in rendered
    assert "ahead=1" in rendered
    assert "missing=no_pushed_branch" in rendered


def test_pushed_branch_with_stubbed_pr_is_clean_and_exit_0(
    stranded_fixture: tuple[Path, Path, str],
) -> None:
    check_stranded_lanes = _load_module()
    root, scratch, branch = stranded_fixture
    _git(scratch, "push", "-q", "-u", "origin", branch)
    output = io.StringIO()

    exit_code = check_stranded_lanes.run_detector(
        root,
        output=output,
        pr_exists=lambda _path, _branch: True,
    )

    assert exit_code == 0
    assert output.getvalue() == "CLEAN no stranded or unknown lanes\n"


def test_pushed_branch_without_pr_is_stranded(
    stranded_fixture: tuple[Path, Path, str],
) -> None:
    check_stranded_lanes = _load_module()
    root, scratch, branch = stranded_fixture
    _git(scratch, "push", "-q", "-u", "origin", branch)
    output = io.StringIO()

    exit_code = check_stranded_lanes.run_detector(
        root,
        output=output,
        pr_exists=lambda _path, _branch: False,
    )

    assert exit_code == 2
    assert str(scratch.resolve()) in output.getvalue()
    assert "missing=no_pull_request" in output.getvalue()


def test_explicit_historical_base_handles_shallow_clone_without_origin_main(
    stranded_fixture: tuple[Path, Path, str],
) -> None:
    check_stranded_lanes = _load_module()
    root, scratch, _branch = stranded_fixture
    base_commit = _git(scratch, "rev-parse", "HEAD^")
    _git(scratch, "update-ref", "-d", "refs/remotes/origin/main")
    output = io.StringIO()

    exit_code = check_stranded_lanes.run_detector(
        root,
        base_ref=base_commit,
        output=output,
        pr_exists=lambda _path, _branch: True,
    )

    assert exit_code == 2
    assert str(scratch.resolve()) in output.getvalue()
    assert "ahead=1" in output.getvalue()
    assert "missing=no_pushed_branch" in output.getvalue()


def test_dubious_ownership_error_is_unknown_not_silently_skipped(tmp_path: Path) -> None:
    check_stranded_lanes = _load_module()
    lane = tmp_path / "codex-tmp" / "sandbox-owned"
    lane.mkdir(parents=True)
    (lane / ".git").mkdir()

    def rejected_git(_args: list[str], _cwd: Path):
        return subprocess.CompletedProcess(
            ["git"],
            128,
            "",
            "fatal: detected dubious ownership in repository at 'sandbox-owned'\n",
        )

    result = check_stranded_lanes.inspect_lane(
        lane,
        git_runner=rejected_git,
        pr_exists=lambda _path, _branch: True,
    )

    assert result is not None
    assert result.state == "UNKNOWN"
    assert result.path == lane.resolve()
    assert "dubious ownership" in result.detail


def _configure_author(repo: Path) -> None:
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test User")
    _git(repo, "config", "commit.gpgsign", "false")


def _git(cwd: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()
