"""Structural caps became usage limits (plan item 6).

The invoke_branch depth cap, the automation ceiling, the cadence floors and
the per-owner schedule counts are gone. What bounds a universe's work now is
its usage: every run -- a run_graph, an automation, a triggered run, a
sub-branch child -- is charged to the universe's admission ledger, per hour
and per rolling day. These tests drive the real ledger, the real compiled
graph and the real triggered-run path.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from tinyassets import engine_admissions as ea
from tinyassets.branches import (
    BranchDefinition,
    EdgeDefinition,
    GraphNodeRef,
    NodeDefinition,
)
from tinyassets.daemon_server import initialize_author_server, save_branch_definition
from tinyassets.runs import execute_branch, initialize_runs_db

UNIVERSE = "universe_usage"
OWNER = "acct_usage_owner"


@pytest.fixture(autouse=True)
def _pin_data_dir(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))


def _ledger_rows(base: Path, *, kind: str | None = None) -> list[tuple]:
    db = base / ea.LEDGER_NAME
    if not db.is_file():
        return []
    with sqlite3.connect(db) as conn:
        query = "SELECT universe_id, kind FROM admissions"
        if kind:
            return conn.execute(query + " WHERE kind = ?", (kind,)).fetchall()
        return conn.execute(query).fetchall()


# -- The daily window -------------------------------------------------------------


def _admit(db: Path, *, kind: str = ea.KIND_WRITE, day_max: int | None = 3,
           universe: str = UNIVERSE) -> ea.Admission:
    return ea.admit_detail(
        universe, write_max=1000, total_max=1000, window_s=ea.RUN_WINDOW_SECONDS,
        fail_closed=True, db=db, kind=kind, day_max=day_max,
    )


def test_runs_are_metered_per_rolling_day_across_hours(tmp_path, monkeypatch) -> None:
    """A chain paced under every hourly cap still meets the day's."""
    clock = {"now": 1_000_000.0}
    monkeypatch.setattr(ea.time, "time", lambda: clock["now"])
    db = tmp_path / ea.LEDGER_NAME
    for _hour in range(3):
        assert _admit(db).ticket is not None
        clock["now"] += ea.RUN_WINDOW_SECONDS + 60  # a fresh hourly window
    refused = _admit(db)
    assert (refused.ticket, refused.refused_by) == (None, ea.REFUSED_BY_DAY)
    # Another universe's day is its own.
    assert _admit(db, universe="universe_other").ticket is not None
    # A day after the first run, one frees up.
    clock["now"] = 1_000_000.0 + ea.RUN_DAY_SECONDS + 1
    assert _admit(db).ticket is not None


def test_read_runs_count_toward_the_day_and_engine_edits_do_not(
    tmp_path, monkeypatch,
) -> None:
    clock = {"now": 2_000_000.0}
    monkeypatch.setattr(ea.time, "time", lambda: clock["now"])
    db = tmp_path / ea.LEDGER_NAME
    first = _admit(db)
    ea.attach_run(first.ticket, "run-read", db=db)
    assert ea.reclassify_read("run-read", db=db)
    for _ in range(5):
        assert _admit(db, kind=ea.KIND_ENGINE).ticket is not None
    assert _admit(db).ticket is not None
    assert _admit(db).ticket is not None
    assert _admit(db).refused_by == ea.REFUSED_BY_DAY


def test_a_day_of_rows_is_kept_and_no_more(tmp_path, monkeypatch) -> None:
    """The hourly prune used to delete everything past an hour; a day-metered
    ledger keeps a day, and still prunes what is older."""
    clock = {"now": 3_000_000.0}
    monkeypatch.setattr(ea.time, "time", lambda: clock["now"])
    db = tmp_path / ea.LEDGER_NAME
    _admit(db, day_max=100)
    clock["now"] += 2 * ea.RUN_WINDOW_SECONDS
    _admit(db, day_max=100)
    assert len(_ledger_rows(tmp_path)) == 2
    clock["now"] += ea.RUN_DAY_SECONDS + 1
    _admit(db, day_max=100)
    assert len(_ledger_rows(tmp_path)) == 1


def test_every_served_run_admission_is_day_metered(tmp_path, monkeypatch) -> None:
    import tinyassets.engine_mcp_server as ems

    monkeypatch.setattr(ea, "RUN_DAY_LIMIT", 2)
    assert ems._engine_run_admit(universe_id=UNIVERSE) is True
    assert ems._engine_run_admit(universe_id=UNIVERSE) is True
    admission = ems._engine_run_admit(universe_id=UNIVERSE, want_ticket=True)
    assert admission.refused_by == ea.REFUSED_BY_DAY
    refusal = ems._engine_refusal("run_graph", admission.refused_by)
    assert "last 24 hours" in refusal and "2 runs" in refusal


# -- invoke_branch: no depth cap, every child metered ------------------------


