"""Tests for tinyassets/cloud_worker.py — supervisor loop + helpers.

The supervisor is subprocess-based; tests avoid real spawns via the
``spawn_fn`` + ``sleep_fn`` injection seams on ``run_supervisor``. A
``FakeProc`` stands in for ``subprocess.Popen`` with scripted exit
codes so we can exercise clean-exit, crash, and stop-signal paths
without touching the OS process table.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest
import rfc8785

_WORKFLOW = Path(__file__).resolve().parent.parent / "workflow"
if str(_WORKFLOW.parent) not in sys.path:
    sys.path.insert(0, str(_WORKFLOW.parent))

import tinyassets.cloud_worker as cw  # noqa: E402
from tinyassets import daemon_registry  # noqa: E402

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
        "after a clean exit, crash backoff must reset to base, not continue doubling from before"
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
        tmp_path,
        max_iterations=5,
        spawn_fn=spawn,
        sleep_fn=sleep_fn,
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
    """Dispatcher pick is gated on TINYASSETS_UNIFIED_EXECUTION — cloud
    worker must ensure it's on so the subprocess actually claims tasks."""
    monkeypatch.delenv("TINYASSETS_UNIFIED_EXECUTION", raising=False)
    env = cw._build_subprocess_env()
    assert env["TINYASSETS_UNIFIED_EXECUTION"] == "1"


def test_subprocess_env_preserves_operator_unified_execution_setting(monkeypatch):
    """If operator explicitly sets TINYASSETS_UNIFIED_EXECUTION=0 (to
    bisect a bug), cloud worker shouldn't override it."""
    monkeypatch.setenv("TINYASSETS_UNIFIED_EXECUTION", "0")
    env = cw._build_subprocess_env()
    assert env["TINYASSETS_UNIFIED_EXECUTION"] == "0"


def test_subprocess_env_sets_workflow_universe(tmp_path):
    env = cw._build_subprocess_env(tmp_path)
    assert env["TINYASSETS_UNIVERSE"] == str(tmp_path)


