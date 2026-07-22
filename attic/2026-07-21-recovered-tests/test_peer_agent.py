"""Tests for scripts/peer_agent.py — CLI construction and result contract.

All subprocess calls are mocked; these tests never launch a real CLI.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

import peer_agent  # noqa: E402


class FakeProc:
    """Minimal Popen stand-in. communicate() returns (stdout, stderr) bytes."""

    def __init__(self, stdout=b"result text", stderr=b"", returncode=0):
        self._stdout = stdout
        self._stderr = stderr
        self.returncode = returncode
        self.pid = 4321

    def communicate(self, input=None, timeout=None):
        return self._stdout, self._stderr

    def wait(self, timeout=None):
        return self.returncode

    def kill(self):
        pass


def _args(**overrides):
    base = dict(
        provider="claude",
        prompt="do the thing",
        prompt_file=None,
        system=None,
        out=None,
        cwd=".",
        timeout=1800,
        write=False,
        model=None,
        effort=None,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def _run_main(monkeypatch, argv, popen_return=None, popen_side_effect=None):
    """Patch Popen and argv; returns the Popen mock for further wiring."""
    popen_mock = MagicMock()
    if popen_side_effect is not None:
        popen_mock.side_effect = popen_side_effect
    else:
        popen_mock.return_value = popen_return or FakeProc()
    monkeypatch.setattr(peer_agent.subprocess, "Popen", popen_mock)
    monkeypatch.setattr(sys, "argv", ["peer_agent.py", *argv])
    return popen_mock


# --- command construction -------------------------------------------------


def test_claude_default_is_read_only():
    cmd = peer_agent.build_claude_cmd(_args())
    assert cmd[1] == "-p"
    assert "--dangerously-skip-permissions" not in cmd


def test_claude_write_adds_skip_permissions():
    cmd = peer_agent.build_claude_cmd(_args(write=True))
    assert "--dangerously-skip-permissions" in cmd


def test_claude_default_model_is_fable():
    """Default tracks the latest Claude frontier via the fable alias."""
    cmd = peer_agent.build_claude_cmd(_args())
    assert cmd[cmd.index("--model") + 1] == "fable"


def test_claude_model_flag_overrides_default():
    cmd = peer_agent.build_claude_cmd(_args(model="sonnet"))
    assert cmd[cmd.index("--model") + 1] == "sonnet"


def test_codex_default_has_no_model_pin(monkeypatch):
    """No -m by default: codex inherits the host's configured frontier model."""
    monkeypatch.delenv("WORKFLOW_CODEX_MODEL", raising=False)
    cmd = peer_agent.build_codex_cmd(_args(provider="codex"), "out.md")
    assert "-m" not in cmd


def test_codex_model_env_and_flag_precedence(monkeypatch):
    monkeypatch.setenv("WORKFLOW_CODEX_MODEL", "gpt-5.6-sol")
    cmd = peer_agent.build_codex_cmd(_args(provider="codex"), "out.md")
    assert cmd[cmd.index("-m") + 1] == "gpt-5.6-sol"
    cmd = peer_agent.build_codex_cmd(_args(provider="codex", model="gpt-x"), "out.md")
    assert cmd[cmd.index("-m") + 1] == "gpt-x"


def test_claude_system_and_model_flags():
    cmd = peer_agent.build_claude_cmd(_args(system="be terse", model="opus"))
    assert cmd[cmd.index("--system-prompt") + 1] == "be terse"
    assert cmd[cmd.index("--model") + 1] == "opus"


def test_codex_default_is_read_only():
    args = _args(provider="codex", cwd="C:/repo")
    cmd = peer_agent.build_codex_cmd(args, "C:/out.md")
    assert "read-only" in cmd
    assert "approval_policy=never" in cmd
    assert "--full-auto" not in cmd
    assert cmd[cmd.index("-C") + 1] == "C:/repo"
    assert cmd[cmd.index("-o") + 1] == "C:/out.md"


def test_codex_write_uses_full_auto():
    cmd = peer_agent.build_codex_cmd(_args(provider="codex", write=True), "out.md")
    assert "--full-auto" in cmd
    assert "read-only" not in cmd


def test_codex_model_and_effort_flags():
    cmd = peer_agent.build_codex_cmd(
        _args(provider="codex", model="gpt-5.4", effort="low"), "out.md"
    )
    assert cmd[cmd.index("-m") + 1] == "gpt-5.4"
    assert "model_reasoning_effort=low" in cmd


# --- cmd.exe metacharacter guard ------------------------------------------


def test_metachar_guard_only_applies_to_cmd_targets():
    assert peer_agent.unsafe_cmd_argv(["/usr/bin/claude", "-p", "a & b"]) is None
    assert peer_agent.unsafe_cmd_argv(["claude.cmd", "-p", "plain"]) is None
    assert peer_agent.unsafe_cmd_argv(["claude.cmd", "-p", "a & b"]) == "a & b"
    assert peer_agent.unsafe_cmd_argv(["claude.bat", "--model", 'x"%']) == 'x"%'


