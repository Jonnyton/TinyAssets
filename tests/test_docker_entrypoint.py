"""Cloud entrypoint rejects ambient provider authority."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from tinyassets.providers.base import AMBIENT_PROVIDER_AUTH_ENV_VARS

REPO = Path(__file__).resolve().parent.parent
ENTRYPOINT = REPO / "deploy" / "docker-entrypoint.sh"
_BASH = shutil.which("bash")
pytestmark = pytest.mark.skipif(_BASH is None, reason="bash not available")


def _bash_path(path: Path) -> str:
    resolved = path.resolve()
    if os.name != "nt":
        return str(resolved)
    return resolved.as_posix()


def _package_root(tmp_path: Path, *, include_data: bool = True) -> Path:
    root = tmp_path / "pkg"
    (root / "data").mkdir(parents=True)
    if include_data:
        (root / "data" / "world_rules.lp").write_text("% stub\n", encoding="utf-8")
    return root


def _run(tmp_path: Path, extra: dict[str, str], *, include_data: bool = True):
    env = {
        **os.environ,
        "TINYASSETS_IMAGE": "test:stub",
        "TINYASSETS_PACKAGE_ROOT": _bash_path(
            _package_root(tmp_path, include_data=include_data)
        ),
        **extra,
    }
    names = " ".join(AMBIENT_PROVIDER_AUTH_ENV_VARS)
    command = f'for name in {names}; do test -z "${{!name:-}}" || exit 91; done'
    return subprocess.run(
        [_BASH, _bash_path(ENTRYPOINT), _BASH, "-c", command],
        capture_output=True,
        text=True,
        env=env,
    )


def test_ambient_provider_credentials_are_removed_before_command(tmp_path: Path) -> None:
    result = _run(
        tmp_path,
        {name: f"host-{name.lower()}" for name in AMBIENT_PROVIDER_AUTH_ENV_VARS},
    )

    assert result.returncode == 0, result.stderr
    assert "removing ambient provider authority" in result.stderr


def test_entrypoint_strip_list_matches_canonical_provider_auth_surface() -> None:
    text = ENTRYPOINT.read_text(encoding="utf-8")
    match = re.search(r"_ambient_provider_env=\(\s*(.*?)\s*\)", text, re.DOTALL)
    assert match is not None
    assert tuple(match.group(1).split()) == AMBIENT_PROVIDER_AUTH_ENV_VARS


def test_empty_env_file_sentinel_fails_loudly(tmp_path: Path) -> None:
    env = {
        **os.environ,
        "TINYASSETS_PACKAGE_ROOT": _bash_path(_package_root(tmp_path)),
        "CLOUDFLARE_TUNNEL_TOKEN": "",
        "SUPABASE_DB_URL": "",
        "TINYASSETS_IMAGE": "",
    }
    result = subprocess.run(
        [_BASH, _bash_path(ENTRYPOINT), "true"],
        capture_output=True,
        text=True,
        env=env,
    )

    assert result.returncode == 1
    assert "ENV-UNREADABLE" in result.stderr


def test_missing_static_data_fails_loudly(tmp_path: Path) -> None:
    result = _run(tmp_path, {}, include_data=False)

    assert result.returncode == 1
    assert "DATA-FILE-MISSING: data/world_rules.lp" in result.stderr
