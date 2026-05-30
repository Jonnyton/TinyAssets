import sqlite3

from workflow.payments.actions import action_escrow_lock
from workflow.payments.escrow import (
    get_staker_balance,
    get_lock,
    list_locks_for_claim,
    migrate_escrow_schema,
    release_bonus,
    upsert_staker_balance,
)


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    migrate_escrow_schema(conn)
    return conn


def test_lock_bonus_reserves_then_release_debits_budget() -> None:
    conn = _conn()
    upsert_staker_balance(
        conn,
        staker_id="claimer-1",
        currency="MicroToken",
        total_amount=100,
        reserved_amount=0,
        updated_at="2026-05-30T00:00:00+00:00",
    )

    result = action_escrow_lock(
        conn,
        node_id="node-1",
        amount=40,
        claimer="claimer-1",
        currency="MicroToken",
    )

    assert result["status"] == "ok"
    budget = get_staker_balance(conn, staker_id="claimer-1", currency="MicroToken")
    assert budget is not None
    assert int(budget.total_amount) == 100
    assert int(budget.reserved_amount) == 40
    assert budget.spendable_amount == 60

    release_bonus(
        conn,
        lock_id=result["lock_id"],
        recipient_id="worker-1",
        resolved_at="2026-05-30T00:05:00+00:00",
    )

    budget = get_staker_balance(conn, staker_id="claimer-1", currency="MicroToken")
    assert budget is not None
    assert int(budget.total_amount) == 60
    assert int(budget.reserved_amount) == 0
    assert budget.spendable_amount == 60


def test_lock_bonus_rejects_when_budget_is_too_low() -> None:
    conn = _conn()
    upsert_staker_balance(
        conn,
        staker_id="claimer-2",
        currency="MicroToken",
        total_amount=25,
        reserved_amount=0,
        updated_at="2026-05-30T00:00:00+00:00",
    )

    result = action_escrow_lock(
        conn,
        node_id="node-2",
        amount=30,
        claimer="claimer-2",
        currency="MicroToken",
    )

    assert result["status"] == "rejected"
    assert "Insufficient uncommitted funds" in result["error"]
    assert get_lock(conn, "lock-does-not-exist") is None
    assert list_locks_for_claim(conn, gate_claim_id="node-2") == []

    budget = get_staker_balance(conn, staker_id="claimer-2", currency="MicroToken")
    assert budget is not None
    assert int(budget.total_amount) == 25
    assert int(budget.reserved_amount) == 0
    assert budget.spendable_amount == 25


def test_concurrent_claim_locks_cannot_exceed_staker_budget() -> None:
    conn = _conn()
    upsert_staker_balance(
        conn,
        staker_id="claimer-3",
        currency="MicroToken",
        total_amount=70,
        reserved_amount=0,
        updated_at="2026-05-30T00:00:00+00:00",
    )

    first = action_escrow_lock(
        conn,
        node_id="node-a",
        amount=50,
        claimer="claimer-3",
        currency="MicroToken",
    )
    second = action_escrow_lock(
        conn,
        node_id="node-b",
        amount=30,
        claimer="claimer-3",
        currency="MicroToken",
    )

    assert first["status"] == "ok"
    assert second["status"] == "rejected"
    assert "Insufficient uncommitted funds" in second["error"]
    assert len(list_locks_for_claim(conn, gate_claim_id="node-a")) == 1
    assert list_locks_for_claim(conn, gate_claim_id="node-b") == []

    budget = get_staker_balance(conn, staker_id="claimer-3", currency="MicroToken")
    assert budget is not None
    assert int(budget.total_amount) == 70
    assert int(budget.reserved_amount) == 50
    assert budget.spendable_amount == 20
