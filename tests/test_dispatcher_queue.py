"""Tier-aware DaemonController and BranchTask queue tests.

Covers docs/specs/phase_e_preflight.md §4.4:

- Queue plumbing (8 tests)
- Dispatcher scoring (6 tests)
- Submission integration (7 tests)
- DaemonController integration (6 tests, flag-matrix parameterized)
- Restart recovery + GC (4 tests)
- Invariants 1/2/3 (3 tests)
- MCP surface (4 tests)

Total: ~38 tests.

All tests are disk-backed via ``tmp_path`` — file-lock primitives are
first introduction in this codebase and require integration, not mock,
coverage.
"""

from __future__ import annotations

import json
import os
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from tinyassets import branch_tasks as bt_mod
from tinyassets.branch_tasks import (
    ARCHIVE_FILENAME,
    QUEUE_FILENAME,
    BranchTask,
    append_task,
    archive_path,
    claim_task,
    garbage_collect,
    mark_status,
    new_task_id,
    queue_path,
    read_queue,
    recover_claimed_tasks,
)
from tinyassets.dispatcher import (
    DispatcherConfig,
    dispatcher_enabled,
    load_dispatcher_config,
    score_task,
    select_next_task,
    soul_guided_dispatch_read,
)

# ───────────────────────────────────────────────────────────────────────
# Fixtures
# ───────────────────────────────────────────────────────────────────────


@pytest.fixture
def universe_dir(tmp_path: Path) -> Path:
    """A fresh universe directory per test."""
    udir = tmp_path / "test-universe"
    udir.mkdir(parents=True, exist_ok=True)
    return udir


def _make_task(
    *,
    trigger_source: str = "user_request",
    priority_weight: float = 0.0,
    status: str = "pending",
    queued_at: str | None = None,
    branch_task_id: str | None = None,
    universe_id: str = "test-universe",
    **extra,
) -> BranchTask:
    return BranchTask(
        branch_task_id=branch_task_id or new_task_id(),
        branch_def_id="fantasy_author:universe_cycle_wrapper",
        universe_id=universe_id,
        inputs=extra.get("inputs", {}),
        trigger_source=trigger_source,
        priority_weight=priority_weight,
        queued_at=queued_at or datetime.now(timezone.utc).isoformat(),
        status=status,
        claimed_by=extra.get("claimed_by", ""),
    )


# ───────────────────────────────────────────────────────────────────────
# Queue plumbing (8 tests)
# ───────────────────────────────────────────────────────────────────────


def test_branch_task_roundtrip_dict():
    t = _make_task()
    d = t.to_dict()
    t2 = BranchTask.from_dict(d)
    assert t2 == t


def test_read_queue_missing_file_returns_empty(universe_dir):
    assert read_queue(universe_dir) == []


def test_read_queue_corrupt_json_raises(universe_dir):
    qp = queue_path(universe_dir)
    qp.write_text("not json at all", encoding="utf-8")
    with pytest.raises(RuntimeError, match="Corrupt"):
        read_queue(universe_dir)


def test_append_task_preserves_ordering(universe_dir):
    t1 = _make_task()
    time.sleep(0.002)
    t2 = _make_task()
    append_task(universe_dir, t1)
    append_task(universe_dir, t2)
    q = read_queue(universe_dir)
    assert [t.branch_task_id for t in q] == [t1.branch_task_id, t2.branch_task_id]


def test_claim_task_idempotent(universe_dir):
    t = _make_task()
    append_task(universe_dir, t)
    first = claim_task(universe_dir, t.branch_task_id, "daemon-1")
    assert first is not None
    assert first.status == "running"
    assert first.claimed_by == "daemon-1"
    second = claim_task(universe_dir, t.branch_task_id, "daemon-2")
    assert second is None


def test_mark_status_valid_transitions(universe_dir):
    t = _make_task()
    append_task(universe_dir, t)
    claim_task(universe_dir, t.branch_task_id, "d1")
    mark_status(universe_dir, t.branch_task_id, status="succeeded")
    q = read_queue(universe_dir)
    assert q[0].status == "succeeded"


def test_mark_status_invalid_transition_raises(universe_dir):
    t = _make_task()
    append_task(universe_dir, t)
    # pending -> succeeded is not in valid transitions
    with pytest.raises(ValueError, match="Invalid transition"):
        mark_status(universe_dir, t.branch_task_id, status="succeeded")


