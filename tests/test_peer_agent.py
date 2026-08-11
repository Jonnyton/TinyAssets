from __future__ import annotations

import argparse
import importlib.util
import os
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "peer_agent.py"
SPEC = importlib.util.spec_from_file_location("peer_agent_contract", SCRIPT)
assert SPEC is not None
peer_agent = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = peer_agent
SPEC.loader.exec_module(peer_agent)


def _args(*, write: bool) -> argparse.Namespace:
    return argparse.Namespace(
        cwd="C:\\worktree",
        write=write,
        model=None,
        effort=None,
    )


def test_windows_provider_processes_are_created_without_a_console(
    monkeypatch,
) -> None:
    monkeypatch.setattr(peer_agent.sys, "platform", "win32")

    assert peer_agent.creation_flags() == 0x08000000


def test_non_windows_provider_processes_keep_default_creation_flags(
    monkeypatch,
) -> None:
    monkeypatch.setattr(peer_agent.sys, "platform", "linux")

    assert peer_agent.creation_flags() == 0


def test_subscription_cli_env_strips_api_keys_without_product_authority(
    monkeypatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "openai-secret")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "anthropic-secret")
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", "C:\\claude-subscription")
    monkeypatch.setenv("CODEX_HOME", "C:\\codex-subscription")

    env = peer_agent.subscription_cli_env()

    assert "OPENAI_API_KEY" not in env
    assert "ANTHROPIC_API_KEY" not in env
    assert env["CLAUDE_CONFIG_DIR"] == "C:\\claude-subscription"
    assert env["CODEX_HOME"] == "C:\\codex-subscription"
    assert env["PATH"] == os.environ["PATH"]


def test_git_common_dir_is_resolved_as_an_absolute_path(tmp_path: Path) -> None:
    common = tmp_path / "source" / ".git"
    common.mkdir(parents=True)
    calls: list[list[str]] = []

    def runner(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=str(common) + "\n",
            stderr="",
        )

    assert peer_agent.resolve_git_common_dir(tmp_path, runner=runner) == str(
        common.resolve()
    )
    assert calls == [
        [
            "git",
            "-C",
            str(tmp_path),
            "rev-parse",
            "--path-format=absolute",
            "--git-common-dir",
        ]
    ]


def test_git_common_dir_discovery_fails_closed_for_non_git_directory(
    tmp_path: Path,
) -> None:
    def runner(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(command, 128, stdout="", stderr="not a repo")

    assert peer_agent.resolve_git_common_dir(tmp_path, runner=runner) is None


def test_write_codex_command_grants_only_the_resolved_git_common_dir(
    monkeypatch,
) -> None:
    monkeypatch.setattr(peer_agent, "resolve_codex", lambda: "codex.exe")

    command = peer_agent.build_codex_cmd(
        _args(write=True),
        "C:\\result.md",
        git_common_dir="C:\\source\\.git",
    )

    assert command.count("--add-dir") == 1
    assert command[command.index("--add-dir") + 1] == "C:\\source\\.git"
    assert "approval_policy=never" in command
    assert command[command.index("-s") + 1] == "danger-full-access"
    assert "--full-auto" not in command


def test_read_only_codex_command_never_grants_git_metadata(monkeypatch) -> None:
    monkeypatch.setattr(peer_agent, "resolve_codex", lambda: "codex.exe")

    command = peer_agent.build_codex_cmd(
        _args(write=False),
        "C:\\result.md",
        git_common_dir="C:\\source\\.git",
    )

    assert "--add-dir" not in command
    assert command[-2:] == ["-s", "read-only"]
