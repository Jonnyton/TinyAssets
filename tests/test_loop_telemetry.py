"""Tests for the 2026-06-10 loop-telemetry slice.

Covers:
  - branch_tasks.reclaim_expired_leases (lease-aware reaper, BUG-011 Phase C)
  - cloud_worker supervisor heartbeat file
  - cloud_worker_healthcheck.check decision logic
  - api.universe._worker_liveness beat interpretation
  - last_activity_canary worker_liveness preference
  - ProviderRouter._call_meta shape + call_with_policy 3-tuple
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from workflow.branch_tasks import (
    BranchTask,
    append_task,
    claim_task,
    new_task_id,
    read_queue,
    reclaim_expired_leases,
)
from workflow.cloud_worker import (
    SUPERVISOR_HEARTBEAT_FILENAME,
    SupervisorState,
    run_supervisor,
    write_supervisor_heartbeat,
)
from workflow.cloud_worker_healthcheck import check as healthcheck_check


def _utc(offset_s: float = 0.0) -> datetime:
    return datetime.now(timezone.utc) + timedelta(seconds=offset_s)


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _make_task(universe: Path) -> BranchTask:
    task = BranchTask(
        branch_task_id=new_task_id(),
        branch_def_id="def-telemetry-test",
        universe_id="u-telemetry-test",
        trigger_source="owner_queued",
    )
    append_task(universe, task)
    return task


# ---------------------------------------------------------------------------
# reclaim_expired_leases
# ---------------------------------------------------------------------------


def test_reclaim_resets_expired_lease(tmp_path):
    task = _make_task(tmp_path)
    claimed = claim_task(tmp_path, task.branch_task_id, "daemon::test::1")
    assert claimed is not None

    future = _utc(offset_s=10_000)
    count = reclaim_expired_leases(tmp_path, now=future)
    assert count == 1
    rows = {t.branch_task_id: t for t in read_queue(tmp_path)}
    row = rows[task.branch_task_id]
    assert row.status == "pending"
    assert row.claimed_by == ""
    assert row.lease_expires_at == ""


def test_reclaim_leaves_fresh_lease_alone(tmp_path):
    task = _make_task(tmp_path)
    claimed = claim_task(tmp_path, task.branch_task_id, "daemon::test::1")
    assert claimed is not None

    count = reclaim_expired_leases(tmp_path)
    assert count == 0
    rows = {t.branch_task_id: t for t in read_queue(tmp_path)}
    assert rows[task.branch_task_id].status == "running"


def test_reclaim_skips_leaseless_running_rows(tmp_path):
    # Pre-lease-era claim: running but no lease stamp. The reaper must
    # not guess — startup recovery owns that case.
    task = _make_task(tmp_path)
    claimed = claim_task(tmp_path, task.branch_task_id, "daemon::test::1")
    assert claimed is not None
    from workflow.branch_tasks import _read_raw, _write_raw, queue_path

    qp = queue_path(tmp_path)
    raw = _read_raw(qp)
    for row in raw:
        row["lease_expires_at"] = ""
    _write_raw(qp, raw)

    count = reclaim_expired_leases(tmp_path, now=_utc(offset_s=10_000))
    assert count == 0


def test_reclaim_ignores_pending_rows(tmp_path):
    _make_task(tmp_path)
    assert reclaim_expired_leases(tmp_path, now=_utc(offset_s=10_000)) == 0


# ---------------------------------------------------------------------------
# supervisor heartbeat
# ---------------------------------------------------------------------------


def test_write_supervisor_heartbeat_atomic_shape(tmp_path):
    state = SupervisorState()
    state.record_exit(0)
    write_supervisor_heartbeat(
        tmp_path, state, iteration=3, phase="backoff", planned_sleep_s=42.0,
    )
    beat = json.loads(
        (tmp_path / SUPERVISOR_HEARTBEAT_FILENAME).read_text(encoding="utf-8")
    )
    assert beat["phase"] == "backoff"
    assert beat["iteration"] == 3
    assert beat["total_spawns"] == 1
    assert beat["planned_sleep_s"] == 42.0
    assert beat["last_exit_rc"] == 0
    assert not (tmp_path / (SUPERVISOR_HEARTBEAT_FILENAME + ".tmp")).exists()


class _FakeProc:
    pid = 4242

    def __init__(self) -> None:
        self._polls = 0

    def poll(self):
        self._polls += 1
        return 0 if self._polls >= 2 else None

    def terminate(self):  # pragma: no cover - stop-signal path
        pass

    def wait(self, timeout=None):  # pragma: no cover - stop-signal path
        return 0


def test_run_supervisor_writes_heartbeats(tmp_path):
    run_supervisor(
        tmp_path,
        max_iterations=1,
        spawn_fn=lambda universe: _FakeProc(),
        sleep_fn=lambda s: None,
        producer_poll_interval=0,
    )
    beat = json.loads(
        (tmp_path / SUPERVISOR_HEARTBEAT_FILENAME).read_text(encoding="utf-8")
    )
    assert beat["phase"] == "stopped"
    assert beat["total_spawns"] == 1
    assert beat["last_exit_rc"] == 0


# ---------------------------------------------------------------------------
# healthcheck decision logic
# ---------------------------------------------------------------------------


def _write_beat(universe: Path, *, age_s: float, phase: str = "polling",
                planned_sleep_s: float = 0.0) -> None:
    beat = {
        "ts": _iso(_utc(-age_s)),
        "phase": phase,
        "planned_sleep_s": planned_sleep_s,
    }
    (universe / SUPERVISOR_HEARTBEAT_FILENAME).write_text(
        json.dumps(beat), encoding="utf-8",
    )


def test_healthcheck_fails_without_beat(tmp_path):
    healthy, reason = healthcheck_check(tmp_path)
    assert not healthy
    assert "no supervisor heartbeat" in reason


def test_healthcheck_passes_on_fresh_beat(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "workflow.cloud_worker._has_pickable_branch_task", lambda u: False,
    )
    _write_beat(tmp_path, age_s=10)
    healthy, reason = healthcheck_check(tmp_path)
    assert healthy, reason


def test_healthcheck_fails_on_stale_beat(tmp_path):
    _write_beat(tmp_path, age_s=600)
    healthy, reason = healthcheck_check(tmp_path)
    assert not healthy
    assert "stale" in reason


def test_healthcheck_honors_planned_backoff_sleep(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "workflow.cloud_worker._has_pickable_branch_task", lambda u: False,
    )
    _write_beat(tmp_path, age_s=600, phase="backoff", planned_sleep_s=900)
    healthy, reason = healthcheck_check(tmp_path)
    assert healthy, reason


def test_healthcheck_fails_when_pickable_waits_through_backoff(
    tmp_path, monkeypatch,
):
    # Work arrived while the supervisor sleeps a long idle backoff: the
    # beat is within its planned-sleep allowance but pickable work is
    # waiting — unhealthy, restart picks it up.
    monkeypatch.setattr(
        "workflow.cloud_worker._has_pickable_branch_task", lambda u: True,
    )
    _write_beat(tmp_path, age_s=600, phase="backoff", planned_sleep_s=900)
    healthy, reason = healthcheck_check(tmp_path)
    assert not healthy
    assert "pickable" in reason


# ---------------------------------------------------------------------------
# universe inspect worker_liveness
# ---------------------------------------------------------------------------


def test_worker_liveness_absent(tmp_path):
    from workflow.api.universe import _worker_liveness

    assert _worker_liveness(tmp_path) == {"present": False}


def test_worker_liveness_alive_and_dead(tmp_path):
    from workflow.api.universe import _worker_liveness

    _write_beat(tmp_path, age_s=10)
    live = _worker_liveness(tmp_path)
    assert live["present"] and live["alive"]

    _write_beat(tmp_path, age_s=3600)
    dead = _worker_liveness(tmp_path)
    assert dead["present"] and not dead["alive"]
    assert dead["beat_age_s"] > 3000


# ---------------------------------------------------------------------------
# canary worker_liveness preference
# ---------------------------------------------------------------------------


def _canary(daemon: dict) -> tuple[int, str]:
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
    import last_activity_canary as canary

    def fake_post(url, sid, payload, timeout, step_code=0):
        if payload and payload.get("method") == "tools/call":
            return {
                "result": {
                    "structuredContent": {
                        "universe_id": "u-test",
                        "daemon": daemon,
                    },
                },
            }, "session-1"
        return {"result": {}}, "session-1"

    return canary.run_canary(
        "http://test/mcp", 5.0, 30, post_fn=fake_post,
    )


def test_canary_pages_on_dead_worker():
    code, msg = _canary({
        "staleness": "fresh",
        "is_paused": False,
        "has_work": True,
        "last_activity_at": _iso(_utc(-60)),
        "worker_liveness": {
            "present": True, "alive": False, "beat_age_s": 9999.0,
            "phase": "polling", "consec_crashes": 0,
        },
    })
    assert code == 2
    assert "worker_wedged" in msg


def test_canary_quiet_on_alive_worker_with_no_work():
    code, msg = _canary({
        "staleness": "dormant",
        "is_paused": False,
        "has_work": False,
        "last_activity_at": _iso(_utc(-90_000)),
        "worker_liveness": {
            "present": True, "alive": True, "beat_age_s": 12.0,
            "phase": "backoff", "consec_crashes": 0,
        },
    })
    assert code == 0
    assert "worker alive" in msg


def test_canary_falls_through_when_alive_with_work():
    code, _msg = _canary({
        "staleness": "dormant",
        "is_paused": False,
        "has_work": True,
        "last_activity_at": _iso(_utc(-90_000)),
        "worker_liveness": {
            "present": True, "alive": True, "beat_age_s": 12.0,
            "phase": "polling", "consec_crashes": 0,
        },
    })
    assert code == 2  # stale activity with live worker + work = real problem


# ---------------------------------------------------------------------------
# router call meta
# ---------------------------------------------------------------------------


def test_call_meta_shape():
    from workflow.providers.base import ProviderResponse
    from workflow.providers.router import ProviderRouter

    resp = ProviderResponse(
        text="hi", provider="codex", model="gpt-5.1-codex",
        family="openai", latency_ms=812,
    )
    meta = ProviderRouter._call_meta(resp, attempts=2)
    assert meta == {
        "model": "gpt-5.1-codex",
        "family": "openai",
        "latency_ms": 812,
        "degraded": False,
        "attempts": 2,
    }


@pytest.mark.asyncio
async def test_call_with_policy_returns_meta_triple():
    from workflow.providers.base import ProviderResponse
    from workflow.providers.router import ProviderRouter

    class _Prov:
        name = "fake"

        async def complete(self, prompt, system, cfg):
            return ProviderResponse(
                text="out", provider="fake", model="fake-1",
                family="test", latency_ms=5,
            )

    router = ProviderRouter()
    router._providers = {"fake": _Prov()}
    router._role_chains = {"writer": ["fake"]}

    text, name, meta = await router.call_with_policy(
        "writer", "p", "s", {"preferred": {"provider": "fake"}},
    )
    assert text == "out"
    assert name == "fake"
    assert meta["model"] == "fake-1"
    assert meta["attempts"] == 1
