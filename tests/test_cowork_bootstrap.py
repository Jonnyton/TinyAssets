from __future__ import annotations

import os
import subprocess
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SCRIPT = _REPO_ROOT / "scripts" / "cowork-bootstrap.sh"


def _env(tmp_path: Path, token: str | None = None) -> dict[str, str]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    gh = bin_dir / "gh"
    gh.write_text("#!/usr/bin/env sh\nexit 0\n", encoding="utf-8")
    gh.chmod(0o755)

    env = os.environ.copy()
    env["HOME"] = str(tmp_path)
    env["PATH"] = f"{bin_dir}{os.pathsep}{env.get('PATH', '')}"
    if token is None:
        env.pop("GH_TOKEN", None)
    else:
        env["GH_TOKEN"] = token
    return env


def test_cowork_bootstrap_uses_vended_gh_token(tmp_path: Path) -> None:
    result = subprocess.run(
        ["bash", str(_SCRIPT)],
        cwd=_REPO_ROOT,
        env=_env(tmp_path, token="ghp_test_token"),
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert (tmp_path / ".git-credentials").read_text(encoding="utf-8") == (
        "https://Jonnyton:ghp_test_token@github.com\n"
    )
    assert (tmp_path / ".cowork-env").read_text(encoding="utf-8") == (
        "GH_TOKEN=ghp_test_token\n"
    )


def test_cowork_bootstrap_stays_read_only_without_token(tmp_path: Path) -> None:
    result = subprocess.run(
        ["bash", str(_SCRIPT)],
        cwd=_REPO_ROOT,
        env=_env(tmp_path),
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert "Cowork stays read-only" in result.stdout
    assert not (tmp_path / ".git-credentials").exists()
    assert not (tmp_path / ".cowork-env").exists()