def test_main_rejects_metachar_argv_for_cmd(monkeypatch, tmp_path):
    out = tmp_path / "result.md"
    monkeypatch.setattr(peer_agent, "resolve_claude", lambda: "claude.cmd")
    _run_main(
        monkeypatch,
        ["claude", "--prompt", "hi", "--system", "a & b", "--out", str(out)],
    )
    assert peer_agent.main() == 2
    assert "metacharacter" in out.read_text(encoding="utf-8")


# --- prompt resolution -----------------------------------------------------


def test_prompt_arg_wins(tmp_path):
    f = tmp_path / "brief.md"
    f.write_text("from file", encoding="utf-8")
    assert peer_agent.resolve_prompt(_args(prompt="inline", prompt_file=str(f))) == "inline"


def test_prompt_file(tmp_path):
    f = tmp_path / "brief.md"
    f.write_text("from file", encoding="utf-8")
    assert peer_agent.resolve_prompt(_args(prompt=None, prompt_file=str(f))) == "from file"


def test_prompt_stdin(monkeypatch):
    monkeypatch.setattr(sys, "stdin", SimpleNamespace(read=lambda: "from stdin"))
    assert peer_agent.resolve_prompt(_args(prompt=None)) == "from stdin"


# --- main() success paths --------------------------------------------------


def test_main_claude_success_writes_out(monkeypatch, tmp_path, capsys):
    out = tmp_path / "result.md"
    _run_main(monkeypatch, ["claude", "--prompt", "hi", "--out", str(out)])
    assert peer_agent.main() == 0
    assert "result text" in out.read_text(encoding="utf-8")
    assert "result text" in capsys.readouterr().out


def test_main_codex_success_reads_o_file(monkeypatch, tmp_path):
    out = tmp_path / "result.md"

    def fake_popen(cmd, **kw):
        Path(cmd[cmd.index("-o") + 1]).write_text("codex verdict", encoding="utf-8")
        return FakeProc()

    _run_main(
        monkeypatch,
        ["codex", "--prompt", "hi", "--out", str(out)],
        popen_side_effect=fake_popen,
    )
    assert peer_agent.main() == 0
    assert "codex verdict" in out.read_text(encoding="utf-8")


def test_main_codex_system_prepended_to_prompt(monkeypatch, tmp_path):
    out = tmp_path / "result.md"
    seen = {}

    class PromptCapturingProc(FakeProc):
        def communicate(self, input=None, timeout=None):
            seen["prompt"] = input.decode("utf-8")
            return b"", b""

    def fake_popen(cmd, **kw):
        Path(cmd[cmd.index("-o") + 1]).write_text("ok", encoding="utf-8")
        return PromptCapturingProc()

    _run_main(
        monkeypatch,
        ["codex", "--prompt", "task", "--system", "be adversarial", "--out", str(out)],
        popen_side_effect=fake_popen,
    )
    assert peer_agent.main() == 0
    assert seen["prompt"].startswith("be adversarial\n\ntask")


def test_main_codex_out_path_is_absolute_for_cwd(monkeypatch, tmp_path):
    """Regression: relative --out + --cwd used to break codex -o (os error 3)."""
    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.chdir(tmp_path)

    def fake_popen(cmd, **kw):
        o_path = Path(cmd[cmd.index("-o") + 1])
        assert o_path.is_absolute(), f"-o path not absolute: {o_path}"
        o_path.write_text("ok", encoding="utf-8")
        return FakeProc()

    _run_main(
        monkeypatch,
        ["codex", "--prompt", "hi", "--out", "result.md", "--cwd", str(work)],
        popen_side_effect=fake_popen,
    )
    assert peer_agent.main() == 0


# --- main() failure contract: every failure leaves an ERROR block ---------


def test_main_missing_prompt_file(monkeypatch, tmp_path):
    out = tmp_path / "result.md"
    _run_main(
        monkeypatch,
        ["claude", "--prompt-file", str(tmp_path / "nope.md"), "--out", str(out)],
    )
    assert peer_agent.main() == 2
    assert "ERROR" in out.read_text(encoding="utf-8")


def test_main_empty_prompt_rejected(monkeypatch, tmp_path):
    out = tmp_path / "result.md"
    monkeypatch.setattr(
        sys, "argv", ["peer_agent.py", "claude", "--prompt", "   ", "--out", str(out)]
    )
    assert peer_agent.main() == 2
    assert "ERROR" in out.read_text(encoding="utf-8")


