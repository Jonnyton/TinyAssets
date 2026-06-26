"""Tests for workflow/cloud_worker.py — supervisor loop + helpers.

The supervisor is subprocess-based; tests avoid real spawns via the
``spawn_fn`` + ``sleep_fn`` injection seams on ``run_supervisor``. A
``FakeProc`` stands in for ``subprocess.Popen`` with scripted exit
codes so we can exercise clean-exit, crash, and stop-signal paths
without touching the OS process table.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

_WORKFLOW = Path(__file__).resolve().parent.parent / "workflow"
if str(_WORKFLOW.parent) not in sys.path:
    sys.path.insert(0, str(_WORKFLOW.parent))

import workflow.cloud_worker as cw  # noqa: E402

# ---- FakeProc: scripted subprocess stand-in ------------------------------


class FakeProc:
    """Scripted Popen stand-in. ``poll()`` returns None until ``steps_until_exit``
    calls have been made, then returns ``returncode``."""

    def __init__(self, returncode: int = 0, steps_until_exit: int = 0):
        self._target_rc = returncode
        self._remaining = steps_until_exit
        self.returncode: int | None = None
        self.terminate_called = False
        self.kill_called = False
        self.wait_called = False

    def poll(self):
        if self._remaining > 0:
            self._remaining -= 1
            return None
        self.returncode = self._target_rc
        return self._target_rc

    def terminate(self):
        self.terminate_called = True
        self.returncode = -15

    def kill(self):
        self.kill_called = True
        self.returncode = -9

    def wait(self, timeout=None):
        self.wait_called = True
        if self.returncode is None:
            self.returncode = self._target_rc
        return self.returncode


def _make_sleep_recorder() -> tuple[list, callable]:
    calls: list[float] = []

    def sleep(delay):
        calls.append(delay)
    return calls, sleep


# ---- _compute_backoff ----------------------------------------------------


def test_compute_backoff_first_crash_is_base():
    assert cw._compute_backoff(1, base=5.0, mult=2.0, ceiling=300.0) == 5.0


def test_compute_backoff_second_crash_doubles():
    assert cw._compute_backoff(2, base=5.0, mult=2.0, ceiling=300.0) == 10.0


def test_compute_backoff_third_crash_doubles_again():
    assert cw._compute_backoff(3, base=5.0, mult=2.0, ceiling=300.0) == 20.0


def test_compute_backoff_respects_ceiling():
    """Exponential growth must cap at ceiling; 10 consecutive crashes
    with base=5, mult=2 would be 2560s without the cap — clamp to 300."""
    assert cw._compute_backoff(10, base=5.0, mult=2.0, ceiling=300.0) == 300.0


def test_compute_backoff_zero_crash_count_is_zero():
    assert cw._compute_backoff(0, base=5.0, mult=2.0, ceiling=300.0) == 0.0


def test_compute_backoff_negative_crash_count_is_zero():
    assert cw._compute_backoff(-1, base=5.0, mult=2.0, ceiling=300.0) == 0.0


# ---- SupervisorState ------------------------------------------------------


def test_state_clean_exit_resets_crash_counter():
    state = cw.SupervisorState()
    state.record_exit(1)
    state.record_exit(1)
    assert state.crash_count == 2
    state.record_exit(0)
    assert state.crash_count == 0, "clean exit resets crash counter"
    assert state.total_clean_exits == 1
    assert state.total_crashes == 2
    assert state.total_spawns == 3


def test_state_summary_includes_counters():
    state = cw.SupervisorState()
    state.record_exit(0)
    state.record_exit(1)
    summary = state.summary()
    assert "spawns=2" in summary
    assert "clean=1" in summary
    assert "crashes=1" in summary
    assert "consec=1" in summary


# ---- run_supervisor — happy path + backoff paths -------------------------


def test_supervisor_clean_exit_uses_idle_backoff(tmp_path):
    """First clean exit sleeps idle_backoff (not crash_backoff)."""
    sleep_calls, sleep_fn = _make_sleep_recorder()

    def spawn(universe):
        return FakeProc(returncode=0, steps_until_exit=0)

    state = cw.run_supervisor(
        tmp_path,
        idle_backoff=7.0,
        crash_backoff=999.0,  # would be visible if used
        max_iterations=2,
        spawn_fn=spawn,
        sleep_fn=sleep_fn,
    )
    assert state.total_clean_exits == 2
    assert state.total_crashes == 0
    assert 7.0 in sleep_calls
    assert 999.0 not in sleep_calls


def test_supervisor_consecutive_clean_exits_back_off(tmp_path):
    """Idle universe-cycle exits should not respawn at a fixed short cadence."""
    sleep_calls, sleep_fn = _make_sleep_recorder()

    def spawn(universe):
        return FakeProc(returncode=0, steps_until_exit=0)

    state = cw.run_supervisor(
        tmp_path,
        idle_backoff=10.0,
        backoff_mult=2.0,
        max_backoff=45.0,
        max_iterations=4,
        spawn_fn=spawn,
        sleep_fn=sleep_fn,
    )

    assert state.total_clean_exits == 4
    assert sleep_calls == [10.0, 20.0, 40.0, 45.0]


def test_supervisor_crash_uses_exponential_backoff(tmp_path):
    """Consecutive crashes trigger doubling backoff."""
    sleep_calls, sleep_fn = _make_sleep_recorder()

    def spawn(universe):
        return FakeProc(returncode=1, steps_until_exit=0)

    state = cw.run_supervisor(
        tmp_path,
        idle_backoff=1.0,
        crash_backoff=4.0,
        backoff_mult=2.0,
        max_backoff=100.0,
        max_iterations=3,
        spawn_fn=spawn,
        sleep_fn=sleep_fn,
    )
    assert state.total_crashes == 3
    # Expected delays: 4, 8, 16.
    # sleep_calls may include the poll-interval sleeps too; filter to
    # only the backoff magnitudes we expect.
    backoff_sleeps = [d for d in sleep_calls if d in (4.0, 8.0, 16.0)]
    assert backoff_sleeps == [4.0, 8.0, 16.0]


def test_supervisor_crash_followed_by_clean_resets_backoff(tmp_path):
    """Crash → clean → crash → sleeps should be: base, idle, base (not 2x)."""
    sleep_calls, sleep_fn = _make_sleep_recorder()
    rc_sequence = [1, 0, 1]
    iter_idx = {"i": 0}

    def spawn(universe):
        rc = rc_sequence[iter_idx["i"]]
        iter_idx["i"] += 1
        return FakeProc(returncode=rc, steps_until_exit=0)

    state = cw.run_supervisor(
        tmp_path,
        idle_backoff=2.0,
        crash_backoff=5.0,
        backoff_mult=2.0,
        max_backoff=100.0,
        max_iterations=3,
        spawn_fn=spawn,
        sleep_fn=sleep_fn,
    )
    assert state.total_crashes == 2
    assert state.total_clean_exits == 1
    # The 3rd spawn is a crash after a clean. crash_count should reset
    # to 1, so backoff should be base (5.0), NOT 2x base (10.0).
    relevant = [d for d in sleep_calls if d in (2.0, 5.0, 10.0)]
    assert 10.0 not in relevant, (
        "after a clean exit, crash backoff must reset to base, not "
        "continue doubling from before"
    )


def test_supervisor_crash_resets_idle_backoff(tmp_path):
    """Crash recovery should not inherit the idle no-work backoff streak."""
    sleep_calls, sleep_fn = _make_sleep_recorder()
    rc_sequence = [0, 0, 1, 0]
    iter_idx = {"i": 0}

    def spawn(universe):
        rc = rc_sequence[iter_idx["i"]]
        iter_idx["i"] += 1
        return FakeProc(returncode=rc, steps_until_exit=0)

    state = cw.run_supervisor(
        tmp_path,
        idle_backoff=3.0,
        crash_backoff=11.0,
        backoff_mult=2.0,
        max_backoff=100.0,
        max_iterations=4,
        spawn_fn=spawn,
        sleep_fn=sleep_fn,
    )

    assert state.total_clean_exits == 3
    assert state.total_crashes == 1
    assert sleep_calls == [3.0, 6.0, 11.0, 3.0]


def test_supervisor_max_iterations_honored(tmp_path):
    sleep_calls, sleep_fn = _make_sleep_recorder()

    def spawn(universe):
        return FakeProc(returncode=0, steps_until_exit=0)

    state = cw.run_supervisor(
        tmp_path, max_iterations=5,
        spawn_fn=spawn, sleep_fn=sleep_fn,
    )
    assert state.total_spawns == 5


def test_supervisor_spawn_failure_counted_as_crash(tmp_path):
    """OSError on spawn (e.g. python binary missing) counts as a crash
    + incurs backoff. We don't want spawn failures to loop-hot."""
    sleep_calls, sleep_fn = _make_sleep_recorder()
    spawn_count = {"n": 0}

    def spawn_fails(universe):
        spawn_count["n"] += 1
        raise OSError("simulated spawn failure")

    state = cw.run_supervisor(
        tmp_path,
        crash_backoff=3.0,
        backoff_mult=2.0,
        max_backoff=50.0,
        max_iterations=3,
        spawn_fn=spawn_fails,
        sleep_fn=sleep_fn,
    )
    assert spawn_count["n"] == 3
    assert state.total_crashes == 3
    # Backoff magnitudes: 3, 6, 12.
    assert [d for d in sleep_calls if d in (3.0, 6.0, 12.0)] == [3.0, 6.0, 12.0]


