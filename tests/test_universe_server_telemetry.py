"""Tests for Universe Server daemon telemetry legibility.

Covers the cluster of bugs where `inspect`, `list`, and `control_daemon
status` returned stale or misleading daemon state:
- #8 raw phase was "unknown" because status.json uses `current_phase`
  but readers looked for `phase`.
- #10 `inspect` silently omitted the premise field when PROGRAM.md was
  missing, making "no premise" indistinguishable from "premise was empty".
- #14/#16 dormant daemons reported as alive because no reader checked
  activity freshness.
- #17 `accept_rate=0.0` was read from a stale status.json field that
  nothing updates at runtime.

The fix centralizes liveness in `_daemon_liveness()` and is consumed by
list, inspect, and control_daemon status.
"""

from __future__ import annotations

import json
import os
import sqlite3
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import tinyassets.api.universe as us


@pytest.fixture
def universe_base(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    base = tmp_path / "output"
    base.mkdir()
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(base))
    return base


def _make_universe(
    base: Path, uid: str, *,
    premise: str | None = None,
    work_targets: list[dict] | None = None,
    status: dict | None = None,
    activity_age_hours: float | None = None,
    scene_history: list[tuple[str, str]] | None = None,
    paused: bool = False,
) -> Path:
    """Build a universe on disk with controllable liveness signals."""
    udir = base / uid
    udir.mkdir()
    if premise is not None:
        (udir / "PROGRAM.md").write_text(premise, encoding="utf-8")
    if work_targets is not None:
        (udir / "work_targets.json").write_text(
            json.dumps(work_targets), encoding="utf-8",
        )
    if status is not None:
        (udir / "status.json").write_text(json.dumps(status), encoding="utf-8")
    if activity_age_hours is not None:
        log = udir / "activity.log"
        log.write_text("[run] sample\n", encoding="utf-8")
        target = time.time() - activity_age_hours * 3600
        os.utime(log, (target, target))
    if paused:
        (udir / ".pause").write_text("paused", encoding="utf-8")
    if scene_history is not None:
        db = udir / "story.db"
        conn = sqlite3.connect(str(db))
        try:
            conn.execute(
                "CREATE TABLE scene_history (scene_id TEXT, verdict TEXT)"
            )
            conn.executemany(
                "INSERT INTO scene_history (scene_id, verdict) VALUES (?, ?)",
                scene_history,
            )
            conn.commit()
        finally:
            conn.close()
    # Declare the universe explicitly public: under the universe-visibility
    # contract an undeclared universe is withheld from list/inspect/status
    # (fail closed). These telemetry tests assert public-universe behavior.
    _declare_public(base, uid, udir)
    return udir


def _declare_public(base: Path, uid: str, udir: Path) -> None:
    from tinyassets.api.visibility import set_universe_visibility
    from tinyassets.daemon_server import ensure_universe_registered

    ensure_universe_registered(base, universe_id=uid, universe_path=udir)
    set_universe_visibility(uid, "public")


# ---------------------------------------------------------------------------
# Core helpers
# ---------------------------------------------------------------------------


def test_staleness_buckets_cover_fresh_idle_dormant_never() -> None:
    now = datetime.now(timezone.utc)
    fresh = (now - timedelta(minutes=30)).isoformat()
    idle = (now - timedelta(hours=6)).isoformat()
    dormant = (now - timedelta(days=3)).isoformat()

    assert us._staleness_bucket(fresh) == "fresh"
    assert us._staleness_bucket(idle) == "idle"
    assert us._staleness_bucket(dormant) == "dormant"
    assert us._staleness_bucket(None) == "never"
    assert us._staleness_bucket("not-a-timestamp") == "never"


def test_phase_human_paused_wins_over_everything() -> None:
    assert us._phase_human(
        "dispatch_execution", has_premise=True, has_work=True,
        is_paused=True, staleness="fresh",
    ) == "paused"


