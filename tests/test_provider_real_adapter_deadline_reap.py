"""A node deadline ends the provider's whole owned tree, not just its direct child.

Scope: the REAL ``complete()`` of both shipped adapters -- ``ClaudeProvider``
(``tinyassets/providers/claude_provider.py``) and ``CodexProvider``
(``tinyassets/providers/codex_provider.py``) -- driven to its deadline against
a REAL subprocess tree. No ``claude``/``codex`` binary, no network, no
credentials, no LLM call, no effects.

**What is replaced and what is under test.** Only three resolution seams are
patched: the command resolver, the sandbox/cwd flag builder, and the
environment builder. Everything downstream of them is production code --
``complete()`` builds the argv, chooses shell vs exec, spawns through
``owned_process.aspawn_owned()``, and its own reaper
(``ClaudeProvider._terminate`` / ``codex_provider._terminate``) runs the
teardown. The child is a harmless bounded Python script that speaks the real
``--output-format stream-json`` NDJSON protocol and spawns one descendant.

This module previously spawned "like production" itself and never called
``complete()``, so it could not observe a change to the real spawn kwargs. It
now does.

**A zombie has stopped executing.** On POSIX, success is not ``kill(pid, 0)``:
a SIGKILLed orphan can sit in ``Z``/``X`` awaiting init while holding nothing.
This uses the ``/proc/<pid>/stat`` state parser from
``tests/test_native_metadata_process_tree.py`` plus two positive proofs that
execution really stopped -- the descendant's exclusive ``flock`` is acquirable
again, and its inherited stdout pipe has reached EOF.

**Platform caveat, stated rather than claimed away.** POSIX gets a real
guarantee, and it is NOT ``killpg`` on a recorded integer -- Linux v6.1
``kernel/pid.c`` ``free_pid()`` releases the numeric id independently of any
``struct pid`` reference, so a recorded pgid can come to name a stranger. The
guarantee is a **live anchor process inside the group**: while it is alive the
group identity cannot be reallocated, and teardown asks *it* to signal its own
group. That reaches an inherited-pipe descendant even when the leader already
exited. Windows has no group to reserve and no anchor; teardown is a bounded
best-effort ``taskkill /F /T`` tree walk, explicitly NOT a Job Object. The
descendant and anchor assertions therefore run POSIX-only; the ownership,
registration and reap-the-direct-child assertions run everywhere.

Every child is short-lived and killed in the fixture's ``finally``.
"""

from __future__ import annotations

import asyncio
import contextlib
import errno
import json
import os
import signal
import subprocess
import sys
import textwrap
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from tinyassets.exceptions import InteractiveDeadlineError, ProviderTimeoutError
from tinyassets.providers import claude_provider as claude_mod
from tinyassets.providers import codex_provider as codex_mod
from tinyassets.providers import owned_process
from tinyassets.providers.base import ModelConfig
from tinyassets.providers.claude_provider import ClaudeProvider

requires_posix = pytest.mark.skipif(
    os.name != "posix",
    reason="POSIX process-group lifecycle; Windows teardown is a bounded "
           "best-effort taskkill tree walk with no equivalent guarantee",
)

#: The node budget, handed to the adapter as ``absolute_cap_s`` exactly as
#: ``graph_compiler`` hands over a node's remaining budget. Scale-free.
ABSOLUTE_CAP_S = 1.5

#: How long the descendant works if nobody stops it: wide enough that "dead
#: after the reap" cannot be a coincidence, bounded so a crash leaks nothing.
DESCENDANT_LIFETIME_S = 12.0

# proc_pid_stat(5) field 3: Z is zombie, X is dead. Neither is executing.
# Same parser as tests/test_native_metadata_process_tree.py.
_TERMINATED_STATES = frozenset({"Z", "X"})


def _assert_stopped_executing(pid: int) -> None:
    status = Path(f"/proc/{pid}/stat")
    try:
        state = status.read_text()
    except (FileNotFoundError, ProcessLookupError):
        return  # Fully reaped: the strongest outcome.
    assert state.split(") ", 1)[1].split()[0] in _TERMINATED_STATES, (
        f"descendant pid {pid} is still executing after the node deadline: "
        f"{state!r}"
    )


def _assert_executing(pid: int) -> None:
    """The opposite proof: this pid is alive and has NOT been signalled."""
    status = Path(f"/proc/{pid}/stat")
    assert status.exists(), f"pid {pid} is gone; it should still be running"
    state = status.read_text().split(") ", 1)[1].split()[0]
    assert state not in _TERMINATED_STATES, f"pid {pid} stopped executing: {state}"


async def _await_stopped(pid: int, timeout: float = 10.0) -> None:
    """Poll until ``pid`` has stopped executing, or fail with the real reason."""
    deadline = time.monotonic() + timeout
    while True:
        try:
            _assert_stopped_executing(pid)
            return
        except AssertionError:
            if time.monotonic() >= deadline:
                raise
            await asyncio.sleep(0.05)


async def _await_descendant_pid(pid_file, timeout: float = 10.0) -> int:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if pid_file.exists():
            text = pid_file.read_text(encoding="utf-8").strip()
            if text:
                return int(text)
        await asyncio.sleep(0.02)
    raise AssertionError(f"the family leader never reported a descendant ({pid_file})")