def test_file_lock_race(universe_dir):
    """5 threads × 20 mixed ops, no lost entries, no duplicate claims."""
    ids = [f"bt_race_{i}" for i in range(100)]
    for tid in ids:
        append_task(universe_dir, _make_task(branch_task_id=tid))

    claimed: list[str] = []
    claimed_lock = threading.Lock()
    errors: list[Exception] = []

    def worker(start: int):
        try:
            for i in range(20):
                tid = ids[(start * 20 + i) % 100]
                got = claim_task(universe_dir, tid, f"w-{start}")
                if got is not None:
                    with claimed_lock:
                        claimed.append(got.branch_task_id)
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == []
    assert len(claimed) == len(set(claimed))  # no duplicate claims
    q = read_queue(universe_dir)
    assert len(q) == 100  # no lost entries
    running = sum(1 for t in q if t.status == "running")
    assert running == len(claimed)


# ───────────────────────────────────────────────────────────────────────
# Dispatcher scoring (6 tests)
# ───────────────────────────────────────────────────────────────────────


def test_tier_weight_dominates_user_boost():
    cfg = DispatcherConfig()
    now = datetime.now(timezone.utc).isoformat()
    host = _make_task(trigger_source="host_request", priority_weight=0.0,
                      queued_at=now)
    user = _make_task(trigger_source="user_request", priority_weight=20.0,
                      queued_at=now)
    assert score_task(host, now_iso=now, config=cfg) > score_task(
        user, now_iso=now, config=cfg,
    )


def test_recency_decay_within_tier():
    cfg = DispatcherConfig()
    now_dt = datetime.now(timezone.utc)
    now = now_dt.isoformat()
    fresh = _make_task(trigger_source="user_request", queued_at=now)
    stale_dt = now_dt - timedelta(days=5)
    stale = _make_task(trigger_source="user_request",
                       queued_at=stale_dt.isoformat())
    assert score_task(fresh, now_iso=now, config=cfg) > score_task(
        stale, now_iso=now, config=cfg,
    )


def test_user_boost_within_tier():
    cfg = DispatcherConfig()
    now = datetime.now(timezone.utc).isoformat()
    lo = _make_task(trigger_source="user_request", priority_weight=0.0,
                    queued_at=now)
    hi = _make_task(trigger_source="user_request", priority_weight=5.0,
                    queued_at=now)
    assert score_task(hi, now_iso=now, config=cfg) > score_task(
        lo, now_iso=now, config=cfg,
    )


def test_deferred_coefficients_zero_until_paid_market_enabled():
    cfg = DispatcherConfig()
    now = datetime.now(timezone.utc).isoformat()
    t_lo = _make_task(trigger_source="user_request", queued_at=now)
    t_hi = BranchTask(
        branch_task_id=new_task_id(),
        branch_def_id="x", universe_id="u",
        trigger_source="user_request", queued_at=now, bid=1000.0,
    )
    # Same tier + same queued_at + no user boost => same score.
    assert score_task(t_lo, now_iso=now, config=cfg) == score_task(
        t_hi, now_iso=now, config=cfg,
    )


def test_dispatcher_determinism(universe_dir):
    cfg = DispatcherConfig()
    append_task(universe_dir, _make_task(trigger_source="host_request"))
    append_task(universe_dir, _make_task(trigger_source="user_request"))
    append_task(universe_dir, _make_task(trigger_source="owner_queued"))
    fixed = datetime.now(timezone.utc).isoformat()
    a = select_next_task(universe_dir, config=cfg, now_iso=fixed)
    b = select_next_task(universe_dir, config=cfg, now_iso=fixed)
    assert a is not None and b is not None
    assert a.branch_task_id == b.branch_task_id


def test_select_next_empty_queue_returns_none(universe_dir):
    cfg = DispatcherConfig()
    assert select_next_task(universe_dir, config=cfg) is None


def test_select_next_skips_tasks_directed_to_other_daemon(tmp_path):
    from tinyassets import daemon_registry

    universe = tmp_path / "test-universe"
    universe.mkdir()
    mine = daemon_registry.create_daemon(
        tmp_path,
        display_name="My Patch Daemon",
        created_by="host",
        soul_text="Prefer TinyAssets patch requests.",
    )
    other = daemon_registry.create_daemon(
        tmp_path,
        display_name="Other Patch Daemon",
        created_by="host",
        soul_text="Prefer unrelated patch requests.",
    )
    now = datetime.now(timezone.utc).isoformat()
    directed_elsewhere = BranchTask(
        branch_task_id="bt-directed-other",
        branch_def_id="fantasy_author:universe_cycle_wrapper",
        universe_id="test-universe",
        trigger_source="owner_queued",
        queued_at=now,
        directed_daemon_id=other["daemon_id"],
    )
    open_task = BranchTask(
        branch_task_id="bt-open",
        branch_def_id="fantasy_author:universe_cycle_wrapper",
        universe_id="test-universe",
        trigger_source="user_request",
        queued_at=now,
    )
    append_task(universe, directed_elsewhere)
    append_task(universe, open_task)

    selected = select_next_task(
        universe,
        config=DispatcherConfig(active_daemon_id=mine["daemon_id"]),
        now_iso=now,
    )

    assert selected is not None
    assert selected.branch_task_id == "bt-open"