def test_phase_human_dormant_paths() -> None:
    assert us._phase_human(
        "dispatch_execution", has_premise=False, has_work=False,
        is_paused=False, staleness="dormant",
    ) == "dormant-no-premise"
    assert us._phase_human(
        "dispatch_execution", has_premise=True, has_work=False,
        is_paused=False, staleness="dormant",
    ) == "dormant-starved"
    assert us._phase_human(
        "dispatch_execution", has_premise=True, has_work=True,
        is_paused=False, staleness="dormant",
    ) == "dormant"


def test_phase_human_starved_paths_for_fresh_daemon() -> None:
    assert us._phase_human(
        "unknown", has_premise=False, has_work=False,
        is_paused=False, staleness="fresh",
    ) == "idle-no-premise"
    assert us._phase_human(
        "unknown", has_premise=True, has_work=False,
        is_paused=False, staleness="fresh",
    ) == "starved"


def test_phase_human_returns_raw_phase_when_running_and_ready() -> None:
    assert us._phase_human(
        "dispatch_execution", has_premise=True, has_work=True,
        is_paused=False, staleness="fresh",
    ) == "dispatch_execution"


def test_phase_human_falls_back_to_idle_when_raw_phase_blank() -> None:
    assert us._phase_human(
        "", has_premise=True, has_work=True,
        is_paused=False, staleness="fresh",
    ) == "idle"
    assert us._phase_human(
        None, has_premise=True, has_work=True,
        is_paused=False, staleness="fresh",
    ) == "idle"


def test_last_activity_prefers_activity_log_mtime(universe_base: Path) -> None:
    udir = _make_universe(
        universe_base, "u",
        status={"current_phase": "x", "last_updated": "2026-04-01T00:00:00+00:00"},
        activity_age_hours=0.5,  # 30 minutes ago
    )
    got = us._last_activity_at(udir, json.loads((udir / "status.json").read_text()))
    assert got is not None
    ts = datetime.fromisoformat(got)
    age_seconds = (datetime.now(timezone.utc) - ts).total_seconds()
    # Activity log wins over status.last_updated; should be ~30min, not 2026-04-01.
    assert age_seconds < 60 * 60


def test_last_activity_falls_back_to_status_last_updated(
    universe_base: Path,
) -> None:
    status = {"current_phase": "x", "last_updated": "2026-04-05T12:00:00+00:00"}
    udir = _make_universe(universe_base, "u", status=status)
    got = us._last_activity_at(udir, status)
    assert got == "2026-04-05T12:00:00+00:00"


def test_last_activity_uses_runtime_status_heartbeat(
    universe_base: Path,
) -> None:
    udir = _make_universe(
        universe_base, "u",
        status={"current_phase": "x", "last_updated": "2026-04-01T00:00:00+00:00"},
        activity_age_hours=2,
    )
    runtime_status = udir / ".runtime_status.json"
    runtime_status.write_text("{}", encoding="utf-8")

    got = us._last_activity_at(
        udir, json.loads((udir / "status.json").read_text()),
    )
    assert got is not None
    ts = datetime.fromisoformat(got)
    age_seconds = (datetime.now(timezone.utc) - ts).total_seconds()
    assert age_seconds < 60


def test_last_activity_returns_none_for_untouched_universe(
    universe_base: Path,
) -> None:
    udir = universe_base / "fresh"
    udir.mkdir()
    assert us._last_activity_at(udir, None) is None


# ---------------------------------------------------------------------------
# last_activity_at from the runs ledger
#
# The fleet daemon loop that wrote activity.log / .runtime_status.json /
# status.json was retired 2026-08-29 (`user-owned-automations`); automation
# and schedule runs since then are recorded only in `tinyassets.runs`, as
# rows scoped to a universe via `queue_universe_id`.
#
# The automations store is deliberately NOT a source: Codex ADAPT
# (2026-08-29) found `AutomationStore.last_finished_at` is bumped on a
# REFUSED attempt too (`finish_attempt` rolls the outcome onto the
# automation row regardless of status), so treating it as activity could
# keep the uptime canary green while every requested automation is refused.
# See `test_last_activity_ignores_refused_automation_attempt` below.
# ---------------------------------------------------------------------------


