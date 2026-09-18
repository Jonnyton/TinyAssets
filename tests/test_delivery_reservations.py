"""Atomic delivery persistence, not public intake or worker recovery proof."""

from __future__ import annotations

import json
import multiprocessing
import os
import sqlite3
from concurrent.futures import ThreadPoolExecutor

import pytest

from tests.test_receiver_links import _link, _save
from tests.test_receiver_links import env as management_env  # noqa: F401
from tinyassets import runs
from tinyassets.api import receiver_links as api
from tinyassets.storage import deliveries, receiver_links


@pytest.fixture
def delivery_env(management_env):  # noqa: F811 - pytest resolves the imported fixture
    base, auth = management_env
    auth("receiver")
    receiver = _save()
    auth("sender")
    link = _link(receiver)
    # Persist the schema before fault injection, like daemon startup would.
    with deliveries.transaction(base):
        pass
    return base, auth, receiver, link


def _accept(conn, link, *, occurrence="send-1", values=None, source_run=None):
    values = {"topic": "exact input 🍉"} if values is None else values
    return deliveries.accept_in_transaction(
        conn,
        sender_id="sender",
        sender_universe_id="u-sender",
        link_id=link["link_id"],
        occurrence_id=occurrence,
        request_payload={"result": values},
        validated_inputs=values,
        source_run_id=source_run,
    )


def _read(conn, receipt, *, principal="sender", universe="u-sender"):
    return deliveries.read_receipt_in_transaction(
        conn,
        delivery_id=receipt["delivery_id"],
        principal_id=principal,
        universe_id=universe,
    )


def _counts(base):
    with deliveries.transaction(base) as conn:
        return tuple(
            conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
            for table in ("graph_deliveries", "graph_delivery_attempts", "runs")
        )


def test_acceptance_reserves_receiver_run_and_returns_only_safe_sender_receipt(delivery_env):
    base, _, receiver, link = delivery_env
    values = {"topic": {"key": "data", "token": "also data", "nested": [1, False, None, "🧪"]}}
    with deliveries.transaction(base) as conn:
        receipt = _accept(conn, link, values=values)
        assert receipt["status"] == "accepted"
        assert receipt["attempt"] == 1
        assert receipt["execution_started_at"] is None
        assert "run_id" not in receipt
        assert "private" not in json.dumps(receipt)
        private = _read(conn, receipt, principal="receiver", universe="u-receiver")
        assert private["run_id"]
        assert {k: v for k, v in private.items() if k != "run_id"} == receipt
        row = conn.execute("SELECT * FROM runs WHERE run_id=?", (private["run_id"],)).fetchone()
        assert row["actor"] == "universe:u-receiver"
        assert row["owner_user_id"] == "receiver"
        assert row["queue_universe_id"] == "u-receiver"
        assert row["thread_id"] == row["run_id"]
        assert row["branch_def_id"] == receiver["branch_def_id"]
        assert json.loads(row["inputs_json"]) == values
    assert _counts(base) == (1, 1, 1)


def test_same_occurrence_after_reopening_database_returns_same_delivery_and_run(delivery_env):
    base, _, _, link = delivery_env
    with deliveries.transaction(base) as conn:
        first = _accept(conn, link)
        private = _read(conn, first, principal="receiver", universe="u-receiver")
    with deliveries.transaction(base) as conn:
        second = _accept(conn, link)
        second_private = _read(conn, second, principal="receiver", universe="u-receiver")
    assert second == first
    assert second_private == private
    assert _counts(base) == (1, 1, 1)


def test_new_occurrences_with_identical_contents_are_independent(delivery_env):
    base, _, _, link = delivery_env
    with deliveries.transaction(base) as conn:
        first = _accept(conn, link)
        second = _accept(conn, link, occurrence="send-2")
    assert first["delivery_id"] != second["delivery_id"]
    assert _counts(base) == (2, 2, 2)


