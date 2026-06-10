"""Tests for deploy/backup.sh and deploy/backup-restore.sh.

Coverage:
  - shellcheck lint (skipped if shellcheck not installed)
  - DRY_RUN=1 exits 0 with no mutations (no tar, upload, or rclone calls)
  - Missing BACKUP_DEST exits 1 when DRY_RUN is not set
  - backup-restore.sh DRY_RUN=1 exits 0 after identifying target archive
  - backup-restore.sh missing BACKUP_DEST exits 1
  - Retention-policy logic: validated via scripts/backup_prune.py (canonical)
    daily-7 / weekly-4 / monthly-6 boundaries
"""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
BACKUP_SH = REPO / "deploy" / "backup.sh"
RESTORE_SH = REPO / "deploy" / "backup-restore.sh"
PRUNE_PY = REPO / "scripts" / "backup_prune.py"

# Import the canonical retention logic directly from the script.
sys.path.insert(0, str(REPO / "scripts"))
from backup_prune import _apply_retention  # noqa: E402

_SHELLCHECK = shutil.which("shellcheck")
_BASH = shutil.which("bash")

pytestmark = pytest.mark.skipif(_BASH is None, reason="bash not available")


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


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


def _bash_path_env(*leading_paths: Path) -> str:
    leading = [_bash_path(path) for path in leading_paths]
    if _is_wsl_bash():
        return ":".join([
            *leading,
            "/usr/local/sbin",
            "/usr/local/bin",
            "/usr/sbin",
            "/usr/bin",
            "/sbin",
            "/bin",
        ])
    return ":".join([*leading, os.environ.get("PATH", "")])


def _run(script: Path, env: dict, args: list[str] | None = None) -> subprocess.CompletedProcess:
    if _is_wsl_bash():
        assignments = " ".join(
            f"{name}={shlex.quote(str(value))}"
            for name, value in env.items()
        )
        command = " ".join(
            [
                "/usr/bin/env",
                assignments,
                shlex.quote(_bash_path(script)),
                *(shlex.quote(arg) for arg in (args or [])),
            ]
        )
        return subprocess.run([_BASH, "-lc", command], capture_output=True, text=True)

    full_env = {**os.environ, **env}
    cmd = [_BASH, _bash_path(script)] + (args or [])
    return subprocess.run(cmd, capture_output=True, text=True, env=full_env)


# ---------------------------------------------------------------------------
# shellcheck
# ---------------------------------------------------------------------------