def test_soul_guided_dispatch_read_boosts_matching_open_brain_task(tmp_path):
    from tinyassets import daemon_registry
    from tinyassets.daemon_brain import capture_daemon_memory

    universe = tmp_path / "test-universe"
    universe.mkdir()
    daemon = daemon_registry.create_daemon(
        tmp_path,
        display_name="TinyAssets Dispatch Daemon",
        created_by="host",
        soul_text="Prefer TinyAssets dispatch and verified patch work.",
        domain_claims=["workflow-platform"],
    )
    memory = capture_daemon_memory(
        tmp_path,
        daemon_id=daemon["daemon_id"],
        memory_kind="preference",
        content="Prefer workflow-platform dispatch patches with narrow tests.",
        source_type="manual",
        source_id="pytest",
        reliability="host_observed",
        language_type="policy",
        importance=0.9,
        visibility="published",
        promotion_state="accepted",
    )
    matching = BranchTask(
        branch_task_id="bt-workflow",
        branch_def_id="fantasy_author:universe_cycle_wrapper",
        universe_id="test-universe",
        inputs={"text": "Fix workflow-platform dispatch scoring."},
        trigger_source="user_request",
        queued_at="2026-05-17T00:00:00+00:00",
    )
    unrelated = BranchTask(
        branch_task_id="bt-other",
        branch_def_id="fantasy_author:universe_cycle_wrapper",
        universe_id="test-universe",
        inputs={"text": "Write a recipe tracker note."},
        trigger_source="user_request",
        queued_at="2026-05-17T00:00:00+00:00",
    )
    append_task(universe, unrelated)
    append_task(universe, matching)

    guidance = soul_guided_dispatch_read(
        universe,
        task=matching,
        active_daemon_id=daemon["daemon_id"],
        coefficient=1.0,
    )
    selected = select_next_task(
        universe,
        config=DispatcherConfig(
            active_daemon_id=daemon["daemon_id"],
            soul_affinity_coefficient=1.0,
        ),
        now_iso="2026-05-17T00:00:00+00:00",
    )

    assert guidance["read_only"] is True
    assert guidance["domain_claim_hits"] == ["workflow-platform"]
    assert guidance["brain_entry_ids"] == [memory["entry_id"]]
    assert guidance["score_adjustment"] > 0
    assert selected is not None
    assert selected.branch_task_id == "bt-workflow"


# ───────────────────────────────────────────────────────────────────────
# Submission integration (7 tests)
# ───────────────────────────────────────────────────────────────────────


@pytest.fixture
def server_base(tmp_path: Path, monkeypatch):
    """Point TINYASSETS_DATA_DIR at a fresh tmp dir with one universe."""
    base = tmp_path / "output"
    base.mkdir()
    uid = "test-uni"
    (base / uid).mkdir()
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(base))
    monkeypatch.setenv("UNIVERSE_SERVER_DEFAULT_UNIVERSE", uid)
    return base, uid


def _call_submit(**kwargs):
    from tinyassets.api.universe import _action_submit_request

    return json.loads(_action_submit_request(**kwargs))


def test_submit_request_as_host_queues_host_request_branch_task(
    server_base, monkeypatch,
):
    _, uid = server_base
    monkeypatch.setenv("UNIVERSE_SERVER_USER", "host")
    monkeypatch.setenv("UNIVERSE_SERVER_HOST_USER", "host")
    resp = _call_submit(universe_id=uid, text="do a scene")
    assert "branch_task_id" in resp and resp["branch_task_id"]
    q = read_queue(Path(os.environ["TINYASSETS_DATA_DIR"]) / uid)
    assert len(q) == 1
    assert q[0].trigger_source == "host_request"


