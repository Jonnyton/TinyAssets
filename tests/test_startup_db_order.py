"""Serving startup initializes `.runs.db` before any background thread opens it.

CI 35650830517 failed entering `TestClient(create_streamable_http_app())` on a
fresh `tmp_path`: `initialize_consumer` -> `initialize_runs_db` ->
`PRAGMA journal_mode = WAL` raised `database is locked` in 0.024 s, on a
connection carrying a 30 s timeout. SQLite skips the busy handler when a lock
upgrade would deadlock, so the *first* WAL switch on a brand-new file fails
instantly against a concurrent switcher or a held RESERVED lock -- which is
exactly what the scheduler's first action takes (`scheduler._connect` sets WAL
and then runs `migrate_scheduler_schema`, a write transaction). Once the file is
WAL the pragma is a no-op and the race cannot happen, so only fresh data dirs
bite.

The stand-in below is not a mock of locking: it is a real `sqlite3` connection
holding a real write transaction on the real `.runs.db` path, taken at the exact
point the production code starts the scheduler. Ordering is what makes the
difference -- with initialization first, the file is already WAL by the time the
background reader attaches, and no lock state it can hold blocks the switch.
"""

from __future__ import annotations

import sqlite3
import threading

import pytest
from starlette.testclient import TestClient


class SchedulerLikeWriter:
    """A background reader that grabs `.runs.db` the way the scheduler does.

    `scheduler._connect` opens the file, switches it to WAL and runs the
    scheduler migration, so between those statements it holds a RESERVED write
    lock. This models that window with a real connection and real locking, and
    signals when the lock is held so the test never sleeps to synchronize.
    """

    def __init__(self, db_path):
        self.db_path = db_path
        self.attached = threading.Event()
        self.journal_mode_when_attached: str | None = None
        self._conn: sqlite3.Connection | None = None

    def attach(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.db_path, timeout=5.0)
        self.journal_mode_when_attached = str(
            self._conn.execute("PRAGMA journal_mode").fetchone()[0]
        ).lower()
        # RESERVED: held by the scheduler migration's CREATE/ALTER before commit.
        self._conn.execute("BEGIN IMMEDIATE")
        self._conn.execute("CREATE TABLE IF NOT EXISTS _scheduler_probe(x)")
        self.attached.set()

    def release(self) -> None:
        if self._conn is not None:
            try:
                self._conn.rollback()
            finally:
                self._conn.close()
                self._conn = None


@pytest.fixture
def fresh_data_dir(tmp_path, monkeypatch):
    """A data dir with no `.runs.db` yet -- the only state the race needs."""
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
    from tinyassets.runs import runs_db_path

    db = runs_db_path(tmp_path)
    assert not db.exists(), "the race only exists on a database that is not yet WAL"
    return tmp_path


def _journal_mode(db_path) -> str:
    conn = sqlite3.connect(db_path, timeout=5.0)
    try:
        return str(conn.execute("PRAGMA journal_mode").fetchone()[0]).lower()
    finally:
        conn.close()


def test_http_lifespan_initializes_runs_db_before_the_scheduler_attaches(
    fresh_data_dir, monkeypatch
):
    """Entering the production HTTP lifespan on a fresh data dir must not race.

    RED before the fix: `start_scheduler_for_serving` runs first, the stand-in
    holds the write lock, and `initialize_consumer`'s `PRAGMA journal_mode=WAL`
    raises `database is locked` out of `TestClient.__enter__`.
    """
    from tinyassets import universe_server as us
    from tinyassets.runs import runs_db_path

    db = runs_db_path(fresh_data_dir)
    writer = SchedulerLikeWriter(db)

    def _start_scheduler_stand_in() -> bool:
        writer.attach()
        return True

    monkeypatch.setattr(us, "start_scheduler_for_serving", _start_scheduler_stand_in)
    monkeypatch.setattr(us, "stop_scheduler_for_serving", writer.release)

    app = us.create_streamable_http_app()
    try:
        with TestClient(app):
            pass
    finally:
        writer.release()

    assert writer.attached.is_set(), "the stand-in scheduler never started"
    assert writer.journal_mode_when_attached == "wal", (
        "the scheduler attached to a database that had not been initialized yet; "
        f"journal_mode was {writer.journal_mode_when_attached!r}"
    )
    assert _journal_mode(db) == "wal"


