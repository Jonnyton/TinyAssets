"""Tests for workflow.payments schema layer — settlement tables + identifiers.

Spec: project_monetization_crypto_1pct (1% treasury fee, batch sub-$1 settlements)
      project_node_escrow_and_abandonment (escrow stays on node, not daemon)

Covers:
  * MicroToken: arithmetic, fee computation, batch threshold, validation.
  * Typed IDs: RunId, NodeId, ActorId, SettlementKey.build().
  * EscrowEntry: field validation, remaining, is_fully_released, from_row.
  * Settlement: net_amount invariant, build(), is_batchable, from_row.
  * BatchedTransaction: net_amount, is_flushable, from_row.
  * migrate_settlement_schema: idempotency + table presence.
  * DDL integration: insert + roundtrip via schema tables.
"""

from __future__ import annotations

import sqlite3

import pytest

from workflow.payments import (
    ActorId,
    BatchedTransaction,
    EscrowEntry,
    MicroToken,
    NodeId,
    RunId,
    Settlement,
    SettlementKey,
    migrate_settlement_schema,
)

# ── Fixtures ──────────────────────────────────────────────────────────────────

def _fresh_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    migrate_settlement_schema(conn)
    return conn


# ── MicroToken ────────────────────────────────────────────────────────────────

class TestMicroToken:
    def test_zero_ok(self):
        t = MicroToken(0)
        assert int(t) == 0

    def test_positive_ok(self):
        t = MicroToken(1_000_000)
        assert int(t) == 1_000_000

    def test_negative_raises(self):
        with pytest.raises(ValueError, match="MicroToken"):
            MicroToken(-1)

    def test_treasury_fee_one_percent(self):
        t = MicroToken(1_000_000)  # 1 Token
        assert int(t.treasury_fee()) == 10_000  # 1% = 10_000 MicroTokens

    def test_treasury_fee_zero_amount(self):
        t = MicroToken(0)
        assert int(t.treasury_fee()) == 0

    def test_net_after_fee(self):
        t = MicroToken(1_000_000)
        assert int(t.net_after_fee()) == 990_000

    def test_net_after_fee_small_amount(self):
        t = MicroToken(99)  # fee = 0 (integer division)
        assert int(t.net_after_fee()) == 99

    def test_is_batchable_below_threshold(self):
        t = MicroToken(999_999)
        assert t.is_batchable() is True

    def test_is_batchable_at_threshold(self):
        t = MicroToken(1_000_000)
        assert t.is_batchable() is False

    def test_is_batchable_above_threshold(self):
        t = MicroToken(2_000_000)
        assert t.is_batchable() is False

    def test_addition(self):
        a = MicroToken(100)
        b = a + 50
        assert isinstance(b, MicroToken)
        assert int(b) == 150

    def test_subtraction(self):
        a = MicroToken(100)
        b = a - 30
        assert isinstance(b, MicroToken)
        assert int(b) == 70

    def test_subtraction_underflow_raises(self):
        a = MicroToken(10)
        with pytest.raises(ValueError, match="negative"):
            a - 20

    def test_repr(self):
        assert "MicroToken" in repr(MicroToken(42))

    def test_fee_rounds_down(self):
        t = MicroToken(101)  # 1% = 1.01 → rounds down to 1
        assert int(t.treasury_fee()) == 1

    @pytest.mark.parametrize("amount,expected_fee", [
        (100, 1),
        (1000, 10),
        (10_000, 100),
        (1_000_000, 10_000),
        (0, 0),
    ])
    def test_fee_parametrized(self, amount: int, expected_fee: int):
        assert int(MicroToken(amount).treasury_fee()) == expected_fee


# ── Typed IDs ─────────────────────────────────────────────────────────────────