def test_submit_request_as_non_host_queues_user_request(
    server_base, monkeypatch,
):
    _, uid = server_base
    monkeypatch.setenv("UNIVERSE_SERVER_USER", "alice")
    monkeypatch.setenv("UNIVERSE_SERVER_HOST_USER", "host")
    resp = _call_submit(universe_id=uid, text="please write")
    assert resp["branch_task_id"]
    q = read_queue(Path(os.environ["TINYASSETS_DATA_DIR"]) / uid)
    assert q[0].trigger_source == "user_request"


def test_submit_creates_both_request_and_branch_task(server_base, monkeypatch):
    _, uid = server_base
    monkeypatch.setenv("UNIVERSE_SERVER_USER", "alice")
    _call_submit(universe_id=uid, text="do a scene")
    udir = Path(os.environ["TINYASSETS_DATA_DIR"]) / uid
    # requests.json populated
    from tinyassets.work_targets import REQUESTS_FILENAME
    reqs = json.loads((udir / REQUESTS_FILENAME).read_text(encoding="utf-8"))
    assert len(reqs) == 1
    # branch_tasks.json populated
    assert len(read_queue(udir)) == 1


def test_submit_8kib_cap_still_enforced(server_base, monkeypatch):
    _, uid = server_base
    monkeypatch.setenv("UNIVERSE_SERVER_USER", "alice")
    huge = "x" * (8 * 1024 + 1)
    resp = _call_submit(universe_id=uid, text=huge)
    assert "error" in resp


def test_submit_host_priority_weight_persists(server_base, monkeypatch):
    _, uid = server_base
    monkeypatch.setenv("UNIVERSE_SERVER_USER", "host")
    monkeypatch.setenv("UNIVERSE_SERVER_HOST_USER", "host")
    _call_submit(universe_id=uid, text="boosted", priority_weight=50.0)
    q = read_queue(Path(os.environ["TINYASSETS_DATA_DIR"]) / uid)
    assert q[0].priority_weight == 50.0


def test_submit_non_host_priority_weight_clamped(server_base, monkeypatch):
    _, uid = server_base
    monkeypatch.setenv("UNIVERSE_SERVER_USER", "alice")
    monkeypatch.setenv("UNIVERSE_SERVER_HOST_USER", "host")
    resp = _call_submit(universe_id=uid, text="sneaky", priority_weight=50.0)
    assert "error" not in resp
    q = read_queue(Path(os.environ["TINYASSETS_DATA_DIR"]) / uid)
    assert q[0].priority_weight == 0.0


def test_submit_negative_priority_weight_rejected(server_base, monkeypatch):
    _, uid = server_base
    monkeypatch.setenv("UNIVERSE_SERVER_USER", "host")
    monkeypatch.setenv("UNIVERSE_SERVER_HOST_USER", "host")
    resp = _call_submit(universe_id=uid, text="bad", priority_weight=-10.0)
    assert "error" in resp
    q = read_queue(Path(os.environ["TINYASSETS_DATA_DIR"]) / uid)
    assert q == []


# ───────────────────────────────────────────────────────────────────────
# DaemonController integration (6 tests)
# ───────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("unified_execution,dispatcher_enabled", [
    ("off", "off"), ("off", "on"), ("on", "off"), ("on", "on"),
])
def test_dispatcher_flag_matrix_observational_safe(
    universe_dir, monkeypatch, unified_execution, dispatcher_enabled,
):
    """Flag matrix: under ANY cell, _dispatcher_startup + _dispatcher_observe
    must not raise and must not alter the queue file.

    Observational means: no side effects on branch_tasks.json beyond the
    startup-recovery + GC already permitted by invariants 7 + 10.
    """
    from fantasy_daemon.__main__ import _dispatcher_observe, _dispatcher_startup

    monkeypatch.setenv(
        "TINYASSETS_UNIFIED_EXECUTION", "1" if unified_execution == "on" else "0",
    )
    monkeypatch.setenv(
        "TINYASSETS_DISPATCHER_ENABLED", "on" if dispatcher_enabled == "on" else "off",
    )
    # Seed the queue with a pending task; call the startup + observe
    # hooks. Queue should be unchanged (pending stays pending).
    append_task(universe_dir, _make_task())
    before = read_queue(universe_dir)
    _dispatcher_startup(universe_dir)
    _dispatcher_observe(universe_dir)
    after = read_queue(universe_dir)
    assert [t.branch_task_id for t in before] == [t.branch_task_id for t in after]
    assert all(t.status == "pending" for t in after)