def test_last_activity_uses_run_ledger_when_newer_than_files(
    universe_base: Path,
) -> None:
    from tinyassets.runs import RUN_STATUS_COMPLETED, create_run, update_run_status

    udir = _make_universe(universe_base, "u1", activity_age_hours=48)
    run_id = create_run(
        universe_base,
        branch_def_id="b1",
        thread_id="t1",
        inputs={},
        actor="universe:u1",
        queue_universe_id="u1",
    )
    recent = time.time() - 60  # 1 minute ago -- newer than the 48h-stale file
    update_run_status(
        universe_base, run_id, status=RUN_STATUS_COMPLETED, finished_at=recent,
    )

    got = us._last_activity_at(udir, None)
    assert got is not None
    ts = datetime.fromisoformat(got)
    age_seconds = (datetime.now(timezone.utc) - ts).total_seconds()
    assert age_seconds < 120


def test_last_activity_ignores_run_for_different_universe_scope(
    universe_base: Path,
) -> None:
    from tinyassets.runs import RUN_STATUS_COMPLETED, create_run, update_run_status

    udir = _make_universe(universe_base, "u1", activity_age_hours=48)
    other_run = create_run(
        universe_base,
        branch_def_id="b1",
        thread_id="t1",
        inputs={},
        actor="universe:other-universe",
        queue_universe_id="other-universe",
    )
    update_run_status(
        universe_base, other_run,
        status=RUN_STATUS_COMPLETED, finished_at=time.time() - 60,
    )

    got = us._last_activity_at(udir, None)
    assert got is not None
    ts = datetime.fromisoformat(got)
    age_seconds = (datetime.now(timezone.utc) - ts).total_seconds()
    # A different universe's fresh run must not leak in -- the 48h-stale
    # activity.log is still the only signal for u1.
    assert age_seconds > 47 * 3600


def test_last_activity_ignores_queued_run_that_never_started(
    universe_base: Path,
) -> None:
    """A `create_run` row is `queued` immediately, with `started_at` stamped
    at row-creation time -- before any worker has picked it up. Without the
    `status != 'queued'` filter, a bare enqueue (never executed) would mark
    the universe fresh (Codex ADAPT, reproduced against 5eab19b1)."""
    from tinyassets.runs import create_run

    udir = _make_universe(universe_base, "u1", activity_age_hours=48)
    create_run(
        universe_base,
        branch_def_id="b1",
        thread_id="t1",
        inputs={},
        actor="universe:u1",
        queue_universe_id="u1",
    )  # left queued -- never transitioned to running/completed/etc.

    got = us._last_activity_at(udir, None)
    assert got is not None
    ts = datetime.fromisoformat(got)
    age_seconds = (datetime.now(timezone.utc) - ts).total_seconds()
    # Only the 48h-stale activity.log is a real signal here.
    assert age_seconds > 47 * 3600


def test_last_activity_scopes_by_queue_universe_id_not_actor(
    universe_base: Path,
) -> None:
    """`actor` and `queue_universe_id` are independent columns on `runs`
    with no DB-level equality invariant (`create_run` takes them as
    separate arguments). Codex ADAPT reproduced a row carrying one
    universe's actor and another's queue_universe_id leaking activity into
    the wrong universe under the old `actor`-scoped query; this asserts the
    row counts for the queue_universe_id owner (u2) and not the actor (u1)."""
    from tinyassets.runs import RUN_STATUS_COMPLETED, create_run, update_run_status

    udir_u1 = _make_universe(universe_base, "u1", activity_age_hours=48)
    udir_u2 = _make_universe(universe_base, "u2", activity_age_hours=48)
    mismatched_run = create_run(
        universe_base,
        branch_def_id="b1",
        thread_id="t1",
        inputs={},
        actor="universe:u1",
        queue_universe_id="u2",
    )
    update_run_status(
        universe_base, mismatched_run,
        status=RUN_STATUS_COMPLETED, finished_at=time.time() - 60,
    )

    got_u1 = us._last_activity_at(udir_u1, None)
    ts_u1 = datetime.fromisoformat(got_u1)
    age_u1 = (datetime.now(timezone.utc) - ts_u1).total_seconds()
    assert age_u1 > 47 * 3600  # the row's actor (u1) does NOT get credit

    got_u2 = us._last_activity_at(udir_u2, None)
    ts_u2 = datetime.fromisoformat(got_u2)
    age_u2 = (datetime.now(timezone.utc) - ts_u2).total_seconds()
    assert age_u2 < 120  # the row's queue_universe_id (u2) does