class TestTypedIds:
    def test_run_id_is_str(self):
        r = RunId("run-abc")
        assert isinstance(r, str)
        assert r == "run-abc"

    def test_node_id_is_str(self):
        n = NodeId("node-xyz")
        assert isinstance(n, str)

    def test_actor_id_is_str(self):
        a = ActorId("daemon-1")
        assert isinstance(a, str)

    def test_settlement_key_build(self):
        k = SettlementKey.build("run1", "node1", "actor1", "completion")
        assert k == "run1:node1:actor1:completion"

    def test_settlement_key_is_str(self):
        k = SettlementKey.build("r", "n", "a", "e")
        assert isinstance(k, str)

    def test_settlement_key_colon_in_component_raises(self):
        with pytest.raises(ValueError, match="':'"):
            SettlementKey.build("run:bad", "n", "a", "e")

    def test_repr_run_id(self):
        assert "RunId" in repr(RunId("r1"))

    def test_repr_node_id(self):
        assert "NodeId" in repr(NodeId("n1"))

    def test_repr_actor_id(self):
        assert "ActorId" in repr(ActorId("a1"))

    def test_repr_settlement_key(self):
        assert "SettlementKey" in repr(SettlementKey.build("r", "n", "a", "e"))


# ── EscrowEntry ───────────────────────────────────────────────────────────────

class TestEscrowEntry:
    def _entry(self, **kwargs) -> EscrowEntry:
        defaults = dict(
            escrow_id="esc-001",
            node_id=NodeId("node-1"),
            run_id=RunId("run-1"),
            staker_id=ActorId("staker-1"),
            total_amount=MicroToken(1_000_000),
            released_amount=MicroToken(0),
            status="locked",
            locked_at="2026-04-25T00:00:00Z",
        )
        defaults.update(kwargs)
        return EscrowEntry(**defaults)

    def test_defaults(self):
        e = self._entry()
        assert e.status == "locked"
        assert e.resolved_at is None

    def test_remaining(self):
        e = self._entry(total_amount=MicroToken(1_000_000), released_amount=MicroToken(300_000))
        assert int(e.remaining) == 700_000

    def test_is_fully_released_false(self):
        e = self._entry()
        assert e.is_fully_released is False

    def test_is_fully_released_true(self):
        e = self._entry(
            total_amount=MicroToken(500),
            released_amount=MicroToken(500),
        )
        assert e.is_fully_released is True

    def test_released_exceeds_total_raises(self):
        with pytest.raises(ValueError, match="released_amount"):
            self._entry(
                total_amount=MicroToken(100),
                released_amount=MicroToken(101),
            )

    def test_from_row(self):
        row = {
            "escrow_id": "e1",
            "node_id": "n1",
            "run_id": "r1",
            "staker_id": "s1",
            "total_amount": 1_000_000,
            "released_amount": 0,
            "status": "locked",
            "locked_at": "2026-04-25T00:00:00Z",
        }
        e = EscrowEntry.from_row(row)
        assert e.escrow_id == "e1"
        assert isinstance(e.total_amount, MicroToken)
        assert isinstance(e.node_id, NodeId)

    def test_from_row_missing_released_defaults_zero(self):
        row = {
            "escrow_id": "e1",
            "node_id": "n1",
            "run_id": "r1",
            "staker_id": "s1",
            "total_amount": 500_000,
            "status": "locked",
            "locked_at": "2026-04-25T00:00:00Z",
        }
        e = EscrowEntry.from_row(row)
        assert int(e.released_amount) == 0


# ── Settlement ────────────────────────────────────────────────────────────────