def test_main_invalid_cwd(monkeypatch, tmp_path):
    out = tmp_path / "result.md"
    _run_main(
        monkeypatch,
        ["claude", "--prompt", "hi", "--cwd", str(tmp_path / "nope"), "--out", str(out)],
    )
    assert peer_agent.main() == 2
    assert "not a directory" in out.read_text(encoding="utf-8")


def test_main_missing_binary_returns_127_with_out_block(monkeypatch, tmp_path):
    out = tmp_path / "result.md"
    _run_main(
        monkeypatch,
        ["claude", "--prompt", "hi", "--out", str(out)],
        popen_side_effect=OSError("WinError 193"),
    )
    assert peer_agent.main() == 127
    assert "ERROR" in out.read_text(encoding="utf-8")


def test_main_claude_nonzero_exit(monkeypatch, tmp_path):
    out = tmp_path / "result.md"
    _run_main(
        monkeypatch,
        ["claude", "--prompt", "hi", "--out", str(out)],
        popen_return=FakeProc(returncode=1, stderr=b"boom"),
    )
    assert peer_agent.main() == 2
    assert "ERROR" in out.read_text(encoding="utf-8")


def test_main_claude_empty_stdout_is_error(monkeypatch, tmp_path):
    out = tmp_path / "result.md"
    _run_main(
        monkeypatch,
        ["claude", "--prompt", "hi", "--out", str(out)],
        popen_return=FakeProc(stdout=b"   \n"),
    )
    assert peer_agent.main() == 2
    assert "empty output" in out.read_text(encoding="utf-8")


def test_main_codex_stale_out_not_accepted(monkeypatch, tmp_path):
    """A pre-existing --out must never pass as a fresh codex result."""
    out = tmp_path / "result.md"
    out.write_text("stale verdict from last week", encoding="utf-8")
    _run_main(
        monkeypatch,
        ["codex", "--prompt", "hi", "--out", str(out)],
        popen_return=FakeProc(),  # codex exits 0, writes nothing
    )
    assert peer_agent.main() == 2
    assert "stale verdict" not in out.read_text(encoding="utf-8")


def test_main_codex_empty_output_with_auth_signal(monkeypatch, tmp_path):
    out = tmp_path / "result.md"
    _run_main(
        monkeypatch,
        ["codex", "--prompt", "hi", "--out", str(out)],
        popen_return=FakeProc(stdout=b"", stderr=b"401 Unauthorized"),
    )
    assert peer_agent.main() == 2
    assert "auth" in out.read_text(encoding="utf-8").lower()


def test_main_timeout_kills_tree_returns_124(monkeypatch, tmp_path):
    out = tmp_path / "result.md"
    proc = FakeProc()
    calls = {"n": 0}

    def communicate(input=None, timeout=None):
        calls["n"] += 1
        if calls["n"] == 1:
            raise subprocess.TimeoutExpired(cmd=["claude"], timeout=5)
        return b"", b""

    proc.communicate = communicate
    kill_mock = MagicMock()
    monkeypatch.setattr(peer_agent, "kill_tree", kill_mock)
    _run_main(
        monkeypatch,
        ["claude", "--prompt", "hi", "--out", str(out), "--timeout", "5"],
        popen_return=proc,
    )
    assert peer_agent.main() == 124
    kill_mock.assert_called_once_with(proc)
    assert "timeout" in out.read_text(encoding="utf-8")


def test_main_codex_temp_out_cleaned_up(monkeypatch):
    """codex without --out: the mkstemp -o file is removed even on failure."""
    temp_paths = {}

    def fake_popen(cmd, **kw):
        temp_paths["p"] = cmd[cmd.index("-o") + 1]
        return FakeProc(returncode=1, stderr=b"boom")

    _run_main(monkeypatch, ["codex", "--prompt", "hi"], popen_side_effect=fake_popen)
    assert peer_agent.main() == 2
    assert not Path(temp_paths["p"]).exists()


def test_main_handles_non_cp1252_output(monkeypatch, tmp_path):
    """Regression: peer output with →/—/… must not crash the stdout echo."""
    import io

    out = tmp_path / "result.md"
    raw_stdout = io.BytesIO()
    monkeypatch.setattr(sys, "stdout", io.TextIOWrapper(raw_stdout, encoding="cp1252"))
    monkeypatch.setattr(
        sys, "stderr", io.TextIOWrapper(io.BytesIO(), encoding="cp1252")
    )
    _run_main(
        monkeypatch,
        ["claude", "--prompt", "hi", "--out", str(out)],
        popen_return=FakeProc(stdout="findings: a → b — c …\n".encode("utf-8")),
    )
    assert peer_agent.main() == 0
    assert "a → b" in out.read_text(encoding="utf-8")
    sys.stdout.flush()  # TextIOWrapper buffers; process exit flushes in real runs
    raw_stdout.seek(0)
    assert "a → b" in raw_stdout.read().decode("utf-8")
