"""The sandbox's ``ws`` binding: one extra bind, and a capability with edges.

Two layers are under test and they fail differently. The argv layer is a pure
function, so it is asserted EXACTLY -- a jail that quietly gains a mount is the
defect this catches, and a loose assertion would not. The runner layer is driven
through a real child process with :class:`PlainSubprocessLauncher` and a temp
directory standing in for ``/workspace``: the code that runs is the code that
ships, on every platform, which is why the runner is a string with an injectable
root rather than a module the test could monkeypatch into something else.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

from tinyassets import graph_compiler as gc
from tinyassets.branches import NodeDefinition
from tinyassets.effectors import EffectChain
from tinyassets.node_sandbox import (
    WORKSPACE_MOUNT_POINT,
    NodeSandbox,
    PlainSubprocessLauncher,
    WorkspaceLimits,
    WorkspaceMount,
    _bwrap_argv,
    _launcher_for_workspace,
    _validate_workspace_bind,
)

GIT_BINARY = shutil.which("git")
BWRAP = shutil.which("bwrap")
PY = sys.executable


# ──────────────────────────────────────────────────────────────────────────────
# The argv: exactly one extra bind, or none
# ──────────────────────────────────────────────────────────────────────────────


def _argv(**kwargs) -> list[str]:
    """The jail prefix with a filesystem where only /usr and /bin exist."""
    return _bwrap_argv(
        exists=lambda p: p in ("/usr", "/bin"),
        bwrap_path="/usr/bin/bwrap",
        realpath=lambda p: p,
        **kwargs,
    )


BASE_ARGV = [
    "/usr/bin/bwrap",
    "--die-with-parent",
    "--new-session",
    "--unshare-all",
    "--clearenv",
    "--setenv", "HOME", "/tmp",
    "--setenv", "PATH", "/usr/bin:/bin",
    "--setenv", "PYTHONIOENCODING", "utf-8",
    "--setenv", "PYTHONDONTWRITEBYTECODE", "1",
    "--dev", "/dev",
    "--proc", "/proc",
    "--tmpfs", "/tmp",
]


def test_argv_without_a_workspace_is_unchanged() -> None:
    assert _argv() == [
        *BASE_ARGV,
        "--chdir", "/tmp",
        "--ro-bind", "/usr", "/usr",
        "--ro-bind", "/bin", "/bin",
        "--",
    ]


def test_argv_with_a_workspace_adds_exactly_one_bind() -> None:
    argv = _argv(
        workspace_bind="/srv/pool/lease-1/gen-2/repo",
        allowed_workspace_roots=("/srv/pool",),
    )
    assert argv == [
        *BASE_ARGV,
        "--ro-bind", "/usr", "/usr",
        "--ro-bind", "/bin", "/bin",
        "--bind", "/srv/pool/lease-1/gen-2/repo", "/workspace",
        "--chdir", "/workspace",
        "--",
    ]
    # The working directory moved; /tmp is still a private tmpfs and HOME.
    assert argv.count("--chdir") == 1
    assert "/tmp" not in argv[argv.index("--chdir") + 1]
    assert argv.count("--bind") == 1
    assert "--share-net" not in argv


def test_the_workspace_bind_is_the_only_difference() -> None:
    plain = _argv()
    bound = _argv(
        workspace_bind="/srv/pool/x", allowed_workspace_roots=("/srv/pool",)
    )
    assert [item for item in plain if item not in bound] == []
    assert [item for item in bound if item not in plain] == [
        "--bind", "/srv/pool/x", "/workspace", "/workspace",
    ]


REFUSED_BINDS: list[tuple[str, str, tuple[str, ...]]] = [
    ("relative", "pool/lease/repo", ("/srv/pool",)),
    ("windows_drive", "C:/pool/repo", ("/srv/pool",)),
    ("dot_dot", "/srv/pool/../etc", ("/srv/pool",)),
    ("outside_root", "/etc", ("/srv/pool",)),
    ("root_prefix_not_boundary", "/srv/poolshop/repo", ("/srv/pool",)),
    ("never_bind_data", "/data/universes/u1", ("/srv/pool",)),
    ("no_roots_at_all", "/srv/pool/repo", ()),
    ("empty", "", ("/srv/pool",)),
    ("nul", "/srv/pool/re\x00po", ("/srv/pool",)),
]


@pytest.mark.parametrize(
    ("path", "roots"),
    [pytest.param(path, roots, id=name) for name, path, roots in REFUSED_BINDS],
)
def test_refused_workspace_binds(path: str, roots: tuple[str, ...]) -> None:
    with pytest.raises(ValueError):
        _argv(workspace_bind=path, allowed_workspace_roots=roots)


def test_a_universe_workspaces_root_under_data_is_bindable() -> None:
    """``/data`` is never bound *by default*; a root the caller vouches for is."""
    argv = _argv(
        workspace_bind="/data/universes/u1/workspaces/repo/gen-3",
        allowed_workspace_roots=("/data/universes/u1/workspaces",),
    )
    assert "--bind" in argv
    assert argv[argv.index("--bind") + 2] == WORKSPACE_MOUNT_POINT


def test_a_bind_that_only_resolves_into_a_root_still_refuses() -> None:
    """Both checks earn their keep, and in opposite directions.

    The realpath check catches a path INSIDE a root that leaves it. This one
    catches the reverse: a path outside every root that resolves into one, ie
    a symlink pointing into the pool. Neither is a lease the caller vouched
    for, and only the literal check refuses this shape.
    """
    with pytest.raises(ValueError, match="not beneath an allowed root"):
        _validate_workspace_bind(
            "/tmp/sneaky", ("/srv/pool",), lambda p: "/srv/pool/lease-1"
        )


def test_a_symlinked_bind_source_that_leaves_the_root_refuses() -> None:
    with pytest.raises(ValueError, match="resolves to"):
        _validate_workspace_bind(
            "/srv/pool/lease-1",
            ("/srv/pool",),
            lambda p: "/etc/shadow-dir",
        )


def test_a_held_directory_handle_is_an_accepted_spelling() -> None:
    """No root and no realpath: what vouches for it is the inherited fd."""
    resolved = _validate_workspace_bind(
        "/proc/self/fd/7",
        (),
        lambda p: pytest.fail("a descriptor bind must not be realpath-ed"),
        pass_fds=(7,),
    )
    assert resolved == "/proc/self/fd/7"


def test_a_held_directory_handle_needs_that_descriptor_inherited() -> None:
    """``/proc/self/fd/7`` in a process that was not given fd 7 names whatever
    that process has open at 7. The bind is only meaningful when the child
    inherits it, so the pass_fds list is what admits the spelling.
    """
    with pytest.raises(ValueError, match="does not inherit"):
        _validate_workspace_bind(
            "/proc/self/fd/7", ("/srv/pool",), lambda p: p, pass_fds=(3,)
        )
    with pytest.raises(ValueError, match="does not inherit"):
        _validate_workspace_bind("/proc/self/fd/7", (), lambda p: p)


def test_empty_roots_refuse_by_name() -> None:
    """Fail closed, and say which condition closed it."""
    with pytest.raises(ValueError, match="no allowed workspace roots"):
        _validate_workspace_bind("/srv/pool/repo", (), lambda p: p)


def test_a_descriptor_bind_reaches_both_the_argv_and_the_child() -> None:
    """The bind names an fd; the child must actually be given that fd."""
    from tinyassets.node_sandbox import BwrapLauncher

    mount = WorkspaceMount(bind_source="/proc/self/fd/9", pass_fds=(9,))
    launcher = BwrapLauncher(bwrap_path="/usr/bin/bwrap").for_workspace(mount)
    assert launcher.pass_fds == (9,)
    argv = launcher.build_argv("print(1)", ["30", "1", ""])
    index = argv.index("--bind")
    assert argv[index : index + 3] == ["--bind", "/proc/self/fd/9", "/workspace"]
    assert argv[argv.index("--chdir") + 1] == "/workspace"


def test_a_descriptor_bind_the_child_does_not_inherit_refuses() -> None:
    from tinyassets.node_sandbox import BwrapLauncher

    mount = WorkspaceMount(bind_source="/proc/self/fd/9", pass_fds=())
    launcher = BwrapLauncher(bwrap_path="/usr/bin/bwrap").for_workspace(mount)
    with pytest.raises(ValueError, match="does not inherit"):
        launcher.build_argv("print(1)", ["30", "1", ""])


def test_the_mount_reaches_the_launcher_not_just_the_runner() -> None:
    """A default-resolved jail used to bind NOTHING: the mount reached the
    runner (told its root is /workspace) but never the launcher, so the node
    found an empty mount point. run_sync specialises the launcher now.
    """
    from tinyassets.node_sandbox import BwrapLauncher

    plain = BwrapLauncher(bwrap_path="/usr/bin/bwrap")
    assert "--bind" not in plain.build_argv("x", ["30", "1", ""])

    # The path form, checked on the launcher rather than through argv: a POSIX
    # bind path does not survive a Windows host's realpath, and what is under
    # test here is that the mount reaches the launcher at all.
    path_mount = WorkspaceMount(
        bind_source="/srv/pool/lease-1", allowed_roots=("/srv/pool",)
    )
    bound = _launcher_for_workspace(plain, path_mount)
    assert bound.workspace_bind == "/srv/pool/lease-1"
    assert bound.allowed_workspace_roots == ("/srv/pool",)
    assert bound is not plain

    # The descriptor form all the way to argv: it never touches realpath.
    fd_bound = _launcher_for_workspace(
        plain, WorkspaceMount(bind_source="/proc/self/fd/9", pass_fds=(9,))
    )
    argv = fd_bound.build_argv("x", ["30", "1", ""])
    assert argv[argv.index("--bind") + 1] == "/proc/self/fd/9"


def test_the_plain_launcher_refuses_a_descriptor_bind() -> None:
    """It performs no mount, so /proc/self/fd/<n> would name ITS own fd."""
    from tinyassets.providers.base import SandboxUnavailableError

    with pytest.raises(SandboxUnavailableError):
        PlainSubprocessLauncher().for_workspace(
            WorkspaceMount(bind_source="/proc/self/fd/9", pass_fds=(9,))
        )


def test_run_sync_specialises_the_launcher_for_the_mount(workspace: Path) -> None:
    """Without this the bind never leaves the mount: argv would carry none."""
    seen: dict[str, object] = {}

    class _Capture(PlainSubprocessLauncher):
        def build_argv(self, runner_script: str, args: list[str]) -> list[str]:
            seen["workspace_bind"] = self.workspace_bind
            return [PY, "-c", "raise SystemExit(0)"]

    NodeSandbox(launcher=_Capture(), timeout=5).run_sync(
        node_id="n",
        source_code="def run(state):\n    return {}\n",
        input_state={},
        input_keys=[],
        output_keys=[],
        timeout=5,
        workspace=WorkspaceMount(bind_source=str(workspace)),
    )
    assert seen["workspace_bind"] == str(workspace)


def test_the_inherited_descriptors_reach_popen(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """argv naming /proc/self/fd/N is meaningless unless the child is given N."""
    from tinyassets import node_sandbox

    captured: dict[str, object] = {}
    real_popen = subprocess.Popen

    class _Launcher(PlainSubprocessLauncher):
        def __init__(self, workspace_bind: str | None = None) -> None:
            super().__init__(workspace_bind=workspace_bind)
            self.pass_fds = (7,)

        def build_argv(self, runner_script: str, args: list[str]) -> list[str]:
            return [PY, "-c", "raise SystemExit(0)"]

    def fake_popen(argv, **kwargs):
        captured.update(kwargs)
        kwargs.pop("pass_fds", None)
        return real_popen(argv, **kwargs)

    monkeypatch.setattr(node_sandbox.sys, "platform", "linux")
    monkeypatch.setattr(node_sandbox.subprocess, "Popen", fake_popen)
    NodeSandbox(launcher=_Launcher(), timeout=5).run_sync(
        node_id="n",
        source_code="def run(state):\n    return {}\n",
        input_state={},
        input_keys=[],
        output_keys=[],
        timeout=5,
        workspace=WorkspaceMount(bind_source=str(workspace), pass_fds=(7,)),
    )
    assert captured["pass_fds"] == (7,)
    assert captured["close_fds"] is True


def test_inherited_descriptors_are_refused_on_windows(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Popen cannot pass a descriptor there; dropping it silently would leave a
    bind naming an fd the child never got."""
    from tinyassets import node_sandbox
    from tinyassets.providers.base import SandboxUnavailableError

    class _Launcher(PlainSubprocessLauncher):
        def __init__(self, workspace_bind: str | None = None) -> None:
            super().__init__(workspace_bind=workspace_bind)
            self.pass_fds = (7,)

        def build_argv(self, runner_script: str, args: list[str]) -> list[str]:
            return [PY, "-c", "raise SystemExit(0)"]

    monkeypatch.setattr(node_sandbox.sys, "platform", "win32")
    with pytest.raises(SandboxUnavailableError, match="POSIX-only"):
        NodeSandbox(launcher=_Launcher(), timeout=5).run_sync(
            node_id="n",
            source_code="def run(state):\n    return {}\n",
            input_state={},
            input_keys=[],
            output_keys=[],
            timeout=5,
            workspace=WorkspaceMount(bind_source=str(workspace), pass_fds=(7,)),
        )