def test_subprocess_env_strips_openai_api_key_by_default(monkeypatch):
    """Cloud worker is subscription-only unless API-key providers opt in."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-fake-test-key-xyz")
    env = cw._build_subprocess_env()
    assert "OPENAI_API_KEY" not in env


def test_subprocess_env_preserves_openai_api_key_when_opted_in(monkeypatch):
    monkeypatch.setenv("TINYASSETS_ALLOW_API_KEY_PROVIDERS", "1")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-fake-test-key-xyz")
    env = cw._build_subprocess_env()
    assert env["OPENAI_API_KEY"] == "sk-fake-test-key-xyz"


# ---- queue pickup --------------------------------------------------------


def _commit_epoch2_worker_task(
    base_path: Path,
    *,
    universe_id: str = "universe-a",
    directed_daemon_id: str = "",
    directed_soul_hash: str = "",
    key_suffix: str = "default",
) -> dict:
    from tinyassets.daemon_server import initialize_author_server
    from tinyassets.storage.request_admissions import RequestAdmissionStore

    initialize_author_server(base_path)
    created_at = datetime.now(timezone.utc).isoformat()
    canonical_body = rfc8785.dumps(
        {
            "branch_id": "",
            "directed_daemon_id": directed_daemon_id,
            "directed_daemon_instruction": "",
            "pickup_incentive": "",
            "priority_weight": 5,
            "request_type": "general",
            "schema_version": "request-admission-v2",
            "text": "run the eligible worker task",
            "universe_id": universe_id,
        }
    )
    return RequestAdmissionStore(base_path).commit_admission(
        tenant_id="tenant-a",
        actor_id="actor-a",
        universe_id=universe_id,
        idempotency_key_hash=(
            "hmac-sha256:"
            + hashlib.sha256(
                f"{universe_id}:{directed_daemon_id}:{key_suffix}".encode()
            ).hexdigest()
        ),
        body_digest="sha256:" + hashlib.sha256(canonical_body).hexdigest(),
        body_digest_version="rfc8785-v1",
        request_type="general",
        text="run the eligible worker task",
        branch_id="",
        branch_def_id="loop-branch",
        trigger_source=("owner_queued" if directed_daemon_id else "operator_request"),
        accepted_priority_weight=5,
        policy_version="operator-priority-v1",
        grant_generation=1,
        receipt={
            "authority": "request-local",
            "grant_generation": 1,
            "priority_policy_version": "operator-priority-v1",
            "directed_assignment": (
                {
                    "daemon_id": directed_daemon_id,
                    "daemon_soul_hash": directed_soul_hash,
                    "authority_scope": "owner",
                }
                if directed_daemon_id
                else {}
            ),
        },
        directed_daemon_id=directed_daemon_id,
        created_at=created_at,
    )


def _seed_epoch2_worker_capacity(
    base_path: Path,
    monkeypatch,
    *,
    worker_id: str = "worker-a",
) -> tuple[Path, dict, dict]:
    monkeypatch.setattr(
        cw,
        "_epoch2_claim_consumer_ready",
        lambda: True,
    )
    _write_worker_release_state(base_path)
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(base_path))
    monkeypatch.setenv("TINYASSETS_WORKER_ID", worker_id)
    monkeypatch.setattr(cw, "_WORKER_PROTOCOL_IDENTITIES", {})
    monkeypatch.setattr(cw, "_WORKER_RUNTIME_INSTANCE_IDS", {}, raising=False)
    universe = base_path / "universe-a"
    universe.mkdir(exist_ok=True)
    daemon = daemon_registry.create_daemon(
        base_path,
        display_name="Eligible Worker",
        created_by="actor-a",
        soul_text="Run compatible epoch-2 queue work.",
    )
    runtime = daemon_registry.ensure_daemon_runtime(
        base_path,
        daemon_id=daemon["daemon_id"],
        universe_id=universe.name,
        provider_name="codex",
        model_name="gpt-5",
        created_by="cloud-droplet",
        worker_id=worker_id,
    )
    monkeypatch.setenv(
        "TINYASSETS_RUNTIME_INSTANCE_ID",
        runtime["runtime_instance_id"],
    )
    cw._snapshot_worker_protocol_identity_at_boot()
    cw.write_supervisor_heartbeat(
        universe,
        cw.SupervisorState(),
        iteration=1,
        phase="polling",
        subprocess_alive=True,
    )
    return universe, daemon, runtime


def test_register_worker_runtime_marks_server_owned_cloud_executor(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("TINYASSETS_WORKER_ID", "worker-a")
    monkeypatch.setattr(cw, "_subscription_auth_available", lambda _name: True)
    universe = tmp_path / "universe-a"
    universe.mkdir()
    daemon_registry.create_daemon(
        tmp_path,
        display_name="Cloud Project Loop",
        created_by="owner-a",
        soul_text="Run ordinary user-authored Branch work.",
        metadata={"project_loop_default": True, "universe_id": "universe-a"},
    )

    runtime_id = cw._register_worker_runtime(universe, "codex")

    assert runtime_id
    runtime = daemon_registry.list_runtime_instances(
        tmp_path,
        universe_id="universe-a",
    )[0]
    assert runtime["metadata"]["automation_executor_class"] == "cloud"


def test_has_pickable_branch_task_detects_pending_dispatcher_row(tmp_path):
    from tinyassets.branch_tasks import BranchTask, append_task

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


def test_running_guard_treats_missing_epoch2_store_as_no_active_claim(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("TINYASSETS_RUNTIME_INSTANCE_ID", "runtime-a")
    monkeypatch.setattr(
        cw,
        "_epoch2_claim_consumer_ready",
        lambda: True,
    )
    universe = tmp_path / "universe-a"
    universe.mkdir()

    assert cw._queue_has_running_branch_task(universe) is False


def test_running_guard_fails_closed_for_partial_epoch2_schema(
    tmp_path,
    monkeypatch,
):
    from tinyassets.storage.request_admissions import RequestAdmissionStore

    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(
        cw,
        "_epoch2_claim_consumer_ready",
        lambda: True,
    )
    universe = tmp_path / "universe-a"
    universe.mkdir()
    with RequestAdmissionStore(tmp_path).connection() as conn:
        conn.execute("CREATE TABLE branch_tasks_v2 (branch_task_id TEXT PRIMARY KEY)")
        conn.commit()

    assert cw._queue_has_running_branch_task(universe) is True


def test_epoch2_wakeup_publishes_capacity_only_with_release_and_runtime(
    tmp_path,
    monkeypatch,
):
    from tinyassets import branch_tasks_v2

    assert branch_tasks_v2.EPOCH2_QUEUE_CONSUMER_READY is True
    assert cw._epoch2_claim_consumer_ready() is True
    _write_worker_release_state(tmp_path)
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("TINYASSETS_WORKER_ID", "worker-a")
    monkeypatch.setattr(cw, "_WORKER_PROTOCOL_IDENTITIES", {})
    cw._snapshot_worker_protocol_identity_at_boot()

    descriptor = cw._worker_queue_descriptor(
        tmp_path / "universe-a",
        runtime_instance_id="runtime-a",
    )
    assert descriptor is not None
    assert descriptor["runtime_instance_id"] == "runtime-a"
    universe = tmp_path / "universe-a"
    universe.mkdir()
    assert cw._queue_has_running_branch_task(universe) is False


def test_has_pickable_branch_task_detects_current_worker_epoch2_candidate(
    tmp_path,
    monkeypatch,
):
    universe, _daemon, _runtime = _seed_epoch2_worker_capacity(
        tmp_path,
        monkeypatch,
    )
    _commit_epoch2_worker_task(tmp_path)

    assert cw._has_pickable_branch_task(universe) is True


def test_has_pickable_branch_task_rejects_epoch2_capacity_owned_by_other_worker(
    tmp_path,
    monkeypatch,
):
    universe, _daemon, _runtime = _seed_epoch2_worker_capacity(
        tmp_path,
        monkeypatch,
        worker_id="worker-a",
    )
    _commit_epoch2_worker_task(tmp_path)
    monkeypatch.setenv("TINYASSETS_WORKER_ID", "worker-b")
    monkeypatch.setenv("TINYASSETS_RUNTIME_INSTANCE_ID", "runtime-b")

    assert cw._has_pickable_branch_task(universe) is False


def test_has_pickable_branch_task_enforces_current_runtime_daemon_direction(
    tmp_path,
    monkeypatch,
):
    universe, daemon, _runtime = _seed_epoch2_worker_capacity(
        tmp_path,
        monkeypatch,
    )
    _commit_epoch2_worker_task(
        tmp_path,
        directed_daemon_id=daemon["daemon_id"],
        directed_soul_hash=daemon["soul_hash"],
    )

    assert cw._has_pickable_branch_task(universe) is True


def test_has_pickable_branch_task_leaves_other_daemon_epoch2_work_pending(
    tmp_path,
    monkeypatch,
):
    universe, _daemon, _runtime = _seed_epoch2_worker_capacity(
        tmp_path,
        monkeypatch,
    )
    other_daemon = daemon_registry.create_daemon(
        tmp_path,
        display_name="Other Worker",
        created_by="actor-a",
        soul_text="Own different directed work.",
    )
    _commit_epoch2_worker_task(
        tmp_path,
        directed_daemon_id=other_daemon["daemon_id"],
        directed_soul_hash=other_daemon["soul_hash"],
    )

    assert cw._has_pickable_branch_task(universe) is False


def test_epoch2_capacity_probe_does_not_reselect_v1_for_other_daemon(
    tmp_path,
    monkeypatch,
):
    from tinyassets.branch_tasks import BranchTask, append_task

    universe, runtime_daemon, _runtime = _seed_epoch2_worker_capacity(
        tmp_path,
        monkeypatch,
    )
    configured_daemon = daemon_registry.create_daemon(
        tmp_path,
        display_name="Configured V1 Worker",
        created_by="actor-a",
        soul_text="Retain the subprocess dispatcher identity.",
    )
    (universe / "dispatcher_config.yaml").write_text(
        f"active_daemon_id: {configured_daemon['daemon_id']}\n",
        encoding="utf-8",
    )
    append_task(
        universe,
        BranchTask(
            branch_task_id="v1-directed-runtime",
            branch_def_id="branch-1",
            universe_id=universe.name,
            trigger_source="owner_queued",
            directed_daemon_id=runtime_daemon["daemon_id"],
        ),
    )

    assert cw._has_pickable_branch_task(universe) is False


def test_has_pickable_branch_task_rejects_empty_canonical_daemon_id(
    tmp_path,
    monkeypatch,
):
    from tinyassets.branch_tasks_v2 import Epoch2BranchTaskAdapter

    universe, _daemon, runtime = _seed_epoch2_worker_capacity(
        tmp_path,
        monkeypatch,
    )
    other_daemon = daemon_registry.create_daemon(
        tmp_path,
        display_name="Other Directed Worker",
        created_by="actor-a",
        soul_text="Own work the anonymous runtime cannot take.",
    )
    _commit_epoch2_worker_task(
        tmp_path,
        directed_daemon_id=other_daemon["daemon_id"],
        directed_soul_hash=other_daemon["soul_hash"],
    )
    adapter = Epoch2BranchTaskAdapter(tmp_path)
    with adapter._store.connection() as conn:
        conn.execute(
            """
            UPDATE author_runtime_instances
            SET author_id = ''
            WHERE instance_id = ?
            """,
            (runtime["runtime_instance_id"],),
        )
        conn.commit()

    assert cw._has_pickable_branch_task(universe) is False


def test_has_pickable_branch_task_ignores_mutable_runtime_daemon_metadata(
    tmp_path,
    monkeypatch,
):
    from tinyassets.daemon_server import update_runtime_instance_metadata

    universe, _daemon, runtime = _seed_epoch2_worker_capacity(
        tmp_path,
        monkeypatch,
    )
    other_daemon = daemon_registry.create_daemon(
        tmp_path,
        display_name="Forged Metadata Daemon",
        created_by="actor-a",
        soul_text="Must not inherit another runtime's capacity.",
    )
    update_runtime_instance_metadata(
        tmp_path,
        instance_id=runtime["runtime_instance_id"],
        metadata_patch={"daemon_id": other_daemon["daemon_id"]},
    )
    _commit_epoch2_worker_task(
        tmp_path,
        directed_daemon_id=other_daemon["daemon_id"],
        directed_soul_hash=other_daemon["soul_hash"],
    )

    assert cw._has_pickable_branch_task(universe) is False


def test_has_pickable_branch_task_applies_request_type_filter_to_epoch2(
    tmp_path,
    monkeypatch,
):
    universe, _daemon, _runtime = _seed_epoch2_worker_capacity(
        tmp_path,
        monkeypatch,
    )
    _commit_epoch2_worker_task(tmp_path)
    monkeypatch.setenv(
        "TINYASSETS_REQUEST_TYPE_PRIORITIES",
        "bug_investigation",
    )

    assert cw._has_pickable_branch_task(universe) is False


def test_has_pickable_branch_task_rejects_expired_epoch2_capacity(
    tmp_path,
    monkeypatch,
):
    universe, _daemon, _runtime = _seed_epoch2_worker_capacity(
        tmp_path,
        monkeypatch,
    )
    _commit_epoch2_worker_task(tmp_path)
    future = datetime.now(timezone.utc) + timedelta(minutes=2)
    monkeypatch.setattr(cw, "_utcnow", lambda: future)

    assert cw._has_pickable_branch_task(universe) is False


def test_has_pickable_branch_task_applies_unified_execution_opt_out_to_epoch2(
    tmp_path,
    monkeypatch,
):
    universe, _daemon, _runtime = _seed_epoch2_worker_capacity(
        tmp_path,
        monkeypatch,
    )
    _commit_epoch2_worker_task(tmp_path)
    monkeypatch.setenv("TINYASSETS_UNIFIED_EXECUTION", "0")

    assert cw._has_pickable_branch_task(universe) is False


def test_has_pickable_branch_task_respects_unified_execution_opt_out(
    tmp_path,
    monkeypatch,
):
    from tinyassets.branch_tasks import BranchTask, append_task

    append_task(
        tmp_path,
        BranchTask(
            branch_task_id="bt-pending",
            branch_def_id="branch-1",
            universe_id="u",
            trigger_source="owner_queued",
        ),
    )
    monkeypatch.setenv("TINYASSETS_UNIFIED_EXECUTION", "0")

    assert cw._has_pickable_branch_task(tmp_path) is False


def test_supervisor_restarts_for_current_worker_epoch2_candidate_after_grace(
    tmp_path,
    monkeypatch,
):
    import itertools

    universe, _daemon, _runtime = _seed_epoch2_worker_capacity(
        tmp_path,
        monkeypatch,
    )
    _commit_epoch2_worker_task(tmp_path)
    times = itertools.chain([100.0, 100.0, 100.0], itertools.repeat(131.0))
    monkeypatch.setattr(cw.time, "monotonic", lambda: next(times))
    _sleep_calls, sleep_fn = _make_sleep_recorder()
    spawned: list[FakeProc] = []

    def spawn(universe_path):
        proc = FakeProc(returncode=0, steps_until_exit=10)
        spawned.append(proc)
        return proc

    state = cw.run_supervisor(
        universe,
        producer_poll_interval=30.0,
        poll_interval=0.01,
        max_iterations=1,
        spawn_fn=spawn,
        sleep_fn=sleep_fn,
    )

    assert state.total_clean_exits == 1
    assert spawned[0].terminate_called is True


def test_supervisor_does_not_restart_epoch2_before_claim_consumer_is_ready(
    tmp_path,
    monkeypatch,
):
    import itertools

    universe, _daemon, _runtime = _seed_epoch2_worker_capacity(
        tmp_path,
        monkeypatch,
    )
    _commit_epoch2_worker_task(tmp_path)
    monkeypatch.setattr(
        cw,
        "_epoch2_claim_consumer_ready",
        lambda: False,
    )
    times = itertools.chain([100.0, 100.0, 100.0], itertools.repeat(131.0))
    monkeypatch.setattr(cw.time, "monotonic", lambda: next(times))
    _sleep_calls, sleep_fn = _make_sleep_recorder()
    spawned: list[FakeProc] = []

    def spawn(universe_path):
        proc = FakeProc(returncode=0, steps_until_exit=1)
        spawned.append(proc)
        return proc

    cw.run_supervisor(
        universe,
        producer_poll_interval=30.0,
        poll_interval=0.01,
        max_iterations=5,
        spawn_fn=spawn,
        sleep_fn=sleep_fn,
    )

    assert len(spawned) == 5
    assert all(proc.terminate_called is False for proc in spawned)


def test_supervisor_does_not_restart_epoch2_work_without_compatible_capacity(
    tmp_path,
    monkeypatch,
):
    import itertools

    universe = tmp_path / "universe-a"
    universe.mkdir()
    committed = _commit_epoch2_worker_task(tmp_path)
    times = itertools.chain([100.0, 100.0, 100.0], itertools.repeat(131.0))
    monkeypatch.setattr(cw.time, "monotonic", lambda: next(times))
    _sleep_calls, sleep_fn = _make_sleep_recorder()
    spawned: list[FakeProc] = []

    def spawn(universe_path):
        proc = FakeProc(returncode=0, steps_until_exit=1)
        spawned.append(proc)
        return proc

    state = cw.run_supervisor(
        universe,
        producer_poll_interval=30.0,
        poll_interval=0.01,
        max_iterations=1,
        spawn_fn=spawn,
        sleep_fn=sleep_fn,
    )

    assert state.total_clean_exits == 1
    assert spawned[0].terminate_called is False
    from tinyassets.branch_tasks_v2 import Epoch2BranchTaskAdapter

    task = Epoch2BranchTaskAdapter(tmp_path).get(
        committed["branch_task_id"],
    )
    assert task is not None
    assert task.status == "pending"


def test_running_guard_protects_active_v2_claim_without_runtime_env(
    tmp_path,
    monkeypatch,
):
    from tinyassets.branch_tasks_v2 import (
        Epoch2BranchTaskAdapter,
        WorkerClaimDescriptor,
    )

    universe, _daemon, _runtime = _seed_epoch2_worker_capacity(
        tmp_path,
        monkeypatch,
    )
    running = _commit_epoch2_worker_task(tmp_path)
    beat = json.loads(
        (universe / cw.supervisor_heartbeat_filename(cw._worker_id())).read_text(encoding="utf-8")
    )
    descriptor = WorkerClaimDescriptor(
        queue_protocol_version=beat["queue_protocol_version"],
        capabilities=frozenset(beat["capabilities"]),
        worker_id=beat["worker_id"],
        runtime_instance_id=beat["runtime_instance_id"],
        boot_id=beat["boot_id"],
        build_sha=beat["build_sha"],
        config_hash=beat["config_hash"],
        universe_id=beat["universe_id"],
        expires_at=beat["expires_at"],
    )
    claimed = Epoch2BranchTaskAdapter(tmp_path).claim(
        running["branch_task_id"],
        descriptor=descriptor,
        descriptor_reader=lambda _conn, _worker_id: descriptor,
    )
    assert claimed is not None
    monkeypatch.delenv("TINYASSETS_RUNTIME_INSTANCE_ID")

    assert cw._queue_has_running_branch_task(universe) is True


def test_supervisor_does_not_recover_expired_v2_claim_while_child_is_alive(
    tmp_path,
    monkeypatch,
):
    import itertools

    from tinyassets.branch_tasks_v2 import (
        Epoch2BranchTaskAdapter,
        WorkerClaimDescriptor,
    )

    universe, _daemon, _runtime = _seed_epoch2_worker_capacity(
        tmp_path,
        monkeypatch,
    )
    running = _commit_epoch2_worker_task(tmp_path)
    beat = json.loads(
        (universe / cw.supervisor_heartbeat_filename(cw._worker_id())).read_text(encoding="utf-8")
    )
    descriptor = WorkerClaimDescriptor(
        queue_protocol_version=beat["queue_protocol_version"],
        capabilities=frozenset(beat["capabilities"]),
        worker_id=beat["worker_id"],
        runtime_instance_id=beat["runtime_instance_id"],
        boot_id=beat["boot_id"],
        build_sha=beat["build_sha"],
        config_hash=beat["config_hash"],
        universe_id=beat["universe_id"],
        expires_at=beat["expires_at"],
    )
    claim_clock = datetime.now(timezone.utc)
    adapter = Epoch2BranchTaskAdapter(
        tmp_path,
        clock=lambda: claim_clock,
    )
    claimed = adapter.claim(
        running["branch_task_id"],
        descriptor=descriptor,
        descriptor_reader=lambda _conn, _worker_id: descriptor,
        lease_seconds=30,
    )
    assert claimed is not None
    with adapter._store.connection() as conn:
        conn.execute(
            """
            UPDATE branch_tasks_v2
            SET lease_expires_at = ?
            WHERE branch_task_id = ?
            """,
            (
                (claim_clock - timedelta(minutes=1)).isoformat(),
                running["branch_task_id"],
            ),
        )
        conn.commit()

    times = itertools.chain([100.0, 100.0, 100.0], itertools.repeat(131.0))
    monkeypatch.setattr(cw.time, "monotonic", lambda: next(times))
    _sleep_calls, sleep_fn = _make_sleep_recorder()
    spawned: list[FakeProc] = []

    def spawn(universe_path):
        proc = FakeProc(returncode=0, steps_until_exit=10)
        spawned.append(proc)
        return proc

    cw.run_supervisor(
        universe,
        producer_poll_interval=30.0,
        poll_interval=0.01,
        max_iterations=1,
        spawn_fn=spawn,
        sleep_fn=sleep_fn,
    )

    assert spawned[0].terminate_called is False
    observed = Epoch2BranchTaskAdapter(tmp_path).get(
        running["branch_task_id"],
    )
    assert observed is not None
    assert observed.status == "running"


def test_supervisor_does_not_restart_while_current_worker_has_active_v2_claim(
    tmp_path,
    monkeypatch,
):
    import itertools

    from tinyassets.branch_tasks_v2 import (
        Epoch2BranchTaskAdapter,
        WorkerClaimDescriptor,
    )

    universe, _daemon, _runtime = _seed_epoch2_worker_capacity(
        tmp_path,
        monkeypatch,
    )
    running = _commit_epoch2_worker_task(
        tmp_path,
        key_suffix="running",
    )
    _commit_epoch2_worker_task(
        tmp_path,
        key_suffix="pending",
    )
    beat = json.loads(
        (universe / cw.supervisor_heartbeat_filename(cw._worker_id())).read_text(encoding="utf-8")
    )
    descriptor = WorkerClaimDescriptor(
        queue_protocol_version=beat["queue_protocol_version"],
        capabilities=frozenset(beat["capabilities"]),
        worker_id=beat["worker_id"],
        runtime_instance_id=beat["runtime_instance_id"],
        boot_id=beat["boot_id"],
        build_sha=beat["build_sha"],
        config_hash=beat["config_hash"],
        universe_id=beat["universe_id"],
        expires_at=beat["expires_at"],
    )
    adapter = Epoch2BranchTaskAdapter(tmp_path)
    claimed = adapter.claim(
        running["branch_task_id"],
        descriptor=descriptor,
        descriptor_reader=lambda _conn, _worker_id: descriptor,
    )
    assert claimed is not None
    assert claimed.status == "running"

    times = itertools.chain([100.0, 100.0, 100.0], itertools.repeat(131.0))
    monkeypatch.setattr(cw.time, "monotonic", lambda: next(times))
    _sleep_calls, sleep_fn = _make_sleep_recorder()
    spawned: list[FakeProc] = []

    def spawn(universe_path):
        proc = FakeProc(returncode=0, steps_until_exit=10)
        spawned.append(proc)
        return proc

    state = cw.run_supervisor(
        universe,
        producer_poll_interval=30.0,
        poll_interval=0.01,
        max_iterations=1,
        spawn_fn=spawn,
        sleep_fn=sleep_fn,
    )

    assert state.total_clean_exits == 1
    assert spawned[0].terminate_called is False


def test_supervisor_does_not_restart_pending_task_before_claim_grace(
    tmp_path,
    monkeypatch,
):
    from tinyassets.branch_tasks import BranchTask, append_task

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
    from tinyassets.branch_tasks import BranchTask, append_task

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


def test_cloud_automation_trigger_pump_uses_exact_registered_worker(
    tmp_path,
    monkeypatch,
):
    universe = tmp_path / "universe-alice"
    universe.mkdir()
    monkeypatch.setenv("TINYASSETS_RUNTIME_INSTANCE_ID", "runtime_cloud_1")
    monkeypatch.setattr(cw, "_worker_id", lambda: "worker_cloud_1")
    monkeypatch.setattr("tinyassets.storage.data_dir", lambda: tmp_path)
    monkeypatch.setattr(
        "tinyassets.daemon_registry.select_project_loop_daemon",
        lambda _base, *, universe_id: {"daemon_id": "daemon_cloud_1"},
    )
    observed = {}

    class _Produced:
        branch_task_id = "bt2_cloud_2"
        continuation_generation = 2

        class trigger:
            trigger_id = "cloud_trigger_2"

    def produce(base, *, universe_id, audience):
        observed.update(
            base=base,
            universe_id=universe_id,
            audience=audience,
        )
        return _Produced()

    monkeypatch.setattr(
        "tinyassets.cloud_automation_runtime.produce_one_due_cloud_automation_slice",
        produce,
    )
    monkeypatch.setattr(
        "tinyassets.cloud_automation_runtime.reconcile_one_terminal_cloud_automation",
        lambda _base, *, universe_id: None,
    )

    assert cw._pump_cloud_automation_triggers(universe) == 1
    assert observed["base"] == tmp_path
    assert observed["universe_id"] == "universe-alice"
    assert observed["audience"].worker_id == "worker_cloud_1"
    assert observed["audience"].runtime_id == "runtime_cloud_1"
    assert observed["audience"].daemon_id == "daemon_cloud_1"


def test_cloud_automation_pump_registers_operator_created_after_worker_boot(
    tmp_path,
    monkeypatch,
):
    universe = tmp_path / "universe-alice"
    universe.mkdir()
    monkeypatch.delenv("TINYASSETS_RUNTIME_INSTANCE_ID", raising=False)
    monkeypatch.setattr(cw, "_worker_id", lambda: "worker_cloud_1")
    monkeypatch.setattr("tinyassets.storage.data_dir", lambda: tmp_path)
    monkeypatch.setattr(
        "tinyassets.daemon_registry.select_project_loop_daemon",
        lambda _base, *, universe_id: {"daemon_id": "daemon_cloud_1"},
    )
    monkeypatch.setattr(
        cw,
        "_register_worker_runtime",
        lambda _universe, provider: (
            "runtime_cloud_1" if provider == "codex" else None
        ),
    )
    monkeypatch.setattr(
        "tinyassets.cloud_automation_runtime.activate_one_requested_cloud_automation",
        lambda _base, *, universe_id, audience: None,
    )
    monkeypatch.setattr(
        "tinyassets.cloud_automation_runtime.reconcile_one_terminal_cloud_automation",
        lambda _base, *, universe_id: None,
    )
    monkeypatch.setattr(
        "tinyassets.cloud_automation_runtime.produce_one_due_cloud_automation_slice",
        lambda _base, *, universe_id, audience: None,
    )

    assert cw._pump_cloud_automation_triggers(universe, provider_name="codex") == 0
    assert os.environ["TINYASSETS_RUNTIME_INSTANCE_ID"] == "runtime_cloud_1"


def test_cloud_automation_trigger_pump_keeps_owner_dimension(
    tmp_path,
    monkeypatch,
):
    from types import SimpleNamespace

    from tinyassets.storage.cloud_automation_control import CloudAutomationControlStore

    universe = tmp_path / "shared-universe"
    universe.mkdir()
    monkeypatch.delenv("TINYASSETS_RUNTIME_INSTANCE_ID", raising=False)
    monkeypatch.setenv("TINYASSETS_WORKER_ID", "worker_cloud_1")
    monkeypatch.setattr("tinyassets.storage.data_dir", lambda: tmp_path)
    monkeypatch.setattr(
        CloudAutomationControlStore,
        "list_controls",
        lambda _self, *, universe_id, limit=100: [
            SimpleNamespace(principal_id="acct_alice")
        ],
    )
    selected: list[tuple[str, str]] = []

    def select(_base, *, universe_id, owner_user_id):
        selected.append((universe_id, owner_user_id))
        return {"daemon_id": "daemon_alice"}

    monkeypatch.setattr(
        "tinyassets.daemon_registry.select_project_loop_daemon",
        select,
    )
    monkeypatch.setattr(
        cw,
        "_register_worker_runtime",
        lambda _universe, provider, *, owner_user_id="", worker_id="": (
            "runtime_alice"
            if (
                provider == "codex"
                and owner_user_id == "acct_alice"
                and worker_id
                == cw._automation_worker_slot(
                    "worker_cloud_1",
                    "shared-universe",
                    "acct_alice",
                )
            )
            else None
        ),
    )

    class _Produced:
        branch_task_id = "bt2_alice"

        class trigger:
            trigger_id = "cloud_trigger_alice"

    observed: dict[str, object] = {}
    audiences: list[object] = []

    def activate(_base, *, universe_id, audience, principal_id=""):
        audiences.append(audience)
        observed.update(
            universe_id=universe_id,
            audience=audience,
            principal_id=principal_id,
        )
        return _Produced()

    monkeypatch.setattr(
        "tinyassets.cloud_automation_runtime.activate_one_requested_cloud_automation",
        activate,
    )
    monkeypatch.setattr(
        "tinyassets.cloud_automation_runtime.reconcile_one_terminal_cloud_automation",
        lambda _base, *, universe_id: None,
    )

    assert cw._pump_cloud_automation_triggers(
        universe,
        provider_name="codex",
        physical_worker_id="worker_cloud_1",
    ) == 1
    assert cw._pump_cloud_automation_triggers(
        universe,
        provider_name="codex",
        physical_worker_id="worker_cloud_1",
    ) == 1
    assert selected == [
        ("shared-universe", "acct_alice"),
        ("shared-universe", "acct_alice"),
    ]
    assert observed["principal_id"] == "acct_alice"
    assert observed["audience"].daemon_id == "daemon_alice"
    assert observed["audience"].runtime_id == "runtime_alice"
    assert observed["audience"].worker_id == cw._automation_worker_slot(
        "worker_cloud_1",
        "shared-universe",
        "acct_alice",
    )
    assert audiences[0] == audiences[1]


def test_cloud_automation_worker_slot_survives_process_replacement() -> None:
    alice_first = cw._automation_worker_slot(
        "codex-1", "shared-universe", "acct_alice"
    )
    alice_replacement = cw._automation_worker_slot(
        "codex-1", "shared-universe", "acct_alice"
    )
    alice_second_container = cw._automation_worker_slot(
        "codex-2", "shared-universe", "acct_alice"
    )
    bob = cw._automation_worker_slot("codex-1", "shared-universe", "acct_bob")

    assert alice_first == alice_replacement
    assert alice_first.startswith("worker_cloud_automation_")
    assert alice_first != alice_second_container
    assert alice_first != bob


def test_four_cloud_workers_bind_distinct_restart_stable_boot_descriptors(
    tmp_path,
    monkeypatch,
) -> None:
    universe = tmp_path / "shared-universe"
    universe.mkdir()
    _write_worker_release_state(tmp_path)
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(cw, "_WORKER_PROTOCOL_IDENTITIES", {})
    monkeypatch.setattr(cw, "_epoch2_claim_consumer_ready", lambda: True)
    descriptors: dict[str, dict[str, object]] = {}

    for physical_worker_id in ("codex-1", "codex-2", "claude-1", "claude-2"):
        monkeypatch.setenv("TINYASSETS_WORKER_ID", physical_worker_id)
        physical_identity = cw._snapshot_worker_protocol_identity_at_boot()
        assert physical_identity is not None
        logical_worker_id = cw._automation_worker_slot(
            physical_worker_id,
            universe.name,
            "acct_alice",
        )
        assert cw._bind_automation_worker_protocol_identity(
            physical_worker_id,
            logical_worker_id,
        )
        monkeypatch.setenv("TINYASSETS_WORKER_ID", logical_worker_id)
        descriptor = cw._worker_queue_descriptor(
            universe,
            runtime_instance_id=f"runtime_{physical_worker_id.replace('-', '_')}",
            _now=datetime(2026, 8, 3, tzinfo=timezone.utc),
        )
        assert descriptor is not None
        descriptors[physical_worker_id] = descriptor

        monkeypatch.setenv("TINYASSETS_WORKER_ID", physical_worker_id)
        assert cw._snapshot_worker_protocol_identity_at_boot() == physical_identity
        assert cw._bind_automation_worker_protocol_identity(
            physical_worker_id,
            logical_worker_id,
        )

    assert len({value["worker_id"] for value in descriptors.values()}) == 4
    assert len({value["boot_id"] for value in descriptors.values()}) == 4


def test_supervisor_does_not_restart_when_task_is_already_running(tmp_path):
    from tinyassets.branch_tasks import BranchTask, append_task

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
    monkeypatch.setenv("TINYASSETS_UNIVERSE", str(explicit))
    resolved = cw._resolve_universe_path()
    assert resolved == explicit


def test_resolve_universe_default_subdir(tmp_path, monkeypatch):
    (tmp_path / "my-default").mkdir()
    monkeypatch.delenv("TINYASSETS_UNIVERSE", raising=False)
    monkeypatch.setenv("UNIVERSE_SERVER_DEFAULT_UNIVERSE", "my-default")
    with patch("tinyassets.storage.data_dir", return_value=tmp_path):
        resolved = cw._resolve_universe_path()
    assert resolved == tmp_path / "my-default"


def test_resolve_universe_active_marker_overrides_default(tmp_path, monkeypatch):
    (tmp_path / "my-default").mkdir()
    (tmp_path / "active-now").mkdir()
    (tmp_path / ".active_universe").write_text("active-now", encoding="utf-8")
    monkeypatch.delenv("TINYASSETS_UNIVERSE", raising=False)
    monkeypatch.setenv("UNIVERSE_SERVER_DEFAULT_UNIVERSE", "my-default")
    with patch("tinyassets.storage.data_dir", return_value=tmp_path):
        resolved = cw._resolve_universe_path()
    assert resolved == tmp_path / "active-now"


def test_resolve_universe_explicit_override_beats_active_marker(tmp_path, monkeypatch):
    explicit = tmp_path / "explicit"
    explicit.mkdir()
    (tmp_path / "active-now").mkdir()
    (tmp_path / ".active_universe").write_text("active-now", encoding="utf-8")
    monkeypatch.setenv("TINYASSETS_UNIVERSE", str(explicit))
    monkeypatch.setenv("UNIVERSE_SERVER_DEFAULT_UNIVERSE", "active-now")
    with patch("tinyassets.storage.data_dir", return_value=tmp_path):
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

    monkeypatch.delenv("TINYASSETS_UNIVERSE", raising=False)
    monkeypatch.delenv("UNIVERSE_SERVER_DEFAULT_UNIVERSE", raising=False)
    with patch("tinyassets.storage.data_dir", return_value=tmp_path):
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

    monkeypatch.delenv("TINYASSETS_UNIVERSE", raising=False)
    monkeypatch.delenv("UNIVERSE_SERVER_DEFAULT_UNIVERSE", raising=False)
    with patch("tinyassets.storage.data_dir", return_value=tmp_path):
        resolved = cw._resolve_universe_path()
    assert resolved == with_soul


def test_resolve_universe_falls_back_to_default_universe_name(tmp_path, monkeypatch):
    """Empty data dir with nothing — falls back to 'default-universe'
    under data_dir so fantasy_daemon creates it on first run."""
    monkeypatch.delenv("TINYASSETS_UNIVERSE", raising=False)
    monkeypatch.delenv("UNIVERSE_SERVER_DEFAULT_UNIVERSE", raising=False)
    with patch("tinyassets.storage.data_dir", return_value=tmp_path):
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
    assert captured["env"]["TINYASSETS_UNIVERSE"] == str(tmp_path / "my-uni")


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

    rc = cw.main(
        [
            "--universe",
            str(universe),
            "--provider",
            "codex",
            "--max-iterations",
            "1",
            "--idle-backoff",
            "0",
        ]
    )

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

    rc = cw.main(
        [
            "--universe",
            str(universe),
            "--max-iterations",
            "2",
            "--idle-backoff",
            "0",
            "--crash-backoff",
            "0",
        ]
    )
    assert rc == 0


# ---- _release_own_orphaned_leases (graceful-drain on shutdown) ------------


def _running_task(tmp_path, *, worker: str) -> None:
    """Append + claim a 'running' task (fresh lease) under *worker*."""
    from tinyassets.branch_tasks import BranchTask, append_task, claim_task

    append_task(
        tmp_path,
        BranchTask(
            branch_task_id=f"bt-{worker}",
            branch_def_id="b",
            universe_id="u",
        ),
    )
    claim_task(tmp_path, f"bt-{worker}", "daemon-a", executor_worker_id=worker)


def test_release_own_orphaned_leases_releases_own(tmp_path, monkeypatch):
    """A still-valid lease under our own worker_id is released on shutdown."""
    from tinyassets.branch_tasks import read_queue

    monkeypatch.setenv("TINYASSETS_WORKER_ID", "claude-1")
    _running_task(tmp_path, worker="claude-1")

    assert cw._release_own_orphaned_leases(tmp_path) == 1
    assert read_queue(tmp_path)[0].status == "pending"


def test_release_own_orphaned_leases_preserves_peer(tmp_path, monkeypatch):
    """A live peer's running task (different worker_id) is never released."""
    from tinyassets.branch_tasks import read_queue

    monkeypatch.setenv("TINYASSETS_WORKER_ID", "claude-1")
    _running_task(tmp_path, worker="claude-2")

    assert cw._release_own_orphaned_leases(tmp_path) == 0
    assert read_queue(tmp_path)[0].status == "running"


