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
import sys
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
) -> tuple[subprocess.CompletedProcess, Path]:
    """Run the entrypoint with a temp HOME + stubbed data file.

    Returns (process result, auth_file_path).
    """
    # Synthesize a HOME with optional pre-existing auth.json.
    home = tmp_path / "home"
    codex_dir = home / ".codex"
    codex_dir.mkdir(parents=True)
    auth_file = codex_dir / "auth.json"
    if create_existing_auth is not None:
        auth_file.write_text(create_existing_auth, encoding="utf-8")
        # Match the chmod 600 the entrypoint would have set.
        try:
            auth_file.chmod(0o600)
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
        "WORKFLOW_IMAGE": "test:stub",
        # Keep API-key stripping silent (truthy).
        "WORKFLOW_ALLOW_API_KEY_PROVIDERS": "0",
        "HOME": _bash_path(home),
        "WORKFLOW_PACKAGE_ROOT": _bash_path(pkg_root),
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
        # Drop any inherited codex env that would confuse the test.
        full_env.pop("WORKFLOW_CODEX_AUTH_JSON_B64", None)
        if "WORKFLOW_CODEX_AUTH_JSON_B64" in env_extra:
            full_env["WORKFLOW_CODEX_AUTH_JSON_B64"] = env_extra[
                "WORKFLOW_CODEX_AUTH_JSON_B64"
            ]
        cmd = [_BASH, _bash_path(ENTRYPOINT), *cmd_args]
        result = subprocess.run(
            cmd, capture_output=True, text=True, env=full_env
        )
    return result, auth_file


def _b64(payload: str) -> str:
    return base64.b64encode(payload.encode("utf-8")).decode("ascii")


# ---------------------------------------------------------------------------
# Branch 1: env set + file missing -> seed
# ---------------------------------------------------------------------------


def test_seeds_auth_when_env_set_and_file_missing(tmp_path):
    seed_payload = '{"OPENAI_API_KEY":"sk-seeded","tokens":{"id_token":"seeded"}}'
    result, auth_file = _run_entrypoint(
        tmp_path,
        env_extra={"WORKFLOW_CODEX_AUTH_JSON_B64": _b64(seed_payload)},
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
    WORKFLOW_CODEX_AUTH_JSON_B64 value on container restart.
    """
    rotated_payload = '{"tokens":{"refresh_token":"rotated-fresh-token-v3"}}'
    stale_env_payload = '{"tokens":{"refresh_token":"stale-bootstrap-token-v1"}}'
    result, auth_file = _run_entrypoint(
        tmp_path,
        env_extra={"WORKFLOW_CODEX_AUTH_JSON_B64": _b64(stale_env_payload)},
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
    result, auth_file = _run_entrypoint(
        tmp_path,
        env_extra={},  # no WORKFLOW_CODEX_AUTH_JSON_B64
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