def test_the_rlimit_profile_rides_in_the_third_argv_slot() -> None:
    limits = WorkspaceLimits()
    captured: dict[str, list[str]] = {}

    class _Capture(PlainSubprocessLauncher):
        def build_argv(self, runner_script: str, args: list[str]) -> list[str]:
            captured["args"] = list(args)
            return [PY, "-c", "raise SystemExit(0)"]

    sandbox = NodeSandbox(launcher=_Capture(workspace_bind="/tmp"), timeout=5)
    sandbox.run_sync(
        node_id="n",
        source_code="def run(state):\n    return {}\n",
        input_state={},
        input_keys=[],
        output_keys=[],
        timeout=5,
        workspace=WorkspaceMount(bind_source="/tmp", limits=limits),
    )
    assert captured["args"][0] == "5"
    assert json.loads(captured["args"][2]) == {
        "RLIMIT_AS": 1536 * 1024 * 1024,
        "RLIMIT_CORE": 0,
        "RLIMIT_FSIZE": 512 * 1024 * 1024,
        "RLIMIT_NOFILE": 1024,
        "RLIMIT_NPROC": 128,
    }


def test_the_workspace_profile_is_the_one_the_design_names() -> None:
    limits = WorkspaceLimits()
    assert limits.rlimit_profile() == {
        "RLIMIT_AS": 1536 * 1024 * 1024,
        "RLIMIT_CORE": 0,
        "RLIMIT_FSIZE": 512 * 1024 * 1024,
        "RLIMIT_NOFILE": 1024,
        "RLIMIT_NPROC": 128,
    }
    assert limits.max_commands == 64
    assert limits.max_output_bytes == 1024 * 1024
    assert limits.command_timeout_s is None