def test_release_own_orphaned_leases_skips_default_id(tmp_path, monkeypatch):
    """The shared cloud-droplet fallback id is not released (could be shared)."""
    from tinyassets.branch_tasks import read_queue

    monkeypatch.delenv("TINYASSETS_WORKER_ID", raising=False)
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


def _write_worker_release_state(
    base_path: Path,
    *,
    build_sha: str = "a" * 40,
    config_hash: str = "sha256:" + ("b" * 64),
    release_state_version: int = 2,
    canary_bundle_status: str = "passed",
) -> None:
    image_ref = "ghcr.io/tinyassets/tinyassets@sha256:" + ("e" * 64)
    (base_path / "release-state.json").write_text(
        json.dumps(
            {
                "release_state_version": release_state_version,
                "outcome": "deployed",
                "active_identity_status": "agreed",
                "canary_bundle_status": canary_bundle_status,
                "configured_image_ref": image_ref,
                "running_image_ref": image_ref,
                "active_image_ref": image_ref,
                "active_image_digest": image_ref,
                "image_ref": image_ref,
                "image_digest": image_ref,
                "git_sha": build_sha,
                "active_git_sha": build_sha,
                "config_hash": config_hash,
                "config_version": "tinyassets-env-v1",
            }
        ),
        encoding="utf-8",
    )


