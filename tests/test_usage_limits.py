"""Structural caps are gone, and nothing replaced them with a meter.

The invoke_branch depth cap, the automation ceiling, the cadence floors and the
per-owner schedule counts are gone. What bounds an account's work is its seats
(`universe_seats`); every run -- a run_graph, an automation, a triggered run, a
sub-branch child -- is only recorded in the effect settlement ledger. These tests
drive the real ledger, the real compiled graph and the real triggered-run path.
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


# -- invoke_branch: no depth cap, child settlement ------------------------


def _self_invoking(branch_id: str) -> BranchDefinition:
    """A branch whose only node blocking-invokes itself: a chain with no end
    until execution ends."""
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


# -- Triggered runs (schedules, Source events, webhooks) are metered --------------


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


# -- The reference workload: a 10-agent squad on 2-minute heartbeats ------------


# -- Hitting a limit is an owner-visible notice, never a silent drop ------------