def test_a_node_without_a_workspace_carries_no_profile() -> None:
    captured: dict[str, list[str]] = {}

    class _Capture(PlainSubprocessLauncher):
        def build_argv(self, runner_script: str, args: list[str]) -> list[str]:
            captured["args"] = list(args)
            return [PY, "-c", "raise SystemExit(0)"]

    NodeSandbox(launcher=_Capture(), timeout=5).run_sync(
        node_id="n",
        source_code="def run(state):\n    return {}\n",
        input_state={},
        input_keys=[],
        output_keys=[],
        timeout=5,
    )
    assert captured["args"] == ["5", "0", ""]


# ──────────────────────────────────────────────────────────────────────────────
# The runner: ws, driven through a real child
# ──────────────────────────────────────────────────────────────────────────────


def _run_node(
    workspace: Path | None,
    source: str,
    *,
    limits: WorkspaceLimits | None = None,
    output_keys: tuple[str, ...] = ("result",),
    timeout: float = 60.0,
):
    bind = None if workspace is None else str(workspace)
    sandbox = NodeSandbox(
        launcher=PlainSubprocessLauncher(workspace_bind=bind), timeout=timeout
    )
    mount = (
        None
        if workspace is None
        else WorkspaceMount(bind_source=bind, limits=limits or WorkspaceLimits())
    )
    return sandbox.run_sync(
        node_id="ws-node",
        source_code=source,
        input_state={},
        input_keys=[],
        output_keys=list(output_keys),
        timeout=timeout,
        workspace=mount,
    )


PROBE = '''
def probe(fn):
    try:
        return {"outcome": "ADMITTED", "value": repr(fn())[:120]}
    except Exception as exc:
        return {"outcome": type(exc).__name__, "message": str(exc)[:160]}
'''


@pytest.fixture()
def workspace(tmp_path: Path) -> Path:
    root = tmp_path / "generation"
    root.mkdir()
    (root / "README.md").write_text("hello workspace\n", encoding="utf-8")
    (root / "pkg").mkdir()
    (root / "pkg" / "mod.py").write_text("VALUE = 1\n", encoding="utf-8")
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("do not read me\n", encoding="utf-8")
    return root


def test_ws_run_returns_the_code_and_bounded_tails(workspace: Path) -> None:
    source = (
        "def run(state):\n"
        f"    out = ws.run([{PY!r}, '-c', "
        "'import sys; print(\"on out\"); sys.stderr.write(\"on err\"); "
        "raise SystemExit(3)'])\n"
        "    return {'result': out}\n"
    )
    result = _run_node(workspace, source)
    assert result.success is True, result.error
    payload = result.output_state["result"]
    assert payload["returncode"] == 3
    assert "on out" in payload["stdout_tail"]
    assert "on err" in payload["stderr_tail"]
    assert payload["truncated"] is False