def test_dispatcher_flag_off_returns_no_observation_logs(
    universe_dir, monkeypatch, caplog,
):
    """Dispatcher flag off means dispatcher_observe silently skips."""
    from fantasy_daemon.__main__ import _dispatcher_observe

    monkeypatch.setenv("TINYASSETS_DISPATCHER_ENABLED", "off")
    append_task(universe_dir, _make_task(trigger_source="host_request"))
    import logging as _logging
    caplog.set_level(_logging.INFO)
    _dispatcher_observe(universe_dir)
    # Nothing observational should have been logged.
    assert not any(
        "dispatcher_observational" in record.message
        for record in caplog.records
    )


def test_dispatcher_enabled_flag_defaults_on(monkeypatch):
    monkeypatch.delenv("TINYASSETS_DISPATCHER_ENABLED", raising=False)
    assert dispatcher_enabled() is True


def test_dispatcher_enabled_flag_off_respected(monkeypatch):
    for val in ("off", "0", "false", "no"):
        monkeypatch.setenv("TINYASSETS_DISPATCHER_ENABLED", val)
        assert dispatcher_enabled() is False


def test_empty_queue_fallback_dispatcher_returns_none(universe_dir):
    """R7 fallback: empty queue => dispatcher returns None, daemon
    falls back to existing graph behavior."""
    cfg = DispatcherConfig()
    assert select_next_task(universe_dir, config=cfg) is None


def test_dispatcher_observe_does_not_raise_on_corrupt_queue(
    universe_dir, monkeypatch, caplog,
):
    """Observational path must NOT crash the daemon even if the
    queue file is corrupt — it logs and moves on."""
    from fantasy_daemon.__main__ import _dispatcher_observe

    monkeypatch.setenv("TINYASSETS_DISPATCHER_ENABLED", "on")
    queue_path(universe_dir).write_text("{not json", encoding="utf-8")
    # Should not raise — observe swallows.
    _dispatcher_observe(universe_dir)


# ───────────────────────────────────────────────────────────────────────
# Restart recovery + GC (4 tests)
# ───────────────────────────────────────────────────────────────────────


def test_recover_claimed_tasks_resets_running_to_pending(universe_dir):
    pending = _make_task(status="pending")
    running = _make_task(status="running")
    running.claimed_by = "dead-daemon"
    append_task(universe_dir, pending)
    # Directly write running task (append_task requires pending)
    qp = queue_path(universe_dir)
    raw = json.loads(qp.read_text(encoding="utf-8"))
    raw.append(running.to_dict())
    qp.write_text(json.dumps(raw), encoding="utf-8")

    count = recover_claimed_tasks(universe_dir)
    assert count == 1
    q = read_queue(universe_dir)
    assert all(t.status == "pending" for t in q)
    running_recovered = next(
        t for t in q if t.branch_task_id == running.branch_task_id
    )
    assert running_recovered.claimed_by == ""


def test_branch_tasks_json_survives_controller_lifecycle(universe_dir):
    """Persistent across process boundaries — append, reread is the
    lifecycle proxy here (real DaemonController tested via integration)."""
    ids = []
    for _ in range(3):
        t = _make_task()
        append_task(universe_dir, t)
        ids.append(t.branch_task_id)
    # Second "process": fresh read.
    q = read_queue(universe_dir)
    assert [t.branch_task_id for t in q] == ids


def test_gc_archives_old_terminal_tasks(universe_dir):
    old = datetime.now(timezone.utc) - timedelta(days=60)
    new = datetime.now(timezone.utc)
    # 3 old-succeeded, 2 old-pending, 1 new-succeeded
    old_done = [
        _make_task(status="pending", queued_at=old.isoformat())
        for _ in range(3)
    ]
    old_pending = [
        _make_task(status="pending", queued_at=old.isoformat())
        for _ in range(2)
    ]
    new_done = _make_task(status="pending", queued_at=new.isoformat())

    for t in old_done + old_pending + [new_done]:
        append_task(universe_dir, t)
    # Flip the "old_done" ones to succeeded directly.
    qp = queue_path(universe_dir)
    raw = json.loads(qp.read_text(encoding="utf-8"))
    done_ids = {t.branch_task_id for t in old_done}
    new_ids = {new_done.branch_task_id}
    for row in raw:
        if row["branch_task_id"] in done_ids:
            row["status"] = "succeeded"
        if row["branch_task_id"] in new_ids:
            row["status"] = "succeeded"
    qp.write_text(json.dumps(raw), encoding="utf-8")

    result = garbage_collect(universe_dir)
    assert result["archived"] == 3
    q = read_queue(universe_dir)
    remaining_ids = {t.branch_task_id for t in q}
    # Old pending kept + new succeeded kept
    assert remaining_ids == (
        {t.branch_task_id for t in old_pending} | new_ids
    )
    # Archive file populated
    ap = archive_path(universe_dir)
    assert ap.exists()
    arch = json.loads(ap.read_text(encoding="utf-8"))
    assert len(arch) == 3