async def _await_leader_exit(proc, timeout: float = 10.0) -> None:
    """Observe the leader's exit WITHOUT awaiting its pipes.

    ``Process.wait()`` also waits for every inherited pipe to report EOF, and
    the descendant under test is holding them -- so waiting here would wait for
    the very thing the teardown is supposed to kill.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if proc.returncode is not None:
            return
        await asyncio.sleep(0.02)
    raise AssertionError("the family leader never exited on its own")


# A leader that starts one descendant, reports its pid, then lives for
# ``leader_lifetime`` seconds -- ``0`` gives the launcher-already-exited case,
# which is precisely what a direct-child kill cannot cover.
_LEADER_SPAWNS_DESCENDANT = textwrap.dedent(
    """
    import subprocess, sys, time
    pid_file, descendant_lifetime, leader_lifetime = sys.argv[1:4]
    child = subprocess.Popen(
        [sys.executable, '-c',
         'import sys, time; time.sleep(float(sys.argv[1]))',
         descendant_lifetime]
    )
    with open(pid_file, 'w', encoding='utf-8') as fh:
        fh.write(str(child.pid))
        fh.flush()
    sys.stdout.write('ready' + chr(10))
    sys.stdout.flush()
    time.sleep(float(leader_lifetime))
    """
)


# A descendant holding an exclusive lock and an inherited pipe, ticking a
# marker. Stands in for the engine-MCP server the CLI spawns, or the real
# binary behind the Windows .cmd shim.
_DESCENDANT = textwrap.dedent(
    """
    import os, sys, time
    marker, lifetime, lock_path = sys.argv[1:4]
    if os.name == 'posix':
        import fcntl
        lock = open(lock_path, 'w')
        fcntl.flock(lock, fcntl.LOCK_EX)
    deadline = time.monotonic() + float(lifetime)
    while time.monotonic() < deadline:
        with open(marker, 'a', encoding='utf-8') as fh:
            fh.write('tick' + chr(10))
            fh.flush()
        time.sleep(0.05)
    """
)

# Stands in for ``claude -p --output-format stream-json`` / ``codex exec
# --json``: spawns its own descendant, then streams well-formed protocol frames
# forever. It never goes idle, so the ONLY bound that can end the turn is the
# absolute cap. Reads its own config from the environment; the adapter's real
# argv arrives as argv[1:] and is deliberately ignored.
_PROVIDER_CHILD = textwrap.dedent(
    """
    import json, os, subprocess, sys, time
    marker = os.environ['TA_PROBE_MARKER']
    pid_file = os.environ['TA_PROBE_PIDFILE']
    lock_path = os.environ['TA_PROBE_LOCK']
    lifetime = os.environ['TA_PROBE_LIFETIME']
    frame = os.environ['TA_PROBE_FRAME']
    child = subprocess.Popen(
        [sys.executable, '-c', os.environ['TA_PROBE_DESCENDANT'],
         marker, lifetime, lock_path]
    )
    with open(pid_file, 'w', encoding='utf-8') as fh:
        fh.write(str(child.pid))
        fh.flush()
    if frame == 'claude':
        first = {'type': 'system', 'subtype': 'init', 'session_id': 's-probe'}
        tick = {'type': 'assistant',
                'message': {'content': [{'type': 'text', 'text': 'working'}]}}
    else:
        first = {'type': 'thread.started', 'thread_id': 't-probe'}
        tick = {'type': 'item.completed',
                'item': {'item_type': 'agent_message', 'text': 'working'}}
    sys.stdout.write(json.dumps(first) + chr(10))
    sys.stdout.flush()
    deadline = time.monotonic() + float(lifetime)
    while time.monotonic() < deadline:
        sys.stdout.write(json.dumps(tick) + chr(10))
        sys.stdout.flush()
        time.sleep(0.1)
    """
)


def _kill_pid_tree(pid: int) -> None:
    """Fixture hygiene only -- never the code under test."""
    try:
        if sys.platform == "win32":
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(pid)],
                capture_output=True, check=False, timeout=30,
            )
        else:
            os.kill(pid, signal.SIGKILL)
    except Exception:  # noqa: BLE001 - already gone
        pass


@pytest.fixture
def probe(tmp_path, monkeypatch):
    """Own every child this module creates, and kill them all in ``finally``.

    Patches ONLY command resolution, sandbox/cwd flags and the environment.
    Process creation, ownership marking and teardown stay production code.
    """
    state = SimpleNamespace(
        marker=tmp_path / "descendant.log",
        pid_file=tmp_path / "descendant.pid",
        lock=tmp_path / "descendant.lock",
        spawn_kwargs=[],
        spawn_argv=[],
        procs=[],
        ownership=[],
    )

    def _env(frame: str) -> dict:
        env = os.environ.copy()
        env.update(
            TA_PROBE_MARKER=str(state.marker),
            TA_PROBE_PIDFILE=str(state.pid_file),
            TA_PROBE_LOCK=str(state.lock),
            TA_PROBE_LIFETIME=str(DESCENDANT_LIFETIME_S),
            TA_PROBE_DESCENDANT=_DESCENDANT,
            TA_PROBE_FRAME=frame,
        )
        return env

    def install(module, *, frame: str, cmd_resolver: str, env_builder: str) -> None:
        monkeypatch.setattr(
            module, cmd_resolver,
            lambda: ([sys.executable, "-c", _PROVIDER_CHILD], False),
        )
        monkeypatch.setattr(module, env_builder, lambda *a, **k: _env(frame))
        # Registration now happens inside ``owned_process.aspawn_owned`` rather
        # than at the adapter call site. Wrap it there -- the real function
        # still runs; the test only observes what production recorded.
        real_mark = owned_process.mark_owned

        def recording_mark(proc, family=None):
            real_mark(proc, family)
            state.ownership.append((
                proc.pid,
                owned_process.owned_group_id(proc),
                owned_process.is_family_anchored(proc),
            ))

        monkeypatch.setattr(owned_process, "mark_owned", recording_mark)
        # Record what production actually asked the OS for, without changing it.
        real_exec = asyncio.create_subprocess_exec

        async def recording_exec(*args, **kwargs):
            proc = await real_exec(*args, **kwargs)
            # Record only the PROVIDER spawn. Teardown itself spawns on
            # Windows (the bounded taskkill tree walk), and that helper
            # process is not the thing under test.
            if args and args[0] == sys.executable:
                state.spawn_kwargs.append(kwargs)
                state.spawn_argv.append(list(args))
                state.procs.append(proc)
            return proc

        monkeypatch.setattr(asyncio, "create_subprocess_exec", recording_exec)

    state.install = install
    try:
        yield state
    finally:
        if state.pid_file.exists():
            try:
                _kill_pid_tree(int(state.pid_file.read_text(encoding="utf-8").strip()))
            except Exception:  # noqa: BLE001 - cleanup is best-effort
                pass
        for proc in state.procs:
            if getattr(proc, "returncode", 0) is None:
                _kill_pid_tree(proc.pid)
            # ``asyncio.run`` has already closed the loop by the time cleanup
            # runs, so a transport still holding this child is never collected
            # cleanly: its ``__del__`` reports the process as leaked
            # ("subprocess is still running" / "unclosed transport"). That fires
            # whenever the test body raised BEFORE reaching the teardown
            # assertions -- an argv mismatch, say -- which turns one real
            # failure into a misleading pair. Releasing it here is cleanup only:
            # it changes nothing production does, and it must never mask the
            # original failure, hence the blanket suppression.
            transport = getattr(proc, "_transport", None)
            if transport is not None:
                with contextlib.suppress(Exception):  # noqa: BLE001
                    transport.close()


def _descendant_pid(probe) -> int:
    assert probe.pid_file.exists(), "the provider child never reported its descendant"
    return int(probe.pid_file.read_text(encoding="utf-8").strip())


def _assert_owned_at_spawn(probe) -> None:
    """Production asked for an owned family and recorded it. Not the test's kwargs."""
    assert probe.spawn_kwargs, "complete() never spawned through create_subprocess_exec"
    kwargs = probe.spawn_kwargs[-1]
    argv = probe.spawn_argv[-1]
    proc = probe.procs[-1]
    if os.name == "posix":
        assert kwargs.get("start_new_session") is True, (
            "the adapter spawned without start_new_session, so it leads no "
            "process group and the anchor would have nothing to hold"
        )
        # The spawn protocol, asserted rather than assumed: one fresh,
        # ISOLATED interpreter running the anchor wrapper, two control
        # descriptors handed to it, and THEN the argv complete() built --
        # unchanged, after the ``--`` separator. ``exec`` keeps the pid, so the
        # CLI is still the group leader the adapter recorded.
        #
        # The startup flags are load-bearing, not cosmetic: ``-I -S`` ARE the
        # single-threaded-before-fork contract. Without them an inherited
        # ``PYTHONPATH``/``PYTHONSTARTUP`` or a ``sitecustomize`` hook executes
        # in this interpreter and may start a thread before ``os.fork()``.
        # Pinned as an EXACT prefix, spelled literally rather than read back
        # from ``owned_process``, so dropping a flag, reordering them, or
        # inserting another one each fail here rather than pass by agreement
        # with the code under test.
        assert argv[:4] == [sys.executable, "-I", "-S", "-c"], (
            "the adapter stopped spawning the wrapper through a fresh, "
            f"isolated interpreter: {argv[:4]}"
        )
        assert argv[4] == owned_process._ANCHOR_WRAPPER_SRC, (
            "the spawned wrapper is not the anchor wrapper under test"
        )
        assert len(kwargs.get("pass_fds", ())) == 2, (
            "the control/readiness descriptors were not handed to the wrapper"
        )
        separator = argv.index("--")
        cli_argv = list(argv[separator + 1:])
        # The resolver's own command prefix, verbatim and first -- the wrapper
        # rewrites nothing and prepends nothing to what ``complete()`` built.
        assert cli_argv[:3] == [sys.executable, "-c", _PROVIDER_CHILD], (
            f"the CLI argv was rewritten on its way through the wrapper: {cli_argv[:3]}"
        )
        assert cli_argv[3:], "the adapter's own CLI flags never reached the exec"
        assert owned_process._ANCHOR_WRAPPER_SRC not in cli_argv, (
            "a control handle or the wrapper itself leaked into the CLI argv"
        )
    if sys.platform == "win32":
        assert kwargs.get("creationflags", 0) & subprocess.CREATE_NO_WINDOW, (
            "the hidden-console-window flag was lost at the spawn site"
        )
    anchored_expected = os.name == "posix"
    assert (proc.pid, proc.pid, anchored_expected) in probe.ownership, (
        "complete() did not record the family it owns; teardown would fall "
        f"back to killing the direct child only. recorded: {probe.ownership}"
    )
    assert owned_process.owned_group_id(proc) is None, "cleanup consumes family authority"