def _self_invoking(branch_id: str) -> BranchDefinition:
    """A branch whose only node blocking-invokes itself: a chain with no end
    but the meter."""
    node = NodeDefinition(
        node_id="again",
        display_name="Again",
        invoke_branch_spec={
            "branch_def_id": branch_id,
            "wait_mode": "blocking",
            "inputs_mapping": {},
            "output_mapping": {},
        },
    )
    return BranchDefinition(
        branch_def_id=branch_id,
        name="self-invoking",
        author=OWNER,
        visibility="private",
        graph_nodes=[GraphNodeRef(id="again", node_def_id="again")],
        edges=[EdgeDefinition(from_node="again", to_node="END")],
        entry_point="again",
        node_defs=[node],
        state_schema=[],
    )


def _seed(base: Path, branch: BranchDefinition) -> None:
    from tinyassets.daemon_server import grant_universe_access, set_founder_home

    initialize_author_server(base)
    initialize_runs_db(base)
    (base / UNIVERSE).mkdir(parents=True, exist_ok=True)
    grant_universe_access(base, universe_id=UNIVERSE, actor_id=OWNER,
                          permission="admin", granted_by=OWNER)
    set_founder_home(base, founder_sub=OWNER, universe_id=UNIVERSE)
    save_branch_definition(base, branch_def=branch.to_dict())


def _run_errors(base: Path) -> list[str]:
    from tinyassets.runs import _connect

    with _connect(base) as conn:
        return [str(row[0] or "") for row in conn.execute("SELECT error FROM runs")]


def _child_runs(base: Path) -> int:
    from tinyassets.runs import _connect

    with _connect(base) as conn:
        return int(conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0])


def test_a_self_invoking_chain_goes_past_the_old_depth_and_stops_at_the_meter(
    tmp_path, monkeypatch,
) -> None:
    """Depth 5 used to end this chain as a shape error. Now it runs deeper, and
    the universe's usage meter is what stops it -- loudly, by name."""
    monkeypatch.setattr(ea, "RUN_WRITE_LIMIT", 8)
    branch = _self_invoking("branch_loop")
    _seed(tmp_path, branch)

    outcome = execute_branch(
        tmp_path, branch=branch, inputs={}, actor=OWNER,
        _enqueue_universe_id=UNIVERSE,
    )

    assert outcome.status == "failed"
    # The innermost child is the one the meter refused; each parent above it
    # fails with the child's failure.
    assert sum("usage limit" in error for error in _run_errors(tmp_path)) == 1
    # The root plus eight metered children: deeper than the old cap of 5.
    assert _child_runs(tmp_path) == 9
    # Eight charges, each bound to its child run: those that failed without
    # firing anything settled off the write budget, as any run does.
    assert len(_ledger_rows(tmp_path)) == 8


def test_an_unmetered_chain_ends_at_the_interpreter_stack_by_name(
    tmp_path,
) -> None:
    """With no universe to meter (the local daemon), nothing charges the chain;
    a blocking chain runs in one thread, so the interpreter's stack is what
    ends it -- reported as that, not as a raw RecursionError."""
    branch = _self_invoking("branch_local")
    _seed(tmp_path, branch)

    outcome = execute_branch(tmp_path, branch=branch, inputs={}, actor=OWNER)

    assert outcome.status == "failed"
    assert any(
        "exhausted the interpreter's stack" in error
        for error in _run_errors(tmp_path)
    )
    assert _ledger_rows(tmp_path) == []
    assert _child_runs(tmp_path) > 6


# -- Triggered runs (schedules, Source events, webhooks) are metered --------------


def test_a_triggered_run_is_charged_and_refused_when_the_meter_is_full(
    tmp_path, monkeypatch,
) -> None:
    from tinyassets.api.runs import enqueue_universe_branch_run

    branch = _self_invoking("branch_triggered")
    branch.node_defs = [NodeDefinition(
        node_id="again", display_name="Noop",
        source_code="def run(state):\n    return {}\n",
    ).mark_approved()]
    _seed(tmp_path, branch)
    started: list[str] = []
    monkeypatch.setattr(
        "tinyassets.runs.execute_branch_async",
        lambda *a, **k: started.append("run") or type(
            "O", (), {"run_id": f"run_{len(started)}", "status": "queued"})(),
    )
    import tinyassets.engine_mcp_server as ems

    monkeypatch.setattr(ems, "_RUN_GRAPH_RATE_MAX", 1)

    run_id = enqueue_universe_branch_run(
        tmp_path, universe_id=UNIVERSE, branch_def_id="branch_triggered",
        inputs={}, principal_id=OWNER,
    )
    assert run_id == "run_1"
    with sqlite3.connect(tmp_path / ea.LEDGER_NAME) as conn:
        assert conn.execute(
            "SELECT universe_id, kind, run_id FROM admissions"
        ).fetchall() == [(UNIVERSE, "write", "run_1")]

    with pytest.raises(ValueError, match="run_usage_limited:write"):
        enqueue_universe_branch_run(
            tmp_path, universe_id=UNIVERSE, branch_def_id="branch_triggered",
            inputs={}, principal_id=OWNER,
        )
    assert started == ["run"]