def test_gc_preserves_pending_and_running_regardless_of_age(universe_dir):
    old = datetime.now(timezone.utc) - timedelta(days=90)
    pending = _make_task(status="pending", queued_at=old.isoformat())
    append_task(universe_dir, pending)
    # Inject running status directly
    qp = queue_path(universe_dir)
    raw = json.loads(qp.read_text(encoding="utf-8"))
    running = _make_task(
        status="running", queued_at=old.isoformat(),
    ).to_dict()
    raw.append(running)
    qp.write_text(json.dumps(raw), encoding="utf-8")

    garbage_collect(universe_dir)
    q = read_queue(universe_dir)
    assert len(q) == 2  # both survive
    assert {t.status for t in q} == {"pending", "running"}


# ───────────────────────────────────────────────────────────────────────
# Invariants (3 tests)
# ───────────────────────────────────────────────────────────────────────


def test_invariant_2_cancel_branch_task_preserves_work_target(
    server_base, monkeypatch,
):
    """WorkTarget (in requests.json) persists even when its BranchTask
    is cancelled. Invariant §4.3 #2."""
    from tinyassets.api.universe import _action_queue_cancel
    from tinyassets.work_targets import REQUESTS_FILENAME

    _, uid = server_base
    monkeypatch.setenv("UNIVERSE_SERVER_USER", "alice")
    _call_submit(universe_id=uid, text="keep this")
    udir = Path(os.environ["TINYASSETS_DATA_DIR"]) / uid
    q_before = read_queue(udir)
    btid = q_before[0].branch_task_id
    resp = json.loads(
        _action_queue_cancel(universe_id=uid, branch_task_id=btid),
    )
    assert resp["status"] == "cancelled"
    # requests.json still has the entry (WorkTarget source-of-truth)
    reqs_path = udir / REQUESTS_FILENAME
    reqs = json.loads(reqs_path.read_text(encoding="utf-8"))
    assert len(reqs) == 1


def test_invariant_3_dispatcher_does_not_call_producers(
    universe_dir, monkeypatch,
):
    """R9 / Invariant §4.3 #3: producers run inside the graph's
    review gates, NEVER inside the dispatcher.

    Patch at the registry boundary — `tinyassets.producers.registered_producers()`.
    """
    from tinyassets import producers as prod_mod

    # Snapshot real registry, replace with a mock producer counter.
    calls: list[str] = []

    class _CountingProducer:
        name = "counting"
        origin = "seed"

        def produce(self, universe_path, *, config=None):
            calls.append("called")
            return []

    saved = list(prod_mod._REGISTRY)
    prod_mod._REGISTRY.clear()
    prod_mod._REGISTRY.append(_CountingProducer())
    try:
        append_task(universe_dir, _make_task())
        # Multiple dispatcher operations — none should trigger a
        # producer call.
        cfg = DispatcherConfig()
        for _ in range(5):
            select_next_task(universe_dir, config=cfg)
            read_queue(universe_dir)
        assert calls == []
    finally:
        prod_mod._REGISTRY.clear()
        prod_mod._REGISTRY.extend(saved)


def test_invariant_3_producer_boundary_each_called_exactly_once(
    universe_dir,
):
    """R9 / Invariant §4.3 #3 complementary axis: the producer-running
    path (``run_producers``) invokes every registered producer exactly
    once per cycle, with distinct ``id(self)`` per producer.

    Patch ``.produce`` at the registry boundary — iterate
    ``registered_producers()`` and wrap each instance's method. Same
    care as unified-execution invariant 4's ``id()``-based check: a
    registration reshuffle that replaces a producer with a different
    instance of the same name must show as a new id, and the counting
    wrapper must catch a double-call regardless.
    """
    from tinyassets import producers as prod_mod
    from tinyassets.producers import run_producers

    class _Producer:
        def __init__(self, name: str):
            self.name = name
            self.origin = "seed"

        def produce(self, universe_path, *, config=None):
            return []

    saved = list(prod_mod._REGISTRY)
    prod_mod._REGISTRY.clear()
    p1 = _Producer("alpha")
    p2 = _Producer("beta")
    p3 = _Producer("gamma")
    prod_mod._REGISTRY.extend([p1, p2, p3])
    try:
        # Patch each registered producer's `.produce` with a
        # counting wrapper that records `id(self)` on entry.
        call_ids: list[int] = []
        for producer in prod_mod.registered_producers():
            original = producer.produce

            def _wrap(orig, pid):
                def _counted(universe_path, *, config=None):
                    call_ids.append(pid)
                    return orig(universe_path, config=config)
                return _counted
            producer.produce = _wrap(original, id(producer))

        # One observational cycle.
        run_producers(universe_dir)

        registered_ids = {id(p) for p in prod_mod.registered_producers()}
        # Each registered producer ran exactly once, all distinct by id.
        assert len(call_ids) == len(registered_ids)
        assert set(call_ids) == registered_ids
        # No id appears twice (catches a double-invocation regression).
        assert len(call_ids) == len(set(call_ids))
    finally:
        prod_mod._REGISTRY.clear()
        prod_mod._REGISTRY.extend(saved)


