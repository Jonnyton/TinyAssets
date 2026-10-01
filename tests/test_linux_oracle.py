"""Container bootstrap regressions; actual oracle run supplies integration proof."""

import re
import subprocess
import sys
import tomllib
from pathlib import Path

from scripts import linux_oracle


def test_classic_builder_gets_real_dependency_generation():
    root = Path(__file__).resolve().parents[1]
    dockerfile = (root / linux_oracle.DOCKERFILE).read_text(encoding="utf-8")
    # Execute the actual Docker RUN's Python payload, not a duplicate generator.
    # A classic builder silently ignored the previous Docker-heredoc payload.
    match = re.search(
        r'^RUN python -c "(.+)" > /tmp/oracle/requirements\.txt', dockerfile, re.MULTILINE
    )
    assert match is not None
    payload = match.group(1).replace(
        "'/tmp/oracle/pyproject.toml'", repr((root / "pyproject.toml").as_posix())
    )
    result = subprocess.run(
        [sys.executable, "-c", payload], capture_output=True, text=True, check=True
    )
    project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    assert result.stdout.splitlines() == (
        project["dependencies"] + project["optional-dependencies"]["dev"]
    )
    assert result.stdout.strip()
    assert "test -s /tmp/oracle/requirements.txt" in dockerfile
    assert "python -m pytest --version" in dockerfile


def test_snapshot_preserves_container_ownership_without_trusting_host_git():
    assert ".git" in linux_oracle.COPY_EXCLUDES
    assert "tar -C /work --no-same-owner -xf -" in linux_oracle._RUN_SCRIPT
    assert "git init -q ." in linux_oracle._RUN_SCRIPT
    assert "safe.directory" not in linux_oracle._RUN_SCRIPT


def _command(*argv: str) -> list[str]:
    import argparse

    parser = argparse.ArgumentParser()
    for flag in ("--shell", "--no-bwrap", "--as-root"):
        parser.add_argument(flag, action="store_true")
    parser.add_argument("pytest_args", nargs="*")
    flags = [a for a in argv if a in ("--shell", "--no-bwrap", "--as-root")]
    rest = [a for a in argv if a not in flags]
    args = parser.parse_args([*flags, "--", *rest])
    return linux_oracle.docker_command(args, Path("/repo"), "img:tag")


def _opts(cmd: list[str]) -> list[str]:
    return [cmd[i + 1] for i, part in enumerate(cmd) if part == "--security-opt"]


def _user_script(cmd: list[str]) -> str:
    return next(part for part in cmd if part.startswith("ORACLE_USER_SCRIPT="))


def test_default_runs_real_jails_as_an_unprivileged_user():
    """As root the universe tool jail refuses to start, so ~20 jail and egress
    tests failed for the oracle's own reasons; the default must not be root."""
    cmd = _command("tests/test_universe_tools_jail.py")
    assert _opts(cmd) == [
        "seccomp=unconfined", "apparmor=unconfined", "systempaths=unconfined",
    ]
    script = cmd[-1]
    assert f"useradd -u {linux_oracle.ORACLE_UID} -m oracle" in script
    assert "exec runuser -u oracle --" in script
    assert "chown -R oracle /work" in script
    # The suite and its repository run as that user, not the bootstrap root.
    assert "git init -q ." not in script
    user = _user_script(cmd)
    assert "git init -q ." in user
    assert "'tests/test_universe_tools_jail.py'" in user


def test_default_basetemp_is_short_and_a_given_one_wins():
    # An AF_UNIX path must fit in 108 bytes; the long default tmp root broke it.
    assert f"'--basetemp={linux_oracle.DEFAULT_BASETEMP}'" in _user_script(_command("-q"))
    assert len(linux_oracle.DEFAULT_BASETEMP) <= 8
    given = _user_script(_command("-q", "--basetemp=/tmp/mine"))
    assert "'--basetemp=/tmp/mine'" in given
    assert linux_oracle.DEFAULT_BASETEMP not in given


def test_as_root_keeps_the_old_run():
    cmd = _command("--as-root", "-q")
    assert _opts(cmd) == ["seccomp=unconfined"]
    assert not any(part.startswith("ORACLE_USER_SCRIPT=") for part in cmd)
    assert "runuser" not in cmd[-1]
    assert "git init -q ." in cmd[-1]


def test_no_bwrap_drops_every_relaxation_in_both_modes():
    assert _opts(_command("--no-bwrap")) == []
    assert _opts(_command("--no-bwrap", "--as-root")) == []


def test_each_run_is_named_so_a_lane_stops_only_its_own():
    cmd = _command("-q")
    name = cmd[cmd.index("--name") + 1]
    assert name.startswith("ta-oracle-")