def test_last_activity_ignores_refused_automation_attempt(
    universe_base: Path,
) -> None:
    """Real refusal lifecycle: `AutomationStore.claim_attempt` then
    `finish_attempt(status="refused")` (matching the actual call site in
    `tinyassets.automations` when provider authority / rate-limit refuses a
    due automation). `finish_attempt` bumps the automation row's
    `last_finished_at` regardless of status -- that field is no longer a
    source at all, so a refused attempt with no run created must not move
    `last_activity_at`."""
    from datetime import datetime as _dt

    from tinyassets.automations import Automation, AutomationStore

    udir = _make_universe(universe_base, "u1", activity_age_hours=48)
    old_iso = "2026-01-01T00:00:00+00:00"
    automation = Automation(
        automation_id="a1",
        universe_id="u1",
        owner_principal_id="p1",
        name="n",
        branch_def_id="b1",
        trigger_kind="interval",
        interval_seconds=300,
        cron_expr="",
        inputs={},
        desired_state="active",
        pause_reason="",
        revision=1,
        created_at=old_iso,
        updated_at=old_iso,
        retired_at="",
        last_due_at="",
        last_run_id="",
        last_reason="",
        last_finished_at="",
    )
    store = AutomationStore(universe_base)
    store.insert(automation)

    now = _dt.now(timezone.utc)
    due_at = now.isoformat()
    assert store.claim_attempt("a1", due_at, now=now) is True
    store.finish_attempt(
        "a1", due_at,
        run_id="",
        status="refused",
        reason="run_rate_limited",
        now=now,
        succeeded=None,
    )

    got = us._last_activity_at(udir, None)
    assert got is not None
    ts = datetime.fromisoformat(got)
    age_seconds = (datetime.now(timezone.utc) - ts).total_seconds()
    # No run was created -- only the 48h-stale activity.log is a real signal.
    assert age_seconds > 47 * 3600


def test_safe_epoch_to_datetime_rejects_bad_values(universe_base: Path) -> None:
    """Direct unit coverage of each rejection branch in the hygiene wrapper
    that guards the runs-ledger epoch before it reaches `datetime`."""
    assert us._safe_epoch_to_datetime(float("nan")) is None
    assert us._safe_epoch_to_datetime(float("inf")) is None
    assert us._safe_epoch_to_datetime(float("-inf")) is None
    assert us._safe_epoch_to_datetime(0.0) is None
    assert us._safe_epoch_to_datetime(-5.0) is None
    assert us._safe_epoch_to_datetime(time.time() + 3600) is None  # 1h future
    assert us._safe_epoch_to_datetime(1e300) is None  # would OverflowError

    good = time.time() - 60
    got = us._safe_epoch_to_datetime(good)
    assert got is not None
    assert abs(got.timestamp() - good) < 1