def test_invariant_9_priority_weight_clamp_at_submission(
    server_base, monkeypatch,
):
    """Redundant with submission-integration tests above, but stated
    here as its own invariant assertion."""
    _, uid = server_base
    monkeypatch.setenv("UNIVERSE_SERVER_USER", "alice")
    monkeypatch.setenv("UNIVERSE_SERVER_HOST_USER", "host")
    _call_submit(universe_id=uid, text="anyone", priority_weight=999.0)
    q = read_queue(Path(os.environ["TINYASSETS_DATA_DIR"]) / uid)
    assert q[0].priority_weight == 0.0


# ───────────────────────────────────────────────────────────────────────
# MCP surface (4 tests)
# ───────────────────────────────────────────────────────────────────────


def test_queue_list_returns_sorted_scored_queue(server_base, monkeypatch):
    from tinyassets.api.universe import _action_queue_list

    _, uid = server_base
    monkeypatch.setenv("UNIVERSE_SERVER_USER", "alice")
    _call_submit(universe_id=uid, text="A", request_type="general")
    monkeypatch.setenv("UNIVERSE_SERVER_USER", "host")
    monkeypatch.setenv("UNIVERSE_SERVER_HOST_USER", "host")
    _call_submit(universe_id=uid, text="B", request_type="general")

    resp = json.loads(_action_queue_list(universe_id=uid))
    assert "queue" in resp
    assert len(resp["queue"]) == 2
    # host_request should be first (higher tier weight)
    assert resp["queue"][0]["trigger_source"] == "host_request"
    # scores present
    assert "score" in resp["queue"][0]
    # tier_status map present
    assert "tier_status" in resp
    assert resp["tier_status"]["host_request"] == "live"
    assert "stubbed" in resp["tier_status"]["goal_pool"]


def test_queue_cancel_on_running_task_as_host_requests_cancel(
    server_base, monkeypatch,
):
    """Task #21: host cancelling a running task triggers cooperative
    cancel (sets cancel_requested) rather than rejecting.

    Prior contract ``running_tasks_require_host_override`` retired;
    host identity is now one of two authorized actors (the other is
    the claiming daemon). See test_queue_cancel_on_running_task_unauthorized
    for the rejection path."""
    from tinyassets.api.universe import _action_queue_cancel
    from tinyassets.branch_tasks import is_task_cancel_requested

    _, uid = server_base
    monkeypatch.setenv("UNIVERSE_SERVER_USER", "host")
    monkeypatch.setenv("UNIVERSE_SERVER_HOST_USER", "host")
    _call_submit(universe_id=uid, text="A")
    udir = Path(os.environ["TINYASSETS_DATA_DIR"]) / uid
    q = read_queue(udir)
    btid = q[0].branch_task_id
    claim_task(udir, btid, "daemon-1")

    resp = json.loads(
        _action_queue_cancel(universe_id=uid, branch_task_id=btid),
    )
    assert resp["status"] == "cancel_requested"
    assert resp["branch_task_id"] == btid
    # Flag is set; status stays "running" — daemon flips it on next event.
    assert is_task_cancel_requested(udir, btid) is True
    final = next(t for t in read_queue(udir) if t.branch_task_id == btid)
    assert final.status == "running"
    assert final.cancel_requested is True


