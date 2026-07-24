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
import textwrap
import time
from pathlib import Path

import pytest

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


def _run_fake_claude_main(
    monkeypatch, tmp_path: Path, fake_popen, *extra_args: str
) -> int:
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
            *extra_args,
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
    group_events: list[tuple[int, int]] = []
    current_group = 7000

    def fake_popen(cmd, **kwargs):
        captured.update(kwargs)
        return _FinishedPeer(cmd, **kwargs)

    monkeypatch.setattr(peer_agent.sys, "platform", "linux")
    monkeypatch.setattr(peer_agent.os, "getpid", lambda: 8123)
    monkeypatch.setattr(
        peer_agent.os, "getpgrp", lambda: current_group, raising=False
    )

    def set_own_group(pid, pgid):
        nonlocal current_group
        group_events.append((pid, pgid))
        current_group = 8123

    monkeypatch.setattr(
        peer_agent.os,
        "setpgid",
        set_own_group,
        raising=False,
    )
    monkeypatch.setattr(
        peer_agent, "subprocess_env_for_provider", lambda provider: {}
    )

    assert _run_fake_claude_main(monkeypatch, tmp_path, fake_popen) == 0
    assert group_events == [(0, 0)]
    assert "start_new_session" not in captured


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


def test_posix_cleanup_uses_wrapper_group_not_provider_pid(monkeypatch):
    proc = _TreeProcess()
    group_kills: list[tuple[int, signal.Signals]] = []
    monkeypatch.setattr(peer_agent.sys, "platform", "linux")
    monkeypatch.setattr(
        peer_agent.os, "getpgrp", lambda: 8123, raising=False
    )

    def fake_killpg(pgid, sig):
        group_kills.append((pgid, sig))

    monkeypatch.setattr(
        peer_agent.os,
        "killpg",
        fake_killpg,
        raising=False,
    )

    with pytest.raises(peer_agent.PeerCleanupError, match="unexpectedly returned"):
        peer_agent.kill_tree(proc)

    assert group_kills == [
        (8123, getattr(signal, "SIGKILL", signal.SIGTERM))
    ]
    assert not proc.events


def test_posix_launcher_rejects_failure_to_own_its_process_group(
    tmp_path: Path, monkeypatch, capsys
):
    monkeypatch.setattr(peer_agent.sys, "platform", "linux")
    monkeypatch.setattr(peer_agent.os, "getpid", lambda: 8123)
    monkeypatch.setattr(
        peer_agent.os, "getpgrp", lambda: 7000, raising=False
    )
    monkeypatch.setattr(
        peer_agent.os,
        "setpgid",
        lambda pid, pgid: (_ for _ in ()).throw(PermissionError("denied")),
        raising=False,
    )
    monkeypatch.setattr(
        peer_agent, "subprocess_env_for_provider", lambda provider: {}
    )

    assert _run_fake_claude_main(
        monkeypatch,
        tmp_path,
        lambda cmd, **kwargs: pytest.fail("provider must not launch"),
    ) == 125
    assert "process group" in capsys.readouterr().err


def test_windows_cleanup_uses_taskkill_tree_and_reaps(
    monkeypatch,
):
    proc = _TreeProcess()
    commands: list[list[str]] = []
    monkeypatch.setattr(peer_agent.sys, "platform", "win32")
    monkeypatch.setattr(
        peer_agent.subprocess,
        "run",
        lambda cmd, **kwargs: (
            commands.append(cmd)
            or subprocess.CompletedProcess(cmd, 0, b"", b"")
        ),
    )

    peer_agent.kill_tree(proc)

    assert commands == [["taskkill", "/F", "/T", "/PID", str(proc.pid)]]
    assert any(event[0] == "wait" for event in proc.events)


def test_windows_cleanup_surfaces_taskkill_failure(
    monkeypatch,
):
    proc = _TreeProcess()
    monkeypatch.setattr(peer_agent.sys, "platform", "win32")
    monkeypatch.setattr(
        peer_agent.subprocess,
        "run",
        lambda cmd, **kwargs: subprocess.CompletedProcess(
            cmd, 1, b"", b"access denied"
        ),
    )

    with pytest.raises(RuntimeError, match="taskkill"):
        peer_agent.kill_tree(proc)

    assert any(event[0] == "wait" for event in proc.events)


def test_windows_cleanup_surfaces_wrapper_wait_timeout(
    monkeypatch,
):
    class WaitTimesOut(_TreeProcess):
        def wait(self, timeout=None):
            self.events.append(("wait", timeout))
            raise subprocess.TimeoutExpired("fake-peer", timeout)

    proc = WaitTimesOut()
    monkeypatch.setattr(peer_agent.sys, "platform", "win32")
    monkeypatch.setattr(
        peer_agent.subprocess,
        "run",
        lambda cmd, **kwargs: subprocess.CompletedProcess(cmd, 0, b"", b""),
    )

    with pytest.raises(RuntimeError, match="did not exit"):
        peer_agent.kill_tree(proc)

    assert proc.events == [("wait", 10)]


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
    monkeypatch.setattr(peer_agent.sys, "platform", "win32")
    monkeypatch.setattr(
        peer_agent, "subprocess_env_for_provider", lambda provider: {}
    )

    assert _run_fake_claude_main(monkeypatch, tmp_path, fake_popen) == 124
    assert events == ["timeout", "kill-tree", "wait", "reap-pipes"]