class TestSettlement:
    def test_build_computes_fee_and_net(self):
        s = Settlement.build(
            settlement_id="s1",
            escrow_id="e1",
            recipient_id="daemon-1",
            amount=1_000_000,
            event_type="completion",
            settlement_key="r:n:a:completion",
            created_at="2026-04-25T00:00:00Z",
        )
        assert int(s.treasury_fee) == 10_000
        assert int(s.net_amount) == 990_000
        assert s.status == "pending"

    def test_build_zero_amount(self):
        s = Settlement.build(
            settlement_id="s0",
            escrow_id="e0",
            recipient_id="r",
            amount=0,
            event_type="refund",
            settlement_key="r:n:a:refund",
            created_at="2026-04-25T00:00:00Z",
        )
        assert int(s.amount) == 0
        assert int(s.treasury_fee) == 0
        assert int(s.net_amount) == 0

    def test_net_amount_invariant_enforced(self):
        with pytest.raises(ValueError, match="net_amount"):
            Settlement(
                settlement_id="s1",
                escrow_id="e1",
                recipient_id=ActorId("r"),
                amount=MicroToken(1_000_000),
                treasury_fee=MicroToken(10_000),
                net_amount=MicroToken(999_000),  # wrong: should be 990_000
                status="pending",
                event_type="completion",
                settlement_key="k",
                created_at="2026-04-25T00:00:00Z",
            )

    def test_is_batchable_small(self):
        s = Settlement.build(
            settlement_id="s1", escrow_id="e1", recipient_id="r",
            amount=500_000, event_type="completion",
            settlement_key="k", created_at="2026-04-25T00:00:00Z",
        )
        assert s.is_batchable is True

    def test_is_batchable_large(self):
        s = Settlement.build(
            settlement_id="s1", escrow_id="e1", recipient_id="r",
            amount=1_500_000, event_type="completion",
            settlement_key="k", created_at="2026-04-25T00:00:00Z",
        )
        assert s.is_batchable is False

    def test_from_row(self):
        row = {
            "settlement_id": "s1",
            "escrow_id": "e1",
            "recipient_id": "d1",
            "amount": 1_000_000,
            "treasury_fee": 10_000,
            "net_amount": 990_000,
            "status": "pending",
            "event_type": "completion",
            "settlement_key": "r:n:a:completion",
            "created_at": "2026-04-25T00:00:00Z",
        }
        s = Settlement.from_row(row)
        assert s.settlement_id == "s1"
        assert isinstance(s.amount, MicroToken)
        assert isinstance(s.recipient_id, ActorId)


# ── BatchedTransaction ────────────────────────────────────────────────────────

class TestBatchedTransaction:
    def _batch(self, **kwargs) -> BatchedTransaction:
        defaults = dict(
            batch_id="batch-1",
            recipient_id=ActorId("daemon-1"),
            total_amount=MicroToken(800_000),
            total_fee=MicroToken(8_000),
            item_count=3,
            status="open",
            opened_at="2026-04-25T00:00:00Z",
        )
        defaults.update(kwargs)
        return BatchedTransaction(**defaults)

    def test_net_amount(self):
        b = self._batch(total_amount=MicroToken(800_000), total_fee=MicroToken(8_000))
        assert int(b.net_amount) == 792_000

    def test_is_flushable_below_threshold(self):
        b = self._batch(total_amount=MicroToken(800_000))
        assert b.is_flushable is False  # 800k < 1M threshold

    def test_is_flushable_above_threshold(self):
        b = self._batch(total_amount=MicroToken(1_100_000))
        assert b.is_flushable is True

    def test_from_row(self):
        row = {
            "batch_id": "b1",
            "recipient_id": "d1",
            "total_amount": 500_000,
            "total_fee": 5_000,
            "item_count": 2,
            "status": "open",
            "opened_at": "2026-04-25T00:00:00Z",
        }
        b = BatchedTransaction.from_row(row)
        assert b.batch_id == "b1"
        assert isinstance(b.total_amount, MicroToken)


# ── migrate_settlement_schema ─────────────────────────────────────────────────

class TestMigrateSettlementSchema:
    def _table_names(self, conn: sqlite3.Connection) -> set[str]:
        return {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }

    def test_all_tables_created(self):
        conn = _fresh_conn()
        tables = self._table_names(conn)
        assert "escrow_balance" in tables
        assert "pending_settlement" in tables
        assert "settlement_batch" in tables
        assert "transaction_log" in tables

    def test_idempotent_double_call(self):
        conn = _fresh_conn()
        migrate_settlement_schema(conn)
        tables = self._table_names(conn)
        assert "escrow_balance" in tables

    def test_idempotent_ten_calls(self):
        conn = _fresh_conn()
        for _ in range(10):
            migrate_settlement_schema(conn)
        tables = self._table_names(conn)
        assert len(tables) >= 4