def test_supervisor_spawn_failure_resets_idle_backoff(tmp_path):
    """Spawn failures are crash-path events and reset idle no-work backoff."""
    sleep_calls, sleep_fn = _make_sleep_recorder()
    outcomes = iter(["clean", "clean", "spawn-fail", "clean"])

    def spawn(universe):
        outcome = next(outcomes)
        if outcome == "spawn-fail":
            raise OSError("simulated spawn failure")
        return FakeProc(returncode=0, steps_until_exit=0)

    state = cw.run_supervisor(
        tmp_path,
        idle_backoff=3.0,
        crash_backoff=11.0,
        backoff_mult=2.0,
        max_backoff=100.0,
        max_iterations=4,
        spawn_fn=spawn,
        sleep_fn=sleep_fn,
    )

    assert state.total_clean_exits == 3
    assert state.total_crashes == 1
    assert sleep_calls == [3.0, 6.0, 11.0, 3.0]


# ---- env construction ---------------------------------------------------


def test_subprocess_env_sets_cloud_droplet_host_user(monkeypatch):
    monkeypatch.delenv("UNIVERSE_SERVER_HOST_USER", raising=False)
    env = cw._build_subprocess_env()
    assert env["UNIVERSE_SERVER_HOST_USER"] == "cloud-droplet"