def _assert_tree_is_gone(probe, direct_pid: int) -> None:
    proc = probe.procs[-1]
    assert proc.returncode is not None, (
        "the adapter left its own direct child unreaped; _terminate regressed"
    )
    if os.name != "posix":
        result = subprocess.run(
            ["tasklist", "/FI", f"PID eq {_descendant_pid(probe)}", "/NH"],
            capture_output=True, text=True, check=True, timeout=5,
            **owned_process.no_window_kwargs(),
        )
        assert str(_descendant_pid(probe)) not in result.stdout
        return
    _assert_stopped_executing(direct_pid)
    # The finding, stated as the behaviour we want: killing the child the
    # adapter owns must end the work that child started
    # (docs/concerns/2026-08-31-cancel-is-advisory-and-the-timeout-is-doing-
    # its-job.md). A zombie counts as stopped; a running process does not.
    _assert_stopped_executing(_descendant_pid(probe))
    # Positive proof execution stopped, not just that /proc says so: the
    # descendant's exclusive lock is free again.
    import fcntl
    with probe.lock.open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)


def test_claude_complete_deadline_reaps_the_whole_owned_tree(probe):
    """Real ``ClaudeProvider.complete()``: cap binds, tree dies, group was owned."""
    probe.install(
        claude_mod, frame="claude",
        cmd_resolver="_resolve_claude_cmd",
        env_builder="subprocess_env_for_provider",
    )
    monkey = pytest.MonkeyPatch()
    monkey.setattr(claude_mod, "_sandbox_cli_args", lambda *a, **k: ([], None))
    config = ModelConfig(
        init_timeout_s=30.0, first_progress_s=30.0, idle_timeout_s=30.0,
        absolute_cap_s=ABSOLUTE_CAP_S,
    )

    async def drive():
        started = time.monotonic()
        with pytest.raises(InteractiveDeadlineError) as exc_info:
            await ClaudeProvider().complete("prompt", "", config)
        return time.monotonic() - started, str(exc_info.value)

    try:
        elapsed, message = asyncio.run(drive())
    finally:
        monkey.undo()

    # The ABSOLUTE cap is what bound the turn -- the child emits a frame every
    # 0.1s, so no idle watchdog (all 30s) could have fired.
    assert elapsed >= ABSOLUTE_CAP_S, f"gave up at {elapsed:.2f}s, before the cap"
    assert "absolute interactive cap" in message
    _assert_owned_at_spawn(probe)
    _assert_tree_is_gone(probe, probe.procs[-1].pid)


