"""Regression tests for deploy/install-tinyassets-env.sh.

The production rename deploy failed because the helper treated a missing
/etc/tinyassets/env as fatal before the renamed image could roll out. These
tests run the helper against tmp_path files and never touch /etc.
"""

from __future__ import annotations

import os
import shutil
import signal
import stat
import subprocess
import time
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
def test_set_once_rejects_duplicate_assignments_before_mutation(tmp_path):
    env_file = tmp_path / "tinyassets" / "request-idempotency.env"
    legacy_file = tmp_path / "never" / "legacy"
    env_file.parent.mkdir(parents=True)
    original = (
        "TINYASSETS_REQUEST_IDEMPOTENCY_HMAC_KEY=old-secret\n"
        "TINYASSETS_REQUEST_IDEMPOTENCY_HMAC_KEY=\n"
    )
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


def test_protected_value_never_uses_a_named_plaintext_file():
    text = _SCRIPT.read_text(encoding="utf-8")
    set_body = text.split("cmd_set()", 1)[1].split("cmd_delete()", 1)[0]
    assert "mktemp" not in set_body
    assert "VALUE_FILE" not in set_body
    assert "/dev/fd/3" in set_body
    assert '3< <(printf \'%s\' "${value}")' in set_body
    assert "ACTIVE_BUILDER_PID" in text
    assert "stop_content_builder" in text
    assert "trap 'handle_signal TERM' TERM" in text


@pytest.mark.skipif(
    os.name == "nt" or shutil.which("bash") is None,
    reason="shell helper is exercised on POSIX CI; Windows test stays structural",
)
@pytest.mark.parametrize("exit_kind", ["failure", "term"])
def test_protected_value_file_is_removed_on_failure_or_signal(
    tmp_path, exit_kind: str
):
    env_file = tmp_path / "tinyassets" / "env"
    legacy_file = tmp_path / "never" / "legacy"
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    marker = tmp_path / "awk-started"
    fake_awk = fake_bin / "awk"
    if exit_kind == "failure":
        fake_awk.write_text("#!/usr/bin/env bash\nexit 19\n", encoding="utf-8")
    else:
        fake_awk.write_text(
            '#!/usr/bin/env bash\n: > "${AWK_MARKER}"\nexec sleep 30\n',
            encoding="utf-8",
        )
    fake_awk.chmod(0o755)

    env = os.environ.copy()
    env.update(
        {
            "TINYASSETS_ENV_FILE": str(env_file),
            "TINYASSETS_LEGACY_ENV_FILE": str(legacy_file),
            "TINYASSETS_ENV_OWNER": "",
            "TINYASSETS_ENV_READ_USER": "",
            "AWK_MARKER": str(marker),
            "PATH": f"{fake_bin}{os.pathsep}{env.get('PATH', '')}",
        }
    )
    protected = "never-print-this-protected-value"
    process = subprocess.Popen(
        ["bash", str(_SCRIPT), "set", "SECRET_VALUE"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        cwd=tmp_path,
        env=env,
        start_new_session=True,
    )
    assert process.stdin is not None
    process.stdin.write(protected)
    process.stdin.close()

    if exit_kind == "term":
        for _ in range(100):
            if marker.exists():
                break
            time.sleep(0.02)
        assert marker.exists(), "fake awk did not start after protected-value handoff"
        os.kill(process.pid, signal.SIGTERM)
        time.sleep(0.25)
        assert not list(env_file.parent.glob("env.value.*")), (
            "installer PID signal must not leave a plaintext value file while "
            "its child is still blocked"
        )
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass

    process.wait(timeout=5)
    stdout = process.stdout.read() if process.stdout else ""
    stderr = process.stderr.read() if process.stderr else ""
    assert process.returncode != 0
    assert not list(env_file.parent.glob("env.value.*"))
    assert protected not in stdout
    assert protected not in stderr


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