def test_subprocess_env_honors_explicit_host_user_override(monkeypatch):
    """Operator override via env var wins over the default — preserves
    multi-tenant identity flexibility (memory: daemons are multi-tenant
    by design)."""
    monkeypatch.setenv("UNIVERSE_SERVER_HOST_USER", "cloud-droplet-us-east-1")
    env = cw._build_subprocess_env()
    assert env["UNIVERSE_SERVER_HOST_USER"] == "cloud-droplet-us-east-1"


def test_subprocess_env_forces_unified_execution(monkeypatch):
    """Dispatcher pick is gated on WORKFLOW_UNIFIED_EXECUTION — cloud
    worker must ensure it's on so the subprocess actually claims tasks."""
    monkeypatch.delenv("WORKFLOW_UNIFIED_EXECUTION", raising=False)
    env = cw._build_subprocess_env()
    assert env["WORKFLOW_UNIFIED_EXECUTION"] == "1"


def test_subprocess_env_preserves_operator_unified_execution_setting(monkeypatch):
    """If operator explicitly sets WORKFLOW_UNIFIED_EXECUTION=0 (to
    bisect a bug), cloud worker shouldn't override it."""
    monkeypatch.setenv("WORKFLOW_UNIFIED_EXECUTION", "0")
    env = cw._build_subprocess_env()
    assert env["WORKFLOW_UNIFIED_EXECUTION"] == "0"


def test_subprocess_env_sets_workflow_universe(tmp_path):
    env = cw._build_subprocess_env(tmp_path)
    assert env["WORKFLOW_UNIVERSE"] == str(tmp_path)


