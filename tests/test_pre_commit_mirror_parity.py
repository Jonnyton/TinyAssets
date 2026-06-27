"""End-to-end test for the pre-commit mirror-parity hook.

Creates a throwaway git repo, installs the hook, and drives two scenarios:

1. Canonical tinyassets/ file changes staged alone → hook rejects.
2. Canonical + mirror both staged with matching bytes → hook passes.

These are full-integration tests (real git, real bash-invoked hook) —
they guard against format drift in the hook script itself that unit-
level stubs would miss. Requires bash available on PATH; skipped
otherwise (which matters only on pure-Windows CI without Git Bash).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOK_SOURCE = REPO_ROOT / "scripts" / "git-hooks" / "pre-commit"


def _have_bash() -> bool:
    """Git ships bash on Windows as git-bash; any bash on PATH is enough."""
    return shutil.which("bash") is not None


pytestmark = pytest.mark.skipif(
    not _have_bash(),
    reason="pre-commit hook is a bash script; no bash on PATH",
)


def _init_repo(tmp_path: Path) -> Path:
    """Initialize a minimal git repo with the real mirror layout stubs."""
    repo = tmp_path / "repo"
    repo.mkdir()

    # Minimal git setup — isolated config so the host's git config
    # can't interfere with the test.
    env = os.environ.copy()
    env["GIT_AUTHOR_NAME"] = "test"
    env["GIT_AUTHOR_EMAIL"] = "test@example.com"
    env["GIT_COMMITTER_NAME"] = "test"
    env["GIT_COMMITTER_EMAIL"] = "test@example.com"
    subprocess.run(["git", "init", "-q"], cwd=repo, env=env, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=repo, check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "test"],
        cwd=repo, check=True,
    )

    # Stage the same directory layout the hook expects.
    (repo / "tinyassets").mkdir()
    mirror = repo / (
        "packaging/claude-plugin/plugins/tinyassets-universe-server/runtime/tinyassets"
    )
    mirror.mkdir(parents=True)
    (repo / ".agents" / "skills").mkdir(parents=True)
    (repo / ".claude" / "skills").mkdir(parents=True)
    (repo / "scripts").mkdir(exist_ok=True)

    # Install the canonical hook.
    hooks_dir = repo / ".git" / "hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy(HOOK_SOURCE, hooks_dir / "pre-commit")
    if sys.platform != "win32":
        os.chmod(hooks_dir / "pre-commit", 0o755)

    # Seed a baseline commit so pre-commit has a HEAD to diff against.
    (repo / "README.md").write_text("seed\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=repo, check=True)
    subprocess.run(
        ["git", "commit", "-q", "-m", "seed", "--no-verify"],
        cwd=repo, check=True, env=env,
    )

    return repo


def _run_commit(repo: Path, message: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "commit", "-q", "-m", message],
        cwd=repo,
        capture_output=True,
        text=True,
    )


def test_mirror_mismatch_rejects_commit(tmp_path):
    """Canonical file staged without mirror update → hook exits non-zero."""
    repo = _init_repo(tmp_path)

    canon = repo / "tinyassets" / "sample.py"
    canon.write_text("x = 1\n", encoding="utf-8")
    mirror = repo / (
        "packaging/claude-plugin/plugins/tinyassets-universe-server/runtime/"
        "tinyassets/sample.py"
    )
    mirror.write_text("x = 2\n", encoding="utf-8")  # intentionally diverged

    subprocess.run(["git", "add", "tinyassets/sample.py"], cwd=repo, check=True)

    result = _run_commit(repo, "should fail")

    assert result.returncode != 0, (
        f"Hook must reject mirror-mismatch commit. stdout={result.stdout!r} "
        f"stderr={result.stderr!r}"
    )
    assert "mirror parity broken" in result.stderr or "plugin-mirror parity" in result.stderr


def test_mirror_match_passes_commit(tmp_path):
    """Canonical + byte-identical mirror staged together → commit succeeds."""
    repo = _init_repo(tmp_path)

    canon = repo / "tinyassets" / "sample.py"
    canon.write_text("x = 1\n", encoding="utf-8")
    mirror = repo / (
        "packaging/claude-plugin/plugins/tinyassets-universe-server/runtime/"
        "tinyassets/sample.py"
    )
    mirror.write_text("x = 1\n", encoding="utf-8")  # byte-equal

    subprocess.run(
        ["git", "add", "tinyassets/sample.py",
         "packaging/claude-plugin/plugins/tinyassets-universe-server/runtime/"
         "tinyassets/sample.py"],
        cwd=repo, check=True,
    )

    result = _run_commit(repo, "parity commit")

    assert result.returncode == 0, (
        f"Hook must pass when mirror is byte-equal. stdout={result.stdout!r} "
        f"stderr={result.stderr!r}"
    )


def test_no_canonical_change_passes_trivially(tmp_path):
    """Staging a non-tinyassets/ file never touches the mirror gate."""
    repo = _init_repo(tmp_path)

    (repo / "docs.md").write_text("docs\n", encoding="utf-8")
    subprocess.run(["git", "add", "docs.md"], cwd=repo, check=True)

    result = _run_commit(repo, "docs only")

    assert result.returncode == 0, (
        f"Hook must pass when no canonical tinyassets/ changed. "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_canonical_file_without_mirror_counterpart_is_allowed(tmp_path):
    """A new canonical file with no mirror path yet → hook does NOT fail.

    The mirror is built by packaging tooling; a newly-introduced module
    often won't have a mirror until the next build. The hook skips
    these rather than blocking.
    """
    repo = _init_repo(tmp_path)

    canon = repo / "tinyassets" / "brand_new.py"
    canon.write_text("# new module\n", encoding="utf-8")
    # Note: NO mirror file created.

    subprocess.run(["git", "add", "tinyassets/brand_new.py"], cwd=repo, check=True)

    result = _run_commit(repo, "new module without mirror yet")

    assert result.returncode == 0, (
        f"Hook must pass when canonical has no mirror counterpart yet. "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_no_verify_override_always_succeeds(tmp_path):
    """`--no-verify` must bypass the hook even when mirror mismatches."""
    repo = _init_repo(tmp_path)

    canon = repo / "tinyassets" / "sample.py"
    canon.write_text("x = 1\n", encoding="utf-8")
    mirror = repo / (
        "packaging/claude-plugin/plugins/tinyassets-universe-server/runtime/"
        "tinyassets/sample.py"
    )
    mirror.write_text("x = 2\n", encoding="utf-8")

    subprocess.run(["git", "add", "tinyassets/sample.py"], cwd=repo, check=True)

    result = subprocess.run(
        ["git", "commit", "-q", "--no-verify", "-m", "override"],
        cwd=repo, capture_output=True, text=True,
    )

    assert result.returncode == 0, (
        f"--no-verify must bypass the hook. stdout={result.stdout!r} "
        f"stderr={result.stderr!r}"
    )