def test_posix_timeout_flushes_failure_artifact_before_terminating_own_group(
    tmp_path: Path, monkeypatch
):
    out_path = tmp_path / "peer-result.md"
    events: list[str] = []

    class TimedOutPeer:
        pid = 9003
        returncode = None

        def communicate(self, input=None, timeout=None):
            events.append("timeout")
            raise subprocess.TimeoutExpired("fake-peer", timeout)

    def terminate_group():
        assert "exceeded 540s timeout" in out_path.read_text(encoding="utf-8")
        events.append("terminate-group")
        raise SystemExit(124)

    monkeypatch.setattr(peer_agent.sys, "platform", "linux")
    monkeypatch.setattr(peer_agent.os, "getpid", lambda: 8123)
    monkeypatch.setattr(
        peer_agent.os, "getpgrp", lambda: 8123, raising=False
    )
    monkeypatch.setattr(peer_agent, "_terminate_own_process_group", terminate_group)
    monkeypatch.setattr(
        peer_agent, "subprocess_env_for_provider", lambda provider: {}
    )

    with pytest.raises(SystemExit, match="124"):
        _run_fake_claude_main(
            monkeypatch,
            tmp_path,
            lambda cmd, **kwargs: TimedOutPeer(),
            "--out",
            str(out_path),
        )

    assert events == ["timeout", "terminate-group"]


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX process groups only")
def test_posix_timeout_kills_wrapper_provider_and_descendant(tmp_path: Path):
    pid_path = tmp_path / "provider-pids.txt"
    out_path = tmp_path / "peer-result.md"
    fake_provider = tmp_path / "fake-claude"
    fake_provider.write_text(
        textwrap.dedent(
            f"""\
            #!{sys.executable}
            import os
            import subprocess
            import sys
            import time
            from pathlib import Path

            child = subprocess.Popen(
                [sys.executable, "-c", "import time; time.sleep(60)"]
            )
            Path({str(pid_path)!r}).write_text(
                f"{{os.getpid()}} {{child.pid}}\\n",
                encoding="utf-8",
            )
            time.sleep(60)
            """
        ),
        encoding="utf-8",
    )
    fake_provider.chmod(0o755)
    env = os.environ.copy()
    env["CLAUDE_BIN"] = str(fake_provider)
    wrapper = subprocess.Popen(
        [
            sys.executable,
            str(_SCRIPT),
            "claude",
            "--cwd",
            str(tmp_path),
            "--prompt",
            "force timeout",
            "--timeout",
            "1",
            "--out",
            str(out_path),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        start_new_session=True,
    )
    wrapper_pid = wrapper.pid
    stdout, stderr = wrapper.communicate(timeout=10)

    assert wrapper.returncode != 0, (stdout, stderr)
    assert "exceeded 1s timeout" in out_path.read_text(encoding="utf-8")
    provider_pid, child_pid = map(
        int, pid_path.read_text(encoding="utf-8").split()
    )

    def is_absent_or_zombie(pid: int) -> bool:
        stat_path = Path(f"/proc/{pid}/stat")
        if not stat_path.exists():
            return True
        return stat_path.read_text(encoding="utf-8").split()[2] == "Z"

    deadline = time.monotonic() + 5
    while time.monotonic() < deadline and not all(
        is_absent_or_zombie(pid)
        for pid in (wrapper_pid, provider_pid, child_pid)
    ):
        time.sleep(0.02)
    assert all(
        is_absent_or_zombie(pid)
        for pid in (wrapper_pid, provider_pid, child_pid)
    )


def test_post_spawn_communicate_oserror_cleans_up_and_reports_runtime_failure(
    tmp_path: Path, monkeypatch, capsys
):
    events: list[str] = []

    class BrokenPipePeer:
        pid = 9002
        returncode = None

        def __init__(self, cmd, **kwargs):
            self.cmd = cmd
            self.calls = 0

        def communicate(self, input=None, timeout=None):
            self.calls += 1
            if self.calls == 1:
                events.append("communicate-error")
                raise OSError("synthetic pipe failure")
            events.append("reap-pipes")
            self.returncode = -9
            return b"", b""

        def wait(self, timeout=None):
            events.append("wait")
            self.returncode = -9
            return self.returncode

    def fake_kill_tree(proc):
        events.append("kill-tree")
        proc.wait(timeout=10)

    monkeypatch.setattr(peer_agent, "kill_tree", fake_kill_tree)
    monkeypatch.setattr(peer_agent.sys, "platform", "win32")
    monkeypatch.setattr(
        peer_agent, "subprocess_env_for_provider", lambda provider: {}
    )

    assert _run_fake_claude_main(
        monkeypatch, tmp_path, lambda cmd, **kwargs: BrokenPipePeer(cmd, **kwargs)
    ) == 126
    assert events == ["communicate-error", "kill-tree", "wait", "reap-pipes"]
    assert "communication failed after launch" in capsys.readouterr().err