@pytest.mark.skipif(_SHELLCHECK is None, reason="shellcheck not installed")
def test_backup_sh_shellcheck():
    result = subprocess.run(
        [_SHELLCHECK, "--severity=warning", str(BACKUP_SH)],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, f"shellcheck backup.sh:\n{result.stdout}\n{result.stderr}"


@pytest.mark.skipif(_SHELLCHECK is None, reason="shellcheck not installed")
def test_restore_sh_shellcheck():
    result = subprocess.run(
        [_SHELLCHECK, "--severity=warning", str(RESTORE_SH)],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, (
        f"shellcheck backup-restore.sh:\n{result.stdout}\n{result.stderr}"
    )


# ---------------------------------------------------------------------------
# backup.sh — DRY_RUN
# ---------------------------------------------------------------------------

def test_backup_dry_run_exits_0_without_backup_dest():
    """DRY_RUN=1 must exit 0 even when BACKUP_DEST is absent."""
    with tempfile.TemporaryDirectory() as tmpdir:
        env = {
            "DRY_RUN": "1",
            "BACKUP_DEST": "",
            "BACKUP_LOG": _bash_path(Path(tmpdir) / "backup.log"),
        }
        result = _run(BACKUP_SH, env)
    assert result.returncode == 0, f"expected exit 0, got {result.returncode}\n{result.stderr}"


def test_backup_dry_run_prints_dry_run_indicator():
    """DRY_RUN=1 output must mention 'dry'."""
    with tempfile.TemporaryDirectory() as tmpdir:
        env = {
            "DRY_RUN": "1",
            "BACKUP_DEST": "s3://test-bucket/backups",
            "BACKUP_LOG": _bash_path(Path(tmpdir) / "backup.log"),
        }
        result = _run(BACKUP_SH, env)
    combined = (result.stdout + result.stderr).lower()
    assert "dry" in combined, f"Expected 'dry' in output:\n{result.stdout}\n{result.stderr}"


def test_backup_dry_run_no_mutating_commands(tmp_path):
    """DRY_RUN=1: tar and rclone must not be invoked."""
    call_log = tmp_path / "calls.log"
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    for cmd in ("tar", "rclone", "docker"):
        fake_cmd = fake_bin / cmd
        fake_cmd.write_text(
            "#!/usr/bin/env bash\n"
            f"echo \"{cmd} called: $*\" >> '{_bash_path(call_log)}'\n"
            "exit 0\n",
            encoding="utf-8",
            newline="\n",
        )
        fake_cmd.chmod(0o755)

    env = {
        "DRY_RUN": "1",
        "BACKUP_DEST": "s3://test-bucket/backups",
        "BACKUP_LOG": _bash_path(tmp_path / "backup.log"),
        "PATH": _bash_path_env(fake_bin),
    }
    result = _run(BACKUP_SH, env)
    assert result.returncode == 0, f"exit {result.returncode}\n{result.stderr}"
    if call_log.exists():
        calls = call_log.read_text()
        assert "tar called" not in calls, f"tar was invoked in DRY_RUN:\n{calls}"
        assert "rclone called" not in calls, f"rclone was invoked in DRY_RUN:\n{calls}"


# ---------------------------------------------------------------------------
# backup.sh — BACKUP_DEST check
# ---------------------------------------------------------------------------

def test_backup_exits_1_when_backup_dest_missing():
    """Without DRY_RUN, missing BACKUP_DEST must exit 1."""
    with tempfile.TemporaryDirectory() as tmpdir:
        env = {
            "DRY_RUN": "0",
            "BACKUP_DEST": "",
            "BACKUP_LOG": _bash_path(Path(tmpdir) / "backup.log"),
        }
        result = _run(BACKUP_SH, env)
    assert result.returncode == 1, (
        f"expected exit 1 for missing BACKUP_DEST, got {result.returncode}\n{result.stderr}"
    )


# ---------------------------------------------------------------------------
# backup-restore.sh — DRY_RUN
# ---------------------------------------------------------------------------

def _fake_rclone_bin(tmp_path: Path) -> Path:
    """Return path dir containing a fake rclone that returns one listing entry."""
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir(exist_ok=True)
    fake_rclone = fake_bin / "rclone"
    fake_rclone.write_text(
        "#!/usr/bin/env bash\n"
        'if [[ "$1" == "lsf" ]]; then\n'
        "    echo '2026-04-20T02-00-00Z;workflow-data-2026-04-20T02-00-00Z.tar.gz'\n"
        "    exit 0\n"
        "fi\n"
        'if [[ "$1" == "ls" ]]; then exit 0; fi\n'
        'if [[ "$1" == "obscure" ]]; then echo "obscured"; exit 0; fi\n'
        "exit 0\n",
        encoding="utf-8",
        newline="\n",
    )
    fake_rclone.chmod(0o755)
    return fake_bin


def _fake_rclone_bash_env(tmp_path: Path) -> Path:
    """Return a BASH_ENV file that defines fake rclone for mounted Windows paths."""
    fake_env = tmp_path / "fake-rclone-env.sh"
    fake_env.write_text(
        "rclone() {\n"
        '    if [[ "$1" == "lsf" ]]; then\n'
        "        echo '2026-04-20T02-00-00Z;workflow-data-2026-04-20T02-00-00Z.tar.gz'\n"
        "        return 0\n"
        "    fi\n"
        '    if [[ "$1" == "ls" ]]; then return 0; fi\n'
        '    if [[ "$1" == "obscure" ]]; then echo "obscured"; return 0; fi\n'
        "    return 0\n"
        "}\n",
        encoding="utf-8",
        newline="\n",
    )
    return fake_env


def test_restore_dry_run_exits_0(tmp_path):
    """DRY_RUN=1 on restore must exit 0 after identifying the archive."""
    fake_bin = _fake_rclone_bin(tmp_path)
    fake_env = _fake_rclone_bash_env(tmp_path)
    env = {
        "DRY_RUN": "1",
        "BACKUP_DEST": "s3://test-bucket/workflow-backups",
        "BACKUP_LOG": _bash_path(tmp_path / "backup.log"),
        "BASH_ENV": _bash_path(fake_env),
        "PATH": _bash_path_env(fake_bin),
    }
    result = _run(RESTORE_SH, env)
    assert result.returncode == 0, f"exit {result.returncode}\n{result.stdout}\n{result.stderr}"


def test_restore_dry_run_prints_dry_run_indicator(tmp_path):
    """DRY_RUN=1 restore output must mention 'dry'."""
    fake_bin = _fake_rclone_bin(tmp_path)
    fake_env = _fake_rclone_bash_env(tmp_path)
    env = {
        "DRY_RUN": "1",
        "BACKUP_DEST": "s3://test-bucket/workflow-backups",
        "BACKUP_LOG": _bash_path(tmp_path / "backup.log"),
        "BASH_ENV": _bash_path(fake_env),
        "PATH": _bash_path_env(fake_bin),
    }
    result = _run(RESTORE_SH, env)
    combined = (result.stdout + result.stderr).lower()
    assert "dry" in combined, f"Expected 'dry':\n{result.stdout}\n{result.stderr}"


def test_restore_exits_1_when_backup_dest_missing():
    """Missing BACKUP_DEST must exit 1 on restore."""
    with tempfile.TemporaryDirectory() as tmpdir:
        env = {
            "BACKUP_DEST": "",
            "BACKUP_LOG": _bash_path(Path(tmpdir) / "backup.log"),
        }
        result = _run(RESTORE_SH, env)
    assert result.returncode == 1, (
        f"expected exit 1 for missing BACKUP_DEST, got {result.returncode}\n{result.stderr}"
    )


# ---------------------------------------------------------------------------
# Retention-policy logic (delegates to scripts/backup_prune.py — canonical)
# ---------------------------------------------------------------------------


def _make_archives(dates: list[str]) -> list[str]:
    return [f"workflow-data-{d}T02-00-00Z.tar.gz" for d in dates]


def _retention_set(names: list[str], **kwargs: int) -> set[str]:
    return set(_apply_retention(names, **kwargs))


def test_retention_keeps_last_7_daily():
    """With 10 archives and daily=7, most recent 7 must never be deleted."""
    dates = [f"2026-04-{d:02d}" for d in range(1, 11)]
    names = _make_archives(dates)
    to_delete = _retention_set(names, keep_daily=7, keep_weekly=4, keep_monthly=6)
    recent_7 = set(_make_archives(dates[-7:]))
    assert recent_7.isdisjoint(to_delete), (
        f"Recent 7 should never be deleted: {to_delete & recent_7}"
    )


def test_retention_keeps_weekly_anchors():
    """Archives from different weeks should be kept beyond the daily window."""
    # 14 days across 2 weeks
    dates = [f"2026-04-{d:02d}" for d in range(1, 15)]
    names = _make_archives(dates)
    to_delete = _retention_set(names, keep_daily=7, keep_weekly=2, keep_monthly=6)
    # Apr 8 is first of week 2 (days 8-14)
    week2_anchor = "workflow-data-2026-04-08T02-00-00Z.tar.gz"
    assert week2_anchor not in to_delete, f"Week anchor should be kept: {week2_anchor}"


def test_retention_all_recent_no_pruning():
    """Fewer archives than daily window means nothing is pruned."""
    dates = [f"2026-04-{d:02d}" for d in range(1, 6)]
    names = _make_archives(dates)
    to_delete = _retention_set(names, keep_daily=7, keep_weekly=4, keep_monthly=6)
    assert to_delete == set(), f"Nothing should be pruned: {to_delete}"


def test_retention_monthly_anchor_kept():
    """One archive per month is kept when beyond weekly window.

    The retention algo keeps the NEWEST archive per monthly bucket (since
    it walks newest-first). With two months of data and keep_monthly=2,
    at least one archive from each month must survive.
    """
    march = [f"2026-03-{d:02d}" for d in range(1, 32) if d <= 31]
    april = [f"2026-04-{d:02d}" for d in range(1, 5)]
    names = _make_archives(march + april)
    to_delete = _retention_set(names, keep_daily=7, keep_weekly=4, keep_monthly=2)
    # At least one March archive must survive (the monthly anchor is newest-first,
    # so Mar 31 is kept as the March monthly representative).
    march_kept = [n for n in names if "2026-03-" in n and n not in to_delete]
    assert march_kept, f"At least one March archive should be kept; all deleted: {to_delete}"


def test_retention_never_deletes_unrecognized_names():
    """Foreign files at the destination must never be emitted for deletion.

    Regression: before 2026-06-10 the delete set was computed as
    all-names-minus-kept, so any file not matching the workflow-data
    pattern was deleted on every successful prune.
    """
    foreign = ["README.txt", "manual-snapshot.tar.gz", "somebody-elses-file.bin"]
    dates = [f"2026-04-{d:02d}" for d in range(1, 15)]
    names = _make_archives(dates) + foreign
    to_delete = _retention_set(names, keep_daily=1, keep_weekly=1, keep_monthly=1)
    assert set(foreign).isdisjoint(to_delete), (
        f"Foreign names must never be pruned: {to_delete & set(foreign)}"
    )


def test_retention_per_tier_independent():
    """Brain and data archives get independent retention windows."""
    dates = [f"2026-04-{d:02d}" for d in range(1, 11)]
    data_names = _make_archives(dates)
    brain_names = [f"workflow-brain-{d}T03-00-00Z.tar.gz" for d in dates]
    to_delete = _retention_set(
        data_names + brain_names, keep_daily=7, keep_weekly=4, keep_monthly=6
    )
    # Same policy as test_prune_script_subprocess_emits_deletions, applied
    # per tier: only the Apr 01 archive of EACH tier is pruned.
    assert to_delete == {
        "workflow-data-2026-04-01T02-00-00Z.tar.gz",
        "workflow-brain-2026-04-01T03-00-00Z.tar.gz",
    }, f"Expected per-tier Apr 01 pruning; got: {to_delete}"


def test_backup_sh_has_brain_tier_and_tolerates_live_tar():
    """Structural anchors for the 2026-06-10 two-tier redesign."""
    text = BACKUP_SH.read_text(encoding="utf-8")
    assert "workflow-brain-" in text, "brain-tier archive missing from backup.sh"
    assert "--warning=no-file-changed" in text, "live-tar warning suppression missing"
    assert 'tar_rc' in text and '-ge 2' in text, (
        "full-tier tar must tolerate rc=1 and fail only on rc>=2"
    )
    assert "src.backup(dst)" in text, "consistent sqlite copy (sqlite3 backup API) missing"


def test_prune_script_subprocess_emits_deletions():
    """backup_prune.py via subprocess: 10 archives, daily=7 → correct prune set.

    Policy: daily=7 keeps Apr 04-10. Apr 03 is the weekly anchor for week 1
    (days 1-7). Apr 02 is the monthly anchor for 2026-04. Only Apr 01 is pruned.
    """
    dates = [f"2026-04-{d:02d}" for d in range(1, 11)]
    names = _make_archives(dates)
    cmd = [sys.executable, str(PRUNE_PY),
           "--keep-daily", "7", "--keep-weekly", "4", "--keep-monthly", "6"]
    proc = subprocess.run(
        cmd,
        input="\n".join(names) + "\n",
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, f"backup_prune.py failed:\n{proc.stderr}"
    deleted = [line for line in proc.stdout.strip().splitlines() if line]
    assert deleted == ["workflow-data-2026-04-01T02-00-00Z.tar.gz"], (
        f"Expected only Apr 01 pruned; got: {deleted}"
    )
