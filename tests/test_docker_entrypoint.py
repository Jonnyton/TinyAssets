"""Tests for deploy/docker-entrypoint.sh: the platform holds no model credential.

AGENTS.md Hard Rule 15. Until 2026-09-24 the entrypoint kept platform Codex and
Claude CLI logins on the data volume, seeded them from base64 bundles, honoured
``CLAUDE_CODE_OAUTH_TOKEN``, and let ``TINYASSETS_ALLOW_API_KEY_PROVIDERS=1``
admit host API keys. All of that is retired. What these tests pin is the
ABSENCE: whatever credential names the container is handed, the daemon process
(the exec'd CMD) sees none of them, no login is written or preserved, no
bundle is decoded, the opt-in switch changes nothing, and only NAMES reach the
log.
"""

from __future__ import annotations

import base64
import os
import shlex
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
ENTRYPOINT = REPO / "deploy" / "docker-entrypoint.sh"

_BASH = shutil.which("bash")

pytestmark = pytest.mark.skipif(_BASH is None, reason="bash not available")

#: Mirrors tests/test_no_platform_llm_credentials.py. Every one of these must be
#: gone from the daemon's environment no matter how it arrived.
PLATFORM_LLM_CREDENTIAL_ENV = (
    "CODEX_HOME",
    "CLAUDE_CONFIG_DIR",
    "CLAUDE_CODE_OAUTH_TOKEN",
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_BASE_URL",
    "GEMINI_API_KEY",
    "GOOGLE_API_KEY",
    "GROQ_API_KEY",
    "XAI_API_KEY",
    "TINYASSETS_ALLOW_API_KEY_PROVIDERS",
    "TINYASSETS_CODEX_AUTH_JSON_B64",
    "TINYASSETS_CLAUDE_CREDENTIALS_JSON_B64",
    "WORKFLOW_CODEX_AUTH_JSON_B64",
    "WORKFLOW_CLAUDE_CREDENTIALS_JSON_B64",
)


def _is_wsl_bash() -> bool:
    return (
        os.name == "nt"
        and _BASH is not None
        and Path(_BASH).name.lower() == "bash.exe"
        and "system32" in str(Path(_BASH).parent).lower()
    )


def _bash_path(path: Path) -> str:
    resolved = path.resolve()
    if os.name != "nt":
        return str(resolved)
    if _is_wsl_bash():
        drive = resolved.drive.rstrip(":").lower()
        rest = resolved.as_posix()[2:]
        return f"/mnt/{drive}{rest}"
    return resolved.as_posix()


def _run_entrypoint(tmp_path: Path, env_extra: dict[str, str]) -> subprocess.CompletedProcess:
    """Run the entrypoint with CMD=`env`, so stdout is the daemon's environment."""
    pkg_root = tmp_path / "pkg"
    (pkg_root / "data").mkdir(parents=True)
    (pkg_root / "data" / "world_rules.lp").write_text("% stub\n", encoding="utf-8")
    home = tmp_path / "home"
    home.mkdir()

    env = {
        # ENV-UNREADABLE sentinel: at least one must be set.
        "TINYASSETS_IMAGE": "test:stub",
        "HOME": _bash_path(home),
        "TINYASSETS_PACKAGE_ROOT": _bash_path(pkg_root),
    }
    env.update(env_extra)

    if _is_wsl_bash():
        assignments = " ".join(
            f"{name}={shlex.quote(str(value))}" for name, value in env.items()
        )
        command = " ".join(
            ["/usr/bin/env", assignments, shlex.quote(_bash_path(ENTRYPOINT)), "env"]
        )
        return subprocess.run([_BASH, "-lc", command], capture_output=True, text=True)

    full_env = {
        name: value
        for name, value in os.environ.items()
        if name not in PLATFORM_LLM_CREDENTIAL_ENV
    }
    full_env.update(env)
    return subprocess.run(
        [_BASH, _bash_path(ENTRYPOINT), "env"],
        capture_output=True,
        text=True,
        env=full_env,
    )


def _daemon_env_names(result: subprocess.CompletedProcess) -> set[str]:
    return {
        line.split("=", 1)[0]
        for line in result.stdout.splitlines()
        if "=" in line
    }


def _b64(payload: str) -> str:
    return base64.b64encode(payload.encode("utf-8")).decode("ascii")


def test_every_platform_credential_is_removed_before_the_daemon_starts(tmp_path):
    secret_values = {
        name: f"sentinel-{name.lower()}-do-not-leak" for name in PLATFORM_LLM_CREDENTIAL_ENV
    }
    result = _run_entrypoint(tmp_path, secret_values)

    assert result.returncode == 0, result.stderr
    leaked = _daemon_env_names(result) & set(PLATFORM_LLM_CREDENTIAL_ENV)
    assert not leaked, f"daemon still sees platform LLM credentials: {sorted(leaked)}"
    for name in PLATFORM_LLM_CREDENTIAL_ENV:
        assert f"removing {name}" in result.stderr, f"{name} removal not logged"
    for value in secret_values.values():
        assert value not in result.stderr, "a credential VALUE reached the log"
        assert value not in result.stdout


def test_opt_in_switch_no_longer_admits_api_keys(tmp_path):
    result = _run_entrypoint(
        tmp_path,
        {"TINYASSETS_ALLOW_API_KEY_PROVIDERS": "1", "GEMINI_API_KEY": "g", "OPENAI_API_KEY": "o"},
    )

    assert result.returncode == 0, result.stderr
    names = _daemon_env_names(result)
    assert "GEMINI_API_KEY" not in names
    assert "OPENAI_API_KEY" not in names
    assert "TINYASSETS_ALLOW_API_KEY_PROVIDERS" not in names
    assert "explicitly enabled" not in result.stderr


def test_no_login_is_seeded_decoded_or_preserved(tmp_path):
    codex_home = tmp_path / "codex-home"
    claude_dir = tmp_path / "claude-config"
    result = _run_entrypoint(
        tmp_path,
        {
            "CODEX_HOME": _bash_path(codex_home),
            "CLAUDE_CONFIG_DIR": _bash_path(claude_dir),
            "TINYASSETS_CODEX_AUTH_JSON_B64": _b64('{"tokens":{"refresh_token":"x"}}'),
            "TINYASSETS_CLAUDE_CREDENTIALS_JSON_B64": _b64('{"claudeAiOauth":{}}'),
        },
    )

    assert result.returncode == 0, result.stderr
    assert not codex_home.exists(), "entrypoint created a platform Codex login home"
    assert not claude_dir.exists(), "entrypoint created a platform Claude config dir"
    combined = result.stdout + result.stderr
    for retired in ("seeding", "preserving existing", "auth.json", ".credentials.json"):
        assert retired not in combined, f"entrypoint still handles a login: {retired!r}"


def test_clean_environment_logs_nothing_about_credentials(tmp_path):
    result = _run_entrypoint(tmp_path, {})

    assert result.returncode == 0, result.stderr
    assert "removing" not in result.stderr
    assert not _daemon_env_names(result) & set(PLATFORM_LLM_CREDENTIAL_ENV)


def test_an_empty_value_is_still_removed(tmp_path):
    # `KEY=` in an env file still defines the name; the daemon must not see it.
    result = _run_entrypoint(tmp_path, {"CLAUDE_CODE_OAUTH_TOKEN": ""})

    assert result.returncode == 0, result.stderr
    assert "CLAUDE_CODE_OAUTH_TOKEN" not in _daemon_env_names(result)
