"""Behaviour of deploy/retire_platform_llm_logins.sh against a fake host.

The script runs on the production droplet after a green deploy canary. Here it
runs against a temp env file, a temp "data volume" and a stub ``docker`` that
answers the two inspections the script makes. It must:

* refuse to touch anything while the retired compose file is still live;
* scrub exactly the retired names from the env file, keeping every other line;
* delete both platform login directories IN FULL, transcripts included
  (founder decision 2026-09-24), logging counts only -- never a transcript
  name or content;
* refuse, untouched and loudly, when a login directory is a symlink or its
  real path is anything but ``<volume root>/.codex`` / ``/.claude``, and never
  follow a symlink inside one;
* log names and counts, never a value;
* retire the platform GitHub push path: scrub the push-capability maps, and
  remove the App token refresher units, script copy, env file and the App key
  at its documented path -- but name, not delete, a key configured elsewhere;
* refuse unless the tinyassets-data mountpoint is its own real path AND the
  daemon mounts that volume at /data, and refuse to delete a login dir that a
  universe symlink or config still points at;
* move GH_TOKEN out of the daemon's env file into a host-only backup env the
  backup unit reads through a drop-in;
* be idempotent.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "deploy" / "retire_platform_llm_logins.sh"
HELPER = REPO / "deploy" / "install-tinyassets-env.sh"

pytestmark = pytest.mark.skipif(
    os.name == "nt" or shutil.which("bash") is None,
    reason="host shell script is exercised on POSIX CI",
)

SECRET = "sentinel-value-do-not-log"
BACKUP_TOKEN = "backup-token-sentinel"


def _host(tmp_path: Path, *, daemon_env: str = "HOME=/app\nTINYASSETS_DATA_DIR=/data") -> dict:
    vol = tmp_path / "volume"
    vol.mkdir()
    env_file = tmp_path / "etc" / "env"
    env_file.parent.mkdir()
    env_file.write_text(
        "TINYASSETS_IMAGE=ghcr.io/x@sha256:abc\n"
        f"CLAUDE_CODE_OAUTH_TOKEN={SECRET}\n"
        f"GEMINI_API_KEY={SECRET}\n"
        f"export GROQ_API_KEY={SECRET}\n"
        f"XAI_API_KEY : {SECRET}\n"
        f"TINYASSETS_GITHUB_PUSH_CAPABILITIES={SECRET}\n"
        f"TINYASSETS_GITHUB_PR_CAPABILITIES={SECRET}\n"
        "TINYASSETS_GITHUB_OUTBOUND_VIA_CONNECTION=1\n"
        f"GH_TOKEN={BACKUP_TOKEN}\n"
        "WORKOS_API_KEY=keep-me\n",
        encoding="utf-8",
    )
    bindir = tmp_path / "bin"
    bindir.mkdir()
    stub = bindir / "docker"
    stub.write_text(
        "#!/usr/bin/env bash\n"
        'if [ "$1" = inspect ] && [[ "$*" == *.Mounts* ]]; '
        'then printf "%s\\n" "$STUB_MOUNT"; exit 0; fi\n'
        'if [ "$1" = inspect ]; then printf "%s\\n" "$STUB_DAEMON_ENV"; exit 0; fi\n'
        'if [ "$1" = volume ] && [ "$2" = inspect ]; '
        'then printf "%s\\n" "$STUB_VOLUME"; exit 0; fi\n'
        "exit 1\n",
        encoding="utf-8",
    )
    stub.chmod(0o755)
    systemctl = bindir / "systemctl"
    systemctl.write_text(
        "#!/usr/bin/env bash\n"
        'printf "%s\\n" "$*" >> "$STUB_SYSTEMCTL_LOG"\n',
        encoding="utf-8",
    )
    systemctl.chmod(0o755)
    return {
        "vol": vol,
        "env_file": env_file,
        "bin": bindir,
        "daemon_env": daemon_env,
        "etc": env_file.parent,
        "opt": tmp_path / "opt",
        "systemd": tmp_path / "systemd",
        "systemctl_log": tmp_path / "systemctl.log",
    }


def _run(host: dict) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env.update({
        "PATH": f"{host['bin']}{os.pathsep}{env['PATH']}",
        "STUB_DAEMON_ENV": host["daemon_env"],
        "STUB_VOLUME": str(host["vol"]),
        "STUB_MOUNT": host.get("mount") or f"volume|tinyassets-data|{host['vol']}",
        "TINYASSETS_BACKUP_ENV_OWNER": "",
        "TINYASSETS_ENV_FILE": str(host["env_file"]),
        "TINYASSETS_LEGACY_ENV_FILE": str(host["env_file"]) + ".legacy",
        "TINYASSETS_ENV_OWNER": "",
        "TINYASSETS_ENV_READ_USER": "",
        "TINYASSETS_ETC_DIR": str(host["etc"]),
        "TINYASSETS_OPT_DIR": str(host["opt"]),
        "TINYASSETS_SYSTEMD_DIR": str(host["systemd"]),
        "STUB_SYSTEMCTL_LOG": str(host["systemctl_log"]),
    })
    return subprocess.run(
        ["bash", str(SCRIPT), str(HELPER)],
        capture_output=True, text=True, env=env, check=False,
    )


def _write(path: Path, text: str = "x") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_refuses_while_the_retired_compose_is_live(tmp_path):
    host = _host(tmp_path, daemon_env="HOME=/app\nCODEX_HOME=/data/.codex")
    _write(host["vol"] / ".codex" / "auth.json", SECRET)
    before = host["env_file"].read_text(encoding="utf-8")

    result = _run(host)

    assert result.returncode == 1
    assert "nothing was touched" in result.stderr
    assert (host["vol"] / ".codex" / "auth.json").exists()
    assert host["env_file"].read_text(encoding="utf-8") == before


def test_scrubs_env_and_removes_both_login_dirs_in_full(tmp_path):
    host = _host(tmp_path)
    codex = host["vol"] / ".codex"
    claude = host["vol"] / ".claude"
    _write(codex / "auth.json", SECRET)
    _write(codex / "config.toml")
    _write(codex / "sessions" / "2026" / "09" / "rollout-secret-transcript.jsonl", SECRET)
    _write(codex / "state_5.sqlite")
    _write(claude / ".credentials.json", SECRET)
    _write(claude / "projects" / "-data-u-tiny" / "turn-secret-transcript.jsonl", SECRET)
    _write(claude / ".claude.json")
    _write(claude / "backups" / ".claude.json.backup.1")
    universe = host["vol"] / "u-tiny"
    _write(universe / "wiki" / "page.md", "universe content")

    result = _run(host)

    assert result.returncode == 0, result.stderr
    env_text = host["env_file"].read_text(encoding="utf-8")
    for name in (
        "CLAUDE_CODE_OAUTH_TOKEN", "GEMINI_API_KEY", "GROQ_API_KEY", "XAI_API_KEY",
        "TINYASSETS_GITHUB_PUSH_CAPABILITIES", "TINYASSETS_GITHUB_PR_CAPABILITIES",
    ):
        assert name not in env_text
    # The owner-connection switch is not a credential and stays.
    assert "TINYASSETS_GITHUB_OUTBOUND_VIA_CONNECTION=1" in env_text
    assert "TINYASSETS_IMAGE=ghcr.io/x@sha256:abc" in env_text
    assert "WORKOS_API_KEY=keep-me" in env_text

    assert not codex.exists(), ".codex was not removed in full"
    assert not claude.exists(), ".claude was not removed in full"
    assert (universe / "wiki" / "page.md").exists(), "a universe was touched"
    assert "removed .codex in full (3 files" in result.stdout
    assert "removed .claude in full (3 files" in result.stdout
    assert "retire_platform_llm_logins_result=complete" in result.stdout

    out = result.stdout + result.stderr
    assert SECRET not in out
    for transcript_name in ("rollout-secret-transcript", "turn-secret-transcript", "-data-u-tiny"):
        assert transcript_name not in out, "a transcript name reached the log"


def test_a_symlinked_login_dir_is_refused_and_its_target_untouched(tmp_path):
    host = _host(tmp_path)
    target = host["vol"] / "u-victim"
    _write(target / "precious.md", "universe content")
    (host["vol"] / ".codex").symlink_to(target, target_is_directory=True)

    result = _run(host)

    assert result.returncode == 1
    assert "refused" in result.stderr
    assert (target / "precious.md").exists(), "symlink target was deleted"
    assert (host["vol"] / ".codex").is_symlink(), "the refused path was touched"
    assert "retire_platform_llm_logins_result=refused" in result.stdout


def test_a_symlink_inside_a_login_dir_is_removed_not_followed(tmp_path):
    host = _host(tmp_path)
    outside = tmp_path / "outside"
    _write(outside / "keep.md", "not the platform's")
    codex = host["vol"] / ".codex"
    _write(codex / "config.toml")
    (codex / "escape").symlink_to(outside, target_is_directory=True)

    result = _run(host)

    assert result.returncode == 0, result.stderr
    assert not codex.exists()
    assert (outside / "keep.md").exists(), "rm followed a symlink out of the login dir"


def test_a_volume_root_reached_through_a_link_is_refused(tmp_path):
    """Volume guard 1: the tinyassets-data mountpoint must be its own real path."""
    host = _host(tmp_path)
    real_root = host["vol"]
    _write(real_root / ".claude" / "x.json")
    link_root = tmp_path / "volume-link"
    link_root.symlink_to(real_root, target_is_directory=True)
    host["vol"] = link_root
    host["mount"] = f"volume|tinyassets-data|{link_root}"

    result = _run(host)

    assert result.returncode == 1
    assert (real_root / ".claude" / "x.json").exists()
    assert "retire_platform_llm_logins_result=refused" in result.stdout


def test_refused_unless_the_daemon_mounts_this_volume_at_data(tmp_path):
    """Volume guard 2: docker inspect must show tinyassets-data at /data."""
    host = _host(tmp_path)
    _write(host["vol"] / ".codex" / "sessions" / "a.jsonl")
    host["mount"] = "volume|some-other-volume|/var/lib/docker/volumes/other/_data"

    result = _run(host)

    assert result.returncode == 1
    assert (host["vol"] / ".codex" / "sessions" / "a.jsonl").exists()
    assert "does not mount tinyassets-data at /data" in result.stderr


def test_a_universe_symlink_into_a_login_dir_blocks_the_delete(tmp_path):
    host = _host(tmp_path)
    codex = host["vol"] / ".codex"
    _write(codex / "sessions" / "a.jsonl")
    universe = host["vol"] / "u-01kxm1vszd8hwp7em418asq8h9"
    (universe / ".runtime").mkdir(parents=True)
    (universe / ".runtime" / "codex-home").symlink_to(codex, target_is_directory=True)

    result = _run(host)

    assert result.returncode == 1
    assert (codex / "sessions" / "a.jsonl").exists(), "deleted a dir a universe points at"
    assert "universe symlink(s)/config(s) point at .codex" in result.stderr


def test_a_universe_config_naming_a_login_dir_blocks_the_delete(tmp_path):
    host = _host(tmp_path)
    claude = host["vol"] / ".claude"
    _write(claude / "projects" / "t.jsonl")
    _write(host["vol"] / "u-tiny" / "config.yaml", "claude_config_dir: /data/.claude\n")

    result = _run(host)

    assert result.returncode == 1
    assert (claude / "projects" / "t.jsonl").exists()


def test_gh_token_moves_to_the_host_only_backup_env(tmp_path):
    host = _host(tmp_path)

    result = _run(host)

    assert result.returncode == 0, result.stderr
    assert "GH_TOKEN" not in host["env_file"].read_text(encoding="utf-8")
    backup_env = host["etc"] / "backup.env"
    assert f"GH_TOKEN={BACKUP_TOKEN}" in backup_env.read_text(encoding="utf-8")
    dropin = host["systemd"] / "tinyassets-backup.service.d" / "10-backup-env.conf"
    assert f"EnvironmentFile=-{backup_env}" in dropin.read_text(encoding="utf-8")
    assert BACKUP_TOKEN not in result.stdout + result.stderr

    again = _run(host)
    assert again.returncode == 0, again.stderr
    assert "holds no GH_TOKEN" in again.stdout
    assert f"GH_TOKEN={BACKUP_TOKEN}" in backup_env.read_text(encoding="utf-8")


def test_is_idempotent(tmp_path):
    host = _host(tmp_path)
    _write(host["vol"] / ".codex" / "auth.json", SECRET)

    first = _run(host)
    second = _run(host)

    assert first.returncode == 0, first.stderr
    assert second.returncode == 0, second.stderr
    assert "holds none of the retired names" in second.stdout
    assert ".codex absent" in second.stdout
    assert ".claude absent" in second.stdout


def _refresher(host: dict, *, key_line: str | None = None) -> dict:
    files = {
        "timer": host["systemd"] / "github-app-token-refresher.timer",
        "service": host["systemd"] / "github-app-token-refresher.service",
        "script": host["opt"] / "scripts" / "github-app-token-refresher.py",
        "env": host["etc"] / "github-app-token-refresher.env",
        "key": host["etc"] / "github-app-private-key.pem",
    }
    for path in files.values():
        _write(path, "x")
    files["env"].write_text(
        "GITHUB_APP_ID=123456\nGITHUB_APP_INSTALLATION_ID=7654321\n"
        + (key_line if key_line is not None
           else f"GITHUB_APP_PRIVATE_KEY_FILE={files['key']}\n"),
        encoding="utf-8",
    )
    files["key"].write_text(SECRET, encoding="utf-8")
    return files


def test_retires_the_github_app_token_refresher(tmp_path):
    host = _host(tmp_path)
    files = _refresher(host)

    result = _run(host)

    assert result.returncode == 0, result.stderr
    for name, path in files.items():
        assert not path.exists(), f"refresher {name} still present"
    log = host["systemctl_log"].read_text(encoding="utf-8")
    assert "disable --now github-app-token-refresher.timer" in log
    assert "daemon-reload" in log
    # Public identifiers are reported so the founder can delete the App.
    assert "GITHUB_APP_ID=123456" in result.stdout
    assert "GITHUB_APP_INSTALLATION_ID=7654321" in result.stdout
    assert SECRET not in result.stdout + result.stderr


def test_a_key_outside_the_documented_path_is_named_not_deleted(tmp_path):
    host = _host(tmp_path)
    other_key = tmp_path / "elsewhere" / "app.pem"
    _write(other_key, SECRET)
    _refresher(host, key_line=f"GITHUB_APP_PRIVATE_KEY_FILE={other_key}\n")

    result = _run(host)

    assert result.returncode == 0, result.stderr
    assert other_key.exists(), "a key at an unexpected path was deleted"
    assert str(other_key) in result.stdout
    assert "retire_platform_llm_logins_result=github_key_held" in result.stdout