def test_queue_cancel_on_running_task_as_owner_requests_cancel(
    server_base, monkeypatch,
):
    """Task #21: the claiming daemon can self-cancel its running task."""
    from tinyassets.api.universe import _action_queue_cancel
    from tinyassets.branch_tasks import is_task_cancel_requested

    _, uid = server_base
    monkeypatch.setenv("UNIVERSE_SERVER_USER", "daemon-1")
    monkeypatch.setenv("UNIVERSE_SERVER_HOST_USER", "host")
    _call_submit(universe_id=uid, text="A")
    udir = Path(os.environ["TINYASSETS_DATA_DIR"]) / uid
    q = read_queue(udir)
    btid = q[0].branch_task_id
    claim_task(udir, btid, "daemon-1")

    resp = json.loads(
        _action_queue_cancel(universe_id=uid, branch_task_id=btid),
    )
    assert resp["status"] == "cancel_requested"
    assert is_task_cancel_requested(udir, btid) is True


def test_queue_cancel_on_running_task_unauthorized(
    server_base, monkeypatch,
):
    """Task #21: actors that are neither host nor owner get rejected.

    Carries forward the original test's intent — running tasks require
    authorization — but narrows it to the actually-unauthorized case
    instead of the now-always-host case."""
    from tinyassets.api.universe import _action_queue_cancel

    _, uid = server_base
    monkeypatch.setenv("UNIVERSE_SERVER_USER", "random-guest")
    monkeypatch.setenv("UNIVERSE_SERVER_HOST_USER", "host")
    _call_submit(universe_id=uid, text="A")
    udir = Path(os.environ["TINYASSETS_DATA_DIR"]) / uid
    q = read_queue(udir)
    btid = q[0].branch_task_id
    claim_task(udir, btid, "daemon-1")

    resp = json.loads(
        _action_queue_cancel(universe_id=uid, branch_task_id=btid),
    )
    assert resp["status"] == "rejected"
    assert resp["error"] == "cancel_not_authorized"


def test_queue_cancel_missing_id_rejects():
    from tinyassets.api.universe import _action_queue_cancel

    resp = json.loads(_action_queue_cancel(universe_id="anything"))
    assert "error" in resp


def test_tier_status_map_reflects_stubbed_vs_live():
    cfg = DispatcherConfig()
    tm = cfg.tier_status_map()
    assert tm["host_request"] == "live"
    assert tm["owner_queued"] == "live"
    assert tm["user_request"] == "live"  # default accept_external=True
    assert "stubbed" in tm["goal_pool"]
    # Paid bids moved from "stubbed" to "disabled"
    # (until accept_paid_bids is True).
    assert tm["paid_bid"] == "disabled"
    assert "stubbed" in tm["opportunistic"]

    cfg2 = DispatcherConfig(accept_external_requests=False,
                            accept_goal_pool=True)
    tm2 = cfg2.tier_status_map()
    assert tm2["user_request"] == "disabled"
    assert tm2["goal_pool"] == "live"


# ───────────────────────────────────────────────────────────────────────
# Config loading (small bonus coverage)
# ───────────────────────────────────────────────────────────────────────


def test_load_dispatcher_config_missing_file_returns_defaults(universe_dir):
    cfg = load_dispatcher_config(universe_dir)
    assert cfg.accept_external_requests is True
    assert cfg.accept_goal_pool is False


def test_load_dispatcher_config_reads_yaml_overrides(universe_dir):
    cfg_path = universe_dir / "dispatcher_config.yaml"
    cfg_path.write_text(
        "accept_external_requests: false\n"
        "accept_goal_pool: true\n"
        "tier_weights:\n"
        "  host_request: 200\n",
        encoding="utf-8",
    )
    cfg = load_dispatcher_config(universe_dir)
    assert cfg.accept_external_requests is False
    assert cfg.accept_goal_pool is True
    assert cfg.tier_weights["host_request"] == 200.0


def test_archive_after_days_override(universe_dir):
    """ARCHIVE_AFTER_DAYS override (exposed for test override per §4.3 #10)."""
    old = datetime.now(timezone.utc) - timedelta(days=2)
    t = _make_task(status="pending", queued_at=old.isoformat())
    append_task(universe_dir, t)
    qp = queue_path(universe_dir)
    raw = json.loads(qp.read_text(encoding="utf-8"))
    raw[0]["status"] = "succeeded"
    qp.write_text(json.dumps(raw), encoding="utf-8")

    # With override of 1 day, 2-day-old succeeded task is archived.
    result = garbage_collect(universe_dir, archive_after_days=1)
    assert result["archived"] == 1


def test_default_archive_constant_matches_spec():
    # Invariant 10: default 30 days.
    assert bt_mod.ARCHIVE_AFTER_DAYS == 30


def test_queue_filename_constants_match_spec():
    assert QUEUE_FILENAME == "branch_tasks.json"
    assert ARCHIVE_FILENAME == "branch_tasks_archive.json"