# Legacy pending_settlement DDL — the pre-soft-ref shape with a HARD FK on
# escrow_id (REFERENCES escrow_balance). Used to reproduce slice1a review HIGH 3.
_LEGACY_PENDING_SETTLEMENT_DDL = """
CREATE TABLE escrow_balance (
    escrow_id       TEXT PRIMARY KEY,
    node_id         TEXT NOT NULL,
    run_id          TEXT NOT NULL,
    staker_id       TEXT NOT NULL,
    total_amount    INTEGER NOT NULL,
    released_amount INTEGER NOT NULL DEFAULT 0,
    status          TEXT NOT NULL DEFAULT 'locked',
    locked_at       TEXT NOT NULL,
    resolved_at     TEXT,
    UNIQUE (node_id, run_id, staker_id)
);
CREATE TABLE pending_settlement (
    settlement_id   TEXT PRIMARY KEY,
    escrow_id       TEXT NOT NULL REFERENCES escrow_balance(escrow_id),
    recipient_id    TEXT NOT NULL,
    amount          INTEGER NOT NULL CHECK (amount >= 0),
    treasury_fee    INTEGER NOT NULL DEFAULT 0,
    net_amount      INTEGER NOT NULL DEFAULT 0,
    status          TEXT NOT NULL DEFAULT 'pending',
    event_type      TEXT NOT NULL DEFAULT 'completion',
    settlement_key  TEXT NOT NULL UNIQUE,
    created_at      TEXT NOT NULL,
    settled_at      TEXT,
    batch_id        TEXT
);
"""


