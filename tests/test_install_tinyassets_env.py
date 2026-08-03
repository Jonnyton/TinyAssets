"""Regression tests for deploy/install-tinyassets-env.sh.

The production rename deploy failed because the helper treated a missing
/etc/tinyassets/env as fatal before the renamed image could roll out. These
tests run the helper against tmp_path files and never touch /etc.
"""

from __future__ import annotations

import json
import os
import shutil
import stat
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
    assert '-v v="${value}"' not in text
    assert "set-once" in text


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
    assert not list(env_file.parent.glob("env.value.*"))


@pytest.mark.skipif(
    os.name == "nt" or shutil.which("bash") is None,
    reason="shell helper is exercised on POSIX CI; Windows test stays structural",
)
def test_set_once_refuses_secret_rotation_without_exposing_values(tmp_path):
    env_file = tmp_path / "tinyassets" / "request-idempotency.env"
    legacy_file = tmp_path / "never" / "legacy"
    original = "first-secret-value"
    replacement = "different-secret-value"

    first = _run_helper(
        tmp_path,
        ["set-once", "TINYASSETS_REQUEST_IDEMPOTENCY_HMAC_KEY"],
        stdin=original,
        env_file=env_file,
        legacy_file=legacy_file,
    )
    second = _run_helper(
        tmp_path,
        ["set-once", "TINYASSETS_REQUEST_IDEMPOTENCY_HMAC_KEY"],
        stdin=replacement,
        env_file=env_file,
        legacy_file=legacy_file,
    )
    env_file.chmod(0o666)
    repair = _run_helper(
        tmp_path,
        ["set-once", "TINYASSETS_REQUEST_IDEMPOTENCY_HMAC_KEY"],
        stdin=original,
        env_file=env_file,
        legacy_file=legacy_file,
    )

    assert first.returncode == 0, first.stderr
    assert second.returncode != 0
    assert repair.returncode == 0, repair.stderr
    assert stat.S_IMODE(env_file.stat().st_mode) == 0o640
    assert env_file.read_text(encoding="utf-8") == (
        "TINYASSETS_REQUEST_IDEMPOTENCY_HMAC_KEY=first-secret-value\n"
    )
    combined = second.stdout + second.stderr
    assert original not in combined
    assert replacement not in combined


def test_set_once_same_value_still_uses_permission_repair_path():
    text = _SCRIPT.read_text(encoding="utf-8")
    immutable_block = text.split('if [ "${immutable}" = "true" ]', 1)[1].split(
        "# Build new content", 1
    )[0]
    assert "return 0" not in immutable_block
    assert "atomic_install" in text.split("cmd_set()", 1)[1].split("cmd_delete()", 1)[0]


def test_set_once_has_duplicate_assignment_guard_before_write():
    text = _SCRIPT.read_text(encoding="utf-8")
    set_body = text.split("cmd_set()", 1)[1].split("cmd_delete()", 1)[0]
    immutable_block = text.split('if [ "${immutable}" = "true" ]', 1)[1].split(
        "# Build new content", 1
    )[0]
    assert "assignment_count" in immutable_block
    assert "duplicate assignments" in immutable_block
    assert set_body.index("duplicate assignments") < set_body.index("atomic_install")


