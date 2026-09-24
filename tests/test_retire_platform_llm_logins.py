"""Behaviour of deploy/retire_platform_llm_logins.sh against a fake host.

The script runs on the production droplet after a green deploy canary. Here it
runs against a temp env file, a temp "data volume" and a stub ``docker`` that
answers the two inspections the script makes. It must:

* refuse to touch anything while the retired compose file is still live;
* scrub exactly the retired names from the env file, keeping every other line;
* delete the credential file in each platform login directory;
* delete a login directory only when nothing but CLI login/runtime artifacts
  remain, and KEEP (with a warning naming what it kept) any directory holding
  session transcripts or other content that may be a universe's own;
* log names and counts, never a value;
* retire the platform GitHub push path: scrub the push-capability maps, and
  remove the App token refresher units, script copy, env file and the App key
  at its documented path -- but name, not delete, a key configured elsewhere;
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
        "WORKOS_API_KEY=keep-me\n",
        encoding="utf-8",
    )
    bindir = tmp_path / "bin"
    bindir.mkdir()
    stub = bindir / "docker"
    stub.write_text(
        "#!/usr/bin/env bash\n"
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


def test_scrubs_env_and_credentials_but_keeps_content(tmp_path):
    host = _host(tmp_path)
    codex = host["vol"] / ".codex"
    claude = host["vol"] / ".claude"
    _write(codex / "auth.json", SECRET)
    _write(codex / "config.toml")
    _write(codex / "sessions" / "2026" / "09" / "rollout.jsonl")
    _write(codex / "state_5.sqlite")
    _write(claude / ".credentials.json", SECRET)
    _write(claude / "projects" / "-data-u-tiny" / "turn.jsonl")
    _write(claude / "policy-limits.json")

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

    assert not (codex / "auth.json").exists()
    assert not (claude / ".credentials.json").exists()
    # Content that may be a universe's own is kept, and named.
    assert (codex / "sessions" / "2026" / "09" / "rollout.jsonl").exists()
    assert (claude / "projects" / "-data-u-tiny" / "turn.jsonl").exists()
    assert "kept .codex" in result.stdout and "sessions(1 files)" in result.stdout
    assert "state_5.sqlite" in result.stdout
    assert "kept .claude" in result.stdout and "projects(1 files)" in result.stdout
    assert "retire_platform_llm_logins_result=credentials_removed_content_held" in result.stdout

    assert SECRET not in result.stdout + result.stderr


def test_removes_directories_holding_only_login_artifacts(tmp_path):
    host = _host(tmp_path)
    codex = host["vol"] / ".codex"
    claude = host["vol"] / ".claude"
    _write(codex / "auth.json", SECRET)
    _write(codex / "config.toml")
    _write(codex / ".tmp" / "plugins" / "x.json")
    (codex / "sessions").mkdir()  # empty content dir does not block
    _write(claude / "policy-limits.json")
    (claude / "session-env" / "abc").mkdir(parents=True)

    result = _run(host)

    assert result.returncode == 0, result.stderr
    assert not codex.exists()
    assert not claude.exists()
    assert "retire_platform_llm_logins_result=complete" in result.stdout


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
    assert "retire_platform_llm_logins_result=credentials_removed_content_held" in result.stdout