def test_subprocess_env_strips_openai_api_key_by_default(monkeypatch):
    """Cloud worker is subscription-only unless API-key providers opt in."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-fake-test-key-xyz")
    env = cw._build_subprocess_env()
    assert "OPENAI_API_KEY" not in env


def test_subprocess_env_preserves_openai_api_key_when_opted_in(monkeypatch):
    monkeypatch.setenv("WORKFLOW_ALLOW_API_KEY_PROVIDERS", "1")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-fake-test-key-xyz")
    env = cw._build_subprocess_env()
    assert env["OPENAI_API_KEY"] == "sk-fake-test-key-xyz"


# ---- queue pickup --------------------------------------------------------


def test_has_pickable_branch_task_detects_pending_dispatcher_row(tmp_path):
    from workflow.branch_tasks import BranchTask, append_task

    append_task(
        tmp_path,
        BranchTask(
            branch_task_id="bt-pending",
            branch_def_id="branch-1",
            universe_id="u",
            trigger_source="owner_queued",
        ),
    )

    assert cw._has_pickable_branch_task(tmp_path) is True


def test_has_pickable_branch_task_respects_unified_execution_opt_out(
    tmp_path, monkeypatch,
):
    from workflow.branch_tasks import BranchTask, append_task

    append_task(
        tmp_path,
        BranchTask(
            branch_task_id="bt-pending",
            branch_def_id="branch-1",
            universe_id="u",
            trigger_source="owner_queued",
        ),
    )
    monkeypatch.setenv("WORKFLOW_UNIFIED_EXECUTION", "0")

    assert cw._has_pickable_branch_task(tmp_path) is False


def test_supervisor_does_not_restart_pending_task_before_claim_grace(
    tmp_path,
    monkeypatch,
):
    from workflow.branch_tasks import BranchTask, append_task

    append_task(
        tmp_path,
        BranchTask(
            branch_task_id="bt-pending",
            branch_def_id="branch-1",
            universe_id="u",
            trigger_source="owner_queued",
        ),
    )
    monkeypatch.setattr(cw.time, "monotonic", lambda: 100.0)
    _sleep_calls, sleep_fn = _make_sleep_recorder()
    spawned: list[FakeProc] = []

    def spawn(universe):
        proc = FakeProc(returncode=0, steps_until_exit=1)
        spawned.append(proc)
        return proc

    state = cw.run_supervisor(
        tmp_path,
        producer_poll_interval=30.0,
        poll_interval=0.01,
        max_iterations=1,
        spawn_fn=spawn,
        sleep_fn=sleep_fn,
    )

    assert state.total_clean_exits == 1
    assert spawned[0].terminate_called is False


def test_supervisor_restarts_idle_subprocess_for_still_pending_task_after_grace(
    tmp_path,
    monkeypatch,
):
    from workflow.branch_tasks import BranchTask, append_task

    append_task(
        tmp_path,
        BranchTask(
            branch_task_id="bt-pending",
            branch_def_id="branch-1",
            universe_id="u",
            trigger_source="owner_queued",
        ),
    )
    # Supervisor consumes monotonic() for the producer clock, the
    # heartbeat clock, and per-tick beat checks; only the producer-poll
    # comparison needs to see the 31s jump, so feed 100.0 until the
    # producer check and 131.0 from there on.
    import itertools

    times = itertools.chain([100.0, 100.0, 100.0], itertools.repeat(131.0))
    monkeypatch.setattr(cw.time, "monotonic", lambda: next(times))
    _sleep_calls, sleep_fn = _make_sleep_recorder()
    spawned: list[FakeProc] = []

    def spawn(universe):
        proc = FakeProc(returncode=0, steps_until_exit=10)
        spawned.append(proc)
        return proc

    state = cw.run_supervisor(
        tmp_path,
        producer_poll_interval=30.0,
        poll_interval=0.01,
        max_iterations=1,
        spawn_fn=spawn,
        sleep_fn=sleep_fn,
    )

    assert state.total_clean_exits == 1
    assert spawned[0].terminate_called is True


def test_supervisor_does_not_restart_when_task_is_already_running(tmp_path):
    from workflow.branch_tasks import BranchTask, append_task

    append_task(
        tmp_path,
        BranchTask(
            branch_task_id="bt-running",
            branch_def_id="branch-1",
            universe_id="u",
            trigger_source="owner_queued",
            status="running",
        ),
    )
    spawned: list[FakeProc] = []

    def spawn(universe):
        proc = FakeProc(returncode=0, steps_until_exit=1)
        spawned.append(proc)
        return proc

    state = cw.run_supervisor(
        tmp_path,
        producer_poll_interval=0.01,
        poll_interval=0.01,
        max_iterations=1,
        spawn_fn=spawn,
        sleep_fn=lambda _: None,
    )

    assert state.total_clean_exits == 1
    assert spawned[0].terminate_called is False


# ---- _cloud_host_user ----------------------------------------------------


def test_cloud_host_user_default(monkeypatch):
    monkeypatch.delenv("UNIVERSE_SERVER_HOST_USER", raising=False)
    assert cw._cloud_host_user() == "cloud-droplet"


def test_cloud_host_user_whitespace_falls_back(monkeypatch):
    monkeypatch.setenv("UNIVERSE_SERVER_HOST_USER", "   ")
    assert cw._cloud_host_user() == "cloud-droplet"


def test_cloud_host_user_override_honored(monkeypatch):
    monkeypatch.setenv("UNIVERSE_SERVER_HOST_USER", "edge-node-42")
    assert cw._cloud_host_user() == "edge-node-42"


# ---- _resolve_universe_path ---------------------------------------------


def test_resolve_universe_explicit_override(tmp_path, monkeypatch):
    explicit = tmp_path / "my-universe"
    explicit.mkdir()
    monkeypatch.setenv("WORKFLOW_UNIVERSE", str(explicit))
    resolved = cw._resolve_universe_path()
    assert resolved == explicit


def test_resolve_universe_default_subdir(tmp_path, monkeypatch):
    (tmp_path / "my-default").mkdir()
    monkeypatch.delenv("WORKFLOW_UNIVERSE", raising=False)
    monkeypatch.setenv("UNIVERSE_SERVER_DEFAULT_UNIVERSE", "my-default")
    with patch("workflow.storage.data_dir", return_value=tmp_path):
        resolved = cw._resolve_universe_path()
    assert resolved == tmp_path / "my-default"


def test_resolve_universe_active_marker_overrides_default(tmp_path, monkeypatch):
    (tmp_path / "my-default").mkdir()
    (tmp_path / "active-now").mkdir()
    (tmp_path / ".active_universe").write_text("active-now", encoding="utf-8")
    monkeypatch.delenv("WORKFLOW_UNIVERSE", raising=False)
    monkeypatch.setenv("UNIVERSE_SERVER_DEFAULT_UNIVERSE", "my-default")
    with patch("workflow.storage.data_dir", return_value=tmp_path):
        resolved = cw._resolve_universe_path()
    assert resolved == tmp_path / "active-now"


def test_resolve_universe_explicit_override_beats_active_marker(tmp_path, monkeypatch):
    explicit = tmp_path / "explicit"
    explicit.mkdir()
    (tmp_path / "active-now").mkdir()
    (tmp_path / ".active_universe").write_text("active-now", encoding="utf-8")
    monkeypatch.setenv("WORKFLOW_UNIVERSE", str(explicit))
    monkeypatch.setenv("UNIVERSE_SERVER_DEFAULT_UNIVERSE", "active-now")
    with patch("workflow.storage.data_dir", return_value=tmp_path):
        resolved = cw._resolve_universe_path()
    assert resolved == explicit


def test_resolve_universe_auto_picks_first_with_program_md(tmp_path, monkeypatch):
    # Create two candidates; one has PROGRAM.md, one doesn't. The auto-
    # pick should land on the one with PROGRAM.md.
    empty = tmp_path / "empty-candidate"
    empty.mkdir()
    with_premise = tmp_path / "has-premise"
    with_premise.mkdir()
    (with_premise / "PROGRAM.md").write_text("premise text", encoding="utf-8")

    monkeypatch.delenv("WORKFLOW_UNIVERSE", raising=False)
    monkeypatch.delenv("UNIVERSE_SERVER_DEFAULT_UNIVERSE", raising=False)
    with patch("workflow.storage.data_dir", return_value=tmp_path):
        resolved = cw._resolve_universe_path()
    # Sorted order → `empty-candidate` comes first alphabetically,
    # but it doesn't have PROGRAM.md so should be skipped.
    assert resolved == with_premise


def test_resolve_universe_auto_picks_first_with_soul_md(tmp_path, monkeypatch):
    empty = tmp_path / "empty-candidate"
    empty.mkdir()
    with_soul = tmp_path / "has-soul"
    with_soul.mkdir()
    (with_soul / "soul.md").write_text("# Universe Soul\n", encoding="utf-8")

    monkeypatch.delenv("WORKFLOW_UNIVERSE", raising=False)
    monkeypatch.delenv("UNIVERSE_SERVER_DEFAULT_UNIVERSE", raising=False)
    with patch("workflow.storage.data_dir", return_value=tmp_path):
        resolved = cw._resolve_universe_path()
    assert resolved == with_soul


def test_resolve_universe_falls_back_to_default_universe_name(tmp_path, monkeypatch):
    """Empty data dir with nothing — falls back to 'default-universe'
    under data_dir so fantasy_daemon creates it on first run."""
    monkeypatch.delenv("WORKFLOW_UNIVERSE", raising=False)
    monkeypatch.delenv("UNIVERSE_SERVER_DEFAULT_UNIVERSE", raising=False)
    with patch("workflow.storage.data_dir", return_value=tmp_path):
        resolved = cw._resolve_universe_path()
    assert resolved == tmp_path / "default-universe"


# ---- _spawn_fantasy_daemon argv shape -----------------------------------


def test_spawn_argv_includes_no_tray_and_universe(tmp_path, monkeypatch):
    """Supervisor must pass --no-tray so fantasy_daemon doesn't try to
    init a system tray (no GUI on the droplet). Also must pass
    --universe pointing at the resolved path."""
    captured = {}

    class _FakePopen:
        def __init__(self, args, env=None, **kw):
            captured["args"] = list(args)
            captured["env"] = dict(env) if env else {}

    monkeypatch.setattr("subprocess.Popen", _FakePopen)
    cw._spawn_fantasy_daemon(tmp_path / "my-uni")
    assert "--no-tray" in captured["args"]
    assert "--universe" in captured["args"]
    idx = captured["args"].index("--universe")
    assert captured["args"][idx + 1] == str(tmp_path / "my-uni")
    assert captured["env"]["WORKFLOW_UNIVERSE"] == str(tmp_path / "my-uni")


def test_spawn_argv_uses_fantasy_daemon_module(tmp_path, monkeypatch):
    captured = {}

    class _FakePopen:
        def __init__(self, args, env=None, **kw):
            captured["args"] = list(args)

    monkeypatch.setattr("subprocess.Popen", _FakePopen)
    cw._spawn_fantasy_daemon(tmp_path / "x")
    # argv shape: python -m fantasy_daemon --universe ... --no-tray
    assert "-m" in captured["args"]
    idx = captured["args"].index("-m")
    assert captured["args"][idx + 1] == "fantasy_daemon"


def test_main_passes_provider_pin_to_supervised_daemon(tmp_path, monkeypatch):
    universe = tmp_path / "test-universe"
    universe.mkdir()
    (universe / "PROGRAM.md").write_text("x", encoding="utf-8")
    captured = {}

    def fake_spawn(u, *, extra_args=None):
        captured["universe"] = u
        captured["extra_args"] = list(extra_args or [])
        return FakeProc(returncode=0, steps_until_exit=0)

    monkeypatch.setattr(cw, "_spawn_fantasy_daemon", fake_spawn)
    monkeypatch.setattr("time.sleep", lambda _: None)

    rc = cw.main([
        "--universe", str(universe),
        "--provider", "codex",
        "--max-iterations", "1",
        "--idle-backoff", "0",
    ])

    assert rc == 0
    assert captured["universe"] == universe
    assert captured["extra_args"] == ["--provider", "codex"]


# ---- main() smoke -------------------------------------------------------


def test_main_exits_zero_after_max_iterations(tmp_path, monkeypatch):
    """Main() with scripted spawn + zero backoff must return 0 after
    hitting max_iterations. Guards against regressions where the loop
    stops respecting max_iterations or main() returns non-zero on clean
    supervisor exit."""
    universe = tmp_path / "test-universe"
    universe.mkdir()
    (universe / "PROGRAM.md").write_text("x", encoding="utf-8")

    # Patch the module-level _spawn_fantasy_daemon so run_supervisor
    # uses our FakeProc instead of a real subprocess. `run_supervisor`
    # dereferences `spawn_fn=_spawn_fantasy_daemon` at call-time (via
    # default arg evaluated each call), so monkeypatching the module
    # attribute is enough.
    def fake_spawn(u):
        return FakeProc(returncode=0, steps_until_exit=0)

    monkeypatch.setattr(cw, "_spawn_fantasy_daemon", fake_spawn)
    # Stub time.sleep so the loop has zero wall-clock cost.
    monkeypatch.setattr("time.sleep", lambda _: None)

    rc = cw.main([
        "--universe", str(universe),
        "--max-iterations", "2",
        "--idle-backoff", "0",
        "--crash-backoff", "0",
    ])
    assert rc == 0


# ---- _release_own_orphaned_leases (graceful-drain on shutdown) ------------


def _running_task(tmp_path, *, worker: str) -> None:
    """Append + claim a 'running' task (fresh lease) under *worker*."""
    from workflow.branch_tasks import BranchTask, append_task, claim_task

    append_task(tmp_path, BranchTask(
        branch_task_id=f"bt-{worker}", branch_def_id="b", universe_id="u",
    ))
    claim_task(tmp_path, f"bt-{worker}", "daemon-a", executor_worker_id=worker)


def test_release_own_orphaned_leases_releases_own(tmp_path, monkeypatch):
    """A still-valid lease under our own worker_id is released on shutdown."""
    from workflow.branch_tasks import read_queue

    monkeypatch.setenv("WORKFLOW_WORKER_ID", "claude-1")
    _running_task(tmp_path, worker="claude-1")

    assert cw._release_own_orphaned_leases(tmp_path) == 1
    assert read_queue(tmp_path)[0].status == "pending"


def test_release_own_orphaned_leases_preserves_peer(tmp_path, monkeypatch):
    """A live peer's running task (different worker_id) is never released."""
    from workflow.branch_tasks import read_queue

    monkeypatch.setenv("WORKFLOW_WORKER_ID", "claude-1")
    _running_task(tmp_path, worker="claude-2")

    assert cw._release_own_orphaned_leases(tmp_path) == 0
    assert read_queue(tmp_path)[0].status == "running"


