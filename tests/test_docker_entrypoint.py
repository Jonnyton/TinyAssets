"""Tests for deploy/docker-entrypoint.sh codex auth conditional.

The entrypoint must NOT overwrite a present `auth.json` on container
start. Codex CLI rotates single-use OAuth refresh tokens in-place;
overwriting on every restart throws away the rotated token and the
next refresh attempt hits `refresh_token_reused`. Triggered the
2026-05-20 production codex outage.

Design source: https://developers.openai.com/codex/auth/ci-cd-auth

Three-branch behavior verified here:
  1. env set, file missing  -> seed (first boot / volume recovery)
  2. env set, file present  -> preserve (in-place refresh chain alive)
  3. env unset, file present -> preserve (volume-only operation)
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


def _run_entrypoint(
    tmp_path: Path,
    env_extra: dict,
    *,
    create_existing_auth: str | None = None,
    create_existing_claude_cred: str | None = None,
) -> tuple[subprocess.CompletedProcess, Path, Path]:
    """Run the entrypoint with temp HOME/CODEX_HOME/CLAUDE_CONFIG_DIR.

    Returns (process result, codex_auth_file_path, claude_credentials_path).
    """
    # Synthesize HOME plus a persistent CODEX_HOME with optional
    # pre-existing auth.json.
    home = tmp_path / "home"
    home.mkdir(parents=True)
    codex_dir = tmp_path / "codex-home"
    codex_dir.mkdir(parents=True)
    auth_file = codex_dir / "auth.json"
    if create_existing_auth is not None:
        auth_file.write_text(create_existing_auth, encoding="utf-8")
        # Match the chmod 600 the entrypoint would have set.
        try:
            auth_file.chmod(0o600)
        except OSError:
            pass

    # Persistent CLAUDE_CONFIG_DIR with optional pre-existing credentials.
    claude_dir = tmp_path / "claude-config"
    claude_dir.mkdir(parents=True)
    claude_cred = claude_dir / ".credentials.json"
    if create_existing_claude_cred is not None:
        claude_cred.write_text(create_existing_claude_cred, encoding="utf-8")
        try:
            claude_cred.chmod(0o600)
        except OSError:
            pass

    # Stub the required data file the entrypoint checks for so it doesn't
    # blow up before reaching the codex branch / exec.
    pkg_root = tmp_path / "pkg"
    (pkg_root / "data").mkdir(parents=True)
    (pkg_root / "data" / "world_rules.lp").write_text("% stub\n", encoding="utf-8")

    # CMD must succeed (we're not testing the real daemon). `true`
    # is on PATH everywhere bash runs.
    cmd_args = ["true"]

    env = {
        # ENV-UNREADABLE sentinel — at least one must be set.
        "TINYASSETS_IMAGE": "test:stub",
        # Keep API-key stripping silent (truthy).
        "TINYASSETS_ALLOW_API_KEY_PROVIDERS": "0",
        "HOME": _bash_path(home),
        "CODEX_HOME": _bash_path(codex_dir),
        "CLAUDE_CONFIG_DIR": _bash_path(claude_dir),
        "TINYASSETS_PACKAGE_ROOT": _bash_path(pkg_root),
    }
    env.update(env_extra)

    if _is_wsl_bash():
        assignments = " ".join(
            f"{name}={shlex.quote(str(value))}"
            for name, value in env.items()
        )
        command = " ".join(
            [
                "/usr/bin/env",
                assignments,
                shlex.quote(_bash_path(ENTRYPOINT)),
                *(shlex.quote(arg) for arg in cmd_args),
            ]
        )
        result = subprocess.run(
            [_BASH, "-lc", command], capture_output=True, text=True
        )
    else:
        full_env = {**os.environ, **env}
        # Drop any inherited codex/claude auth env that would confuse the test,
        # then re-add only what env_extra explicitly provides.
        for _var in (
            "TINYASSETS_CODEX_AUTH_JSON_B64",
            "TINYASSETS_CLAUDE_CREDENTIALS_JSON_B64",
            "CLAUDE_CODE_OAUTH_TOKEN",
        ):
            full_env.pop(_var, None)
            if _var in env_extra:
                full_env[_var] = env_extra[_var]
        cmd = [_BASH, _bash_path(ENTRYPOINT), *cmd_args]
        result = subprocess.run(
            cmd, capture_output=True, text=True, env=full_env
        )
    return result, auth_file, claude_cred


def _b64(payload: str) -> str:
    return base64.b64encode(payload.encode("utf-8")).decode("ascii")


# ---------------------------------------------------------------------------
# Branch 1: env set + file missing -> seed
# ---------------------------------------------------------------------------


def test_seeds_auth_when_env_set_and_file_missing(tmp_path):
    seed_payload = '{"OPENAI_API_KEY":"sk-seeded","tokens":{"id_token":"seeded"}}'
    result, auth_file, _ = _run_entrypoint(
        tmp_path,
        env_extra={"TINYASSETS_CODEX_AUTH_JSON_B64": _b64(seed_payload)},
        create_existing_auth=None,
    )
    # First start: prep code creates parent dir; this test pre-creates it
    # to mirror what the volume mount would. We remove the empty
    # auth.json scenario by deleting the file the helper would have
    # made — but the helper only creates it when create_existing_auth is
    # not None. Confirm baseline.
    assert result.returncode == 0, (
        f"entrypoint exit {result.returncode}\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    assert auth_file.exists(), "auth.json should have been seeded"
    assert auth_file.read_text(encoding="utf-8") == seed_payload
    assert "seeding codex auth.json" in (result.stdout + result.stderr)


# ---------------------------------------------------------------------------
# Branch 2: env set + file present -> preserve (the regression-blocker)
# ---------------------------------------------------------------------------


def test_preserves_auth_when_env_set_and_file_present(tmp_path):
    """REGRESSION GUARD for 2026-05-20 outage.

    A rotated auth.json must NOT be overwritten by an older
    TINYASSETS_CODEX_AUTH_JSON_B64 value on container restart.
    """
    rotated_payload = '{"tokens":{"refresh_token":"rotated-fresh-token-v3"}}'
    stale_env_payload = '{"tokens":{"refresh_token":"stale-bootstrap-token-v1"}}'
    result, auth_file, _ = _run_entrypoint(
        tmp_path,
        env_extra={"TINYASSETS_CODEX_AUTH_JSON_B64": _b64(stale_env_payload)},
        create_existing_auth=rotated_payload,
    )
    assert result.returncode == 0, (
        f"entrypoint exit {result.returncode}\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    assert auth_file.exists()
    assert auth_file.read_text(encoding="utf-8") == rotated_payload, (
        "rotated auth.json must be preserved verbatim across restart; "
        "stale env-var payload must NOT overwrite it"
    )
    combined = result.stdout + result.stderr
    assert "preserving existing codex auth.json" in combined
    assert "seeding codex auth.json" not in combined


# ---------------------------------------------------------------------------
# Branch 3: env unset + file present -> preserve (volume-only operation)
# ---------------------------------------------------------------------------


def test_preserves_auth_when_env_unset_and_file_present(tmp_path):
    rotated_payload = '{"tokens":{"refresh_token":"volume-only-token"}}'
    result, auth_file, _ = _run_entrypoint(
        tmp_path,
        env_extra={},  # no TINYASSETS_CODEX_AUTH_JSON_B64
        create_existing_auth=rotated_payload,
    )
    assert result.returncode == 0, (
        f"entrypoint exit {result.returncode}\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    assert auth_file.exists()
    assert auth_file.read_text(encoding="utf-8") == rotated_payload
    combined = result.stdout + result.stderr
    assert "preserving existing codex auth.json" in combined
    assert "seeding codex auth.json" not in combined


# ---------------------------------------------------------------------------
# Claude auth seeding — mirrors the codex branches (2026-06-25 loop-wedge fix)
# ---------------------------------------------------------------------------


def test_seeds_claude_credentials_when_env_set_and_file_missing(tmp_path):
    seed_payload = '{"claudeAiOauth":{"accessToken":"seeded-tok"}}'
    result, _, claude_cred = _run_entrypoint(
        tmp_path,
        env_extra={"TINYASSETS_CLAUDE_CREDENTIALS_JSON_B64": _b64(seed_payload)},
        create_existing_claude_cred=None,
    )
    assert result.returncode == 0, (
        f"entrypoint exit {result.returncode}\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    assert claude_cred.exists(), ".credentials.json should have been seeded"
    assert claude_cred.read_text(encoding="utf-8") == seed_payload
    assert "seeding claude credentials" in (result.stdout + result.stderr)


def test_preserves_claude_credentials_when_env_set_and_file_present(tmp_path):
    """A rotated .credentials.json must NOT be overwritten by a stale B64."""
    rotated = '{"claudeAiOauth":{"refreshToken":"rotated-fresh"}}'
    stale = '{"claudeAiOauth":{"refreshToken":"stale-bootstrap"}}'
    result, _, claude_cred = _run_entrypoint(
        tmp_path,
        env_extra={"TINYASSETS_CLAUDE_CREDENTIALS_JSON_B64": _b64(stale)},
        create_existing_claude_cred=rotated,
    )
    assert result.returncode == 0
    assert claude_cred.read_text(encoding="utf-8") == rotated, (
        "rotated claude credentials must be preserved; stale B64 must not win"
    )
    combined = result.stdout + result.stderr
    assert "preserving existing claude credentials" in combined
    assert "seeding claude credentials" not in combined


def test_claude_env_token_used_when_no_credentials_file(tmp_path):
    result, _, claude_cred = _run_entrypoint(
        tmp_path,
        env_extra={"CLAUDE_CODE_OAUTH_TOKEN": "sk-ant-oat-stub"},
        create_existing_claude_cred=None,
    )
    assert result.returncode == 0
    assert not claude_cred.exists(), "env-token path must not write a file"
    assert "using CLAUDE_CODE_OAUTH_TOKEN" in (result.stdout + result.stderr)


def test_claude_warns_when_no_auth_present(tmp_path):
    result, _, claude_cred = _run_entrypoint(
        tmp_path,
        env_extra={},
        create_existing_claude_cred=None,
    )
    assert result.returncode == 0, "missing claude auth warns, never aborts boot"
    assert not claude_cred.exists()
    assert "no claude credentials present" in (result.stdout + result.stderr)