@pytest.mark.skipif(
    os.name == "nt" or shutil.which("bash") is None,
    reason="shell helper is exercised on POSIX CI; Windows test stays structural",
)
@pytest.mark.parametrize(
    "first_assignment",
    [
        "TINYASSETS_REQUEST_IDEMPOTENCY_HMAC_KEY=old-secret",
        "export TINYASSETS_REQUEST_IDEMPOTENCY_HMAC_KEY=old-secret",
        "  TINYASSETS_REQUEST_IDEMPOTENCY_HMAC_KEY=old-secret",
        "TINYASSETS_REQUEST_IDEMPOTENCY_HMAC_KEY =old-secret",
        "\texport\tTINYASSETS_REQUEST_IDEMPOTENCY_HMAC_KEY\t=old-secret",
        "TINYASSETS_REQUEST_IDEMPOTENCY_HMAC_KEY: old-secret",
        "  export TINYASSETS_REQUEST_IDEMPOTENCY_HMAC_KEY : old-secret",
    ],
)
def test_set_once_rejects_duplicate_assignments_before_mutation(
    tmp_path, first_assignment: str
):
    env_file = tmp_path / "tinyassets" / "request-idempotency.env"
    legacy_file = tmp_path / "never" / "legacy"
    env_file.parent.mkdir(parents=True)
    original = first_assignment + "\nTINYASSETS_REQUEST_IDEMPOTENCY_HMAC_KEY=\n"
    env_file.write_text(original, encoding="utf-8")
    replacement = "replacement-secret"

    result = _run_helper(
        tmp_path,
        ["set-once", "TINYASSETS_REQUEST_IDEMPOTENCY_HMAC_KEY"],
        stdin=replacement,
        env_file=env_file,
        legacy_file=legacy_file,
    )

    assert result.returncode == 5
    assert env_file.read_text(encoding="utf-8") == original
    assert "old-secret" not in result.stdout + result.stderr
    assert replacement not in result.stdout + result.stderr


@pytest.mark.skipif(
    os.name == "nt" or shutil.which("bash") is None,
    reason="shell helper is exercised on POSIX CI; Windows test stays structural",
)
def test_delete_removes_every_compose_recognized_assignment_shape(tmp_path):
    env_file = tmp_path / "tinyassets" / "env"
    legacy_file = tmp_path / "never" / "legacy"
    env_file.parent.mkdir(parents=True)
    env_file.write_text(
        "KEEP=1\n"
        "export TARGET=one\n"
        "  TARGET=two\n"
        "TARGET =three\n"
        "\texport\tTARGET\t=four\n"
        "TARGET: five\n"
        "  export TARGET : six\n",
        encoding="utf-8",
    )

    result = _run_helper(
        tmp_path,
        ["delete", "TARGET"],
        env_file=env_file,
        legacy_file=legacy_file,
    )

    assert result.returncode == 0, result.stderr
    assert env_file.read_text(encoding="utf-8") == "KEEP=1\n"


@pytest.mark.skipif(
    os.name == "nt" or shutil.which("bash") is None,
    reason="shell helper is exercised on POSIX CI; Windows test stays structural",
)
@pytest.mark.parametrize(
    "assignment",
    [
        "TARGET=secret",
        "export TARGET=secret",
        "  TARGET =secret",
        "TARGET: secret",
        "  export TARGET : secret",
    ],
)
def test_assert_absent_rejects_every_compose_assignment_shape(
    tmp_path, assignment: str
):
    env_file = tmp_path / "tinyassets" / "env"
    legacy_file = tmp_path / "never" / "legacy"
    env_file.parent.mkdir(parents=True)
    env_file.write_text(f"KEEP=1\n{assignment}\n", encoding="utf-8")

    result = _run_helper(
        tmp_path,
        ["assert-absent", "TARGET"],
        env_file=env_file,
        legacy_file=legacy_file,
    )

    assert result.returncode == 6
    assert "secret" not in result.stdout + result.stderr


@pytest.mark.skipif(
    os.name == "nt" or shutil.which("bash") is None,
    reason="shell helper is exercised on POSIX CI; Windows test stays structural",
)
def test_utf8_bom_first_assignment_cannot_bypass_protected_key_operations(tmp_path):
    env_file = tmp_path / "tinyassets" / "env"
    legacy_file = tmp_path / "never" / "legacy"
    env_file.parent.mkdir(parents=True)
    bom_only = "\ufeffTARGET: old-secret\nKEEP=1\n"
    env_file.write_text(bom_only, encoding="utf-8")

    absent = _run_helper(
        tmp_path,
        ["assert-absent", "TARGET"],
        env_file=env_file,
        legacy_file=legacy_file,
    )
    assert absent.returncode == 6
    assert env_file.read_text(encoding="utf-8") == bom_only

    duplicate = "\ufeffTARGET: old-secret\nTARGET=\nKEEP=1\n"
    env_file.write_text(duplicate, encoding="utf-8")
    immutable = _run_helper(
        tmp_path,
        ["set-once", "TARGET"],
        stdin="replacement-secret",
        env_file=env_file,
        legacy_file=legacy_file,
    )

    assert immutable.returncode == 5
    assert env_file.read_text(encoding="utf-8") == duplicate
    combined = absent.stdout + absent.stderr + immutable.stdout + immutable.stderr
    assert "old-secret" not in combined
    assert "replacement-secret" not in combined

    env_file.write_text(bom_only, encoding="utf-8")
    deleted = _run_helper(
        tmp_path,
        ["delete", "TARGET"],
        env_file=env_file,
        legacy_file=legacy_file,
    )
    assert deleted.returncode == 0, deleted.stderr
    assert env_file.read_text(encoding="utf-8") == "KEEP=1\n"


