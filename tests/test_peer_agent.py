from __future__ import annotations

import argparse
import importlib.util
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


# --- Fail-closed dispatch -------------------------------------------------
#
# `openspec/specs/development-coordination-runtime/spec.md` requires that "a
# provider failure, timeout, or non-launchable CLI SHALL produce a non-zero
# exit and an explicit error marker rather than a silent empty result."
#
# That contract used to be covered by 11 tests against `scripts/codex_review.py`
# in `tests/test_codex_dispatch.py`. The 2026-08-26 cut consolidated the two
# dispatchers onto `peer_agent.py` and deleted those tests with the script,
# leaving the surviving file testing only console flags and worktree
# permissions -- so every fail-closed path could regress to silent success with
# CI green. Found by cross-family review of PR #2561. Ported here against the
# surviving implementation.


class _FakeProc:
    """Stand-in for Popen: scripted returncode / output / timeout."""

    def __init__(self, *, returncode=0, stdout=b"", stderr=b"", timeout=False):
        self.returncode = returncode
        self._stdout = stdout
        self._stderr = stderr
        self._timeout = timeout
        self.communicate_input = None
        self.killed = False

    def communicate(self, input=None, timeout=None):  # noqa: A002 - Popen's name
        if self._timeout:
            self._timeout = False  # the post-kill reap call succeeds
            raise subprocess.TimeoutExpired(cmd="peer", timeout=timeout or 0)
        self.communicate_input = input
        return self._stdout, self._stderr

    def kill(self):
        self.killed = True

    def wait(self, timeout=None):
        return self.returncode

    @property
    def pid(self):
        return 4242


def _run_main(monkeypatch, tmp_path, proc, *, provider="claude", extra=()):
    """Invoke peer_agent.main() with a scripted subprocess; return (rc, out)."""
    out = tmp_path / "verdict.txt"
    monkeypatch.setattr(peer_agent.subprocess, "Popen", lambda *a, **k: proc)
    monkeypatch.setattr(peer_agent, "kill_tree", lambda p: p.kill())
    monkeypatch.setattr(
        peer_agent.sys,
        "argv",
        [
            "peer_agent.py",
            provider,
            "--prompt",
            "review this",
            "--cwd",
            str(tmp_path),
            "--out",
            str(out),
            *extra,
        ],
    )
    rc = peer_agent.main()
    return rc, (out.read_text(encoding="utf-8") if out.exists() else "")


def test_timeout_kills_the_tree_and_writes_an_error_marker(monkeypatch, tmp_path):
    proc = _FakeProc(timeout=True)
    rc, out = _run_main(monkeypatch, tmp_path, proc, extra=("--timeout", "5"))
    assert rc == 124
    assert "[peer_agent] ERROR" in out
    assert "timeout" in out.lower()
    assert proc.killed, "a timed-out .cmd leaves node grandchildren alive"


def test_non_launchable_binary_writes_an_error_marker(monkeypatch, tmp_path):
    def _boom(*a, **k):
        raise OSError(2, "No such file or directory")

    out = tmp_path / "verdict.txt"
    monkeypatch.setattr(peer_agent.subprocess, "Popen", _boom)
    monkeypatch.setattr(
        peer_agent.sys,
        "argv",
        [
            "peer_agent.py", "codex", "--prompt", "x",
            "--cwd", str(tmp_path), "--out", str(out),
        ],
    )
    assert peer_agent.main() == 127
    text = out.read_text(encoding="utf-8")
    assert "[peer_agent] ERROR" in text
    assert "not launchable" in text


def test_zero_exit_with_empty_output_is_a_failure_not_a_silent_pass(
    monkeypatch, tmp_path
):
    # The whole point: exit 0 + nothing produced must NOT read as a clean review.
    rc, out = _run_main(monkeypatch, tmp_path, _FakeProc(returncode=0, stdout=b"  \n"))
    assert rc == 2
    assert "[peer_agent] ERROR" in out
    assert "empty output" in out


def test_nonzero_exit_writes_an_error_marker_carrying_stderr(monkeypatch, tmp_path):
    rc, out = _run_main(
        monkeypatch,
        tmp_path,
        _FakeProc(returncode=3, stdout=b"partial", stderr=b"upstream exploded"),
    )
    assert rc == 2
    assert "[peer_agent] ERROR" in out
    assert "upstream exploded" in out


def test_prompt_reaches_the_provider_on_stdin_not_argv(monkeypatch, tmp_path):
    # Windows cmd.exe truncates argv at a newline, which silently shortened
    # multi-line review prompts -- stdin is the contract.
    proc = _FakeProc(returncode=0, stdout=b"VERDICT: APPROVE")
    rc, _ = _run_main(monkeypatch, tmp_path, proc)
    assert rc == 0
    assert proc.communicate_input == b"review this"


def test_success_leaves_the_provider_output_intact(monkeypatch, tmp_path):
    rc, out = _run_main(
        monkeypatch, tmp_path, _FakeProc(returncode=0, stdout=b"VERDICT: REJECT\n")
    )
    assert rc == 0
    assert "VERDICT: REJECT" in out
    assert "[peer_agent] ERROR" not in out