def test_ws_run_tails_are_capped_and_flagged(workspace: Path) -> None:
    source = (
        "def run(state):\n"
        f"    out = ws.run([{PY!r}, '-c', 'print(\"x\" * 400000)'])\n"
        "    return {'result': {'len': len(out['stdout_tail']), "
        "'truncated': out['truncated']}}\n"
    )
    limits = WorkspaceLimits(tail_bytes=4096, max_output_bytes=1024 * 1024)
    result = _run_node(workspace, source, limits=limits)
    assert result.success is True, result.error
    assert result.output_state["result"]["truncated"] is True
    assert result.output_state["result"]["len"] <= 4096


def test_the_command_after_the_last_one_refuses(workspace: Path) -> None:
    """The cap is per NODE. Two here for speed; the shipped default is 64."""
    source = (
        PROBE + "\n"
        "def run(state):\n"
        "    seen = []\n"
        "    for _ in range(3):\n"
        f"        seen.append(probe(lambda: ws.run([{PY!r}, '-c', 'pass'])['returncode']))\n"
        "    return {'result': seen}\n"
    )
    result = _run_node(workspace, source, limits=WorkspaceLimits(max_commands=2))
    assert result.success is True, result.error
    outcomes = [step["outcome"] for step in result.output_state["result"]]
    assert outcomes == ["ADMITTED", "ADMITTED", "RuntimeError"]
    assert "workspace limit" in result.output_state["result"][2]["message"]
    assert "at most 2 commands" in result.output_state["result"][2]["message"]


def test_the_cumulative_byte_cap_refuses(workspace: Path) -> None:
    source = (
        PROBE + "\n"
        "def run(state):\n"
        "    seen = []\n"
        "    for _ in range(3):\n"
        f"        seen.append(probe(lambda: ws.run([{PY!r}, '-c', 'print(\"y\" * 500)'])))\n"
        "    return {'result': [s['outcome'] for s in seen], 'why': seen[-1].get('message', '')}\n"
    )
    result = _run_node(
        workspace,
        source,
        limits=WorkspaceLimits(max_output_bytes=600),
        output_keys=("result", "why"),
    )
    assert result.success is True, result.error
    assert result.output_state["result"][0] == "ADMITTED"
    assert result.output_state["result"][-1] == "RuntimeError"
    assert "workspace limit" in result.output_state["why"]


def test_write_then_read_round_trips_and_makes_parents(workspace: Path) -> None:
    source = (
        "def run(state):\n"
        "    written = ws.write('out/nested/report.md', 'a line\\n')\n"
        "    return {'result': {'written': written, 'back': ws.read('out/nested/report.md'),\n"
        "                       'existing': ws.read('README.md')}}\n"
    )
    result = _run_node(workspace, source)
    assert result.success is True, result.error
    payload = result.output_state["result"]
    assert payload["written"] == 7
    assert payload["back"] == "a line\n"
    assert payload["existing"].startswith("hello workspace")
    assert (workspace / "out" / "nested" / "report.md").is_file()


def test_ws_read_refuses_a_file_over_the_cap(workspace: Path) -> None:
    (workspace / "big.txt").write_text("z" * 5000, encoding="utf-8")
    source = (
        PROBE + "\n"
        "def run(state):\n"
        "    return {'result': probe(lambda: ws.read('big.txt', max_bytes=100))}\n"
    )
    result = _run_node(workspace, source)
    assert result.success is True, result.error
    assert result.output_state["result"]["outcome"] == "RuntimeError"
    assert "workspace limit" in result.output_state["result"]["message"]


def test_ws_glob_returns_relative_paths(workspace: Path) -> None:
    source = (
        "def run(state):\n"
        "    return {'result': {'py': ws.glob('**/*.py'), 'top': ws.glob('*.md')}}\n"
    )
    result = _run_node(workspace, source)
    assert result.success is True, result.error
    assert result.output_state["result"]["py"] == ["pkg/mod.py"]
    assert result.output_state["result"]["top"] == ["README.md"]


def test_ws_glob_is_capped(workspace: Path) -> None:
    for index in range(12):
        (workspace / f"file{index}.dat").write_text("x", encoding="utf-8")
    source = (
        "def run(state):\n"
        "    return {'result': len(ws.glob('*.dat'))}\n"
    )
    result = _run_node(workspace, source, limits=WorkspaceLimits(max_glob_results=5))
    assert result.success is True, result.error
    assert result.output_state["result"] == 5


# Each case names the rule that must refuse it. Asserting only the exception
# TYPE let two different rules stand in for each other, so removing either
# one left the table green.
ESCAPES = [
    ("read_parent", "ws.read('../outside/secret.txt')", "may not contain"),
    ("read_absolute", "ws.read('/etc/passwd')", "must be relative, not absolute"),
    ("read_drive", "ws.read('C:/Windows/win.ini')", "not a drive path"),
    (
        "read_nested_parent",
        "ws.read('pkg/../../outside/secret.txt')",
        "may not contain",
    ),
    (
        "write_parent",
        "ws.write('../outside/planted.txt', 'x')",
        "may not contain",
    ),
    (
        "write_absolute",
        "ws.write('/tmp/planted.txt', 'x')",
        "must be relative, not absolute",
    ),
    ("glob_parent", "ws.glob('../outside/*')", "may not contain"),
    ("glob_absolute", "ws.glob('/etc/*')", "must be relative"),
    ("cwd_parent", "ws.run(['echo'], cwd='../outside')", "may not contain"),
    (
        "cwd_absolute",
        "ws.run(['echo'], cwd='/etc')",
        "must be relative, not absolute",
    ),
    ("read_empty", "ws.read('')", "non-empty string"),
    ("write_root", "ws.write('.', 'x')", "not the workspace root"),
]


