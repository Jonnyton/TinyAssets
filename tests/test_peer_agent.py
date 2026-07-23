"""Security and process-lifecycle proofs for the fake peer launcher.

Every subprocess in this module is a fake.  No provider executable or model is
ever resolved or invoked.
"""

from __future__ import annotations

import importlib.util
import os
import signal
import subprocess
import sys
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "peer_agent.py"
_SPEC = importlib.util.spec_from_file_location("peer_agent_under_test", _SCRIPT)
assert _SPEC and _SPEC.loader
peer_agent = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(peer_agent)


class _FinishedPeer:
    pid = 4242
    returncode = 0

    def __init__(self, cmd, **kwargs):
        self.cmd = cmd
        self.kwargs = kwargs
        self.communications = 0

    def communicate(self, input=None, timeout=None):
        self.communications += 1
        return b"fake peer answer", b""

    def wait(self, timeout=None):
        return self.returncode


def _run_fake_claude_main(monkeypatch, tmp_path: Path, fake_popen) -> int:
    monkeypatch.setattr(peer_agent, "resolve_claude", lambda: "fake-claude")
    monkeypatch.setattr(peer_agent.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "peer_agent.py",
            "claude",
            "--cwd",
            str(tmp_path),
            "--prompt",
            "fake prompt",
            "--timeout",
            "540",
        ],
    )
    return peer_agent.main()


def test_peer_launcher_scrubs_village_and_mcp_bearers_but_preserves_provider_auth(
    tmp_path: Path, monkeypatch
):
    captured: dict = {}

    def fake_provider_env(provider):
        assert provider == "claude-code"
        return {
            "TINYASSETS_VILLAGE_TOKEN": "must-not-reach-peer",
            "WORKFLOW_MCP_TOKEN": "must-not-reach-peer",
            "FAKE_PROVIDER_SUBSCRIPTION_AUTH": "must-survive",
            "PATH": os.environ.get("PATH", ""),
        }

    def fake_popen(cmd, **kwargs):
        captured.update(cmd=cmd, kwargs=kwargs)
        return _FinishedPeer(cmd, **kwargs)

    monkeypatch.setattr(
        peer_agent, "subprocess_env_for_provider", fake_provider_env
    )

    assert _run_fake_claude_main(monkeypatch, tmp_path, fake_popen) == 0

    env = captured["kwargs"]["env"]
    assert "TINYASSETS_VILLAGE_TOKEN" not in env
    assert "WORKFLOW_MCP_TOKEN" not in env
    assert env["FAKE_PROVIDER_SUBSCRIPTION_AUTH"] == "must-survive"


def test_peer_launcher_owns_a_posix_process_group(
    tmp_path: Path, monkeypatch
):
    captured: dict = {}

    def fake_popen(cmd, **kwargs):
        captured.update(kwargs)
        return _FinishedPeer(cmd, **kwargs)

    monkeypatch.setattr(peer_agent.sys, "platform", "linux")
    monkeypatch.setattr(
        peer_agent, "subprocess_env_for_provider", lambda provider: {}
    )

    assert _run_fake_claude_main(monkeypatch, tmp_path, fake_popen) == 0
    assert captured.get("start_new_session") is True


def test_peer_launcher_owns_a_windows_process_group(
    tmp_path: Path, monkeypatch
):
    captured: dict = {}
    new_group = 0x00000200

    def fake_popen(cmd, **kwargs):
        captured.update(kwargs)
        return _FinishedPeer(cmd, **kwargs)

    monkeypatch.setattr(peer_agent.sys, "platform", "win32")
    monkeypatch.setattr(
        peer_agent.subprocess, "CREATE_NEW_PROCESS_GROUP", new_group, raising=False
    )
    monkeypatch.setattr(
        peer_agent, "subprocess_env_for_provider", lambda provider: {}
    )

    assert _run_fake_claude_main(monkeypatch, tmp_path, fake_popen) == 0
    assert captured.get("creationflags", 0) & new_group


class _TreeProcess:
    pid = 7331

    def __init__(self):
        self.events: list[tuple] = []

    def kill(self):
        self.events.append(("proc.kill",))

    def wait(self, timeout=None):
        self.events.append(("wait", timeout))
        return 0


def test_posix_cleanup_targets_the_process_group_and_reaps(
    monkeypatch,
):
    proc = _TreeProcess()
    group_kills: list[tuple[int, signal.Signals]] = []
    monkeypatch.setattr(peer_agent.sys, "platform", "linux")
    monkeypatch.setattr(peer_agent.os, "getpgid", lambda pid: pid, raising=False)
    monkeypatch.setattr(
        peer_agent.os,
        "killpg",
        lambda pgid, sig: group_kills.append((pgid, sig)),
        raising=False,
    )

    peer_agent.kill_tree(proc)

    assert group_kills
    assert group_kills[0][0] == proc.pid
    assert group_kills[0][1] in {signal.SIGTERM, signal.SIGKILL}
    assert any(event[0] == "wait" for event in proc.events)


def test_windows_cleanup_uses_taskkill_tree_and_reaps(
    monkeypatch,
):
    proc = _TreeProcess()
    commands: list[list[str]] = []
    monkeypatch.setattr(peer_agent.sys, "platform", "win32")
    monkeypatch.setattr(
        peer_agent.subprocess,
        "run",
        lambda cmd, **kwargs: commands.append(cmd),
    )

    peer_agent.kill_tree(proc)

    assert commands == [["taskkill", "/F", "/T", "/PID", str(proc.pid)]]
    assert any(event[0] == "wait" for event in proc.events)


class _TimeoutPeer:
    pid = 9001
    returncode = None

    def __init__(self, cmd, events: list[str], **kwargs):
        self.cmd = cmd
        self.events = events
        self.calls = 0

    def communicate(self, input=None, timeout=None):
        self.calls += 1
        if self.calls == 1:
            self.events.append("timeout")
            raise subprocess.TimeoutExpired(self.cmd, timeout)
        self.events.append("reap-pipes")
        self.returncode = -9
        return b"", b""

    def wait(self, timeout=None):
        self.events.append("wait")
        self.returncode = -9
        return self.returncode


def test_timeout_cleans_and_reaps_before_launcher_returns(
    tmp_path: Path, monkeypatch
):
    events: list[str] = []
    process: _TimeoutPeer | None = None

    def fake_popen(cmd, **kwargs):
        nonlocal process
        process = _TimeoutPeer(cmd, events, **kwargs)
        return process

    def fake_kill_tree(proc):
        assert proc is process
        events.append("kill-tree")
        proc.wait(timeout=10)

    monkeypatch.setattr(peer_agent, "kill_tree", fake_kill_tree)
    monkeypatch.setattr(
        peer_agent, "subprocess_env_for_provider", lambda provider: {}
    )

    assert _run_fake_claude_main(monkeypatch, tmp_path, fake_popen) == 124
    assert events == ["timeout", "kill-tree", "wait", "reap-pipes"]