@requires_posix
def test_claude_deadline_teardown_is_not_bounded_by_a_surviving_pipe_holder(probe):
    """Teardown returns promptly once the tree -- not just the child -- is gone.

    Measured on this host 2026-09-23 BEFORE the fix, on this one controlled
    inherited-pipe case: teardown ran to its full declared budget
    (``_terminate``'s ``wait_for(proc.wait(), 5)`` plus ``_finish_stderr``'s
    ``wait_for(..., 2)``) because the surviving descendant held the inherited
    stdout/stderr handles open and ``Process.wait()`` does not return until
    every pipe transport reports connection-lost.

    That measurement is this case only. It is NOT evidence that every deadline
    in production cost +7s, and no live incident has been traced to it.
    """
    probe.install(
        claude_mod, frame="claude",
        cmd_resolver="_resolve_claude_cmd",
        env_builder="subprocess_env_for_provider",
    )
    monkey = pytest.MonkeyPatch()
    monkey.setattr(claude_mod, "_sandbox_cli_args", lambda *a, **k: ([], None))
    config = ModelConfig(
        init_timeout_s=30.0, first_progress_s=30.0, idle_timeout_s=30.0,
        absolute_cap_s=ABSOLUTE_CAP_S,
    )

    async def drive():
        started = time.monotonic()
        with pytest.raises(InteractiveDeadlineError):
            await ClaudeProvider().complete("prompt", "", config)
        return time.monotonic() - started

    try:
        elapsed = asyncio.run(drive())
    finally:
        monkey.undo()

    assert elapsed < ABSOLUTE_CAP_S + 5.0, (
        f"teardown took {elapsed - ABSOLUTE_CAP_S:.2f}s past the "
        f"{ABSOLUTE_CAP_S}s cap: a descendant is still holding the inherited "
        "pipes open, so the group reap did not reach it"
    )


def test_codex_complete_owns_its_group_and_terminate_reaps_the_tree(probe):
    """Real ``CodexProvider.complete()`` reaches the same shared helper."""
    probe.install(
        codex_mod, frame="codex",
        cmd_resolver="_resolve_codex_cmd",
        env_builder="subprocess_env_for_provider",
    )
    monkey = pytest.MonkeyPatch()
    monkey.setattr(codex_mod, "_codex_workdir", lambda: os.getcwd())
    config = ModelConfig(timeout=ABSOLUTE_CAP_S, absolute_cap_s=ABSOLUTE_CAP_S)

    async def drive():
        with pytest.raises(ProviderTimeoutError, match="codex exec exceeded"):
            await codex_mod.CodexProvider().complete("prompt", "", config)

    try:
        asyncio.run(drive())
    finally:
        monkey.undo()

    _assert_owned_at_spawn(probe)
    _assert_tree_is_gone(probe, probe.procs[-1].pid)


# --- the ownership contract itself ------------------------------------------


def test_unmarked_process_is_killed_individually_and_never_by_group(monkeypatch):
    """A mock or externally supplied handle must not trigger group signalling."""
    calls = []
    # raising=False: os.killpg does not exist on Windows, where the teardown
    # under test is the taskkill tree walk instead. Both are pinned silent.
    monkeypatch.setattr(
        owned_process.os, "killpg", lambda *a: calls.append(a), raising=False,
    )
    monkeypatch.setattr(
        owned_process.subprocess, "run", lambda *a, **k: calls.append(a),
    )
    for proc in (Mock(pid=4242, returncode=None),
                 SimpleNamespace(pid=4242, returncode=None, kill=Mock())):
        owned_process.kill_owned_tree(proc)
    assert calls == [], (
        "an unmarked process reached group/tree signalling; a Mock's "
        "auto-attribute or a recycled pid could then be signalled"
    )


@pytest.mark.parametrize("pid", [0, -1, None, True, "123"])
def test_marking_rejects_ids_that_are_not_a_real_owned_group(pid):
    """A handle whose pid is not a plausible id records no teardown authority.

    The stand-in must be registrable, or this proves nothing: the pid check and
    the "cannot go in the registry" path both end at ``owned_group_id() is
    None``, and a ``SimpleNamespace`` -- unhashable, because it defines
    ``__eq__`` -- always takes the second. ``True`` is in the set because
    ``isinstance(True, int)`` is True and a bool is not a pid.
    """
    proc = _RegistrableProc()
    proc.pid = pid
    owned_process.mark_owned(proc)
    assert owned_process.owned_group_id(proc) is None


def test_marking_a_plausible_id_does_register_so_the_rejections_can_fail():
    """The positive control for the test above.

    Without it, every rejection case would still pass if ``mark_owned`` had
    simply stopped registering anything at all.
    """
    proc = _RegistrableProc(pid=4242)
    owned_process.mark_owned(proc)
    assert owned_process.owned_group_id(proc) == 4242
    assert not owned_process.is_family_anchored(proc), (
        "a plain mark must never claim anchor authority; on POSIX that "
        "authority comes from a live anchor and nothing else"
    )