@pytest.mark.parametrize(
    ("expression", "because"),
    [pytest.param(expr, why, id=name) for name, expr, why in ESCAPES],
)
def test_paths_that_leave_the_workspace_refuse(
    workspace: Path, expression: str, because: str
) -> None:
    source = (
        PROBE + "\n"
        "def run(state):\n"
        f"    return {{'result': probe(lambda: {expression})}}\n"
    )
    result = _run_node(workspace, source)
    assert result.success is True, result.error
    outcome = result.output_state["result"]
    assert outcome["outcome"] in ("ValueError", "TypeError"), outcome
    assert because in outcome["message"], outcome
    assert not (workspace.parent / "outside" / "planted.txt").exists()


def test_a_symlink_out_of_the_workspace_is_not_a_way_out(workspace: Path) -> None:
    link = workspace / "escape"
    try:
        os.symlink(str(workspace.parent / "outside"), str(link), target_is_directory=True)
    except (OSError, NotImplementedError, AttributeError) as exc:
        pytest.skip(f"this host cannot create a directory symlink: {exc}")

    source = (
        PROBE + "\n"
        "def run(state):\n"
        "    return {'result': {\n"
        "        'read': probe(lambda: ws.read('escape/secret.txt')),\n"
        "        'write': probe(lambda: ws.write('escape/planted.txt', 'x')),\n"
        "        'cwd': probe(lambda: ws.run(['echo'], cwd='escape')),\n"
        "        'glob': ws.glob('escape/*'),\n"
        "    }}\n"
    )
    result = _run_node(workspace, source)
    assert result.success is True, result.error
    payload = result.output_state["result"]
    assert payload["read"]["outcome"] == "ValueError"
    assert payload["write"]["outcome"] == "ValueError"
    assert payload["cwd"]["outcome"] == "ValueError"
    # The glob does not refuse; it simply does not report what is not inside.
    assert payload["glob"] == []
    assert not (workspace.parent / "outside" / "planted.txt").exists()


def test_a_symlinked_leaf_cannot_be_written_through(workspace: Path) -> None:
    target = workspace.parent / "outside" / "secret.txt"
    link = workspace / "secret-link.txt"
    try:
        os.symlink(str(target), str(link))
    except (OSError, NotImplementedError, AttributeError) as exc:
        pytest.skip(f"this host cannot create a file symlink: {exc}")

    source = (
        PROBE + "\n"
        "def run(state):\n"
        "    return {'result': probe(lambda: ws.write('secret-link.txt', 'planted'))}\n"
    )
    result = _run_node(workspace, source)
    assert result.success is True, result.error
    assert result.output_state["result"]["outcome"] != "ADMITTED"
    assert target.read_text(encoding="utf-8") == "do not read me\n"


def test_ws_run_refuses_a_shell_string_and_a_bad_env(workspace: Path) -> None:
    source = (
        PROBE + "\n"
        "def run(state):\n"
        "    return {'result': {\n"
        "        'string': probe(lambda: ws.run('echo hi')),\n"
        "        'empty': probe(lambda: ws.run([])),\n"
        "        'nonstr': probe(lambda: ws.run(['echo', 3])),\n"
        f"        'badenv': probe(lambda: ws.run([{PY!r}, '-c', 'pass'], "
        "env={'lower': 'x'})),\n"
        "    }}\n"
    )
    result = _run_node(workspace, source)
    assert result.success is True, result.error
    for key, outcome in result.output_state["result"].items():
        assert outcome["outcome"] == "ValueError", (key, outcome)


def test_ws_run_env_is_a_fixed_base_plus_screened_keys(workspace: Path) -> None:
    source = (
        "def run(state):\n"
        f"    out = ws.run([{PY!r}, '-c', "
        "'import os,json; print(json.dumps(dict(os.environ)))'], "
        "env={'MY_FLAG': 'on'})\n"
        "    return {'result': out['stdout_tail']}\n"
    )
    result = _run_node(workspace, source)
    assert result.success is True, result.error
    child_env = json.loads(result.output_state["result"])
    assert child_env.get("MY_FLAG") == "on"
    assert child_env.get("LANG") == "C.UTF-8"
    assert child_env.get("PATH") == "/usr/bin:/bin"
    assert "TINYASSETS_DATA_DIR" not in child_env


def test_a_node_without_a_workspace_has_no_ws_name(workspace: Path) -> None:
    # `dir()` inside a function lists locals, and `ws` is a global of the
    # node's own namespace: the honest probe is whether the NAME resolves.
    source = (
        "def run(state):\n"
        "    try:\n"
        "        ws\n"
        "    except NameError:\n"
        "        return {'result': False}\n"
        "    return {'result': True}\n"
    )
    assert _run_node(None, source).output_state["result"] is False
    assert _run_node(workspace, source).output_state["result"] is True


def test_the_import_allowlist_is_unaffected_by_what_ws_uses(workspace: Path) -> None:
    """``ws`` needs os/glob/threading; node code must still be refused them.

    They are imported at the top of the runner, before the allowlist replaces
    ``__import__``, and they live in the RUNNER's globals -- the node executes in
    its own namespace dict, so it cannot reach them through ``ws`` either.
    """
    source = (
        PROBE + "\n"
        "def run(state):\n"
        "    def _os():\n"
        "        import os\n"
        "        return os\n"
        "    def _glob():\n"
        "        import glob\n"
        "        return glob\n"
        "    def _threading():\n"
        "        import threading\n"
        "        return threading\n"
        "    return {'result': {\n"
        "        'os': probe(_os), 'glob': probe(_glob), 'threading': probe(_threading),\n"
        "        'reachable': [n for n in dir(ws) if not n.startswith('_')],\n"
        "    }}\n"
    )
    result = _run_node(workspace, source)
    assert result.success is True, result.error
    payload = result.output_state["result"]
    for name in ("os", "glob", "threading"):
        assert payload[name]["outcome"] == "ImportError", payload[name]
    assert sorted(payload["reachable"]) == [
        "bundle", "glob", "path", "read", "run", "write",
    ]