class TestLegacyFkMigration:
    """slice1a review HIGH 3: a DB created before the soft-ref change keeps the
    hard escrow_id FK, which rejects soft-ref settlement rows (lock_id / claim_id
    origins). migrate_settlement_schema must rebuild the table off the FK."""

    def _legacy_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.executescript(_LEGACY_PENDING_SETTLEMENT_DDL)
        # Seed one valid (escrow-backed) row so we can verify data is preserved.
        conn.execute(
            "INSERT INTO escrow_balance "
            "(escrow_id, node_id, run_id, staker_id, total_amount, locked_at) "
            "VALUES ('e1','n1','r1','s1',1000,'2026-06-08T00:00:00Z')"
        )
        conn.execute(
            "INSERT INTO pending_settlement "
            "(settlement_id, escrow_id, recipient_id, amount, treasury_fee, "
            " net_amount, status, event_type, settlement_key, created_at) "
            "VALUES ('s-old','e1','r1',1000,10,990,'settled','completion',"
            "'old-key','2026-06-08T00:00:00Z')"
        )
        return conn

    def test_legacy_db_rejects_soft_ref_before_migration(self):
        """Baseline: the legacy FK blocks a soft-ref row (proves the bug)."""
        conn = self._legacy_conn()
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO pending_settlement "
                "(settlement_id, escrow_id, recipient_id, amount, treasury_fee, "
                " net_amount, status, event_type, settlement_key, created_at) "
                "VALUES ('s-soft','lock-abc','r2',500,5,495,'settled',"
                "'escrow_release','soft-key','2026-06-08T00:00:00Z')"
            )

    def test_migration_drops_stale_fk_and_accepts_soft_ref(self):
        conn = self._legacy_conn()
        migrate_settlement_schema(conn)
        # FK is gone — a soft-ref row (escrow_id not in escrow_balance) inserts.
        conn.execute(
            "INSERT INTO pending_settlement "
            "(settlement_id, escrow_id, recipient_id, amount, treasury_fee, "
            " net_amount, status, event_type, settlement_key, created_at) "
            "VALUES ('s-soft','lock-abc','r2',500,5,495,'settled',"
            "'escrow_release','soft-key','2026-06-08T00:00:00Z')"
        )
        row = conn.execute(
            "SELECT * FROM pending_settlement WHERE settlement_id='s-soft'"
        ).fetchone()
        assert row is not None
        assert row["escrow_id"] == "lock-abc"

    def test_migration_preserves_existing_rows(self):
        conn = self._legacy_conn()
        migrate_settlement_schema(conn)
        row = conn.execute(
            "SELECT * FROM pending_settlement WHERE settlement_id='s-old'"
        ).fetchone()
        assert row is not None
        assert row["amount"] == 1000
        assert row["net_amount"] == 990
        assert row["settlement_key"] == "old-key"

    def test_migration_idempotent_on_already_migrated_db(self):
        conn = self._legacy_conn()
        migrate_settlement_schema(conn)
        # Second call must be a no-op (no stale FK left to rebuild) and keep data.
        migrate_settlement_schema(conn)
        rows = conn.execute(
            "SELECT COUNT(*) AS c FROM pending_settlement"
        ).fetchone()
        assert rows["c"] == 1

    def test_migration_noop_on_fresh_db(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        # Fresh DB — migration creates everything, then a soft-ref row inserts.
        migrate_settlement_schema(conn)
        conn.execute(
            "INSERT INTO pending_settlement "
            "(settlement_id, escrow_id, recipient_id, amount, treasury_fee, "
            " net_amount, status, event_type, settlement_key, created_at) "
            "VALUES ('s1','lock-x','r1',100,1,99,'settled','escrow_release',"
            "'k1','2026-06-08T00:00:00Z')"
        )
        row = conn.execute(
            "SELECT * FROM pending_settlement WHERE settlement_id='s1'"
        ).fetchone()
        assert row is not None


# ── Migration atomicity (slice1a review HIGH — round 2) ────────────────────────

class _FailingConn:
    """Thin proxy over a real sqlite3 connection that raises on a chosen SQL
    fragment, simulating a mid-rebuild crash. ``sqlite3.Connection.execute`` is
    a read-only C attribute and can't be monkeypatched, so the rebuild is driven
    through this proxy instead. All other attributes delegate to the real conn,
    so commit/rollback/in_transaction behave exactly as on the underlying DB."""

    def __init__(self, conn: sqlite3.Connection, *, fail_on: str) -> None:
        self._conn = conn
        self._fail_on = fail_on

    def execute(self, sql, *args, **kwargs):  # type: ignore[no-untyped-def]
        if self._fail_on in sql:
            raise sqlite3.OperationalError("simulated mid-rebuild failure")
        return self._conn.execute(sql, *args, **kwargs)

    def executescript(self, sql, *args, **kwargs):  # type: ignore[no-untyped-def]
        # Delegate verbatim. Pre-fix code creates the scratch table via
        # executescript() (implicit COMMIT) — we let that run so the test can
        # observe whether the scratch table leaks after a later failure.
        if self._fail_on in sql:
            raise sqlite3.OperationalError("simulated mid-rebuild failure")
        return self._conn.executescript(sql, *args, **kwargs)

    def __enter__(self):  # type: ignore[no-untyped-def]
        # Support `with conn:` (the pre-fix rebuild used this) by delegating the
        # transaction context to the real connection, so the test exercises the
        # genuine commit/rollback behavior and can observe a scratch-table leak.
        self._conn.__enter__()
        return self

    def __exit__(self, *exc):  # type: ignore[no-untyped-def]
        return self._conn.__exit__(*exc)

    def __getattr__(self, name):  # type: ignore[no-untyped-def]
        # Delegate commit / rollback / in_transaction / etc. to the real conn.
        return getattr(self._conn, name)


class TestRebuildAtomicity:
    """A mid-rebuild failure must leave NO scratch table and the original
    pending_settlement intact. The fix replaces executescript() (implicit
    COMMIT) with individual statements inside one explicit transaction plus a
    drop-on-failure cleanup."""

    def _legacy_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.executescript(_LEGACY_PENDING_SETTLEMENT_DDL)
        conn.execute(
            "INSERT INTO escrow_balance "
            "(escrow_id, node_id, run_id, staker_id, total_amount, locked_at) "
            "VALUES ('e1','n1','r1','s1',1000,'2026-06-08T00:00:00Z')"
        )
        conn.execute(
            "INSERT INTO pending_settlement "
            "(settlement_id, escrow_id, recipient_id, amount, treasury_fee, "
            " net_amount, status, event_type, settlement_key, created_at) "
            "VALUES ('s-old','e1','r1',1000,10,990,'settled','completion',"
            "'old-key','2026-06-08T00:00:00Z')"
        )
        conn.commit()
        return conn

    def _scratch_tables(self, conn: sqlite3.Connection) -> set[str]:
        return {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "AND name LIKE '%_new'"
            )
        }

    def test_pending_rebuild_failure_leaves_no_scratch_table(self):
        from workflow.payments import schema as schema_mod

        conn = self._legacy_conn()
        # Inject a failure AFTER the scratch table is created + populated but
        # BEFORE the swap commits, by wrapping the connection in a proxy that
        # raises on the copy-INSERT step. (sqlite3.Connection.execute is a
        # read-only C attribute and cannot be monkeypatched directly.)
        proxy = _FailingConn(conn, fail_on="INSERT INTO pending_settlement_new")
        with pytest.raises(sqlite3.OperationalError, match="simulated"):
            schema_mod._rebuild_pending_settlement(proxy)

        # No scratch table left behind, and the original survives intact.
        assert self._scratch_tables(conn) == set()
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        assert "pending_settlement" in tables
        row = conn.execute(
            "SELECT * FROM pending_settlement WHERE settlement_id='s-old'"
        ).fetchone()
        assert row is not None
        assert row["amount"] == 1000
        assert row["net_amount"] == 990

    def test_failed_rebuild_is_retryable_and_then_succeeds(self):
        from workflow.payments import schema as schema_mod

        conn = self._legacy_conn()
        proxy = _FailingConn(conn, fail_on="INSERT INTO pending_settlement_new")
        with pytest.raises(sqlite3.OperationalError):
            schema_mod._rebuild_pending_settlement(proxy)

        # A clean retry now completes (no leftover scratch table blocks it).
        schema_mod.migrate_settlement_schema(conn)
        assert self._scratch_tables(conn) == set()
        # Soft-ref row now accepted (FK gone) — original data still present.
        conn.execute(
            "INSERT INTO pending_settlement "
            "(settlement_id, escrow_id, recipient_id, amount, treasury_fee, "
            " net_amount, status, event_type, settlement_key, created_at) "
            "VALUES ('s-soft','lock-x','r2',500,5,495,'settled',"
            "'escrow_release','soft-key','2026-06-08T00:00:00Z')"
        )
        assert conn.execute(
            "SELECT COUNT(*) FROM pending_settlement"
        ).fetchone()[0] == 2