def test_a_childs_charge_is_bound_to_the_child_run(tmp_path) -> None:
    """Bound by ticket, a child that only read settles off the write budget
    like any other run, instead of spending it for good."""
    child = BranchDefinition(
        branch_def_id="branch_child_noop",
        name="noop child",
        author=OWNER,
        visibility="private",
        graph_nodes=[GraphNodeRef(id="noop", node_def_id="noop")],
        edges=[EdgeDefinition(from_node="noop", to_node="END")],
        entry_point="noop",
        node_defs=[NodeDefinition(
            node_id="noop", display_name="Noop",
            source_code="def run(state):\n    return {}\n",
        ).mark_approved()],
        state_schema=[],
    )
    parent = _self_invoking("branch_parent_once")
    parent.node_defs[0].invoke_branch_spec["branch_def_id"] = "branch_child_noop"
    _seed(tmp_path, child)
    save_branch_definition(tmp_path, branch_def=parent.to_dict())

    execute_branch(tmp_path, branch=parent, inputs={}, actor=OWNER,
                   _enqueue_universe_id=UNIVERSE)

    from tinyassets.runs import _connect

    with _connect(tmp_path) as conn:
        child_run = conn.execute(
            "SELECT run_id FROM runs WHERE branch_def_id = 'branch_child_noop'"
        ).fetchone()[0]
    with sqlite3.connect(tmp_path / ea.LEDGER_NAME) as conn:
        bound = conn.execute("SELECT run_id FROM admissions").fetchall()
    assert bound == [(child_run,)]


# -- Folded from the gpt-6-astra refute round (2026-09-28) -----------------------


def test_a_caller_without_the_day_window_keeps_everyones_day(
    tmp_path, monkeypatch,
) -> None:
    """The prune is global: a caller metering only the hour used to delete
    every universe's day history (refute P1, receiver deliveries)."""
    clock = {"now": 4_000_000.0}
    monkeypatch.setattr(ea.time, "time", lambda: clock["now"])
    db = tmp_path / ea.LEDGER_NAME
    for _ in range(3):
        assert _admit(db).ticket is not None
    assert _admit(db).refused_by == ea.REFUSED_BY_DAY
    clock["now"] += 2 * ea.RUN_WINDOW_SECONDS
    # Another universe, admitted by an hour-only caller.
    assert _admit(db, universe="universe_b", day_max=None).ticket is not None
    assert _admit(db).refused_by == ea.REFUSED_BY_DAY


def test_a_refused_cadence_instant_leaves_no_row(tmp_path, monkeypatch) -> None:
    """A one-second cadence on a full meter used to add a durable attempt row
    every poll, outside the meter (refute P1). The instant is skipped with
    no row, and a refusal by the meter is not a failure of the work."""
    from datetime import datetime, timedelta, timezone

    import tinyassets.engine_mcp_server as ems
    from tests.test_automations import (
        _registration_kwargs,
        _seed_branch,
        _seed_owner,
    )
    from tests.test_background_budget_finalization_e2e import (
        _seed_serving_assignment,
    )
    from tinyassets.automations import (
        AutomationStore,
        due_automations,
        register_automation,
        run_due_automation,
    )

    monkeypatch.setenv("TINYASSETS_ASSIGNED_QUEUE_CONSUMER", "1")
    _seed_serving_assignment(tmp_path)
    _seed_owner(tmp_path)
    _seed_branch(tmp_path)
    start = datetime(2026, 9, 1, tzinfo=timezone.utc)
    automation = register_automation(
        tmp_path, **_registration_kwargs(interval_seconds=1, now=start),
    )
    monkeypatch.setattr(ems, "_RUN_GRAPH_RATE_MAX", 0)
    from tests.test_automations import UNIVERSE as AUTO_UNIVERSE

    moment = start
    for _poll in range(3):
        moment += timedelta(seconds=5)
        [(row, due_at)] = due_automations(
            tmp_path, universe_id=AUTO_UNIVERSE, now=moment,
        )
        assert run_due_automation(tmp_path, row, due_at, now=moment) == (
            "run_rate_limited"
        )
    with sqlite3.connect(AutomationStore(tmp_path).db_path) as conn:
        assert conn.execute(
            "SELECT COUNT(*) FROM automation_attempts WHERE automation_id = ?",
            (automation.automation_id,),
        ).fetchone()[0] == 0
    stored = AutomationStore(tmp_path).get(automation.automation_id)
    assert stored.last_due_at and stored.consecutive_failures == 0
    assert stored.desired_state == "active"
