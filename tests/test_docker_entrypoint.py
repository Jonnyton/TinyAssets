"""Runtime tests for the production control-plane container entrypoint."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
ENTRYPOINT = ROOT / "deploy" / "docker-entrypoint.sh"
_BASH = shutil.which("bash")

pytestmark = pytest.mark.skipif(_BASH is None, reason="bash not available")


def _bash_path(path: Path) -> str:
    resolved = path.resolve()
    if os.name != "nt":
        return str(resolved)
    drive = resolved.drive.rstrip(":").lower()
    if _BASH and "system32" in str(Path(_BASH).parent).lower():
        return f"/mnt/{drive}{resolved.as_posix()[2:]}"
    return resolved.as_posix()


def _run(tmp_path: Path, extra_env: dict[str, str]) -> subprocess.CompletedProcess:
    package_root = tmp_path / "package"
    (package_root / "data").mkdir(parents=True)
    (package_root / "data" / "world_rules.lp").write_text("% stub\n")
    env = {
        **os.environ,
        "TINYASSETS_IMAGE": "test:stub",
        "TINYASSETS_PACKAGE_ROOT": _bash_path(package_root),
        **extra_env,
    }
    return subprocess.run(
        [_BASH, _bash_path(ENTRYPOINT), "true"],
        capture_output=True,
        text=True,
        env=env,
    )


def test_entrypoint_does_not_create_provider_auth_homes(tmp_path):
    codex_home = tmp_path / "codex-home"
    claude_home = tmp_path / "claude-home"
    result = _run(
        tmp_path,
        {
            "CODEX_HOME": _bash_path(codex_home),
            "CLAUDE_CONFIG_DIR": _bash_path(claude_home),
            "TINYASSETS_CODEX_AUTH_JSON_B64": "e30=",
            "TINYASSETS_CLAUDE_CREDENTIALS_JSON_B64": "e30=",
            "CLAUDE_CODE_OAUTH_TOKEN": "test-token",
        },
    )

    assert result.returncode == 0, result.stderr
    assert not codex_home.exists()
    assert not claude_home.exists()


def test_entrypoint_does_not_mutate_existing_provider_auth_homes(tmp_path):
    codex_home = tmp_path / "codex-home"
    claude_home = tmp_path / "claude-home"
    codex_home.mkdir()
    claude_home.mkdir()
    auth = codex_home / "auth.json"
    credentials = claude_home / ".credentials.json"
    auth.write_text("codex-original", encoding="utf-8")
    credentials.write_text("claude-original", encoding="utf-8")

    result = _run(
        tmp_path,
        {
            "CODEX_HOME": _bash_path(codex_home),
            "CLAUDE_CONFIG_DIR": _bash_path(claude_home),
            "TINYASSETS_CODEX_AUTH_JSON_B64": "e30=",
            "TINYASSETS_CLAUDE_CREDENTIALS_JSON_B64": "e30=",
        },
    )

    assert result.returncode == 0, result.stderr
    assert auth.read_text(encoding="utf-8") == "codex-original"
    assert credentials.read_text(encoding="utf-8") == "claude-original"


def test_entrypoint_strips_provider_api_keys_even_with_legacy_opt_in(tmp_path):
    result = _run(
        tmp_path,
        {
            "TINYASSETS_ALLOW_API_KEY_PROVIDERS": "1",
            "OPENAI_API_KEY": "secret",
            "ANTHROPIC_API_KEY": "secret",
        },
    )

    assert result.returncode == 0, result.stderr
    assert "ignoring OPENAI_API_KEY" in result.stderr
    assert "ignoring ANTHROPIC_API_KEY" in result.stderr