def test_http_lifespan_orders_initialization_before_background_work(
    fresh_data_dir, monkeypatch
):
    """The ordering itself, independent of whether SQLite happens to lock."""
    from tinyassets import consumer_runtime
    from tinyassets import universe_server as us

    order: list[str] = []
    real_initialize = consumer_runtime.initialize

    def _record_initialize(base):
        order.append("initialize")
        return real_initialize(base)

    monkeypatch.setattr(consumer_runtime, "initialize", _record_initialize)
    monkeypatch.setattr(
        us, "start_scheduler_for_serving", lambda: (order.append("scheduler"), True)[1]
    )
    monkeypatch.setattr(us, "stop_scheduler_for_serving", lambda: None)

    with TestClient(us.create_streamable_http_app()):
        pass

    assert order == ["initialize", "scheduler"], order


def test_sse_stdio_startup_initializes_before_the_assigned_consumer_starts(
    fresh_data_dir, monkeypatch
):
    """The second serving entrypoint has the same ordering obligation.

    `main`'s sse/stdio path starts `AssignedQueueConsumer` -- a polling
    thread -- before `initialize_consumer`. Fixing only the HTTP lifespan would
    leave this race in place.

    The earlier boot-maintenance block (`universe_server.py:4126-4131`) usually
    initializes first and hides this, but it swallows its own failure
    (`except Exception: logger.exception(...)`). So the first initialize here
    raises, exactly as that swallowed path leaves things, and the serving block
    must still initialize before it starts a background consumer.
    """
    from tinyassets import consumer_runtime
    from tinyassets import universe_server as us
    from tinyassets.runtime import assigned_queue_consumer as aqc

    order: list[str] = []
    real_initialize = consumer_runtime.initialize
    calls = {"n": 0}

    def _record_initialize(base):
        calls["n"] += 1
        if calls["n"] == 1:
            order.append("initialize_swallowed")
            raise sqlite3.OperationalError("database is locked")
        order.append("initialize")
        return real_initialize(base)

    class _RecordingConsumer:
        def __init__(self, base):
            self.base = base

        def start(self):
            order.append("assigned_consumer")

        def stop(self):
            order.append("assigned_consumer_stop")

    monkeypatch.setattr(consumer_runtime, "initialize", _record_initialize)
    monkeypatch.setattr(aqc, "assigned_queue_consumer_enabled", lambda: True)
    monkeypatch.setattr(aqc, "AssignedQueueConsumer", _RecordingConsumer)
    monkeypatch.setattr(us.mcp, "run", lambda *a, **k: order.append("serve"))

    us.main(transport="stdio")

    assert order[:3] == [
        "initialize_swallowed",
        "initialize",
        "assigned_consumer",
    ], order
    assert "serve" in order, order
    assert order[-1] == "assigned_consumer_stop", (
        "teardown must still stop the consumer it started: " f"{order}"
    )


def test_initializing_a_fresh_runs_db_under_a_held_write_lock_fails_fast():
    """Executable spec for WHY the ordering matters -- do not let this go vacuous.

    A 30 s busy timeout does not save the loser: the WAL switch on a fresh file
    needs a lock upgrade, and SQLite returns SQLITE_BUSY without invoking the
    busy handler. If this test ever stops failing, the ordering tests above stop
    proving anything and the reason for the ordering has changed.
    """
    import tempfile
    from pathlib import Path

    from tinyassets import runs

    base = Path(tempfile.mkdtemp())
    writer = SchedulerLikeWriter(runs.runs_db_path(base))
    writer.attach()
    try:
        with pytest.raises(sqlite3.OperationalError, match="database is locked"):
            runs.initialize_runs_db(base)
    finally:
        writer.release()