@pytest.mark.parametrize(
    ("mutate",),
    [
        (lambda payload: payload.pop("release_state_version"),),
        (lambda payload: payload.update(release_state_version=1),),
        (lambda payload: payload.update(outcome="rollback_failed"),),
        (lambda payload: payload.update(active_identity_status="unknown"),),
        (lambda payload: payload.update(canary_bundle_status="failed"),),
        (lambda payload: payload.update(running_image_ref="mismatch"),),
        (lambda payload: payload.update(active_git_sha="f" * 40),),
        (
            lambda payload: payload.update(
                config_hash=payload["config_hash"].removeprefix("sha256:")
            ),
        ),
        (lambda payload: payload.update(config_version=""),),
    ],
)
def test_worker_release_identity_requires_v2_terminal_proof(
    tmp_path,
    monkeypatch,
    mutate,
):
    _write_worker_release_state(tmp_path)
    path = tmp_path / "release-state.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    mutate(payload)
    path.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))

    assert cw._load_worker_release_identity() is None


def test_worker_queue_descriptor_is_release_derived_and_boot_bound(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(
        cw,
        "_epoch2_claim_consumer_ready",
        lambda: True,
    )
    _write_worker_release_state(tmp_path)
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("TINYASSETS_WORKER_ID", "worker-a")
    monkeypatch.setenv("TINYASSETS_QUEUE_PROTOCOL_VERSION", "999")
    monkeypatch.setenv("TINYASSETS_WORKER_CAPABILITIES", "forged")
    monkeypatch.setattr(cw, "_WORKER_PROTOCOL_IDENTITIES", {})
    now = [datetime.fromisoformat("2026-07-24T08:00:00+00:00")]
    monkeypatch.setattr(cw, "_utcnow", lambda: now[0])
    universe = tmp_path / "universe-a"

    boot_identity = cw._snapshot_worker_protocol_identity_at_boot()
    assert boot_identity["build_sha"] == "a" * 40
    assert (
        cw._worker_queue_descriptor(
            universe,
            runtime_instance_id="",
        )
        is None
    )

    # A registration-delayed process must retain the release that was
    # terminal-proof when it booted, even if deploy state changes meanwhile.
    _write_worker_release_state(
        tmp_path,
        build_sha="c" * 40,
        config_hash="sha256:" + ("d" * 64),
    )
    first = cw._worker_queue_descriptor(
        universe,
        runtime_instance_id="runtime-a",
    )

    assert first == {
        "queue_protocol_version": 2,
        "capabilities": ["operator_request_v1"],
        "worker_id": "worker-a",
        "runtime_instance_id": "runtime-a",
        "boot_id": first["boot_id"],
        "build_sha": "a" * 40,
        "config_hash": "sha256:" + ("b" * 64),
        "universe_id": "universe-a",
        "expires_at": "2026-07-24T08:01:30Z",
    }
    assert first["boot_id"]

    now[0] = datetime.fromisoformat("2026-07-24T08:00:30+00:00")
    refreshed = cw._worker_queue_descriptor(
        universe,
        runtime_instance_id="runtime-a",
    )
    assert refreshed["build_sha"] == "a" * 40
    assert refreshed["config_hash"] == "sha256:" + ("b" * 64)
    assert refreshed["boot_id"] == first["boot_id"]
    assert refreshed["expires_at"] == "2026-07-24T08:02:00Z"

    monkeypatch.setenv("TINYASSETS_WORKER_ID", "worker-b")
    cw._snapshot_worker_protocol_identity_at_boot()
    other_worker = cw._worker_queue_descriptor(
        universe,
        runtime_instance_id="runtime-b",
    )
    assert other_worker["build_sha"] == "c" * 40
    assert other_worker["config_hash"] == "sha256:" + ("d" * 64)
    assert other_worker["boot_id"] != first["boot_id"]


def test_supervisor_heartbeat_persists_isolated_worker_descriptors(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(
        cw,
        "_epoch2_claim_consumer_ready",
        lambda: True,
    )
    _write_worker_release_state(tmp_path)
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(cw, "_WORKER_PROTOCOL_IDENTITIES", {})
    monkeypatch.setattr(cw, "_WORKER_RUNTIME_INSTANCE_IDS", {}, raising=False)
    now = datetime.fromisoformat("2026-07-24T08:00:00+00:00")
    monkeypatch.setattr(cw, "_utcnow", lambda: now)
    universe = tmp_path / "universe-a"
    universe.mkdir()
    daemon = daemon_registry.create_daemon(
        tmp_path,
        display_name="Descriptor Runner",
        created_by="host",
        soul_text="Run descriptor-capable queue work.",
    )

    def runtime_for(worker_id: str) -> dict:
        return daemon_registry.ensure_daemon_runtime(
            tmp_path,
            daemon_id=daemon["daemon_id"],
            universe_id="universe-a",
            provider_name="codex",
            model_name="gpt-5",
            created_by="cloud-droplet",
            worker_id=worker_id,
        )

    runtime_a = runtime_for("worker-a")
    monkeypatch.setenv("TINYASSETS_WORKER_ID", "worker-a")
    cw._snapshot_worker_protocol_identity_at_boot()
    monkeypatch.setenv(
        "TINYASSETS_RUNTIME_INSTANCE_ID",
        runtime_a["runtime_instance_id"],
    )
    cw.write_supervisor_heartbeat(
        universe,
        cw.SupervisorState(),
        iteration=1,
        phase="polling",
    )
    worker_a_path = universe / ".worker_supervisor.worker-a.json"
    worker_a = json.loads(worker_a_path.read_text(encoding="utf-8"))
    descriptor_a = {key: worker_a[key] for key in cw.WORKER_QUEUE_DESCRIPTOR_FIELDS}

    runtime_a_after = daemon_registry.list_runtime_instances(
        tmp_path,
        universe_id="universe-a",
    )[0]
    assert runtime_a_after["metadata"]["queue_protocol_descriptor"] == descriptor_a
    assert descriptor_a["worker_id"] == "worker-a"
    assert descriptor_a["runtime_instance_id"] == runtime_a["runtime_instance_id"]

    runtime_b = runtime_for("worker-b")
    monkeypatch.setenv("TINYASSETS_WORKER_ID", "worker-b")
    cw._snapshot_worker_protocol_identity_at_boot()
    monkeypatch.setenv(
        "TINYASSETS_RUNTIME_INSTANCE_ID",
        runtime_b["runtime_instance_id"],
    )
    cw.write_supervisor_heartbeat(
        universe,
        cw.SupervisorState(),
        iteration=1,
        phase="polling",
    )
    worker_b = json.loads(
        (universe / ".worker_supervisor.worker-b.json").read_text(encoding="utf-8")
    )

    assert json.loads(worker_a_path.read_text(encoding="utf-8")) == worker_a
    assert worker_b["worker_id"] == "worker-b"
    assert worker_b["runtime_instance_id"] == runtime_b["runtime_instance_id"]
    assert worker_b["boot_id"] != worker_a["boot_id"]

    (tmp_path / "release-state.json").unlink()
    monkeypatch.setattr(cw, "_WORKER_PROTOCOL_IDENTITIES", {})
    monkeypatch.setenv("TINYASSETS_WORKER_ID", "worker-a")
    # This block stands in for a separate worker-a container, so run the boot
    # ritual it would run. The supervisor's beat identity is frozen there and
    # deliberately does not follow a later env change (the automation pump
    # rebinds TINYASSETS_WORKER_ID in-process and never restores it).
    cw._snapshot_worker_protocol_identity_at_boot()
    monkeypatch.setenv(
        "TINYASSETS_RUNTIME_INSTANCE_ID",
        runtime_a["runtime_instance_id"],
    )
    cw.write_supervisor_heartbeat(
        universe,
        cw.SupervisorState(),
        iteration=2,
        phase="polling",
    )
    runtime_a_cleared = next(
        runtime
        for runtime in daemon_registry.list_runtime_instances(
            tmp_path,
            universe_id="universe-a",
        )
        if runtime["runtime_instance_id"] == runtime_a["runtime_instance_id"]
    )
    assert runtime_a_cleared["metadata"]["queue_protocol_descriptor"] is None
    cleared_beat = json.loads(worker_a_path.read_text(encoding="utf-8"))
    assert "queue_protocol_version" not in cleared_beat

    _write_worker_release_state(tmp_path)
    monkeypatch.setattr(cw, "_WORKER_PROTOCOL_IDENTITIES", {})
    monkeypatch.setenv("TINYASSETS_WORKER_ID", "worker-b")
    cw._snapshot_worker_protocol_identity_at_boot()
    monkeypatch.setenv(
        "TINYASSETS_RUNTIME_INSTANCE_ID",
        runtime_a["runtime_instance_id"],
    )
    cw.write_supervisor_heartbeat(
        universe,
        cw.SupervisorState(),
        iteration=3,
        phase="polling",
    )
    mismatched_beat = json.loads(
        (universe / ".worker_supervisor.worker-b.json").read_text(encoding="utf-8")
    )
    assert "queue_protocol_version" not in mismatched_beat


def test_supervisor_clears_last_durable_descriptor_when_runtime_id_is_lost(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(
        cw,
        "_epoch2_claim_consumer_ready",
        lambda: True,
    )
    _write_worker_release_state(tmp_path)
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("TINYASSETS_WORKER_ID", "worker-a")
    monkeypatch.setattr(cw, "_WORKER_PROTOCOL_IDENTITIES", {})
    monkeypatch.setattr(cw, "_WORKER_RUNTIME_INSTANCE_IDS", {}, raising=False)
    cw._snapshot_worker_protocol_identity_at_boot()
    universe = tmp_path / "universe-a"
    universe.mkdir()
    daemon = daemon_registry.create_daemon(
        tmp_path,
        display_name="Descriptor Runner",
        created_by="host",
        soul_text="Run descriptor-capable queue work.",
    )
    runtime = daemon_registry.ensure_daemon_runtime(
        tmp_path,
        daemon_id=daemon["daemon_id"],
        universe_id="universe-a",
        provider_name="codex",
        model_name="gpt-5",
        created_by="cloud-droplet",
        worker_id="worker-a",
    )
    monkeypatch.setenv(
        "TINYASSETS_RUNTIME_INSTANCE_ID",
        runtime["runtime_instance_id"],
    )

    cw.write_supervisor_heartbeat(
        universe,
        cw.SupervisorState(),
        iteration=1,
        phase="polling",
    )
    monkeypatch.delenv("TINYASSETS_RUNTIME_INSTANCE_ID")
    cw.write_supervisor_heartbeat(
        universe,
        cw.SupervisorState(),
        iteration=2,
        phase="registration_failed",
    )

    observed = daemon_registry.list_runtime_instances(
        tmp_path,
        universe_id="universe-a",
    )[0]
    assert observed["metadata"]["queue_protocol_descriptor"] is None
    beat = json.loads((universe / ".worker_supervisor.worker-a.json").read_text(encoding="utf-8"))
    assert "queue_protocol_version" not in beat


def test_run_supervisor_snapshots_protocol_identity_before_polling(
    tmp_path,
    monkeypatch,
):
    snapshots = []
    monkeypatch.setattr(
        cw,
        "_snapshot_worker_protocol_identity_at_boot",
        lambda _physical_worker_id="", state=None: snapshots.append("boot"),
    )
    monkeypatch.setattr(cw, "threading_is_main", lambda: False)

    cw.run_supervisor(tmp_path, max_iterations=0)

    assert snapshots == ["boot"]


def test_runtime_switch_ignores_absent_prior_slot_and_publishes_new_one(
    monkeypatch,
    tmp_path,
):
    descriptor = {
        "runtime_instance_id": "runtime-new",
        "worker_id": "worker-a",
    }
    calls = []

    def persist(_base_path, *, runtime_instance_id, descriptor, **_kwargs):
        calls.append((runtime_instance_id, descriptor))
        if runtime_instance_id == "runtime-gone":
            raise KeyError(runtime_instance_id)

    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("TINYASSETS_WORKER_ID", "worker-a")
    monkeypatch.setenv("TINYASSETS_RUNTIME_INSTANCE_ID", "runtime-new")
    monkeypatch.setattr(
        cw,
        "_WORKER_RUNTIME_INSTANCE_IDS",
        {"worker-a": "runtime-gone"},
    )
    monkeypatch.setattr(
        daemon_registry,
        "set_worker_queue_descriptor",
        persist,
    )

    assert cw._persist_worker_queue_descriptor(descriptor) is True
    assert calls == [
        ("runtime-gone", None),
        ("runtime-new", descriptor),
    ]
    assert cw._WORKER_RUNTIME_INSTANCE_IDS["worker-a"] == "runtime-new"


def test_runtime_switch_clears_retired_slot_and_publishes_replacement(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(
        cw,
        "_epoch2_claim_consumer_ready",
        lambda: True,
    )
    _write_worker_release_state(tmp_path)
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("TINYASSETS_WORKER_ID", "worker-a")
    monkeypatch.setattr(cw, "_WORKER_PROTOCOL_IDENTITIES", {})
    monkeypatch.setattr(cw, "_WORKER_RUNTIME_INSTANCE_IDS", {})
    cw._snapshot_worker_protocol_identity_at_boot()
    universe = tmp_path / "universe-a"
    universe.mkdir()
    daemon = daemon_registry.create_daemon(
        tmp_path,
        display_name="Switching Descriptor Runner",
        created_by="host",
        soul_text="Move only between trusted runtime slots.",
    )

    def new_runtime() -> dict:
        return daemon_registry.ensure_daemon_runtime(
            tmp_path,
            daemon_id=daemon["daemon_id"],
            universe_id="universe-a",
            provider_name="codex",
            model_name="gpt-5",
            created_by="cloud-droplet",
            worker_id="worker-a",
        )

    runtime_a = new_runtime()
    monkeypatch.setenv(
        "TINYASSETS_RUNTIME_INSTANCE_ID",
        runtime_a["runtime_instance_id"],
    )
    cw.write_supervisor_heartbeat(
        universe,
        cw.SupervisorState(),
        iteration=1,
        phase="polling",
    )
    daemon_registry.banish_daemon(
        tmp_path,
        runtime_instance_id=runtime_a["runtime_instance_id"],
    )
    runtime_b = new_runtime()
    monkeypatch.setenv(
        "TINYASSETS_RUNTIME_INSTANCE_ID",
        runtime_b["runtime_instance_id"],
    )

    cw.write_supervisor_heartbeat(
        universe,
        cw.SupervisorState(),
        iteration=2,
        phase="polling",
    )

    runtimes = {
        runtime["runtime_instance_id"]: runtime
        for runtime in daemon_registry.list_runtime_instances(
            tmp_path,
            universe_id="universe-a",
        )
    }
    assert runtimes[runtime_a["runtime_instance_id"]]["status"] == "retired"
    assert (
        runtimes[runtime_a["runtime_instance_id"]]["metadata"]["queue_protocol_descriptor"] is None
    )
    descriptor_b = runtimes[runtime_b["runtime_instance_id"]]["metadata"][
        "queue_protocol_descriptor"
    ]
    assert descriptor_b["runtime_instance_id"] == runtime_b["runtime_instance_id"]
    beat = json.loads((universe / ".worker_supervisor.worker-a.json").read_text(encoding="utf-8"))
    assert beat["runtime_instance_id"] == runtime_b["runtime_instance_id"]
    assert beat["boot_id"] == descriptor_b["boot_id"]


def test_short_lived_child_still_pumps_cloud_automation_triggers(tmp_path, monkeypatch):
    """A child that exits fast must not starve the first cloud-automation slice.

    The producer clock starts when the child spawns, and the pump only fires
    once `producer_poll_interval` has elapsed — but the poll loop breaks as soon
    as `proc.poll()` returns, and every respawn resets the clock. On an idle
    queue the child exits in well under one interval, so
    `_pump_cloud_automation_triggers` never ran at all: the only code path that
    can converge a `desired_state=active` automation into its first slice was
    reachable only when work already existed.

    Observed live 2026-08-05: two independently created automations sat at
    `activation.state=stopped`, epoch 0, zero terminal receipts — one of them for
    over two hours.
    """
    pumped: list[int] = []
    monkeypatch.setattr(
        cw,
        "_pump_cloud_automation_triggers",
        lambda *args, **kwargs: (pumped.append(1), 0)[1],
    )
    _sleep_calls, sleep_fn = _make_sleep_recorder()

    cw.run_supervisor(
        tmp_path,
        idle_backoff=0.0,
        max_iterations=2,
        producer_poll_interval=30.0,
        spawn_fn=lambda universe: FakeProc(returncode=0, steps_until_exit=0),
        sleep_fn=sleep_fn,
    )

    assert pumped, (
        "the cloud-automation trigger pump never ran across two subprocess "
        "lifecycles, so a desired-active automation can never reach slice 1"
    )


def test_beat_stays_findable_after_the_pump_rebinds_worker_identity(
    tmp_path,
    monkeypatch,
):
    """The healthcheck must still find the beat once an automation ran.

    `_pump_cloud_automation_triggers` rebinds ``TINYASSETS_WORKER_ID``
    in-process to a per-owner logical slot and never restores it. The
    supervisor derives its beat filename from that id, while
    `cloud_worker_healthcheck` runs in a FRESH process and reads the
    container's configured value -- so a drifted filename makes a healthy
    worker read as dead. Live 2026-08-05: three of four workers reported
    `supervisor beat stale` for ~50 minutes while beating normally, and the
    host's autoheal timer was inactive so nothing recovered them.
    """
    from tinyassets import cloud_worker_healthcheck as hc

    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("TINYASSETS_WORKER_ID", "claude-1")
    universe = tmp_path / "universe-a"
    universe.mkdir(parents=True, exist_ok=True)

    # Boot as the container does, then let the pump rebind identity.
    monkeypatch.setattr(cw, "_WORKER_PROTOCOL_IDENTITIES", {})
    state = cw.SupervisorState()
    cw._snapshot_worker_protocol_identity_at_boot(state=state)
    monkeypatch.setenv(
        "TINYASSETS_WORKER_ID",
        cw._automation_worker_slot("claude-1", "universe-a", "user-a"),
    )
    assert cw._worker_id().startswith("worker_cloud_automation_")

    cw.write_supervisor_heartbeat(
        universe,
        state,
        iteration=1,
        phase="polling",
    )

    # The healthcheck's fresh process sees the container's configured id.
    healthy, reason = hc.check(universe, worker_id="claude-1")
    assert healthy, reason


def test_supervisor_worker_id_falls_back_before_boot(monkeypatch):
    """Not yet booted (tests, direct calls) must still resolve an id."""

    assert cw._supervisor_worker_id(None) == cw._worker_id()
    assert cw._supervisor_worker_id(cw.SupervisorState()) == cw._worker_id()


def test_one_supervisors_frozen_id_cannot_leak_into_another(
    tmp_path,
    monkeypatch,
):
    """A second supervisor must beat under ITS configured id, not the first's.

    The frozen identity lives on `SupervisorState` rather than a module
    global precisely so it cannot survive between supervisors that share an
    interpreter. A leaked global made a worker write its beat under a peer's
    name -- the same false-dead failure this freeze exists to prevent.
    """
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
    universe = tmp_path / "universe-a"
    universe.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(cw, "_WORKER_PROTOCOL_IDENTITIES", {})

    monkeypatch.setenv("TINYASSETS_WORKER_ID", "claude-1")
    booted = cw.SupervisorState()
    cw._snapshot_worker_protocol_identity_at_boot(state=booted)

    # A LATER beat that never booted (a direct caller, or another
    # supervisor in the same interpreter) must resolve its own configured
    # id -- not inherit `claude-1` from the supervisor that booted first.
    monkeypatch.setenv("TINYASSETS_WORKER_ID", "codex-1")
    cw.write_supervisor_heartbeat(
        universe,
        cw.SupervisorState(),
        iteration=1,
        phase="polling",
    )

    assert (universe / ".worker_supervisor.codex-1.json").exists()
    assert not (universe / ".worker_supervisor.claude-1.json").exists()


# ---- serve the universe that actually has work -------------------------


def test_configured_universe_keeps_the_worker_while_it_has_work(
    tmp_path,
    monkeypatch,
):
    """A busy configured universe must behave exactly as before.

    This is the accept-direction control: the selection may only move a
    worker OFF an idle universe, never off a working one.
    """
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
    configured = tmp_path / "universe-a"
    configured.mkdir(parents=True, exist_ok=True)
    starving = tmp_path / "universe-b"
    starving.mkdir(parents=True, exist_ok=True)

    _commit_epoch2_worker_task(tmp_path, universe_id="universe-a")
    _commit_epoch2_worker_task(tmp_path, universe_id="universe-b")

    assert cw._universe_to_serve(configured) == configured


def test_an_idle_worker_serves_the_universe_that_is_starving(
    tmp_path,
    monkeypatch,
):
    """Live 2026-08-05: four admissible rows waited >15h in the founder home
    while the fleet served `concordance`, because the served universe comes
    from a host-global marker no authenticated user can repoint."""
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
    configured = tmp_path / "universe-a"
    configured.mkdir(parents=True, exist_ok=True)
    starving = tmp_path / "universe-b"
    starving.mkdir(parents=True, exist_ok=True)

    # Only universe-b has admissible work.
    _commit_epoch2_worker_task(tmp_path, universe_id="universe-b")
    monkeypatch.setattr(cw, "_worker_runtime_already_bound", lambda _u: True)

    assert cw._universe_to_serve(configured) == starving


def test_no_work_anywhere_stays_on_the_configured_universe(
    tmp_path,
    monkeypatch,
):
    """Idle everywhere must not make the worker wander."""
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
    configured = tmp_path / "universe-a"
    configured.mkdir(parents=True, exist_ok=True)
    (tmp_path / "universe-b").mkdir(parents=True, exist_ok=True)

    assert cw._universe_to_serve(configured) == configured


def test_the_supervisor_spawns_against_the_universe_it_selected(
    tmp_path,
    monkeypatch,
):
    """Spawn, beat, and pump must share ONE universe per iteration.

    Advertising capacity for a universe while the child drains a different
    one makes a stalled row look claimable to a worker that will never work
    it -- a visible stall traded for an invisible one.
    """
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
    configured = tmp_path / "universe-a"
    configured.mkdir(parents=True, exist_ok=True)
    starving = tmp_path / "universe-b"
    starving.mkdir(parents=True, exist_ok=True)
    _commit_epoch2_worker_task(tmp_path, universe_id="universe-b")
    monkeypatch.setattr(cw, "_worker_runtime_already_bound", lambda _u: True)

    spawned: list[Path] = []

    class _Proc:
        pid = 4321
        returncode = 0

        def poll(self):
            return 0

    def _spawn(universe: Path):
        spawned.append(universe)
        return _Proc()

    monkeypatch.setattr(cw, "threading_is_main", lambda: False)
    cw.run_supervisor(
        configured,
        max_iterations=1,
        idle_backoff=0,
        spawn_fn=_spawn,
        sleep_fn=lambda _s: None,
    )

    assert spawned == [starving]
    # The beat that advertises this iteration's capacity lands in the SAME
    # universe the child was spawned against.
    assert list(starving.glob(".worker_supervisor*.json"))
    assert not list(configured.glob(".worker_supervisor*.json"))


def test_a_universe_with_no_bound_worker_runtime_is_never_served(
    tmp_path,
    monkeypatch,
):
    """The authority gate: pending rows alone must not move a worker.

    A maintainer-credentialled worker that wandered into any universe with
    pending rows would be the ambient-credential identity leak, not a
    scheduling improvement. Only a universe the platform ALREADY registered a
    worker runtime for may take the worker.
    """
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
    configured = tmp_path / "universe-a"
    configured.mkdir(parents=True, exist_ok=True)
    (tmp_path / "universe-b").mkdir(parents=True, exist_ok=True)

    # universe-b has admissible work but no bound worker runtime.
    _commit_epoch2_worker_task(tmp_path, universe_id="universe-b")

    assert cw._worker_runtime_already_bound(tmp_path / "universe-b") is False
    assert cw._universe_to_serve(configured) == configured