@pytest.mark.parametrize("change", ["inputs", "source_run"])
def test_changed_occurrence_is_rejected_without_reserving_another_run(delivery_env, change):
    base, _, _, link = delivery_env
    with deliveries.transaction(base) as conn:
        _accept(conn, link)
    kwargs = (
        {"values": {"topic": "changed"}} if change == "inputs" else {"source_run": "different-run"}
    )
    with pytest.raises(deliveries.OccurrenceConflict, match="occurrence_conflict"):
        with deliveries.transaction(base) as conn:
            _accept(conn, link, **kwargs)
    assert _counts(base) == (1, 1, 1)


def test_accepted_replay_survives_disconnect_but_new_occurrence_does_not(delivery_env):
    base, _, _, link = delivery_env
    with deliveries.transaction(base) as conn:
        first = _accept(conn, link)
    api.disconnect_output(link_id=link["link_id"], universe_id="u-sender")
    with deliveries.transaction(base) as conn:
        assert _accept(conn, link) == first
        with pytest.raises(receiver_links.ReceiverAccessDenied):
            _accept(conn, link, occurrence="new-after-disconnect")
    assert _counts(base) == (1, 1, 1)


def test_receiver_revision_does_not_change_accepted_snapshot(delivery_env):
    base, auth, receiver, link = delivery_env
    with deliveries.transaction(base) as conn:
        first = _accept(conn, link)
        before = dict(conn.execute("SELECT * FROM graph_deliveries").fetchone())
    auth("receiver")
    _save(receiver_id=receiver["receiver_id"], expected_generation=1, allowed_senders=[])
    with deliveries.transaction(base) as conn:
        assert _accept(conn, link) == first
        assert dict(conn.execute("SELECT * FROM graph_deliveries").fetchone()) == before
        with pytest.raises(receiver_links.ReceiverAccessDenied):
            _accept(conn, link, occurrence="new-after-removal")
    assert _counts(base) == (1, 1, 1)


@pytest.mark.parametrize(
    "principal, universe",
    [
        ("outsider", "u-outsider"),
        ("sender", "u-other"),
        ("receiver", "u-other"),
        ("", "u-sender"),
    ],
)
def test_receipt_scope_does_not_follow_identifier_knowledge(delivery_env, principal, universe):
    base, _, _, link = delivery_env
    with deliveries.transaction(base) as conn:
        receipt = _accept(conn, link)
        with pytest.raises((receiver_links.ReceiverAccessDenied, ValueError)):
            _read(conn, receipt, principal=principal, universe=universe)


@pytest.mark.parametrize("crash_point", ["after_intent", "after_run", "after_attempt"])
def test_failed_acceptance_rolls_back_intent_run_and_attempt(
    delivery_env, monkeypatch, crash_point
):
    base, _, _, link = delivery_env
    insert = runs._insert_run_in_transaction

    def fail_insert(*args, **kwargs):
        if crash_point == "after_run":
            insert(*args, **kwargs)
        raise RuntimeError("injected crash point")

    if crash_point != "after_attempt":
        monkeypatch.setattr(runs, "_insert_run_in_transaction", fail_insert)
    with pytest.raises(RuntimeError, match="injected crash point"):
        with deliveries.transaction(base) as conn:
            _accept(conn, link)
            raise RuntimeError("injected crash point")
    assert _counts(base) == (0, 0, 0)
    monkeypatch.setattr(runs, "_insert_run_in_transaction", insert)
    with deliveries.transaction(base) as conn:
        assert _accept(conn, link)["status"] == "accepted"
    assert _counts(base) == (1, 1, 1)


def test_corrupt_missing_attempt_is_not_reported_as_success(delivery_env):
    base, _, _, link = delivery_env
    with deliveries.transaction(base) as conn:
        receipt = _accept(conn, link)
        conn.execute("DELETE FROM graph_delivery_attempts")
        with pytest.raises(RuntimeError, match="missing its durable run reservation"):
            _read(conn, receipt)


