from __future__ import annotations

import sqlite3
from concurrent.futures import Future
from pathlib import Path

import pytest

from tests.cloud_runtime_fixture import cloud_runtime  # noqa: F401
from tests.test_background_budget_finalization_e2e import (
    _seed_serving_assignment,
)
from tinyassets.api.universe import (
    _classify_epoch2_workers,
)
from tinyassets.runtime.assigned_queue_consumer import (
    AssignedQueueConsumer,
    supervisor_heartbeat_filename,
)
from tinyassets.storage import db_path

pytestmark = pytest.mark.usefixtures("cloud_runtime")


SERVING_UNIVERSE = "universe_alice"


class _DeferredExecutor:
    def __init__(self) -> None:
        self.future: Future[None] | None = None
        self.job = None

    def submit(self, fn, *args):
        self.future = Future()
        self.job = (fn, args)
        return self.future

    def run(self) -> None:
        assert self.future is not None and self.job is not None
        fn, args = self.job
        try:
            fn(*args)
        except BaseException as exc:
            self.future.set_exception(exc)
            raise
        else:
            self.future.set_result(None)

    def shutdown(self, **_kwargs) -> None:
        pass


def test_flag_off_poll_leaves_no_beat_or_refusal_side_effect(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _seed_serving_assignment(tmp_path)
    monkeypatch.delenv("TINYASSETS_ASSIGNED_QUEUE_CONSUMER", raising=False)
    consumer = AssignedQueueConsumer(tmp_path, max_concurrency=1)

    try:
        assert consumer.poll_once() == 0
    finally:
        consumer.stop()

    assert list((tmp_path / SERVING_UNIVERSE).glob(".worker_supervisor*.json")) == []
    with sqlite3.connect(db_path(tmp_path)) as conn:
        refusal_table = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' "
            "AND name = 'assigned_queue_refusals'"
        ).fetchone()
    assert refusal_table is None


def test_flag_on_poll_publishes_the_beat_but_registers_no_fleet_worker(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """The beat is what the watchdog reads, so it always goes out. The fleet-era
    runtime row and queue descriptor retired with the legacy pump (plan C1):
    the consumer no longer advertises itself as a fleet worker."""
    _seed_serving_assignment(tmp_path)
    # The epoch-2 queue store exists on every served daemon; its claim pass
    # reads it until plan C3 retires that pass.
    from tinyassets.storage.request_admissions import migrate_request_admission_schema

    with sqlite3.connect(db_path(tmp_path)) as conn:
        migrate_request_admission_schema(conn)
    monkeypatch.setenv("TINYASSETS_ASSIGNED_QUEUE_CONSUMER", "1")
    consumer = AssignedQueueConsumer(tmp_path, max_concurrency=1)

    try:
        consumer.poll_once()
        workers, _evidence = _classify_epoch2_workers(tmp_path / SERVING_UNIVERSE)
    finally:
        consumer.stop()

    assert workers == []
    assert (
        tmp_path / SERVING_UNIVERSE / supervisor_heartbeat_filename(consumer.consumer_id)
    ).is_file()


def _refusal_reason(base: Path, branch_task_id: str) -> str | None:
    with sqlite3.connect(db_path(base)) as conn:
        row = conn.execute(
            "SELECT reason FROM assigned_queue_refusals WHERE branch_task_id = ?",
            (branch_task_id,),
        ).fetchone()
    return None if row is None else str(row[0])


def test_error_reason_sanitises_paths_and_long_tokens():
    """The ledger row is the only place prod can show a cause, so it carries the
    message - with filesystem paths and secret-shaped tokens stripped."""
    from tinyassets.runtime.assigned_queue_consumer import _error_reason

    reason = _error_reason(
        "prepare_error",
        PermissionError("denied for C:/Users/someone/data/vault.json"),
    )
    assert reason.startswith("prepare_error:PermissionError:")
    assert "C:/Users" not in reason and "<path>" in reason
    token = _error_reason("produce_error", RuntimeError("token sk-" + "a" * 40))
    assert "<redacted>" in token and "a" * 40 not in token
    assert len(_error_reason("x", RuntimeError("y" * 500))) < 200
    assert _error_reason("prepare_error", PermissionError()) == (
        "prepare_error:PermissionError"
    )