@requires_posix
def test_teardown_never_signals_a_process_group_integer_from_the_daemon(tmp_path):
    """The daemon ends a family through the anchor, never by naming a pgid.

    This is the whole point of the shape. ``os.killpg`` on a recorded integer
    is unsafe once the leader is reaped -- Linux v6.1 ``kernel/pid.c``
    ``free_pid()`` removes the numeric id from the IDR independently of any
    ``struct pid`` reference, so the number can already name a stranger. Both
    ``killpg`` and ``getpgid`` are made to explode here, and a real anchored
    spawn plus a real teardown must still work.
    """
    calls = []

    def _forbidden(name):
        def _boom(*args, **kwargs):  # pragma: no cover - asserts unreached
            calls.append(name)
            raise AssertionError(
                f"the daemon called os.{name} during teardown; a recorded "
                "group integer can already name another user's session"
            )
        return _boom

    monkey = pytest.MonkeyPatch()
    monkey.setattr(owned_process.os, "killpg", _forbidden("killpg"))
    monkey.setattr(owned_process.os, "getpgid", _forbidden("getpgid"))

    async def exercise():
        proc = await owned_process.aspawn_owned(
            [sys.executable, "-c", "import time; time.sleep(12)"],
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            assert owned_process.is_family_anchored(proc)
            owned_process.kill_owned_tree(proc)
            await asyncio.wait_for(proc.wait(), timeout=10)
        finally:
            if proc.returncode is None:
                _kill_pid_tree(proc.pid)

    try:
        asyncio.run(exercise())
    finally:
        monkey.undo()
    assert calls == []


@requires_posix
def test_anchor_reaps_the_family_after_the_leader_has_already_exited(tmp_path):
    """The case a direct-child kill cannot cover, and the reason for the anchor.

    The leader exits on its own, so its pid is reaped and any integer recorded
    for it stops meaning anything. The anchor is still alive inside the group,
    so the group identity is still reserved and the descendant still dies.
    """
    pid_file = tmp_path / "descendant.pid"

    async def exercise():
        proc = await owned_process.aspawn_owned(
            [sys.executable, "-c", _LEADER_SPAWNS_DESCENDANT,
             str(pid_file), str(DESCENDANT_LIFETIME_S), "0"],
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            descendant = await _await_descendant_pid(pid_file)
            # Observe the leader's exit WITHOUT waiting on its pipes: the very
            # descendant we must kill is holding them open.
            await _await_leader_exit(proc, timeout=10)
            assert Path(f"/proc/{descendant}").exists(), "descendant never started"
            owned_process.kill_owned_tree(proc)
            await _await_stopped(descendant, timeout=10)
        finally:
            if pid_file.exists():
                _kill_pid_tree(int(pid_file.read_text(encoding="utf-8").strip()))
            if proc.returncode is None:
                _kill_pid_tree(proc.pid)

    asyncio.run(exercise())


@requires_posix
def test_ending_one_family_never_reaches_another(tmp_path):
    """Two live families; tearing one down leaves the other untouched."""
    first_pid_file = tmp_path / "first.pid"
    second_pid_file = tmp_path / "second.pid"

    async def spawn(pid_file):
        return await owned_process.aspawn_owned(
            [sys.executable, "-c", _LEADER_SPAWNS_DESCENDANT,
             str(pid_file), str(DESCENDANT_LIFETIME_S),
             str(DESCENDANT_LIFETIME_S)],
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

    async def exercise():
        first = await spawn(first_pid_file)
        second = await spawn(second_pid_file)
        try:
            first_descendant = await _await_descendant_pid(first_pid_file)
            second_descendant = await _await_descendant_pid(second_pid_file)
            assert owned_process.owned_group_id(first) != \
                owned_process.owned_group_id(second)
            owned_process.kill_owned_tree(first)
            await _await_stopped(first_descendant, timeout=10)
            # The survivor: a family teardown that reached across groups would
            # be exactly the cross-user kill hazard this design exists to avoid.
            assert second.returncode is None, "tearing down one family killed another"
            _assert_executing(second_descendant)
            owned_process.kill_owned_tree(second)
            await _await_stopped(second_descendant, timeout=10)
        finally:
            for proc, pid_file in ((first, first_pid_file), (second, second_pid_file)):
                if pid_file.exists():
                    _kill_pid_tree(int(pid_file.read_text(encoding="utf-8").strip()))
                if proc.returncode is None:
                    _kill_pid_tree(proc.pid)

    asyncio.run(exercise())


@requires_posix
def test_normal_completion_still_ends_the_family_and_leaks_no_descriptor(tmp_path):
    """The success path: the CLI exits cleanly and the leftovers still die.

    Also the leak census. The control descriptor is the one new OS resource
    this design introduces, and an fd leak per turn in a long-lived daemon is
    an outage, so the count is pinned across repeated spawn/teardown cycles.
    """
    def _open_fds() -> int:
        return len(os.listdir("/proc/self/fd"))

    async def one_cycle(index: int) -> None:
        pid_file = tmp_path / f"cycle-{index}.pid"
        proc = await owned_process.aspawn_owned(
            [sys.executable, "-c", _LEADER_SPAWNS_DESCENDANT,
             str(pid_file), str(DESCENDANT_LIFETIME_S), "0"],
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            descendant = await _await_descendant_pid(pid_file)
            await _await_leader_exit(proc, timeout=10)
            owned_process.kill_owned_tree(proc)
            await _await_stopped(descendant, timeout=10)
            assert owned_process.owned_group_id(proc) is None
        finally:
            if pid_file.exists():
                _kill_pid_tree(int(pid_file.read_text(encoding="utf-8").strip()))
            if proc.returncode is None:
                _kill_pid_tree(proc.pid)

    async def exercise():
        await one_cycle(0)  # warm up: first-use allocations are not a leak
        baseline = _open_fds()
        for index in range(1, 4):
            await one_cycle(index)
        assert _open_fds() <= baseline, (
            "the control descriptor leaked across turns: "
            f"{baseline} -> {_open_fds()} open fds over three spawns"
        )

    asyncio.run(exercise())


@requires_posix
def test_a_failed_handshake_fails_closed_and_leaves_nothing_running(monkeypatch):
    """No anchor means no invocation -- never an un-endable CLI, never a broad signal.

    Only the module's own readiness bound is changed; the handshake code under
    test is production.
    """
    spawned = []
    real_exec = asyncio.create_subprocess_exec

    async def recording_exec(*args, **kwargs):
        proc = await real_exec(*args, **kwargs)
        spawned.append(proc)
        return proc

    monkeypatch.setattr(asyncio, "create_subprocess_exec", recording_exec)
    monkeypatch.setattr(owned_process, "_ANCHOR_READY_TIMEOUT_S", 0.001)

    async def exercise():
        with pytest.raises(owned_process.FamilyAnchorError):
            await owned_process.aspawn_owned(
                [sys.executable, "-c", "import time; time.sleep(12)"],
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        assert spawned, "nothing was spawned, so nothing was proven"
        for proc in spawned:
            await _await_stopped(proc.pid, timeout=10)
            assert not owned_process.is_family_anchored(proc)

    asyncio.run(exercise())


@requires_posix
def test_cancellation_before_the_handshake_leaves_nothing_running(monkeypatch):
    """Owner cancellation during admission: the family dies with the control pipe."""
    spawned = []
    real_exec = asyncio.create_subprocess_exec

    async def recording_exec(*args, **kwargs):
        proc = await real_exec(*args, **kwargs)
        spawned.append(proc)
        return proc

    monkeypatch.setattr(asyncio, "create_subprocess_exec", recording_exec)

    async def exercise():
        task = asyncio.ensure_future(owned_process.aspawn_owned(
            [sys.executable, "-c", "import time; time.sleep(12)"],
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        ))
        # Cancel once the wrapper really exists -- otherwise this passes
        # vacuously by cancelling before anything was created.
        deadline = time.monotonic() + 5
        while not spawned and not task.done() and time.monotonic() < deadline:
            await asyncio.sleep(0)
        task.cancel()
        try:
            proc = await task
        except asyncio.CancelledError:
            proc = None
        if proc is not None:
            # The handshake beat the cancellation. End the family the way a
            # caller's ``finally`` would; the survival check below is the same.
            owned_process.kill_owned_tree(proc)
        assert spawned, "nothing was spawned, so nothing was proven"
        for spawned_proc in spawned:
            await _await_stopped(spawned_proc.pid, timeout=10)

    asyncio.run(exercise())


@requires_posix
def test_a_missing_cli_binary_still_raises_filenotfounderror():
    """The wrapper must not turn "not installed" into a new wrapper-shaped failure."""
    async def exercise():
        with pytest.raises(FileNotFoundError):
            await owned_process.aspawn_owned(
                ["tinyassets-no-such-cli-binary", "--version"],
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

    asyncio.run(exercise())


# --- the handshake contract: descriptors, strictness, interpreter startup ----
#
# These run on every platform: they exercise pure helpers, so they are real
# coverage on Windows rather than a skip. The POSIX tests above prove the same
# contract end to end with a real fork.


def test_wrapper_argv_starts_the_interpreter_isolated_and_without_site():
    """Single-threaded-before-fork is enforced by startup flags, not assumed.

    ``-I`` implies ``-E`` (ignore ``PYTHON*``), ``-s`` (no user site-dir) and
    ``-P`` (no cwd on ``sys.path``); ``-S`` skips :mod:`site` outright, so
    ``sitecustomize``/``usercustomize`` never execute. An inherited
    ``PYTHONPATH`` or a site hook that starts a thread therefore cannot run in
    the interpreter that is about to ``fork``. Without these, "fresh
    interpreter" is a hope about the daemon's environment.
    """
    argv = owned_process._wrapper_argv(11, 12, ["claude", "-p", "hi"])

    assert argv[0] == sys.executable
    # Order matters: the flags must precede ``-c`` to be interpreter options
    # rather than arguments to the script.
    assert argv[1:3] == ["-I", "-S"], f"startup isolation lost: {argv[1:4]}"
    assert argv[3] == "-c"
    assert argv[4] == owned_process._ANCHOR_WRAPPER_SRC
    # Descriptors are passed positionally; ``--`` separates them from an argv
    # that may itself begin with a dash.
    assert argv[5:8] == ["11", "12", "--"]
    # The provider's argv is preserved verbatim, in order, as the exec target.
    assert argv[8:] == ["claude", "-p", "hi"]


def test_wrapper_flags_really_isolate_the_interpreter_that_is_about_to_fork(tmp_path):
    """The isolation contract, proven by RUNNING the flags, not by spelling them.

    The test above pins which flags are sent; this one pins that those flags
    deliver what the module's header claims. A hostile ``PYTHONPATH`` carrying
    a ``sitecustomize`` that starts a thread is exactly the shape that makes
    ``os.fork()`` in a multi-threaded interpreter -- the pattern
    ``node_sandbox`` bans -- and env-stripping at the spawn site is NOT what
    protects against it, because the adapter deliberately hands the CLI the
    daemon's own environment.

    Reading ``_WRAPPER_FLAGS`` here is the point: whatever the code sends must
    survive this, so a future flag change cannot silently lose isolation.
    """
    hostile = tmp_path / "hostile"
    hostile.mkdir()
    (hostile / "sitecustomize.py").write_text(
        "import threading\n"
        "threading.Thread(target=lambda: __import__('time').sleep(30),\n"
        "                 daemon=True).start()\n",
        encoding="utf-8",
    )
    (hostile / "startup_probe.py").write_text("RAN = True\n", encoding="utf-8")
    env = os.environ.copy()
    env["PYTHONPATH"] = str(hostile)
    env["PYTHONSTARTUP"] = str(hostile / "startup_probe.py")

    report = subprocess.run(
        [sys.executable, *owned_process._WRAPPER_FLAGS, "-c", textwrap.dedent("""
            import json, sys, threading
            print(json.dumps({
                "isolated": bool(sys.flags.isolated),
                "no_site": bool(sys.flags.no_site),
                "ignore_environment": bool(sys.flags.ignore_environment),
                "no_user_site": bool(sys.flags.no_user_site),
                "site_hook_ran": "sitecustomize" in sys.modules,
                "hostile_on_path": any("hostile" in p for p in sys.path),
                "threads": threading.active_count(),
            }))
        """)],
        capture_output=True, text=True, check=True, timeout=60, env=env,
        cwd=str(hostile), **owned_process.no_window_kwargs(),
    )
    state = json.loads(report.stdout.strip().splitlines()[-1])

    assert state["isolated"] and state["no_site"], (
        f"the wrapper flags no longer isolate the interpreter: {state}"
    )
    assert state["ignore_environment"] and state["no_user_site"], (
        f"-I stopped implying -E/-s, so PYTHON* env vars apply again: {state}"
    )
    assert not state["site_hook_ran"], (
        "a sitecustomize hook executed in the interpreter that forks the anchor"
    )
    assert not state["hostile_on_path"], (
        f"an inherited PYTHONPATH (or cwd) reached sys.path: {state}"
    )
    # The whole reason for the flags: one thread at the moment of ``os.fork()``.
    assert state["threads"] == 1, (
        f"the interpreter that forks the anchor is multi-threaded: {state}"
    )


def test_wrapper_never_reaches_a_shell_and_carries_no_env_or_cwd_override():
    """``exec`` preserves the adapter's env and cwd; the wrapper adds nothing.

    ``-I``/``-E`` change how *this* interpreter configures itself. They do not
    edit ``os.environ``, so ``execvp`` still hands the CLI the environment and
    working directory the adapter chose. The absence of an ``env=``/``cwd=``
    rewrite in the spawn is what keeps that true.
    """
    source = Path(owned_process.__file__).read_text(encoding="utf-8")
    spawn = source[source.index("async def _aspawn_anchored"):
                   source.index("async def aspawn_owned")]
    assert "create_subprocess_shell" not in spawn, (
        "the anchored spawn must never route the wrapper through a shell"
    )
    for override in ("env=", "cwd="):
        assert override not in spawn, (
            f"the anchored spawn now sets {override!r} itself; the caller's "
            "value would be silently replaced for the CLI"
        )
    # The caller's kwargs -- stdio, env, cwd, limit -- reach the spawn unchanged.
    assert "**kwargs," in spawn


def test_fd_bag_closes_each_descriptor_exactly_once():
    """The released bug, made unrepresentable.

    ``ready_r`` used to be closed after the handshake and then closed AGAIN by
    the abandon path on a bad status line. A second close can land on a
    descriptor the runtime has since handed to something else.
    """
    closed: list[int] = []
    bag = owned_process._FdBag()
    read_fd, write_fd = os.pipe()
    bag.add("r", read_fd)
    bag.add("w", write_fd)

    original = owned_process._close_fd
    try:
        owned_process._close_fd = lambda fd: (
            closed.append(fd) or original(fd)  # type: ignore[func-returns-value]
        ) if fd is not None else None
        bag.close("r")
        bag.close("r")          # already consumed: must be a no-op
        bag.close_all()         # takes only what is left
        bag.close_all()         # idempotent
    finally:
        owned_process._close_fd = original

    assert closed == [read_fd, write_fd], (
        f"descriptors were not consumed exactly once: {closed}"
    )


def test_fd_bag_take_transfers_ownership_out():
    """``ctrl_w`` survives a successful spawn because the bag stops owning it."""
    bag = owned_process._FdBag()
    read_fd, write_fd = os.pipe()
    bag.add("r", read_fd)
    bag.add("w", write_fd)
    try:
        assert bag.take("w") == write_fd
        assert bag.take("w") is None
        bag.close_all()
        # Still open: the bag released it rather than closing it. ``fstat``
        # rather than a write, because the read end IS in the bag and a write
        # to a pipe with no reader is a platform-specific error, not the point.
        assert os.fstat(write_fd) is not None
    finally:
        for fd in (read_fd, write_fd):
            try:
                os.close(fd)
            except OSError:
                pass


@pytest.mark.parametrize(
    "status, why",
    [
        (b"", "EOF before any status line"),
        (b"ANCHOR", "no pid, no pgid"),
        (b"ANCHOR 5", "no pgid"),
        (b"ANCHOR 5 7 extra", "trailing field"),
        (b"ANCHOR x 7", "non-numeric pid"),
        (b"ANCHOR 5 y", "non-numeric pgid"),
        (b"ANCHOR 0 7", "pid not positive"),
        (b"ANCHOR -5 7", "negative pid"),
        (b"ANCHOR 5 9", "pgid is not the leader's pid"),
        (b"ANCHOR 7 7", "anchor pid equals the leader -- no fork happened"),
        (b"ERR fork 11", "the wrapper could not fork"),
        (b"READY 5 7", "not the ANCHOR keyword"),
    ],
)
def test_malformed_readiness_fails_closed_rather_than_recording_no_anchor(status, why):
    """Anything we cannot fully parse means we do not know a member is holding
    the group -- and "we do not know" must fail the spawn, not register a
    family with ``anchor_pid=None`` that teardown would treat as anchored."""
    with pytest.raises(ValueError):
        owned_process._parse_anchor_ready(status, 7)


def test_a_well_formed_readiness_line_yields_the_anchor_pid():
    assert owned_process._parse_anchor_ready(b"ANCHOR 5 7", 7) == 5


@requires_posix
@pytest.mark.parametrize("emit, label", [
    ("", "EOF: the wrapper died before writing anything"),
    ("ANCHOR\n", "a truncated status line"),
    ("ANCHOR 0 0\n", "an implausible pid/pgid pair"),
])
def test_bad_readiness_fails_closed_and_consumes_each_descriptor_once(
    monkeypatch, emit, label,
):
    """The released double-close, end to end on a real spawn.

    The old code closed ``ready_r`` after the handshake and then let
    ``_abandon`` close it a second time on a status line it rejected. Here a
    substitute wrapper -- the only thing replaced; the handshake, the abandon
    path and the fd accounting are production -- emits a status the daemon must
    refuse, and every ``_close_fd`` call is recorded. A descriptor number may
    appear at most once.
    """
    substitute = textwrap.dedent(f'''
        import os, sys, time
        ready_w = int(sys.argv[2])
        payload = {emit!r}
        if payload:
            os.write(ready_w, payload.encode())
        os.close(ready_w)
        time.sleep(30)
    ''')
    monkeypatch.setattr(owned_process, "_ANCHOR_WRAPPER_SRC", substitute)

    spawned = []
    real_exec = asyncio.create_subprocess_exec

    async def recording_exec(*args, **kwargs):
        proc = await real_exec(*args, **kwargs)
        spawned.append(proc)
        return proc

    monkeypatch.setattr(asyncio, "create_subprocess_exec", recording_exec)

    closed: list[int] = []
    original_close = owned_process._close_fd

    def recording_close(fd):
        if fd is not None:
            closed.append(fd)
        original_close(fd)

    monkeypatch.setattr(owned_process, "_close_fd", recording_close)

    async def exercise():
        with pytest.raises(owned_process.FamilyAnchorError):
            await owned_process.aspawn_owned(
                [sys.executable, "-c", "import time; time.sleep(30)"],
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        assert spawned, f"nothing was spawned for {label}; nothing was proven"
        for proc in spawned:
            # Fail closed means the half-spawned family is gone, not merely
            # unregistered.
            await _await_stopped(proc.pid, timeout=10)
            assert not owned_process.is_family_anchored(proc)
            assert owned_process.anchor_pid(proc) is None

    asyncio.run(exercise())

    assert len(closed) == len(set(closed)), (
        f"a descriptor was closed twice on the {label} path: {closed}; a "
        "second close can land on an fd the runtime has since reissued"
    )
    # All four of the attempt's descriptors are released, none survives.
    assert len(closed) == 4, (
        f"expected ctrl_r/ctrl_w/ready_r/ready_w released once each, got {closed}"
    )


class _RegistrableProc:
    """A process stand-in that can actually enter the weak registry.

    ``SimpleNamespace`` cannot: it defines ``__eq__``, so ``__hash__`` is
    ``None`` and ``WeakKeyDictionary.__setitem__`` raises ``TypeError``. Any
    test using one as a registered handle silently exercises the
    *unregisterable* path instead of the one it names.
    """

    __slots__ = ("pid", "returncode", "kill", "__weakref__")

    def __init__(self, pid: int = 4242):
        self.pid = pid
        self.returncode = None
        self.kill = Mock()


def _drain(read_fd: int) -> bytes:
    """Everything the control pipe carries, up to and including EOF."""
    chunks = []
    while True:
        chunk = os.read(read_fd, 64)
        if not chunk:
            return b"".join(chunks)
        chunks.append(chunk)


def test_ending_a_family_writes_the_command_then_closes_exactly_once():
    """Teardown is a write plus a close, and the close is what guarantees it.

    Runs everywhere: ``os.pipe`` is the daemon's half of the contract and needs
    no fork. The anchor acts on the command byte OR on EOF, so a second
    ``end()`` must not close again -- the descriptor number may already have
    been reissued by the runtime to something else entirely.
    """
    read_fd, write_fd = os.pipe()
    closed: list[int] = []
    real_close = os.close

    family = owned_process._Family(
        kind="anchor", pgid=4242, anchor_pid=4243, ctrl_w=write_fd,
    )
    try:
        original = os.close
        os.close = lambda fd: (closed.append(fd), real_close(fd))[1]  # noqa: E731
        try:
            family.end()
            family.end()   # idempotent: must not touch the fd again
            family.end()
        finally:
            os.close = original

        assert closed.count(write_fd) == 1, (
            f"the control descriptor was closed {closed.count(write_fd)} times; "
            "a second close can land on an fd the runtime has since reissued"
        )
        # The anchor sees the command byte and then EOF. Both mean "end the
        # family"; the EOF is the part that survives a failed write.
        assert _drain(read_fd) == b"K"
    finally:
        real_close(read_fd)


def test_daemon_teardown_of_an_anchored_family_is_the_pipe_and_nothing_else():
    """``kill_owned_tree`` on an anchor family signals no group and walks no tree.

    The daemon's whole authority is the control pipe. If it ever reached
    ``killpg`` or ``taskkill`` with an id it recorded at spawn, that id could
    already name a stranger -- which is the hazard the anchor exists to remove.
    """
    read_fd, write_fd = os.pipe()
    forbidden: list[str] = []
    monkey = pytest.MonkeyPatch()
    monkey.setattr(
        owned_process.os, "killpg",
        lambda *a, **k: forbidden.append("killpg"), raising=False,
    )
    monkey.setattr(
        owned_process.subprocess, "run",
        lambda *a, **k: forbidden.append("taskkill"),
    )

    proc = _RegistrableProc()
    owned_process.mark_owned(proc, owned_process._Family(
        kind="anchor", pgid=4242, anchor_pid=4243, ctrl_w=write_fd,
    ))
    try:
        assert owned_process.is_family_anchored(proc)
        assert owned_process.anchor_pid(proc) == 4243
        owned_process.kill_owned_tree(proc)
        assert forbidden == [], f"the daemon named an id itself: {forbidden}"
        assert _drain(read_fd) == b"K"
        proc.kill.assert_called_once()   # the narrow, handle-backed backstop
        # Authority is consumed: a second teardown cannot re-enter the pipe.
        assert not owned_process.is_family_anchored(proc)
        owned_process.kill_owned_tree(proc)
        assert forbidden == []
    finally:
        monkey.undo()
        os.close(read_fd)


def test_an_unregisterable_handle_closes_the_control_fd_instead_of_leaking_it():
    """Fail closed when the family cannot be recorded at all.

    A ``Process`` stand-in that is unhashable cannot go in the weak registry, so
    nothing would ever end that family -- and the control fd would leak once per
    turn in a long-lived daemon. ``mark_owned`` ends it immediately instead.
    """
    read_fd, write_fd = os.pipe()
    try:
        unhashable = {"pid": 4242}   # dict: unhashable, so registration raises
        owned_process.mark_owned(unhashable, owned_process._Family(
            kind="anchor", pgid=4242, anchor_pid=4243, ctrl_w=write_fd,
        ))
        assert owned_process.owned_group_id(unhashable) is None
        assert not owned_process.is_family_anchored(unhashable)
        # Ended, not leaked: the read end sees the command byte and then EOF.
        assert _drain(read_fd) == b"K"
    finally:
        os.close(read_fd)


def test_a_failed_second_pipe_releases_the_first_and_launches_nothing(monkeypatch):
    """An allocation failure part-way through a spawn must leak no descriptor.

    ``_aspawn_anchored`` needs two pipes. The control pipe is allocated first
    and handed to the bag; if the *second* allocation then fails -- EMFILE is
    the realistic way, and a long-lived daemon under load is exactly where the
    descriptor table fills -- the spawn must unwind with the first pair closed
    exactly once and no wrapper process started. A leak here is per-attempt and
    self-amplifying: each failed spawn makes the next one likelier to fail.

    Runs on every platform: the failure is reached before any spawn, so nothing
    platform-specific executes.
    """
    real_pipe = os.pipe
    real_close_fd = owned_process._close_fd
    allocated: list[tuple[int, int]] = []
    closed: list[int] = []
    spawned: list[tuple] = []

    def recording_close_fd(fd) -> None:
        if isinstance(fd, int) and fd >= 0:
            closed.append(fd)
        real_close_fd(fd)

    def failing_second_pipe() -> tuple[int, int]:
        if allocated:
            raise OSError(errno.EMFILE, os.strerror(errno.EMFILE))
        allocated.append(real_pipe())
        return allocated[0]

    async def forbidden_exec(*args, **kwargs):
        spawned.append(args)
        raise AssertionError("a child was launched after the spawn had failed")

    async def exercise():
        # Patched inside the loop so the event loop's own startup cannot be
        # caught by the fake allocator and pass this test vacuously.
        monkeypatch.setattr(owned_process.os, "pipe", failing_second_pipe)
        monkeypatch.setattr(owned_process, "_close_fd", recording_close_fd)
        monkeypatch.setattr(asyncio, "create_subprocess_exec", forbidden_exec)

        with pytest.raises(OSError) as caught:
            await owned_process._aspawn_anchored([sys.executable, "-c", "pass"])
        assert caught.value.errno == errno.EMFILE, "a different failure was raised"

        assert allocated, "the first pipe was never taken, so nothing was proven"
        assert spawned == [], "a wrapper was spawned despite the failed allocation"
        assert sorted(closed) == sorted(allocated[0]), (
            f"control pipe {allocated[0]} was not released exactly once "
            f"(closed: {closed})"
        )
        for fd in allocated[0]:
            with pytest.raises(OSError):
                os.fstat(fd)

    asyncio.run(exercise())