@pytest.mark.parametrize(
    "values",
    [
        {"topic": b"not-json"},
        {"topic": float("nan")},
        {"topic": {1: "lossy key"}},
        {"topic": (1, 2)},
        {"topic": float("inf")},
    ],
)
def test_non_json_values_are_not_silently_rewritten(delivery_env, values):
    base, _, _, link = delivery_env
    with deliveries.transaction(base) as conn:
        with pytest.raises(ValueError):
            _accept(conn, link, values=values)
    assert _counts(base) == (0, 0, 0)


def test_acceptance_requires_an_explicit_transaction(delivery_env):
    base, _, _, link = delivery_env
    with sqlite3.connect(runs.runs_db_path(base)) as conn:
        with pytest.raises(ValueError, match="active caller-owned transaction"):
            _accept(conn, link)


def test_many_concurrent_retries_reserve_exactly_one_run(delivery_env):
    base, _, _, link = delivery_env

    def accept(_):
        with deliveries.transaction(base) as conn:
            return _accept(conn, link)

    with ThreadPoolExecutor(max_workers=4) as pool:
        receipts = list(pool.map(accept, range(12)))
    assert all(receipt == receipts[0] for receipt in receipts)
    assert _counts(base) == (1, 1, 1)


def _process_accept(base, link, ready, start, results):
    with deliveries.transaction(base):
        pass
    ready.put(True)
    if not start.wait(20):
        raise RuntimeError("test did not start competing acceptance")
    with deliveries.transaction(base) as conn:
        results.put(_accept(conn, link))


def test_separate_process_retries_share_one_durable_reservation(delivery_env):
    base, _, _, link = delivery_env
    context = multiprocessing.get_context("spawn")
    ready, results, start = context.Queue(), context.Queue(), context.Event()
    children = [
        context.Process(target=_process_accept, args=(base, link, ready, start, results))
        for _ in range(2)
    ]
    try:
        for child in children:
            child.start()
        for _ in children:
            assert ready.get(timeout=20)
        start.set()
        receipts = [results.get(timeout=20) for _ in children]
        for child in children:
            child.join(timeout=10)
            assert child.exitcode == 0
        assert receipts[0] == receipts[1]
        assert _counts(base) == (1, 1, 1)
    finally:
        for child in children:
            if child.is_alive():
                child.terminate()
                child.join(timeout=5)
        ready.close()
        results.close()


def _process_crash_at_acceptance(base, link, point):
    insert = runs._insert_run_in_transaction

    def crash_insert(*args, **kwargs):
        if point == "after_run":
            insert(*args, **kwargs)
        os._exit(73)

    if point in {"after_intent", "after_run"}:
        runs._insert_run_in_transaction = crash_insert
    with deliveries.transaction(base) as conn:
        _accept(conn, link)
        if point == "after_attempt":
            os._exit(73)
    # The sender never receives its response after this committed acceptance.
    os._exit(73)


@pytest.mark.parametrize("point", ["after_intent", "after_run", "after_attempt", "after_commit"])
def test_process_exit_during_acceptance_is_atomic_and_retryable(delivery_env, point):
    base, _, _, link = delivery_env
    child = multiprocessing.get_context("spawn").Process(
        target=_process_crash_at_acceptance,
        args=(base, link, point),
    )
    try:
        child.start()
        child.join(timeout=20)
        assert child.exitcode == 73
    finally:
        if child.is_alive():
            child.terminate()
            child.join(timeout=5)
    expected = (1, 1, 1) if point == "after_commit" else (0, 0, 0)
    assert _counts(base) == expected
    with deliveries.transaction(base) as conn:
        before = conn.execute("SELECT delivery_id FROM graph_deliveries").fetchone()
        receipt = _accept(conn, link)
        if before is not None:
            assert receipt["delivery_id"] == before[0]
    assert _counts(base) == (1, 1, 1)