# Legacy settlement_batch DDL — the pre-round-2 shape whose status CHECK only
# allows open/flushed/failed and rejects the newer submitted/in_doubt states.
_LEGACY_SETTLEMENT_BATCH_DDL = """
CREATE TABLE settlement_batch (
    batch_id        TEXT PRIMARY KEY,
    recipient_id    TEXT NOT NULL,
    total_amount    INTEGER NOT NULL DEFAULT 0 CHECK (total_amount >= 0),
    total_fee       INTEGER NOT NULL DEFAULT 0 CHECK (total_fee >= 0),
    item_count      INTEGER NOT NULL DEFAULT 0,
    status          TEXT NOT NULL DEFAULT 'open'
                        CHECK (status IN ('open','flushed','failed')),
    opened_at       TEXT NOT NULL,
    flushed_at      TEXT
);
"""


class TestLegacyBatchStatusMigration:
    """slice1a review HIGH — round 2: a DB created before the in-doubt states
    keeps a status CHECK that rejects 'submitted'/'in_doubt'. The migration must
    rebuild settlement_batch to the wider CHECK while preserving rows."""

    def _legacy_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.executescript(_LEGACY_SETTLEMENT_BATCH_DDL)
        conn.execute(
            "INSERT INTO settlement_batch "
            "(batch_id, recipient_id, total_amount, status, opened_at) "
            "VALUES ('b-old','r1',1000,'flushed','2026-06-08T00:00:00Z')"
        )
        conn.commit()
        return conn

    def test_legacy_rejects_in_doubt_before_migration(self):
        conn = self._legacy_conn()
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO settlement_batch "
                "(batch_id, recipient_id, total_amount, status, opened_at) "
                "VALUES ('b-id','r1',500,'in_doubt','2026-06-08T00:00:00Z')"
            )

    def test_migration_widens_check_and_preserves_rows(self):
        conn = self._legacy_conn()
        migrate_settlement_schema(conn)
        # in_doubt / submitted now accepted.
        conn.execute(
            "INSERT INTO settlement_batch "
            "(batch_id, recipient_id, total_amount, status, opened_at) "
            "VALUES ('b-id','r1',500,'in_doubt','2026-06-08T00:00:00Z')"
        )
        conn.execute(
            "INSERT INTO settlement_batch "
            "(batch_id, recipient_id, total_amount, status, opened_at) "
            "VALUES ('b-sub','r1',300,'submitted','2026-06-08T00:00:00Z')"
        )
        # Original row preserved.
        row = conn.execute(
            "SELECT * FROM settlement_batch WHERE batch_id='b-old'"
        ).fetchone()
        assert row is not None
        assert row["total_amount"] == 1000
        assert row["status"] == "flushed"
        assert conn.execute(
            "SELECT COUNT(*) FROM settlement_batch"
        ).fetchone()[0] == 3

    def test_migration_idempotent_on_already_widened_db(self):
        conn = self._legacy_conn()
        migrate_settlement_schema(conn)
        # Second call is a no-op: no legacy CHECK left, scratch table absent.
        migrate_settlement_schema(conn)
        assert {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "AND name LIKE '%_new'"
            )
        } == set()
        assert conn.execute(
            "SELECT COUNT(*) FROM settlement_batch"
        ).fetchone()[0] == 1

    def test_fresh_db_accepts_in_doubt(self):
        conn = _fresh_conn()
        conn.execute(
            "INSERT INTO settlement_batch "
            "(batch_id, recipient_id, total_amount, status, opened_at) "
            "VALUES ('b1','r1',100,'in_doubt','2026-06-08T00:00:00Z')"
        )
        row = conn.execute(
            "SELECT status FROM settlement_batch WHERE batch_id='b1'"
        ).fetchone()
        assert row["status"] == "in_doubt"


