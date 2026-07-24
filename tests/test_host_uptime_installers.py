from __future__ import annotations

import functools
import os
import shlex
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parent.parent
INSTALLER = REPO / "deploy" / "install-host-uptime-services.sh"
BOOTSTRAP = REPO / "deploy" / "hetzner-bootstrap.sh"
WORKFLOW = REPO / ".github" / "workflows" / "install-host-services.yml"
RESTART_WORKFLOW = REPO / ".github" / "workflows" / "restart-daemon.yml"

TIMERS = (
    "tinyassets-watchdog.timer",
    "daemon-watchdog.timer",
    "tinyassets-backup.timer",
    "tinyassets-prune.timer",
    "tinyassets-disk-watch.timer",
)
SERVICES = tuple(name.removesuffix(".timer") + ".service" for name in TIMERS)
UNIT_FILES = tuple(item for pair in zip(SERVICES, TIMERS, strict=True) for item in pair)
RUNTIME_FILES = (
    "deploy/daemon-watchdog.sh",
    "deploy/backup.sh",
    "scripts/__init__.py",
    "scripts/watchdog.py",
    "scripts/mcp_public_canary.py",
    "scripts/disk_watch.py",
    "scripts/disk_autoprune.py",
    "scripts/rotate_run_transcripts.py",
    "scripts/backup_ship_gh.py",
    "scripts/backup_prune.py",
    "tinyassets/__init__.py",
    "tinyassets/storage/__init__.py",
    "tinyassets/storage/rotation.py",
)

_BASH = shutil.which("bash")


@functools.cache
def _is_wsl_bash() -> bool:
    if not _BASH or os.name != "nt":
        return False
    probe = subprocess.run(
        [_BASH, "-lc", "test -d /mnt/c"],
        capture_output=True,
        check=False,
    )
    return probe.returncode == 0


def _bash_path(path: Path) -> str:
    resolved = path.resolve()
    if _is_wsl_bash():
        drive = resolved.drive.rstrip(":").lower()
        suffix = resolved.as_posix().split(":", 1)[1]
        return f"/mnt/{drive}{suffix}"
    return str(resolved)


def _bash_path_env(fake_bin: Path) -> str:
    return f"{_bash_path(fake_bin)}:/usr/local/bin:/usr/bin:/bin"


def _backup_state_script() -> str:
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    backup_step = next(
        step
        for step in workflow["jobs"]["install"]["steps"]
        if step.get("name") == "Ensure off-host backup configuration"
    )
    run = backup_step["run"]
    marker = "<<'BACKUP_STATE'\n"
    assert marker in run
    body = run.split(marker, 1)[1]
    terminator = "\nBACKUP_STATE\n"
    assert terminator in body
    return body.split(terminator, 1)[0]


def _backup_cleanup_function() -> str:
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    backup_step = next(
        step
        for step in workflow["jobs"]["install"]["steps"]
        if step.get("name") == "Ensure off-host backup configuration"
    )
    run = backup_step["run"]
    marker = "cleanup() {\n"
    assert marker in run
    body = run.split(marker, 1)[1]
    terminator = "\ntrap cleanup EXIT"
    assert terminator in body
    return f"cleanup() {{\n{body.split(terminator, 1)[0]}"


def _run_backup_cleanup(
    tmp_path: Path,
    *,
    delete_status: str,
    transport_rc: int,
) -> subprocess.CompletedProcess[str]:
    if not _BASH:
        pytest.skip("bash unavailable")
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_curl = fake_bin / "curl"
    harness = tmp_path / "cleanup-harness.sh"
    fake_curl.write_text(
        f"#!/usr/bin/env bash\nprintf '%s' {shlex.quote(delete_status)}\n"
        f"exit {transport_rc}\n",
        encoding="utf-8",
        newline="\n",
    )
    temp_files = [tmp_path / name for name in ("response", "credentials", "rclone", "header")]
    for path in temp_files:
        path.write_text("fixture\n", encoding="utf-8", newline="\n")
    assignments = "\n".join(
        (
            f"response_file={shlex.quote(_bash_path(temp_files[0]))}",
            f"credentials_file={shlex.quote(_bash_path(temp_files[1]))}",
            f"rclone_file={shlex.quote(_bash_path(temp_files[2]))}",
            f"api_header_file={shlex.quote(_bash_path(temp_files[3]))}",
            'remote_stage=""',
            'created_access_key="ACCESSKEY12345678"',
            'DO_SSH_USER="fixture"',
            'DO_DROPLET_HOST="fixture"',
        )
    )
    harness.write_text(
        f"set -uo pipefail\n{assignments}\n{_backup_cleanup_function()}\n"
        "false\ncleanup\n",
        encoding="utf-8",
        newline="\n",
    )
    command = (
        f"chmod +x {shlex.quote(_bash_path(fake_curl))} && "
        f"PATH={shlex.quote(_bash_path(fake_bin))}:/usr/local/bin:/usr/bin:/bin "
        f"bash {shlex.quote(_bash_path(harness))}"
    )
    return subprocess.run(
        [_BASH, "-lc", command],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )


def _run_backup_state(
    tmp_path: Path,
    *,
    env_text: str | None,
    config_kind: str,
    config_mode: str = "600",
    rclone_rc: int = 0,
) -> subprocess.CompletedProcess[str]:
    if not _BASH:
        pytest.skip("bash unavailable")
    state_script = tmp_path / "backup-state.sh"
    env_file = tmp_path / "tinyassets.env"
    config = tmp_path / "rclone.conf"
    real_config = tmp_path / "rclone.real.conf"
    fake_rclone = tmp_path / "rclone"
    state_script.write_text(
        _backup_state_script(),
        encoding="utf-8",
        newline="\n",
    )
    if env_text is not None:
        env_file.write_text(env_text, encoding="utf-8", newline="\n")
    if config_kind == "regular":
        config.write_text(
            "[spaces]\ntype = s3\n",
            encoding="utf-8",
            newline="\n",
        )
    elif config_kind == "symlink":
        real_config.write_text(
            "[spaces]\ntype = s3\n",
            encoding="utf-8",
            newline="\n",
        )
    elif config_kind != "absent":
        raise AssertionError(f"unknown config kind: {config_kind}")
    fake_rclone.write_text(
        f"#!/usr/bin/env bash\nexit {rclone_rc}\n",
        encoding="utf-8",
        newline="\n",
    )

    setup = [f"chmod +x {shlex.quote(_bash_path(fake_rclone))}"]
    if config_kind == "regular":
        setup.append(f"chmod {config_mode} {shlex.quote(_bash_path(config))}")
    elif config_kind == "symlink":
        setup.extend(
            (
                f"chmod {config_mode} {shlex.quote(_bash_path(real_config))}",
                (
                    f"ln -s {shlex.quote(_bash_path(real_config))} "
                    f"{shlex.quote(_bash_path(config))}"
                ),
            )
        )
    subprocess.run(
        [_BASH, "-lc", " && ".join(setup)],
        capture_output=True,
        text=True,
        timeout=10,
        check=True,
    )
    identity_target = real_config if config_kind == "symlink" else config
    if config_kind == "absent":
        expected_identity = "root:root 600"
    else:
        actual_identity = subprocess.run(
            [
                _BASH,
                "-lc",
                f"stat -c '%U:%G %a' {shlex.quote(_bash_path(identity_target))}",
            ],
            capture_output=True,
            text=True,
            timeout=10,
            check=True,
        ).stdout.strip()
        if config_mode == "600":
            expected_identity = actual_identity
        else:
            owner_group = actual_identity.rsplit(" ", 1)[0]
            expected_identity = f"{owner_group} 600"

    args = (
        "spaces:tinyassets-backups-jonnyton-sfo3/tinyassets-backups",
        _bash_path(env_file),
        _bash_path(config),
        _bash_path(fake_rclone),
        expected_identity,
    )
    command = " ".join(
        (
            "bash",
            shlex.quote(_bash_path(state_script)),
            *(shlex.quote(arg) for arg in args),
        )
    )
    return subprocess.run(
        [_BASH, "-lc", command],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )


def _assert_current_release(runtime_root: Path) -> Path:
    current = runtime_root / "current"
    result = subprocess.run(
        [
            _BASH,
            "-lc",
            (
                f"test -L {shlex.quote(_bash_path(current))} && "
                f"test -d {shlex.quote(_bash_path(current))}"
            ),
        ],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert result.returncode == 0, f"{result.stdout}\n{result.stderr}"
    releases = [path for path in (runtime_root / "releases").iterdir() if path.is_dir()]
    assert len(releases) == 1
    return releases[0]


def _bash_readlink(path: Path) -> str:
    result = subprocess.run(
        [_BASH, "-lc", f"readlink {shlex.quote(_bash_path(path))}"],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert result.returncode == 0, f"{result.stdout}\n{result.stderr}"
    return result.stdout.strip()


def _bash_path_exists(path: Path) -> bool:
    result = subprocess.run(
        [
            _BASH,
            "-lc",
            (
                f"test -e {shlex.quote(_bash_path(path))} || "
                f"test -L {shlex.quote(_bash_path(path))}"
            ),
        ],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    return result.returncode == 0


@pytest.fixture(autouse=True)
def _clean_wsl_current_links(tmp_path):
    yield
    if _is_wsl_bash() and tmp_path.exists():
        subprocess.run(
            [
                _BASH,
                "-lc",
                (
                    f"find {shlex.quote(_bash_path(tmp_path))} "
                    "-type l -name current -delete"
                ),
            ],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )


def _run_installer(env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    if not _BASH:
        pytest.skip("bash unavailable")
    if _is_wsl_bash():
        assignments = " ".join(
            f"{key}={shlex.quote(value)}" for key, value in env.items()
        )
        command = f"/usr/bin/env {assignments} {shlex.quote(_bash_path(INSTALLER))}"
        return subprocess.run(
            [_BASH, "-lc", command],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
    return subprocess.run(
        [_BASH, str(INSTALLER)],
        env={**os.environ, **env},
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )


def _popen_installer(env: dict[str, str]) -> subprocess.Popen[str]:
    if _is_wsl_bash():
        assignments = " ".join(
            f"{key}={shlex.quote(value)}" for key, value in env.items()
        )
        command = f"/usr/bin/env {assignments} {shlex.quote(_bash_path(INSTALLER))}"
        return subprocess.Popen(
            [_BASH, "-lc", command],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    return subprocess.Popen(
        [_BASH, str(INSTALLER)],
        env={**os.environ, **env},
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def _copy_source(tmp_path: Path) -> Path:
    source = tmp_path / "source"
    for relative in (*UNIT_FILES, *RUNTIME_FILES):
        if relative in UNIT_FILES:
            source_file = REPO / "deploy" / relative
            target = source / "deploy" / relative
        else:
            source_file = REPO / relative
            target = source / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_file, target)
    return source


def _fake_tools(tmp_path: Path) -> Path:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    (fake_bin / "systemctl").write_text(
        """#!/usr/bin/env bash
set -euo pipefail
echo "${INSTALL_RUN_ID:-run}:$*" >> "$SYSTEMCTL_LOG"
cmd="$1"; shift
case "$cmd" in
  show)
    [[ "${FAIL_SYSTEMCTL_AT:-}" == "show" ]] && exit 68
    property="$1"
    unit="${@: -1}"
    if [[ "$property" == "--property=ActiveState" ]]; then
      if [[ "${FORCE_ACTIVE_SERVICE:-}" == "$unit" ]]; then
        echo "${FORCE_ACTIVE_STATE:-active}"
      elif [[ -f "$SYSTEMCTL_STATE/$unit.active" ]]; then
        echo active
      else
        echo inactive
      fi
    elif [[ -f "$SYSTEMD_UNITS/$unit" ]]; then
      echo loaded
    else
      echo not-found
    fi
    ;;
  stop)
    for unit in "$@"; do
      [[ -f "$SYSTEMD_UNITS/$unit" ]] || exit 5
      [[ "${FAIL_STOP_UNIT:-}" == "$unit" ]] && exit 69
      rm -f "$SYSTEMCTL_STATE/$unit.active"
    done
    ;;
  is-active)
    [[ "$1" == "--quiet" ]] && shift
    [[ "${FORCE_ACTIVE_SERVICE:-}" == "$1" ]] && exit 0
    [[ -f "$SYSTEMCTL_STATE/$1.active" ]]
    ;;
  reset-failed|restart)
    exit 0
    ;;
  daemon-reload)
    [[ "${FAIL_SYSTEMCTL_AT:-}" == "daemon-reload" ]] && exit 70
    [[ -n "${DAEMON_RELOAD_MARKER:-}" ]] && touch "$DAEMON_RELOAD_MARKER"
    [[ "${DAEMON_RELOAD_SLEEP:-0}" == "0" ]] || sleep "$DAEMON_RELOAD_SLEEP"
    ;;
  enable)
    [[ "${FAIL_SYSTEMCTL_AT:-}" == "enable" ]] && exit 71
    [[ "$1" == "--now" ]] && shift
    for unit in "$@"; do
      touch "$SYSTEMCTL_STATE/$unit.enabled" "$SYSTEMCTL_STATE/$unit.active"
    done
    ;;
  is-enabled)
    [[ "${FAIL_SYSTEMCTL_AT:-}" == "is-enabled" ]] && exit 72
    [[ -f "$SYSTEMCTL_STATE/$1.enabled" ]]
    ;;
  *)
    exit 73
    ;;
esac
""",
        encoding="utf-8",
        newline="\n",
    )
    (fake_bin / "systemctl").chmod(0o755)
    (fake_bin / "visudo").write_text(
        """#!/usr/bin/env bash
[[ "${FAIL_VISUDO:-0}" == "1" ]] && exit 80
[[ "$1" == "-cf" && -f "$2" ]]
""",
        encoding="utf-8",
        newline="\n",
    )
    (fake_bin / "visudo").chmod(0o755)
    (fake_bin / "docker").write_text(
        """#!/usr/bin/env bash
if [[ "$1" == "inspect" ]]; then
  echo true
  exit 0
fi
if [[ "$1" == "volume" && "$2" == "inspect" ]]; then
  exit 1
fi
exit 90
""",
        encoding="utf-8",
        newline="\n",
    )
    (fake_bin / "docker").chmod(0o755)
    return fake_bin


def _install_env(tmp_path: Path, source: Path | None = None) -> dict[str, str]:
    source = source or _copy_source(tmp_path)
    fake_bin = _fake_tools(tmp_path)
    state = tmp_path / "state"
    state.mkdir()
    return {
        "TINYASSETS_SOURCE_ROOT": _bash_path(source),
        "TINYASSETS_RUNTIME_ROOT": _bash_path(tmp_path / "runtime"),
        "TINYASSETS_SYSTEMD_DIR": _bash_path(tmp_path / "systemd"),
        "TINYASSETS_SUDOERS_DIR": _bash_path(tmp_path / "sudoers"),
        "TINYASSETS_LOCK_DIR": _bash_path(tmp_path / "locks"),
        "TINYASSETS_SOURCE_SHA": "a" * 40,
        "TINYASSETS_ALLOW_TEST_ROOTS": "1",
        "TINYASSETS_ACTIVE_WAIT_SECONDS": "0",
        "TINYASSETS_LOCK_WAIT_SECONDS": "60",
        "SYSTEMCTL_BIN": _bash_path(fake_bin / "systemctl"),
        "VISUDO_BIN": _bash_path(fake_bin / "visudo"),
        "SYSTEMCTL_LOG": _bash_path(tmp_path / "systemctl.log"),
        "SYSTEMCTL_STATE": _bash_path(state),
        "SYSTEMD_UNITS": _bash_path(tmp_path / "systemd"),
        "PATH": _bash_path_env(fake_bin),
    }


def test_fresh_install_converges_exact_manifest(tmp_path):
    env = _install_env(tmp_path)
    result = _run_installer(env)

    assert result.returncode == 0, f"{result.stdout}\n{result.stderr}"
    systemd = tmp_path / "systemd"
    assert {path.name for path in systemd.iterdir()} == set(UNIT_FILES)
    current = _assert_current_release(tmp_path / "runtime")
    assert {
        path.relative_to(current).as_posix()
        for path in current.rglob("*")
        if path.is_file()
    } == set(RUNTIME_FILES)
    for service in (
        "tinyassets-watchdog.service",
        "daemon-watchdog.service",
        "tinyassets-backup.service",
        "tinyassets-disk-watch.service",
    ):
        text = (systemd / service).read_text(encoding="utf-8")
        assert "/opt/tinyassets-host-uptime/current/" in text
        assert "/opt/tinyassets/scripts/" not in text
        assert "/opt/tinyassets/deploy/" not in text
    disk_watch = (systemd / "tinyassets-disk-watch.service").read_text(
        encoding="utf-8"
    )
    assert "WorkingDirectory=/opt/tinyassets-host-uptime/current" in disk_watch
    for watchdog_service in (
        "tinyassets-watchdog.service",
        "daemon-watchdog.service",
    ):
        watchdog_unit = (systemd / watchdog_service).read_text(encoding="utf-8")
        assert "EnvironmentFile=/etc/tinyassets/env" in watchdog_unit
        assert 'ExecCondition=/usr/bin/test -n "${TINYASSETS_IMAGE}"' in (
            watchdog_unit
        )
    log = (tmp_path / "systemctl.log").read_text(encoding="utf-8")
    assert "\nrun:stop " not in f"\n{log}"
    assert f"enable --now {' '.join(TIMERS)}" in log
    for timer in TIMERS:
        assert f"is-enabled {timer}" in log
        assert f"is-active {timer}" in log


def test_repeat_install_repairs_disabled_current_timer(tmp_path):
    env = _install_env(tmp_path)
    assert _run_installer(env).returncode == 0
    state = tmp_path / "state"
    (state / f"{TIMERS[0]}.active").unlink()
    (state / f"{TIMERS[0]}.enabled").unlink()

    result = _run_installer(env)

    assert result.returncode == 0, f"{result.stdout}\n{result.stderr}"
    assert (state / f"{TIMERS[0]}.active").exists()
    assert (state / f"{TIMERS[0]}.enabled").exists()


def test_repeat_install_repairs_corrupt_content_addressed_release(tmp_path):
    source = _copy_source(tmp_path)
    env = _install_env(tmp_path, source)
    first = _run_installer(env)
    assert first.returncode == 0, f"{first.stdout}\n{first.stderr}"
    release = _assert_current_release(tmp_path / "runtime")
    installed_watchdog = release / "scripts" / "watchdog.py"
    installed_watchdog.write_text("corrupt\n", encoding="utf-8", newline="\n")
    extra = release / "scripts" / "unexpected.py"
    extra.write_text("unexpected\n", encoding="utf-8", newline="\n")

    result = _run_installer(env)

    assert result.returncode == 0, f"{result.stdout}\n{result.stderr}"
    assert installed_watchdog.read_bytes() == (
        source / "scripts" / "watchdog.py"
    ).read_bytes()
    assert not extra.exists()
    assert _bash_readlink(tmp_path / "runtime" / "current") == (
        f"releases/{release.name}"
    )


def test_missing_manifest_source_fails_before_systemd(tmp_path):
    source = _copy_source(tmp_path)
    (source / RUNTIME_FILES[-1]).unlink()
    env = _install_env(tmp_path, source)

    result = _run_installer(env)

    assert result.returncode != 0
    assert not (tmp_path / "systemctl.log").exists()
    assert not (tmp_path / "runtime" / "current").exists()


@pytest.mark.parametrize(
    "active_state", ["active", "activating", "reloading", "deactivating"]
)
def test_active_service_timeout_reactivates_timers_before_file_mutation(
    tmp_path, active_state
):
    env = _install_env(tmp_path)
    first = _run_installer(env)
    assert first.returncode == 0, f"{first.stdout}\n{first.stderr}"
    current_before = _bash_readlink(tmp_path / "runtime" / "current")
    units_before = {
        unit: (tmp_path / "systemd" / unit).read_bytes()
        for unit in UNIT_FILES
    }
    env["FORCE_ACTIVE_SERVICE"] = SERVICES[2]
    env["FORCE_ACTIVE_STATE"] = active_state

    result = _run_installer(env)

    assert result.returncode != 0
    assert _bash_readlink(tmp_path / "runtime" / "current") == current_before
    assert {
        unit: (tmp_path / "systemd" / unit).read_bytes()
        for unit in UNIT_FILES
    } == units_before
    log = (tmp_path / "systemctl.log").read_text(encoding="utf-8")
    for timer in TIMERS:
        assert f"stop {timer}" in log
    assert f"enable --now {' '.join(TIMERS)}" in log


def test_unknown_service_state_fails_closed_before_file_mutation(tmp_path):
    env = _install_env(tmp_path)
    first = _run_installer(env)
    assert first.returncode == 0, f"{first.stdout}\n{first.stderr}"
    current_before = _bash_readlink(tmp_path / "runtime" / "current")
    units_before = {
        unit: (tmp_path / "systemd" / unit).read_bytes()
        for unit in UNIT_FILES
    }
    env["FORCE_ACTIVE_SERVICE"] = SERVICES[2]
    env["FORCE_ACTIVE_STATE"] = "maintenance"

    result = _run_installer(env)

    assert result.returncode != 0
    assert "unsafe service active state" in result.stdout
    assert _bash_readlink(tmp_path / "runtime" / "current") == current_before
    assert {
        unit: (tmp_path / "systemd" / unit).read_bytes()
        for unit in UNIT_FILES
    } == units_before
    assert f"enable --now {' '.join(TIMERS)}" in (
        tmp_path / "systemctl.log"
    ).read_text(encoding="utf-8")


def test_partial_timer_stop_failure_reactivates_every_timer(tmp_path):
    env = _install_env(tmp_path)
    first = _run_installer(env)
    assert first.returncode == 0, f"{first.stdout}\n{first.stderr}"
    env["FAIL_STOP_UNIT"] = TIMERS[2]

    result = _run_installer(env)

    assert result.returncode != 0
    state = tmp_path / "state"
    for timer in TIMERS:
        assert (state / f"{timer}.active").exists()
        assert (state / f"{timer}.enabled").exists()


@pytest.mark.parametrize("failure", ["show", "daemon-reload", "enable", "is-enabled"])
def test_systemd_failure_propagates(tmp_path, failure):
    env = _install_env(tmp_path)
    env["FAIL_SYSTEMCTL_AT"] = failure
    result = _run_installer(env)
    assert result.returncode != 0
    assert "converged" not in result.stdout.lower()
    assert not _bash_path_exists(tmp_path / "runtime" / "current")
    assert not any((tmp_path / "systemd").iterdir())


def test_post_mutation_failure_rolls_back_units_and_runtime(tmp_path):
    source = _copy_source(tmp_path)
    env = _install_env(tmp_path, source)
    first = _run_installer(env)
    assert first.returncode == 0, f"{first.stdout}\n{first.stderr}"
    current_before = _bash_readlink(tmp_path / "runtime" / "current")
    units_before = {
        unit: (tmp_path / "systemd" / unit).read_bytes()
        for unit in UNIT_FILES
    }
    (source / "deploy" / "tinyassets-watchdog.service").write_text(
        (source / "deploy" / "tinyassets-watchdog.service").read_text(
            encoding="utf-8"
        )
        + "\n# replacement candidate\n",
        encoding="utf-8",
        newline="\n",
    )
    (source / "scripts" / "watchdog.py").write_text(
        (source / "scripts" / "watchdog.py").read_text(encoding="utf-8")
        + "\n# replacement candidate\n",
        encoding="utf-8",
        newline="\n",
    )
    env["TINYASSETS_SOURCE_SHA"] = "b" * 40
    env["FAIL_SYSTEMCTL_AT"] = "daemon-reload"

    result = _run_installer(env)

    assert result.returncode != 0
    assert _bash_readlink(tmp_path / "runtime" / "current") == current_before
    assert {
        unit: (tmp_path / "systemd" / unit).read_bytes()
        for unit in UNIT_FILES
    } == units_before
    log = (tmp_path / "systemctl.log").read_text(encoding="utf-8")
    assert f"enable --now {' '.join(TIMERS)}" in log


def test_installed_disk_rotation_imports_from_runtime(tmp_path):
    env = _install_env(tmp_path)
    assert _run_installer(env).returncode == 0
    current = tmp_path / "runtime" / "current"
    data = tmp_path / "data"
    (data / "runs").mkdir(parents=True)
    result = subprocess.run(
        [
            _BASH,
            "-lc",
            (
                f"cd {shlex.quote(_bash_path(current))} && "
                f"TINYASSETS_DATA_DIR={shlex.quote(_bash_path(data))} "
                "python3 -m scripts.rotate_run_transcripts --dry-run"
            ),
        ],
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    assert result.returncode == 0, f"{result.stdout}\n{result.stderr}"


def test_package_public_api_stays_compatible_but_initializes_lazily():
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys, tinyassets; "
                "assert 'tinyassets.discovery' not in sys.modules; "
                "[getattr(tinyassets, name) for name in tinyassets.__all__]"
            ),
        ],
        cwd=REPO,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    assert result.returncode == 0, f"{result.stdout}\n{result.stderr}"


def test_installed_operational_entrypoints_invoke_from_runtime(tmp_path):
    env = _install_env(tmp_path)
    assert _run_installer(env).returncode == 0
    current = tmp_path / "runtime" / "current"
    (tmp_path / "state" / "tinyassets-daemon.service.active").touch()
    commands = (
        "python3 scripts/watchdog.py --help",
        "python3 scripts/mcp_public_canary.py --help",
        "python3 scripts/disk_watch.py --help",
        "python3 scripts/disk_autoprune.py --help",
        "python3 scripts/backup_ship_gh.py --help",
        "python3 scripts/backup_prune.py --help",
        (
            f"DRY_RUN=1 BACKUP_LOG={shlex.quote(_bash_path(tmp_path / 'backup.log'))} "
            "bash deploy/backup.sh"
        ),
        (
            f"PATH={shlex.quote(env['PATH'])} "
            f"SYSTEMCTL_LOG={shlex.quote(env['SYSTEMCTL_LOG'])} "
            f"SYSTEMCTL_STATE={shlex.quote(env['SYSTEMCTL_STATE'])} "
            f"SYSTEMD_UNITS={shlex.quote(env['SYSTEMD_UNITS'])} "
            f"TINYASSETS_DAEMON_WATCHDOG_LOCK="
            f"{shlex.quote(_bash_path(tmp_path / 'daemon-watchdog.lock'))} "
            f"TINYASSETS_COMPOSE_FILE={shlex.quote(_bash_path(tmp_path / 'missing.yml'))} "
            "bash deploy/daemon-watchdog.sh"
        ),
    )
    for command in commands:
        result = subprocess.run(
            [
                _BASH,
                "-lc",
                f"cd {shlex.quote(_bash_path(current))} && {command}",
            ],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
        assert result.returncode == 0, (
            f"command failed: {command}\n{result.stdout}\n{result.stderr}"
        )


def test_bounded_distinct_target_burst_is_isolated(tmp_path):
    cases = [(tmp_path / f"host-{index}", index) for index in range(64)]

    def install(item: tuple[Path, int]) -> subprocess.CompletedProcess[str]:
        case, index = item
        case.mkdir()
        source = _copy_source(case)
        watchdog = source / "scripts" / "watchdog.py"
        watchdog.write_text(
            watchdog.read_text(encoding="utf-8") + f"\n# host-{index}\n",
            encoding="utf-8",
            newline="\n",
        )
        return _run_installer(_install_env(case, source))

    with ThreadPoolExecutor(max_workers=64) as executor:
        results = list(executor.map(install, cases))

    failures = [
        f"host-{index}: {result.stdout}\n{result.stderr}"
        for index, result in enumerate(results)
        if result.returncode != 0
    ]
    assert not failures, "\n".join(failures)
    for case, index in cases:
        release = _assert_current_release(case / "runtime")
        watchdog = (release / "scripts" / "watchdog.py").read_text(
            encoding="utf-8"
        )
        assert watchdog.endswith(f"# host-{index}\n")


def test_same_target_burst_waits_and_each_caller_verifies(tmp_path):
    env = _install_env(tmp_path)
    env["DAEMON_RELOAD_SLEEP"] = "0.05"
    # Leave headroom for a loaded Windows/WSL runner while keeping the test
    # wait bounded below the subprocess harness's 120-second timeout.
    env["TINYASSETS_LOCK_WAIT_SECONDS"] = "110"
    caller_ids = tuple(f"same-{index}" for index in range(32))

    def install(caller_id: str) -> subprocess.CompletedProcess[str]:
        return _run_installer({**env, "INSTALL_RUN_ID": caller_id})

    with ThreadPoolExecutor(max_workers=32) as executor:
        results = list(executor.map(install, caller_ids))

    failures = [
        f"{caller_id}: {result.stdout}\n{result.stderr}"
        for caller_id, result in zip(caller_ids, results, strict=True)
        if result.returncode != 0
    ]
    assert not failures, "\n".join(failures)
    observed = [
        line.split(":", 1)[0]
        for line in (tmp_path / "systemctl.log").read_text(
            encoding="utf-8"
        ).splitlines()
    ]
    blocks = [
        caller_id
        for index, caller_id in enumerate(observed)
        if index == 0 or caller_id != observed[index - 1]
    ]
    assert len(blocks) == len(caller_ids)
    assert set(blocks) == set(caller_ids)


def test_same_target_lock_timeout_is_red_before_systemd(tmp_path):
    env = _install_env(tmp_path)
    marker = tmp_path / "reload.marker"
    env["DAEMON_RELOAD_MARKER"] = _bash_path(marker)
    env["DAEMON_RELOAD_SLEEP"] = "2"
    first = _popen_installer(env)
    deadline = time.time() + 10
    while not marker.exists() and time.time() < deadline:
        time.sleep(0.05)
    assert marker.exists()
    second_env = {
        **env,
        "INSTALL_RUN_ID": "second",
        "DAEMON_RELOAD_SLEEP": "0",
        "TINYASSETS_LOCK_WAIT_SECONDS": "0",
    }
    second = _run_installer(second_env)
    first_stdout, first_stderr = first.communicate(timeout=20)

    assert first.returncode == 0, f"{first_stdout}\n{first_stderr}"
    assert second.returncode != 0
    log = (tmp_path / "systemctl.log").read_text(encoding="utf-8")
    assert "second:" not in log


def test_callers_and_workflow_have_one_pinned_installer_owner():
    bootstrap = BOOTSTRAP.read_text(encoding="utf-8")
    workflow_text = WORKFLOW.read_text(encoding="utf-8")
    workflow = yaml.safe_load(workflow_text)
    restart_text = RESTART_WORKFLOW.read_text(encoding="utf-8")
    restart = yaml.safe_load(restart_text)
    manifest = _run_installer({"TINYASSETS_PRINT_MANIFEST": "1"})

    assert bootstrap.count("install-host-uptime-services.sh") == 1
    for timer in TIMERS:
        assert f"systemctl enable --now {timer}" not in bootstrap
    checkout = workflow["jobs"]["install"]["steps"][0]
    assert checkout["with"]["ref"] == (
        "${{ github.event_name == 'workflow_run' && "
        "github.event.workflow_run.head_sha || github.sha }}"
    )
    assert "source_ref:" not in workflow_text
    assert "sha256sum" in workflow_text
    assert "mktemp -d /tmp/tinyassets-host-uptime." in workflow_text
    assert "REQUESTED_SOURCE_REF:" in workflow_text
    assert "Resolved requested source ${REQUESTED_SOURCE_REF}" in workflow_text
    assert '[[ "${source_sha}" == "${REQUESTED_SOURCE_REF}" ]]' in workflow_text
    assert "install-host-uptime-services.sh" in workflow_text
    assert workflow_text.count('"bash -se --') == 2
    assert workflow_text.count("<<'REMOTE'") == 1
    assert workflow_text.count("<<'BACKUP_REMOTE'") == 1
    assert 'remote_stage="$1"' in workflow_text
    assert manifest.returncode == 0, f"{manifest.stdout}\n{manifest.stderr}"
    assert manifest.stdout.splitlines() == [
        "deploy/install-host-uptime-services.sh",
        *(f"deploy/{unit}" for unit in UNIT_FILES),
        *RUNTIME_FILES,
    ]
    restart_checkout = restart["jobs"]["restart"]["steps"][0]
    assert restart_checkout["with"]["ref"] == "${{ github.sha }}"
    assert "TINYASSETS_PRINT_MANIFEST=1" in restart_text
    assert "install-host-uptime-services.sh" in restart_text
    assert "sha256sum" in restart_text
    assert "mktemp -d /tmp/tinyassets-host-uptime." in restart_text
    assert restart_text.count('"bash -se --') == 1
    assert restart_text.count("<<'REMOTE'") == 1
    assert 'remote_stage="$1"' in restart_text
    assert "/tmp/daemon-watchdog" not in restart_text
    assert "systemctl enable --now daemon-watchdog.timer" not in restart_text


def test_host_service_workflow_converges_backup_before_installing_timers():
    workflow_text = WORKFLOW.read_text(encoding="utf-8")
    workflow = yaml.safe_load(workflow_text)
    steps = workflow["jobs"]["install"]["steps"]
    names = [step.get("name") for step in steps]
    backup_index = names.index("Ensure off-host backup configuration")
    install_index = names.index("Install exact uptime bundle and token refresher")
    assert backup_index < install_index

    backup_step = steps[backup_index]
    run = backup_step["run"]
    assert backup_step["env"]["DO_API_TOKEN"] == "${{ secrets.DO_API_TOKEN }}"
    assert "/v2/spaces/keys" in run
    assert '"permission":"readwrite"' in run
    assert 'bucket="tinyassets-backups-jonnyton-sfo3"' in run
    assert '"bucket":"%s"' in run
    assert "fullaccess" not in run
    assert "::add-mask::" in run
    assert "secret_key" in run
    assert 'Authorization: Bearer ${DO_API_TOKEN}' not in run
    assert '-H @"${api_header_file}"' in run
    assert "/root/.config/rclone/rclone.conf" in run
    assert 'install-tinyassets-env.sh" set BACKUP_DEST' in run
    assert "rclone lsf" in run
    assert "configured_ready" in run
    assert "completely_absent" in run
    assert "partial_or_invalid" in run
    assert "stat -c '%U:%G %a'" in run
    assert "root:root 600" in run
    assert '! -L "${config}"' in run
    assert '"${assignment_count}" == "1"' in run
    assert 'delete_http_status="$(' in run
    assert "-w '%{http_code}' -X DELETE" in run
    assert '"${delete_http_status}" != "204"' in run
    assert "Spaces key rollback failed with HTTP" in run
    assert 'curl -sS -o /dev/null -X DELETE' not in run
    assert 'cat "${response_file}"' not in run
    assert "GITHUB_OUTPUT" not in run


@pytest.mark.parametrize(
    ("env_text", "config_kind", "config_mode", "rclone_rc", "expected"),
    (
        (
            "BACKUP_DEST=spaces:tinyassets-backups-jonnyton-sfo3/"
            "tinyassets-backups\n",
            "regular",
            "600",
            0,
            "configured_ready",
        ),
        (
            "BACKUP_DEST=spaces:tinyassets-backups-jonnyton-sfo3/"
            "tinyassets-backups\n",
            "regular",
            "644",
            0,
            "partial_or_invalid",
        ),
        (
            "BACKUP_DEST=spaces:tinyassets-backups-jonnyton-sfo3/"
            "tinyassets-backups\n",
            "symlink",
            "600",
            0,
            "partial_or_invalid",
        ),
        (None, "absent", "600", 0, "completely_absent"),
        (
            "BACKUP_DEST=spaces:tinyassets-backups-jonnyton-sfo3/"
            "tinyassets-backups\n",
            "absent",
            "600",
            0,
            "partial_or_invalid",
        ),
        (
            "BACKUP_DEST=spaces:tinyassets-backups-jonnyton-sfo3/"
            "tinyassets-backups\n",
            "regular",
            "600",
            1,
            "partial_or_invalid",
        ),
        (
            "BACKUP_DEST=spaces:tinyassets-backups-jonnyton-sfo3/"
            "tinyassets-backups\n"
            "BACKUP_DEST=spaces:tinyassets-backups-jonnyton-sfo3/"
            "tinyassets-backups\n",
            "regular",
            "600",
            0,
            "partial_or_invalid",
        ),
    ),
)
def test_backup_state_classifier_is_fail_closed(
    tmp_path,
    env_text,
    config_kind,
    config_mode,
    rclone_rc,
    expected,
):
    result = _run_backup_state(
        tmp_path,
        env_text=env_text,
        config_kind=config_kind,
        config_mode=config_mode,
        rclone_rc=rclone_rc,
    )
    assert result.returncode == 0, f"{result.stdout}\n{result.stderr}"
    assert result.stdout.strip() == expected


@pytest.mark.parametrize(
    ("delete_status", "transport_rc", "expected_message"),
    (
        ("204", 0, "Rolled back the newly created Spaces key."),
        ("403", 0, "Spaces key rollback failed with HTTP 403."),
        ("000", 7, "Spaces key rollback failed with a transport error."),
    ),
)
def test_backup_key_rollback_requires_explicit_204(
    tmp_path,
    delete_status,
    transport_rc,
    expected_message,
):
    result = _run_backup_cleanup(
        tmp_path,
        delete_status=delete_status,
        transport_rc=transport_rc,
    )
    assert result.returncode == 1
    combined = f"{result.stdout}\n{result.stderr}"
    assert expected_message in combined
    if delete_status != "204" or transport_rc != 0:
        assert "::error::" in combined


def test_host_service_workflow_requires_backup_provisioning_authority():
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    verify_step = next(
        step
        for step in workflow["jobs"]["install"]["steps"]
        if step.get("name") == "Verify secrets present"
    )
    run = verify_step["run"]
    assert verify_step["env"]["DO_API_TOKEN"] == "${{ secrets.DO_API_TOKEN }}"
    assert '[ -z "$DO_API_TOKEN" ]' in run
    assert 'missing+=("DO_API_TOKEN")' in run