def test_last_activity_ignores_huge_run_timestamp_without_raising(
    universe_base: Path,
) -> None:
    """Codex ADAPT reproduction: a finite-but-huge `finished_at` (1e300)
    reached `datetime.fromtimestamp` unguarded and raised `OverflowError`,
    turning the public read into an error. This must degrade to "no
    signal" instead -- the call not raising is itself part of the proof."""
    from tinyassets.runs import RUN_STATUS_COMPLETED, create_run, update_run_status

    udir = _make_universe(universe_base, "u1", activity_age_hours=48)
    run_id = create_run(
        universe_base,
        branch_def_id="b1",
        thread_id="t1",
        inputs={},
        actor="universe:u1",
        queue_universe_id="u1",
    )
    update_run_status(
        universe_base, run_id, status=RUN_STATUS_COMPLETED, finished_at=1e300,
    )

    got = us._last_activity_at(udir, None)  # must not raise

    assert got is not None
    ts = datetime.fromisoformat(got)
    age_seconds = (datetime.now(timezone.utc) - ts).total_seconds()
    assert age_seconds > 47 * 3600  # falls back to the file-based signal


def test_last_activity_runs_lookup_bounded_under_exclusive_lock(
    universe_base: Path,
) -> None:
    """The runs-ledger lookup must be bounded (~2s busy timeout) rather than
    blocking behind a writer, since it backs a public MCP status read.
    `PRAGMA locking_mode = EXCLUSIVE` + an uncommitted write is what
    actually blocks a WAL reader locally (a bare `BEGIN EXCLUSIVE` with no
    write does not -- WAL readers see the last committed snapshot)."""
    import sqlite3

    from tinyassets.runs import (
        RUN_STATUS_COMPLETED,
        create_run,
        runs_db_path,
        update_run_status,
    )

    udir = _make_universe(universe_base, "u1", activity_age_hours=48)
    run_id = create_run(
        universe_base,
        branch_def_id="b1",
        thread_id="t1",
        inputs={},
        actor="universe:u1",
        queue_universe_id="u1",
    )
    update_run_status(
        universe_base, run_id, status=RUN_STATUS_COMPLETED, finished_at=time.time() - 60,
    )

    locker = sqlite3.connect(runs_db_path(universe_base), timeout=1.0)
    try:
        locker.execute("PRAGMA locking_mode = EXCLUSIVE")
        locker.execute("BEGIN IMMEDIATE")
        locker.execute(
            "UPDATE runs SET status = status WHERE run_id = ?", (run_id,),
        )

        start = time.perf_counter()
        got = us._last_activity_at(udir, None)
        elapsed = time.perf_counter() - start
    finally:
        locker.execute("ROLLBACK")
        locker.close()

    assert elapsed < 5.0
    # The locked runs DB contributes no signal -- falls back to the
    # 48h-stale file value, not the recent (now-unreadable) run.
    assert got is not None
    ts = datetime.fromisoformat(got)
    age_seconds = (datetime.now(timezone.utc) - ts).total_seconds()
    assert age_seconds > 47 * 3600


def test_latest_run_activity_query_uses_scope_status_finished_index(
    universe_base: Path,
) -> None:
    import sqlite3

    from tinyassets.runs import initialize_runs_db, runs_db_path

    initialize_runs_db(universe_base)
    conn = sqlite3.connect(runs_db_path(universe_base))
    try:
        plan = conn.execute(
            "EXPLAIN QUERY PLAN SELECT MAX(COALESCE(finished_at, started_at)) "
            "FROM runs WHERE queue_universe_id = ? AND status != ?",
            ("u1", "queued"),
        ).fetchall()
    finally:
        conn.close()
    plan_text = " ".join(str(row) for row in plan)
    assert "idx_runs_scope_status_finished" in plan_text


def test_read_graph_target_graph_surfaces_run_ledger_activity(
    universe_base: Path,
) -> None:
    """Public-surface proof: `read_graph target=graph` dispatches to
    `_action_inspect_universe` (`universe_server.py`'s `normalized ==
    "graph"` branch), which nests liveness under `daemon`. Assert
    `daemon.last_activity_at` reflects the run's own timestamp, not merely
    "some non-null value"."""
    from tinyassets.runs import RUN_STATUS_COMPLETED, create_run, update_run_status

    _make_universe(universe_base, "u1", activity_age_hours=48)
    run_id = create_run(
        universe_base,
        branch_def_id="b1",
        thread_id="t1",
        inputs={},
        actor="universe:u1",
        queue_universe_id="u1",
    )
    finished_at = time.time() - 60
    update_run_status(
        universe_base, run_id, status=RUN_STATUS_COMPLETED, finished_at=finished_at,
    )

    out = json.loads(us._action_inspect_universe(universe_id="u1"))

    got = out["daemon"]["last_activity_at"]
    assert got is not None
    ts = datetime.fromisoformat(got)
    assert abs(ts.timestamp() - finished_at) < 1