def test_every_ws_method_raises_the_import_depth_around_its_internals() -> None:
    """A lazy import inside the internals must not be checked against the node's
    allowlist. On POSIX ``subprocess.Popen`` imports ``warnings`` on first use,
    at depth 0 while the allowlist is installed, so without this guard every
    ``ws.run`` raises ImportError on Linux while passing on Windows.
    """
    import ast

    from tinyassets import node_sandbox

    tree = ast.parse(node_sandbox._RUNNER_SCRIPT)
    workspace_class = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.ClassDef) and node.name == "_Workspace"
    )
    methods = {
        node.name: node
        for node in workspace_class.body
        if isinstance(node, ast.FunctionDef)
    }
    def guarded_blocks(node):
        return [
            block
            for block in ast.walk(node)
            if isinstance(block, ast.With)
            and any(
                isinstance(item.context_expr, ast.Call)
                and getattr(item.context_expr.func, "id", "") == "_ws_internals"
                for item in block.items
            )
        ]

    for name in ("run", "read", "write", "glob", "bundle"):
        assert guarded_blocks(methods[name]), (
            f"ws.{name} does not raise the import depth"
        )

    # The spawn is the one that matters: Popen is where the lazy import is.
    spawn_calls = [
        call
        for block in guarded_blocks(methods["run"])
        for call in ast.walk(block)
        if isinstance(call, ast.Call)
        and getattr(call.func, "attr", "") == "_spawn"
    ]
    assert spawn_calls, "ws.run spawns outside the raised import depth"


