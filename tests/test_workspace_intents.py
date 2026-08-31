"""Tests for durable push intents (``tinyassets.workspace_intents``).

A push is not idempotent from the daemon's side, so the question this module
answers is "did the remote take it?" -- and both wrong answers are expensive:
reporting success for a push that never landed, or retrying one that did. The
tests below are mostly about the states, because the states ARE the contract.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from tinyassets import runs
from tinyassets.workspace_intents import (
    INTENT_STATES,
    open_intents,
    reconcile_push_intents,
    record_push_intent,
    settle_push_intent,
)

SHA = "a" * 40
OTHER = "b" * 40


@pytest.fixture()
def universe(tmp_path: Path) -> Path:
    base = tmp_path / "data" / "universe-1"
    base.mkdir(parents=True)
    runs.initialize_runs_db(base)
    return base


def _record(universe: Path, **over) -> str:
    fields = {
        "run_id": "run-1",
        "node_id": "push-node",
        "connection_id": "conn-git",
        "repo": "owner/name",
        "remote_ref": "refs/heads/tiny/u/slug",
        "sha": SHA,
    }
    fields.update(over)
    return record_push_intent(universe, **fields)


def _states(universe: Path) -> list[tuple[str, str]]:
    conn = sqlite3.connect(runs.runs_db_path(universe))
    try:
        return [
            (row[0], row[1])
            for row in conn.execute(
                "SELECT state, COALESCE(observed_sha, '') FROM workspace_push_intents"
            )
        ]
    finally:
        conn.close()


def test_an_intent_is_durable_the_moment_it_is_recorded(universe: Path) -> None:
    """Written BEFORE the wire: a crash mid-flight must leave a row."""
    intent_id = _record(universe)
    assert intent_id
    open_now = open_intents(universe)
    assert [i.intent_id for i in open_now] == [intent_id]
    assert open_now[0].state == "sent"
    assert open_now[0].sha == SHA


def test_settling_removes_it_from_the_open_set(universe: Path) -> None:
    intent_id = _record(universe)
    settle_push_intent(universe, intent_id, "done")
    assert open_intents(universe) == []
    assert _states(universe) == [("done", "")]


@pytest.mark.parametrize("state", INTENT_STATES)
def test_every_declared_state_is_settleable(universe: Path, state: str) -> None:
    intent_id = _record(universe)
    settle_push_intent(universe, intent_id, state)
    assert _states(universe)[0][0] == state


def test_an_undeclared_state_is_rejected(universe: Path) -> None:
    """The CHECK constraint is the backstop; this is the loud front door."""
    intent_id = _record(universe)
    with pytest.raises(ValueError):
        settle_push_intent(universe, intent_id, "probably-fine")


def test_the_table_refuses_an_undeclared_state_at_the_database_too(
    universe: Path,
) -> None:
    _record(universe)
    conn = sqlite3.connect(runs.runs_db_path(universe))
    try:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("UPDATE workspace_push_intents SET state = 'maybe'")
            conn.commit()
    finally:
        conn.close()


# --------------------------------------------------------------------------- #
# Reconciliation
# --------------------------------------------------------------------------- #


def test_the_same_sha_already_at_the_ref_reconciles_to_done(universe: Path) -> None:
    """A repeated non-force push of the same commit is success, not failure."""
    _record(universe)
    settled = reconcile_push_intents(
        universe,
        execute=lambda request: {"ok": True, "observed_sha": SHA},
        credential_ref_for=lambda cid: "vault://http/x",
    )
    assert [state for _id, state in settled] == ["done"]
    assert open_intents(universe) == []


def test_a_different_sha_at_the_ref_reconciles_to_failed_and_records_it(
    universe: Path,
) -> None:
    _record(universe)
    settled = reconcile_push_intents(
        universe,
        execute=lambda request: {"ok": True, "observed_sha": OTHER},
        credential_ref_for=lambda cid: "vault://http/x",
    )
    assert [state for _id, state in settled] == ["failed"]
    assert _states(universe) == [("failed", OTHER)]


def test_a_remote_that_cannot_be_asked_stays_unknown_not_guessed(
    universe: Path,
) -> None:
    """Neither answer is safe to invent, so it stays owed."""
    _record(universe)
    settled = reconcile_push_intents(
        universe,
        execute=lambda request: {"ok": False, "error": "transport"},
        credential_ref_for=lambda cid: "vault://http/x",
    )
    assert [state for _id, state in settled] == ["unknown"]
    assert _states(universe)[0][0] == "unknown"


def test_an_execute_that_raises_is_unknown_rather_than_a_crash(
    universe: Path,
) -> None:
    def explode(request):
        raise OSError("the worker could not start")

    _record(universe)
    settled = reconcile_push_intents(
        universe, execute=explode, credential_ref_for=lambda cid: "vault://http/x"
    )
    assert [state for _id, state in settled] == ["unknown"]


def test_reconciliation_asks_about_the_intent_s_own_ref_and_repo(
    universe: Path,
) -> None:
    seen: list[dict] = []
    _record(universe, repo="owner/other", remote_ref="refs/heads/tiny/u/other")
    reconcile_push_intents(
        universe,
        execute=lambda request: seen.append(request) or {"ok": True, "observed_sha": SHA},
        credential_ref_for=lambda cid: "vault://http/x",
    )
    assert seen[0]["op"] == "ls_remote"
    assert seen[0]["owner_repo"] == "owner/other"
    assert seen[0]["remote_ref"] == "refs/heads/tiny/u/other"


def test_nothing_open_asks_the_remote_nothing(universe: Path) -> None:
    """A startup path that queries a remote for no reason is a startup path
    that fails when the remote is down."""
    seen: list[dict] = []
    assert reconcile_push_intents(universe, execute=lambda r: seen.append(r) or {}) == []
    assert seen == []


def test_a_settled_intent_is_not_reconciled_again(universe: Path) -> None:
    intent_id = _record(universe)
    settle_push_intent(universe, intent_id, "done")
    seen: list[dict] = []
    assert reconcile_push_intents(universe, execute=lambda r: seen.append(r) or {}) == []
    assert seen == []


def test_several_open_intents_are_all_settled(universe: Path) -> None:
    _record(universe, node_id="a")
    _record(universe, node_id="b", sha=OTHER)
    settled = reconcile_push_intents(
        universe,
        execute=lambda request: {"ok": True, "observed_sha": SHA},
        credential_ref_for=lambda cid: "vault://http/x",
    )
    assert sorted(state for _id, state in settled) == ["done", "failed"]


def test_the_worker_exposes_the_reconciler_for_the_startup_path() -> None:
    """``runs.py`` calls ``workspace_worker.reconcile_push_intents``."""
    from tinyassets import workspace_worker

    assert callable(workspace_worker.reconcile_push_intents)
    assert "reconcile_push_intents" in workspace_worker.__all__