def test_last_activity_file_based_value_survives_missing_dbs(
    universe_base: Path,
) -> None:
    assert not (universe_base / ".runs.db").exists()
    udir = _make_universe(universe_base, "u1", activity_age_hours=0.5)

    got = us._last_activity_at(udir, None)

    assert got is not None
    ts = datetime.fromisoformat(got)
    age_seconds = (datetime.now(timezone.utc) - ts).total_seconds()
    assert age_seconds < 60 * 60
    # The runs DB is not created as a side effect of a read.
    assert not (universe_base / ".runs.db").exists()


# ---------------------------------------------------------------------------
# accept_rate from scene_history
# ---------------------------------------------------------------------------


def test_accept_rate_returns_none_without_db(universe_base: Path) -> None:
    udir = _make_universe(universe_base, "u")
    rate, sample = us._compute_accept_rate_from_db(udir)
    assert rate is None
    assert sample["source"] == "none"


def test_accept_rate_ignores_pending_verdicts(universe_base: Path) -> None:
    """#17: status.json cached `accept_rate: 0.0` confused readers when
    really no scenes had been evaluated yet. The fix: pending scenes do
    NOT count as rejects. `None` means "no evaluated sample", not 0%.
    """
    udir = _make_universe(
        universe_base, "u",
        scene_history=[("s1", "pending"), ("s2", "pending")],
    )
    rate, sample = us._compute_accept_rate_from_db(udir)
    assert rate is None
    assert sample == {"accepted": 0, "evaluated": 0, "source": "scene_history"}


def test_accept_rate_computes_when_scenes_evaluated(universe_base: Path) -> None:
    udir = _make_universe(
        universe_base, "u",
        scene_history=[
            ("s1", "accept"),
            ("s2", "second_draft"),
            ("s3", "reject"),
            ("s4", "pending"),  # excluded from both numerator and denominator
        ],
    )
    rate, sample = us._compute_accept_rate_from_db(udir)
    assert rate == pytest.approx(2 / 3)
    assert sample == {"accepted": 2, "evaluated": 3, "source": "scene_history"}


# ---------------------------------------------------------------------------
# inspect
# ---------------------------------------------------------------------------


def test_inspect_surfaces_has_premise_false_when_missing(
    universe_base: Path,
) -> None:
    """#10: has_premise must be an explicit boolean in the inspect response."""
    _make_universe(universe_base, "u")  # no premise
    out = json.loads(us._action_inspect_universe(universe_id="u"))
    assert out["has_premise"] is False
    assert "premise" not in out


def test_inspect_surfaces_has_premise_true_with_text(
    universe_base: Path,
) -> None:
    _make_universe(universe_base, "u", premise="A tower of bones.")
    out = json.loads(us._action_inspect_universe(universe_id="u"))
    assert out["has_premise"] is True
    assert out["premise"] == "A tower of bones."


def test_inspect_translates_current_phase_from_status_json(
    universe_base: Path,
) -> None:
    """#8: status.json uses `current_phase`; inspect previously read `phase`
    and reported 'unknown'. Fix: we read current_phase with phase as fallback.
    """
    _make_universe(
        universe_base, "u",
        premise="x",
        status={"current_phase": "dispatch_execution", "word_count": 1000},
        activity_age_hours=0.1,
    )
    out = json.loads(us._action_inspect_universe(universe_id="u"))
    assert out["daemon"]["phase"] == "dispatch_execution"
    assert out["daemon"]["phase_human"] != "unknown"