# ── DDL integration ───────────────────────────────────────────────────────────

class TestDDLIntegration:
    def test_insert_escrow_balance(self):
        conn = _fresh_conn()
        conn.execute(
            "INSERT INTO escrow_balance "
            "(escrow_id, node_id, run_id, staker_id, total_amount, locked_at) "
            "VALUES (?,?,?,?,?,?)",
            ("e1", "n1", "r1", "s1", 1_000_000, "2026-04-25T00:00:00Z"),
        )
        row = conn.execute(
            "SELECT * FROM escrow_balance WHERE escrow_id='e1'"
        ).fetchone()
        assert row is not None
        assert row["total_amount"] == 1_000_000
        assert row["released_amount"] == 0
        assert row["status"] == "locked"

    def test_insert_pending_settlement(self):
        conn = _fresh_conn()
        conn.execute(
            "INSERT INTO escrow_balance "
            "(escrow_id, node_id, run_id, staker_id, total_amount, locked_at) "
            "VALUES (?,?,?,?,?,?)",
            ("e1", "n1", "r1", "s1", 1_000_000, "2026-04-25T00:00:00Z"),
        )
        conn.execute(
            "INSERT INTO pending_settlement "
            "(settlement_id, escrow_id, recipient_id, amount, treasury_fee, "
            "net_amount, settlement_key, created_at) VALUES (?,?,?,?,?,?,?,?)",
            ("ps1", "e1", "d1", 1_000_000, 10_000, 990_000,
             "r1:n1:d1:completion", "2026-04-25T01:00:00Z"),
        )
        row = conn.execute(
            "SELECT * FROM pending_settlement WHERE settlement_id='ps1'"
        ).fetchone()
        assert row["amount"] == 1_000_000
        assert row["status"] == "pending"

    def test_duplicate_settlement_key_rejected(self):
        conn = _fresh_conn()
        conn.execute(
            "INSERT INTO escrow_balance "
            "(escrow_id, node_id, run_id, staker_id, total_amount, locked_at) "
            "VALUES (?,?,?,?,?,?)",
            ("e1", "n1", "r1", "s1", 1_000_000, "2026-04-25T00:00:00Z"),
        )
        conn.execute(
            "INSERT INTO pending_settlement "
            "(settlement_id, escrow_id, recipient_id, amount, treasury_fee, "
            "net_amount, settlement_key, created_at) VALUES (?,?,?,?,?,?,?,?)",
            ("ps1", "e1", "d1", 100, 1, 99, "unique-key", "2026-04-25T01:00:00Z"),
        )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO pending_settlement "
                "(settlement_id, escrow_id, recipient_id, amount, treasury_fee, "
                "net_amount, settlement_key, created_at) VALUES (?,?,?,?,?,?,?,?)",
                ("ps2", "e1", "d2", 200, 2, 198, "unique-key", "2026-04-25T01:00:00Z"),
            )

    def test_insert_batch(self):
        conn = _fresh_conn()
        conn.execute(
            "INSERT INTO settlement_batch "
            "(batch_id, recipient_id, opened_at) VALUES (?,?,?)",
            ("batch-1", "daemon-1", "2026-04-25T00:00:00Z"),
        )
        row = conn.execute(
            "SELECT * FROM settlement_batch WHERE batch_id='batch-1'"
        ).fetchone()
        assert row["status"] == "open"
        assert row["item_count"] == 0

    def test_transaction_log_autoincrement(self):
        conn = _fresh_conn()
        for _ in range(3):
            conn.execute(
                "INSERT INTO transaction_log "
                "(kind, actor_id, recorded_at) VALUES (?,?,?)",
                ("lock", "actor-1", "2026-04-25T00:00:00Z"),
            )
        count = conn.execute(
            "SELECT COUNT(*) FROM transaction_log"
        ).fetchone()[0]
        assert count == 3

    def test_negative_amount_rejected_by_check(self):
        conn = _fresh_conn()
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO escrow_balance "
                "(escrow_id, node_id, run_id, staker_id, total_amount, locked_at) "
                "VALUES (?,?,?,?,?,?)",
                ("e-bad", "n1", "r1", "s1", -100, "2026-04-25T00:00:00Z"),
            )

    def test_escrow_roundtrip_via_from_row(self):
        conn = _fresh_conn()
        conn.execute(
            "INSERT INTO escrow_balance "
            "(escrow_id, node_id, run_id, staker_id, total_amount, locked_at) "
            "VALUES (?,?,?,?,?,?)",
            ("e-rt", "n-rt", "r-rt", "s-rt", 2_000_000, "2026-04-25T00:00:00Z"),
        )
        row = dict(conn.execute(
            "SELECT * FROM escrow_balance WHERE escrow_id='e-rt'"
        ).fetchone())
        entry = EscrowEntry.from_row(row)
        assert entry.escrow_id == "e-rt"
        assert int(entry.total_amount) == 2_000_000
        assert int(entry.remaining) == 2_000_000
