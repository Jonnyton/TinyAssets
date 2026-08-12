from __future__ import annotations

import os
import shlex
import shutil
import subprocess
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SCRIPT = _REPO_ROOT / "scripts" / "cowork-bootstrap.sh"
_WINDOWS_WSL_BASH = (
    Path(os.environ.get("WINDIR", r"C:\Windows")) / "System32" / "bash.exe"
)
_BASH = (
    str(_WINDOWS_WSL_BASH)
    if os.name == "nt" and _WINDOWS_WSL_BASH.is_file()
    else shutil.which("bash") or "bash"
)


def _bash_path(path: Path) -> str:
    resolved = path.resolve()
    if os.name != "nt":
        return str(resolved)
    drive = resolved.drive.rstrip(":").lower()
    prefix = "/mnt" if "system32" in _BASH.lower() else ""
    return f"{prefix}/{drive}{resolved.as_posix()[2:]}"


def _env(tmp_path: Path, token: str | None = None) -> dict[str, str]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    gh = bin_dir / "gh"
    gh.write_text("#!/usr/bin/env sh\nexit 0\n", encoding="utf-8")
    gh.chmod(0o755)

    env = os.environ.copy()
    env["HOME"] = _bash_path(tmp_path)
    if os.name == "nt":
        env["PATH"] = ":".join(
            (_bash_path(bin_dir), "/usr/local/bin", "/usr/bin", "/bin")
        )
    else:
        env["PATH"] = f"{bin_dir}{os.pathsep}{env.get('PATH', '')}"
    if token is None:
        env.pop("GH_TOKEN", None)
    else:
        env["GH_TOKEN"] = token
    return env


def _run(tmp_path: Path, token: str | None = None) -> subprocess.CompletedProcess:
    env = _env(tmp_path, token)
    if os.name == "nt" and "system32" in _BASH.lower():
        command = " ".join(
            (
                "/usr/bin/env",
                f"HOME={shlex.quote(env['HOME'])}",
                f"PATH={shlex.quote(env['PATH'])}",
                f"GH_TOKEN={shlex.quote(token or '')}",
                shlex.quote(_bash_path(_SCRIPT)),
            )
        )
        return subprocess.run(
            [_BASH, "-lc", command],
            cwd=tmp_path,
            capture_output=True,
            text=True,
            check=False,
        )
    return subprocess.run(
        [_BASH, _bash_path(_SCRIPT)],
        cwd=_REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_cowork_bootstrap_uses_vended_gh_token(tmp_path: Path) -> None:
    result = _run(tmp_path, token="ghp_test_token")

    assert result.returncode == 0
    assert (tmp_path / ".git-credentials").read_text(encoding="utf-8") == (
        "https://Jonnyton:ghp_test_token@github.com\n"
    )
    assert (tmp_path / ".cowork-env").read_text(encoding="utf-8") == (
        "GH_TOKEN=ghp_test_token\n"
    )


def test_cowork_bootstrap_stays_read_only_without_token(tmp_path: Path) -> None:
    result = _run(tmp_path)

    assert result.returncode == 0
    assert "Cowork stays read-only" in result.stdout
    assert not (tmp_path / ".git-credentials").exists()
    assert not (tmp_path / ".cowork-env").exists()