def test_inspect_reports_dormant_for_stale_daemon(universe_base: Path) -> None:
    """#14/#16: a status.json that claims 'running' must not be trusted
    as a liveness signal. Activity log age drives staleness.
    """
    _make_universe(
        universe_base, "u",
        premise="x",
        work_targets=[{"lifecycle": "active", "target_id": "t1"}],
        status={"current_phase": "dispatch_execution", "daemon_state": "running"},
        activity_age_hours=48,  # 2 days stale
    )
    out = json.loads(us._action_inspect_universe(universe_id="u"))
    d = out["daemon"]
    assert d["staleness"] == "dormant"
    assert d["phase_human"] == "dormant"


def test_inspect_reports_idle_no_premise_for_empty_universe(
    universe_base: Path,
) -> None:
    """#8 broader: missing premise should surface as `idle-no-premise`,
    not fall through to `unknown`.
    """
    _make_universe(universe_base, "u")  # no premise, no work, no activity
    out = json.loads(us._action_inspect_universe(universe_id="u"))
    d = out["daemon"]
    assert d["has_premise"] is False
    assert d["phase_human"] == "idle-no-premise"
    assert d["staleness"] == "never"


def test_inspect_accept_rate_is_null_not_zero(universe_base: Path) -> None:
    """#17: returning accept_rate=0.0 when nothing has been evaluated is
    misleading. Callers should see null + the sample counts."""
    _make_universe(universe_base, "u", premise="x")
    out = json.loads(us._action_inspect_universe(universe_id="u"))
    assert out["daemon"]["accept_rate"] is None
    assert out["daemon"]["accept_rate_sample"]["evaluated"] == 0


# ---------------------------------------------------------------------------
# control_daemon status
# ---------------------------------------------------------------------------


def test_control_daemon_status_includes_liveness_fields(
    universe_base: Path,
) -> None:
    """#14: status must expose last_activity_at + staleness so readers
    can tell a dormant daemon from an alive one.
    """
    _make_universe(
        universe_base, "u",
        premise="x",
        work_targets=[{"lifecycle": "active", "target_id": "t1"}],
        status={"current_phase": "dispatch_execution"},
        activity_age_hours=72,  # 3 days stale
    )
    out = json.loads(us._action_control_daemon(universe_id="u", text="status"))
    assert out["action"] == "status"
    assert out["phase_human"] == "dormant"
    assert out["staleness"] == "dormant"
    assert out["last_activity_at"] is not None
    assert out["has_premise"] is True
    assert "accept_rate" in out
    assert "accept_rate_sample" in out


def test_control_daemon_status_reports_paused_state(universe_base: Path) -> None:
    _make_universe(
        universe_base, "u",
        premise="x",
        work_targets=[{"lifecycle": "active", "target_id": "t1"}],
        status={"current_phase": "dispatch_execution"},
        activity_age_hours=0.1,
        paused=True,
    )
    out = json.loads(us._action_control_daemon(universe_id="u", text="status"))
    assert out["is_paused"] is True
    assert out["phase_human"] == "paused"


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------


def test_list_surfaces_telemetry_for_every_universe(universe_base: Path) -> None:
    _make_universe(
        universe_base, "alive",
        premise="x",
        work_targets=[{"lifecycle": "active", "target_id": "t1"}],
        status={"current_phase": "draft"},
        activity_age_hours=0.1,
    )
    _make_universe(universe_base, "empty")  # no premise
    out = json.loads(us._action_list_universes())
    by_id = {u["id"]: u for u in out["universes"]}

    alive = by_id["alive"]
    assert alive["has_premise"] is True
    assert alive["staleness"] == "fresh"
    assert alive["phase_human"] == "draft"

    empty = by_id["empty"]
    assert empty["has_premise"] is False
    assert empty["phase_human"] == "idle-no-premise"
    assert empty["staleness"] == "never"
    assert empty["last_activity_at"] is None