def test_ws_run_works_when_the_node_allowlist_is_minimal(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The regression for the lazy-import bug, driven through a real child."""
    from tinyassets import node_sandbox

    monkeypatch.setattr(node_sandbox, "ALLOWED_IMPORTS", {"json"})
    source = (
        "def run(state):\n"
        f"    out = ws.run([{PY!r}, '-c', 'print(1)'])\n"
        "    ws.write('probe.txt', 'x')\n"
        "    return {'result': [out['returncode'], ws.read('probe.txt'),"
        " ws.glob('*.txt')]}\n"
    )
    result = _run_node(workspace, source)
    assert result.success is True, result.error
    assert result.output_state["result"] == [0, "x", ["probe.txt"]]


def test_the_source_denylist_still_refuses_a_node_that_names_subprocess(
    workspace: Path,
) -> None:
    result = _run_node(
        workspace,
        "def run(state):\n    import subprocess\n    return {'result': 1}\n",
    )
    assert result.success is False
    assert "subprocess" in result.error


# ──────────────────────────────────────────────────────────────────────────────
# ws.bundle
# ──────────────────────────────────────────────────────────────────────────────


def test_bundle_refuses_anything_that_is_not_a_commit_sha(workspace: Path) -> None:
    source = (
        PROBE + "\n"
        "def run(state):\n"
        "    return {'result': [\n"
        "        probe(lambda: ws.bundle('HEAD'))['outcome'],\n"
        "        probe(lambda: ws.bundle('z' * 40))['outcome'],\n"
        "        probe(lambda: ws.bundle('abc'))['outcome'],\n"
        "        probe(lambda: ws.bundle('A' * 40))['outcome'],\n"
        "        probe(lambda: ws.bundle(7))['outcome'],\n"
        "    ]}\n"
    )
    result = _run_node(workspace, source)
    assert result.success is True, result.error
    assert result.output_state["result"] == ["ValueError"] * 5


@pytest.mark.skipif(
    GIT_BINARY is None or sys.platform == "win32",
    reason=(
        "needs git resolvable from the sandbox child; the tests-only launcher "
        "gives the runner no PATH, and on Windows CreateProcess searches the "
        "child's own environment rather than the jail's fixed /usr/bin:/bin"
    ),
)
def test_bundle_produces_a_prerequisite_free_bundle(tmp_path: Path) -> None:
    from tinyassets.workspace_git import git_environment, verify_bundle

    repo = tmp_path / "generation"
    repo.mkdir()
    home = tmp_path / "githome"
    home.mkdir()
    env = git_environment(home, path=str(Path(GIT_BINARY).parent))
    if sys.platform == "win32":
        for key in ("SystemRoot", "COMSPEC"):
            value = os.environ.get(key)
            if value:
                env[key] = value

    def git(*args: str) -> str:
        done = subprocess.run(
            [GIT_BINARY, *args],
            cwd=str(repo),
            env=env,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=120,
            check=True,
        )
        return done.stdout.strip()

    git("init", "--quiet", ".")
    (repo / "README.md").write_text("workspace\n", encoding="utf-8")
    git("add", "README.md")
    git(
        "-c", "user.name=Tiny",
        "-c", "user.email=tiny@universes.tinyassets.io",
        "commit", "--quiet", "-m", "first",
    )
    sha = git("rev-parse", "HEAD")

    source = (
        "def run(state):\n"
        f"    return {{'result': ws.bundle({sha!r})}}\n"
    )
    result = _run_node(repo, source)
    assert result.success is True, result.error
    relative = result.output_state["result"]
    assert relative == f".tiny-export/{sha}.bundle"

    bundle = repo / ".tiny-export" / f"{sha}.bundle"
    assert bundle.is_file()
    scratch = tmp_path / "verify"
    scratch.mkdir()
    refs = verify_bundle(bundle, max_bytes=10_000_000, scratch_dir=scratch, env=env)
    assert refs == ["refs/tiny/export"]

    # The synthetic ref is deleted: the workspace is left as it was found.
    listed = subprocess.run(
        [GIT_BINARY, "show-ref"],
        cwd=str(repo), env=env, capture_output=True, text=True, timeout=60,
    )
    assert "refs/tiny/export" not in listed.stdout


# ──────────────────────────────────────────────────────────────────────────────
# The compiler: a workspace is a graph fact
# ──────────────────────────────────────────────────────────────────────────────


def _code_node(**overrides) -> NodeDefinition:
    fields = {
        "node_id": "build",
        "display_name": "Build",
        "phase": "draft",
        "source_code": "def run(state):\n    return {'ok': True}\n",
        "output_keys": ["ok"],
    }
    fields.update(overrides)
    return NodeDefinition(**fields)


def test_a_workspace_naming_a_non_ancestor_fails_at_compile() -> None:
    node = _code_node(workspace="checkout")
    with pytest.raises(gc.CodeNodeError, match="not one of its ancestors"):
        gc._build_source_code_node(
            node, event_sink=None, effect_chain=EffectChain(), ancestors={"other"}
        )


def test_a_workspace_with_no_ancestry_at_all_fails_at_compile() -> None:
    with pytest.raises(gc.CodeNodeError, match="not one of its ancestors"):
        gc._build_source_code_node(
            _code_node(workspace="checkout"),
            event_sink=None,
            effect_chain=EffectChain(),
            ancestors=None,
        )


def test_a_node_without_a_workspace_compiles_with_no_ancestry() -> None:
    fn = gc._build_source_code_node(
        _code_node(), event_sink=None, effect_chain=EffectChain(), ancestors=None
    )
    assert callable(fn)


def test_an_ancestor_workspace_compiles() -> None:
    fn = gc._build_source_code_node(
        _code_node(workspace="checkout"),
        event_sink=None,
        effect_chain=EffectChain(),
        ancestors={"checkout", "plan"},
    )
    assert callable(fn)


def test_a_missing_mount_fails_the_node_with_the_not_available_message() -> None:
    chain = EffectChain()
    fn = gc._build_source_code_node(
        _code_node(workspace="checkout"),
        event_sink=None,
        effect_chain=chain,
        ancestors={"checkout"},
    )
    with pytest.raises(gc.CodeNodeError, match="workspace not available"):
        fn({})


def test_a_revoked_mount_fails_the_node_the_same_way() -> None:
    chain = EffectChain()
    chain.register_workspace("checkout", WorkspaceMount(bind_source="/srv/pool/x"))
    fn = gc._build_source_code_node(
        _code_node(workspace="checkout"),
        event_sink=None,
        effect_chain=chain,
        ancestors={"checkout"},
    )
    chain.revoke_workspace("checkout")
    with pytest.raises(gc.CodeNodeError, match="was discarded"):
        fn({})


def test_a_run_with_no_effect_chain_cannot_supply_a_workspace() -> None:
    fn = gc._build_source_code_node(
        _code_node(workspace="checkout"),
        event_sink=None,
        effect_chain=None,
        ancestors={"checkout"},
    )
    with pytest.raises(gc.CodeNodeError, match="workspace not available"):
        fn({})


def test_the_registry_refuses_a_junk_registration() -> None:
    chain = EffectChain()
    with pytest.raises(ValueError):
        chain.register_workspace("", WorkspaceMount(bind_source="/srv/pool/x"))
    with pytest.raises(ValueError):
        chain.register_workspace("checkout", None)


def test_the_registry_hands_back_exactly_what_was_registered() -> None:
    chain = EffectChain()
    mount = WorkspaceMount(bind_source="/srv/pool/x")
    chain.register_workspace("checkout", mount)
    assert chain.workspace_mount("checkout") is mount


def test_the_workspace_is_not_serialised_into_the_node_dict() -> None:
    """It travels as a capability; a branch may only NAME an ancestor."""
    node = _code_node(workspace="checkout")
    assert node.to_dict()["workspace"] == "checkout"
    assert NodeDefinition.from_dict(node.to_dict()).workspace == "checkout"


class _ChainMount:
    """Stands in for the sink's capability: a path plus a held directory fd."""

    def __init__(self, bind_source: str, lease_fd: int | None = None) -> None:
        self.bind_source = bind_source
        self.lease_fd = lease_fd
        self.limits = WorkspaceLimits()
        self.allowed_roots: tuple[str, ...] = ()


def test_without_a_descriptor_the_compiler_uses_the_path(workspace: Path) -> None:
    built = gc._sandbox_workspace_mount(_ChainMount(str(workspace)), "build")
    assert built.bind_source == str(workspace)
    assert built.pass_fds == ()


def test_a_host_that_cannot_bind_a_descriptor_uses_the_path(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(gc, "WORKSPACE_FD_BIND_SUPPORTED", False)
    built = gc._sandbox_workspace_mount(_ChainMount(str(workspace), lease_fd=9), "build")
    assert built.bind_source == str(workspace)
    assert built.pass_fds == ()


def test_a_dead_lease_descriptor_fails_the_node_loudly(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Falling back to the path here would silently reintroduce the swap."""
    monkeypatch.setattr(gc, "WORKSPACE_FD_BIND_SUPPORTED", True)
    with pytest.raises(gc.CodeNodeError, match="lease descriptor is unusable"):
        gc._sandbox_workspace_mount(_ChainMount(str(workspace), lease_fd=9999), "build")


def test_a_capability_naming_no_directory_fails_the_node() -> None:
    with pytest.raises(gc.CodeNodeError, match="names no directory"):
        gc._sandbox_workspace_mount(_ChainMount(""), "build")


@pytest.mark.skipif(os.name != "posix", reason="a directory descriptor is POSIX-only")
def test_the_compiler_prefers_the_held_descriptor(workspace: Path) -> None:
    handle = os.open(str(workspace), os.O_RDONLY)
    try:
        built = gc._sandbox_workspace_mount(
            _ChainMount(str(workspace), lease_fd=handle), "build"
        )
        assert built.bind_source == f"/proc/self/fd/{handle}"
        assert built.pass_fds == (handle,)
    finally:
        os.close(handle)


@pytest.mark.skipif(
    sys.platform != "linux" or BWRAP is None,
    reason="binding through a descriptor needs Linux and bwrap",
)
def test_a_rename_mid_run_cannot_swap_the_bound_directory(tmp_path: Path) -> None:
    """The bind resolves through the fd, so the path it came from may move.

    A path bind would follow the name; this one follows the descriptor, which is
    the whole reason production uses it.
    """
    import threading

    from tinyassets.node_sandbox import BwrapLauncher

    lease = tmp_path / "lease-1"
    lease.mkdir()
    (lease / "README.md").write_text("bound through the fd\n", encoding="utf-8")
    decoy = tmp_path / "lease-2"
    decoy.mkdir()
    (decoy / "README.md").write_text("the wrong directory\n", encoding="utf-8")

    handle = os.open(str(lease), os.O_RDONLY)
    renamed = threading.Event()

    def rename_after_a_moment() -> None:
        time.sleep(1.0)
        os.rename(str(lease), str(tmp_path / "lease-1-moved"))
        os.rename(str(decoy), str(lease))
        renamed.set()

    mover = threading.Thread(target=rename_after_a_moment, daemon=True)
    source = (
        "def run(state):\n"
        f"    ws.run([{PY!r}, '-c', 'import time; time.sleep(3)'])\n"
        "    return {'result': ws.read('README.md')}\n"
    )
    try:
        mover.start()
        launcher = BwrapLauncher(
            workspace_bind=f"/proc/self/fd/{handle}", pass_fds=(handle,)
        )
        result = NodeSandbox(launcher=launcher, timeout=60).run_sync(
            node_id="ws-node",
            source_code=source,
            input_state={},
            input_keys=[],
            output_keys=["result"],
            timeout=60,
            workspace=WorkspaceMount(
                bind_source=f"/proc/self/fd/{handle}", pass_fds=(handle,)
            ),
        )
    finally:
        os.close(handle)
    assert renamed.is_set(), "the rename never happened; the test proves nothing"
    assert result.success is True, result.error
    assert result.output_state["result"] == "bound through the fd\n"


def test_workspace_command_timeout_is_a_node_timeout() -> None:
    assert issubclass(gc.WorkspaceCommandTimeout, gc.NodeTimeoutError)
    error = gc.WorkspaceCommandTimeout("boom", node_id="build")
    assert error.node_id == "build"


def test_a_workspace_command_timeout_reaches_the_compiler_as_its_own_class(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The flag on the result, not a phrase in the message, is what classifies."""
    from tinyassets import node_sandbox

    class _TimedOut:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def run_sync(self, **kwargs):
            return node_sandbox.SandboxResult(
                node_id="build",
                success=False,
                error="workspace command timeout: ['sleep'] exceeded 1.000s",
                workspace_timeout=True,
            )

    monkeypatch.setattr(node_sandbox, "NodeSandbox", _TimedOut)
    chain = EffectChain()
    chain.register_workspace("checkout", WorkspaceMount(bind_source=str(workspace)))
    fn = gc._build_source_code_node(
        _code_node(workspace="checkout"),
        event_sink=None,
        effect_chain=chain,
        ancestors={"checkout"},
    )
    with pytest.raises(gc.WorkspaceCommandTimeout, match="workspace command timeout"):
        fn({})


def test_a_workspace_command_timeout_ends_the_run_and_the_jail(workspace: Path) -> None:
    """End to end through a real child: the runner leaves and the frame says why."""
    source = (
        "def run(state):\n"
        f"    ws.run([{PY!r}, '-c', 'import time; time.sleep(30)'], timeout=1)\n"
        "    return {'result': 'never'}\n"
    )
    started = time.monotonic()
    result = _run_node(workspace, source, timeout=30)
    assert result.success is False
    assert result.workspace_timeout is True
    assert "workspace command timeout" in result.error
    # It failed on the COMMAND budget, not by burning the node's 30s.
    assert time.monotonic() - started < 25


# ──────────────────────────────────────────────────────────────────────────────
# Whole-jail termination (Linux + bwrap only)
# ──────────────────────────────────────────────────────────────────────────────


def _marker_is_running(marker: str) -> bool:
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        try:
            cmdline = (entry / "cmdline").read_bytes()
        except OSError:
            continue
        if marker.encode() in cmdline:
            return True
    return False


@pytest.mark.skipif(
    sys.platform != "linux" or BWRAP is None,
    reason="the jail cascade needs Linux and bwrap",
)
def test_a_double_forked_sleeper_dies_with_the_jail(tmp_path: Path) -> None:
    """A `setsid` double-fork survives a process-group kill; it must not survive
    the jail. The sleeper's pid is namespace-local and means nothing on the host,
    so the host-side check is for a unique marker in any live command line.
    """
    from tinyassets.node_sandbox import BwrapLauncher

    root = tmp_path / "generation"
    root.mkdir()
    marker = "ta-jail-canary-" + os.urandom(6).hex()
    spawner = (
        "import os, subprocess, sys\n"
        "subprocess.Popen(['sleep', '300', sys.argv[1]], start_new_session=True)\n"
    )
    source = (
        "def run(state):\n"
        f"    ws.run([{PY!r}, '-c', {spawner!r}, {marker!r}])\n"
        f"    ws.run([{PY!r}, '-c', 'import time; time.sleep(120)'], timeout=2)\n"
        "    return {'result': 'never'}\n"
    )
    launcher = BwrapLauncher(
        workspace_bind=str(root), allowed_workspace_roots=(str(tmp_path),)
    )
    sandbox = NodeSandbox(launcher=launcher, timeout=30)
    result = sandbox.run_sync(
        node_id="ws-node",
        source_code=source,
        input_state={},
        input_keys=[],
        output_keys=["result"],
        timeout=30,
        workspace=WorkspaceMount(bind_source=str(root)),
    )
    assert result.success is False
    assert result.workspace_timeout is True

    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        if not _marker_is_running(marker):
            break
        time.sleep(0.2)
    assert not _marker_is_running(marker), (
        f"a double-forked descendant carrying {marker} outlived the jail"
    )