def test_release_own_orphaned_leases_skips_default_id(tmp_path, monkeypatch):
    """The shared cloud-droplet fallback id is not released (could be shared)."""
    from workflow.branch_tasks import read_queue

    monkeypatch.delenv("WORKFLOW_WORKER_ID", raising=False)
    monkeypatch.delenv("UNIVERSE_SERVER_HOST_USER", raising=False)
    assert cw._worker_id() == cw.DEFAULT_HOST_USER  # precondition
    _running_task(tmp_path, worker=cw.DEFAULT_HOST_USER)

    assert cw._release_own_orphaned_leases(tmp_path) == 0
    assert read_queue(tmp_path)[0].status == "running"


# ---- _terminate_child_for_stop (confirm-before-release) -------------------


class _StopProc:
    """Popen stand-in scripting wait() outcomes for the stop sequence."""

    def __init__(self, wait_results):
        # wait_results: sequence of "exit" (returns rc) or "timeout" (raises).
        self._results = list(wait_results)
        self.returncode = None
        self.terminated = False
        self.killed = False

    def terminate(self):
        self.terminated = True

    def kill(self):
        self.killed = True
        self.returncode = -9

    def wait(self, timeout=None):
        outcome = self._results.pop(0)
        if outcome == "timeout":
            raise subprocess.TimeoutExpired(cmd="daemon", timeout=timeout)
        self.returncode = -15
        return self.returncode


def test_terminate_child_for_stop_clean_exit_confirms():
    """Child exits on SIGTERM within the drain wait → confirmed (no kill)."""
    proc = _StopProc(["exit"])
    assert cw._terminate_child_for_stop(proc) is True
    assert proc.killed is False


def test_terminate_child_for_stop_kill_then_confirm():
    """Child ignores SIGTERM, gets SIGKILLed, then confirmed dead → True."""
    proc = _StopProc(["timeout", "exit"])  # drain times out, confirm succeeds
    assert cw._terminate_child_for_stop(proc) is True
    assert proc.killed is True


def test_terminate_child_for_stop_unconfirmed_returns_false():
    """Child still alive after kill (confirm times out) → False (skip release)."""
    proc = _StopProc(["timeout", "timeout"])
    assert cw._terminate_child_for_stop(proc) is False
    assert proc.killed is True