@pytest.mark.skipif(
    shutil.which("docker") is None,
    reason="requires the installed Docker Compose CLI grammar",
)
def test_installed_compose_resolves_bom_prefixed_colon_assignment(tmp_path):
    compose_file = tmp_path / "compose.yml"
    env_file = tmp_path / "probe.env"
    compose_file.write_text(
        "services:\n"
        "  probe:\n"
        "    image: alpine:3.20\n"
        "    env_file:\n"
        "      - ./probe.env\n",
        encoding="utf-8",
    )
    env_file.write_bytes(b"\xef\xbb\xbfTARGET: secret\n")

    result = subprocess.run(
        [
            "docker",
            "compose",
            "-f",
            str(compose_file),
            "config",
            "--format",
            "json",
        ],
        text=True,
        capture_output=True,
        cwd=tmp_path,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    model = json.loads(result.stdout)
    assert model["services"]["probe"]["environment"]["TARGET"] == "secret"


@pytest.mark.skipif(
    os.name == "nt" or shutil.which("bash") is None,
    reason="requires a POSIX file-size limit and real shell write failure",
)
def test_atomic_write_failure_preserves_original_file(tmp_path):
    env_file = tmp_path / "tinyassets" / "env"
    legacy_file = tmp_path / "never" / "legacy"
    env_file.parent.mkdir(parents=True)
    original = "KEEP=" + ("a" * 4096) + "\n"
    env_file.write_text(original, encoding="utf-8")

    env = os.environ.copy()
    env.update(
        {
            "TINYASSETS_ENV_FILE": str(env_file),
            "TINYASSETS_LEGACY_ENV_FILE": str(legacy_file),
            "TINYASSETS_ENV_OWNER": "",
            "TINYASSETS_ENV_READ_USER": "",
        }
    )
    result = subprocess.run(
        [
            "bash",
            "-c",
            'ulimit -f 1; exec bash "$@"',
            "bash",
            str(_SCRIPT),
            "set",
            "TARGET",
        ],
        input="b" * 4096,
        text=True,
        capture_output=True,
        cwd=tmp_path,
        env=env,
        check=False,
    )

    assert result.returncode != 0
    assert env_file.read_text(encoding="utf-8") == original
    assert not list(env_file.parent.glob(".env.tmp.*"))


def test_protected_value_never_uses_a_secret_only_plaintext_file():
    text = _SCRIPT.read_text(encoding="utf-8")
    set_body = text.split("cmd_set()", 1)[1].split("cmd_delete()", 1)[0]
    assert "VALUE_FILE" not in set_body
    assert "awk" not in set_body
    assert "coproc" not in set_body
    assert "compose_line_assigns_key" in set_body
    assert 'new_content+="${key}=${value}"' in set_body


def test_atomic_install_uses_sibling_transaction_and_rename():
    text = _SCRIPT.read_text(encoding="utf-8")
    transaction_body = text.split("prepare_atomic_temp()", 1)[1].split(
        "cmd_set()", 1
    )[0]
    assert "mktemp" in transaction_body
    assert "trap" in transaction_body
    assert "mv " in transaction_body
    assert "install_env_file /dev/stdin" not in transaction_body


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
