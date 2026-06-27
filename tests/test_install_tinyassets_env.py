"""Regression tests for deploy/install-tinyassets-env.sh.

The production rename deploy failed because the helper treated a missing
/etc/tinyassets/env as fatal before the renamed image could roll out. These
tests run the helper against tmp_path files and never touch /etc.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest


_REPO = Path(__file__).resolve().parents[1]
_SCRIPT = _REPO / "deploy" / "install-tinyassets-env.sh"


def test_helper_knows_renamed_env_can_bootstrap_from_legacy_file():
    text = _SCRIPT.read_text(encoding="utf-8")
    assert 'LEGACY_ENV_FILE="${TINYASSETS_LEGACY_ENV_FILE-/etc/workflow/env}"' in text
    assert "ensure_env_file" in text
    assert "ensure_owner_principals" in text
    assert "groupadd --system" in text
    assert "useradd" in text
    assert "usermod -aG docker" in text
    assert "missing — bootstrap should have created it" not in text


@pytest.mark.skipif(
    os.name == "nt" or shutil.which("bash") is None,
    reason="shell helper is exercised on POSIX CI; Windows test stays structural",
)
def test_delete_bootstraps_from_legacy_env(tmp_path):
    env_file = tmp_path / "tinyassets" / "env"
    legacy_file = tmp_path / "workflow" / "env"
    legacy_file.parent.mkdir()
    legacy_file.write_text("KEEP=1\nTINYASSETS_UNIVERSE=/old\n", encoding="utf-8")

    result = _run_helper(
        tmp_path,
        ["delete", "TINYASSETS_UNIVERSE"],
        env_file=env_file,
        legacy_file=legacy_file,
    )

    assert result.returncode == 0, result.stderr
    assert env_file.read_text(encoding="utf-8") == "KEEP=1\n"
    assert "bootstrapping from" in result.stderr


@pytest.mark.skipif(
    os.name == "nt" or shutil.which("bash") is None,
    reason="shell helper is exercised on POSIX CI; Windows test stays structural",
)
def test_set_creates_empty_env_when_no_legacy_file_exists(tmp_path):
    env_file = tmp_path / "tinyassets" / "env"
    legacy_file = tmp_path / "workflow" / "env"

    result = _run_helper(
        tmp_path,
        ["set", "TINYASSETS_IMAGE"],
        stdin="ghcr.io/jonnyton/tinyassets-daemon@sha256:abc\n",
        env_file=env_file,
        legacy_file=legacy_file,
    )

    assert result.returncode == 0, result.stderr
    assert (
        env_file.read_text(encoding="utf-8")
        == "TINYASSETS_IMAGE=ghcr.io/jonnyton/tinyassets-daemon@sha256:abc\n"
    )
    assert "creating empty env file" in result.stderr


def _run_helper(
    tmp_path: Path,
    args: list[str],
    *,
    env_file: Path,
    legacy_file: Path,
    stdin: str = "",
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.update(
        {
            "TINYASSETS_ENV_FILE": str(env_file),
            "TINYASSETS_LEGACY_ENV_FILE": str(legacy_file),
            "TINYASSETS_ENV_OWNER": "",
            "TINYASSETS_ENV_READ_USER": "",
        }
    )
    return subprocess.run(
        ["bash", str(_SCRIPT), *args],
        input=stdin,
        text=True,
        capture_output=True,
        cwd=tmp_path,
        env=env,
        check=False,
    )
