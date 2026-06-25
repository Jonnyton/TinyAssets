"""Settlement schema — DDL and dataclasses for the paid-market settlement layer.

Spec: project_monetization_crypto_1pct + project_node_escrow_and_abandonment.

Five tables:
  staker_escrow_budget — per-staker funded budget backing escrow reservations
  escrow_balance     — per-node locked funds (node is the escrow holder)
  pending_settlement — individual settlement events awaiting batch or direct settle
  settlement_batch   — grouped settlements flushed together (sub-$1 batching)
  transaction_log    — immutable append-only audit trail for every state change

Treasury fee (1%) is computed at settlement time from MicroToken.treasury_fee().
Batch threshold: pending_settlements with amount < 1 Token defer to a batch.

All amounts are stored as INTEGER (MicroTokens) — never REAL/FLOAT.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from workflow.payments.identifiers import ActorId, MicroToken, NodeId, RunId

# ── Status enums ──────────────────────────────────────────────────────────────

EscrowBalanceStatus = Literal["locked", "released", "refunded", "partial"]
SettlementStatus = Literal["pending", "batched", "settled", "cancelled"]
# 'submitted' — payout handed to the backend, outcome not yet confirmed
#               (durable pre-settle reservation; see action_escrow_withdraw).
# 'in_doubt'  — backend errored with an UNKNOWN result; the payout may or may
#               not have landed and must be reconciled (never auto-refunded).
BatchStatus = Literal[
    "open", "submitted", "flushed", "failed", "in_doubt"
]
_BATCH_STATUS_VALUES = ("open", "submitted", "flushed", "failed", "in_doubt")
TransactionKind = Literal[
    "lock", "release", "refund", "fee", "checkpoint_partial", "batch_flush"
]

# ── DDL ───────────────────────────────────────────────────────────────────────

STAKER_ESCROW_BUDGET_SCHEMA = """
CREATE TABLE IF NOT EXISTS staker_escrow_budget (
    staker_id       TEXT NOT NULL,
    currency        TEXT NOT NULL,
    total_amount    INTEGER NOT NULL DEFAULT 0 CHECK (total_amount >= 0),
    reserved_amount INTEGER NOT NULL DEFAULT 0 CHECK (reserved_amount >= 0),
    updated_at      TEXT NOT NULL,
    PRIMARY KEY (staker_id, currency),
    CHECK (reserved_amount <= total_amount)
);

CREATE INDEX IF NOT EXISTS idx_staker_escrow_budget_currency
    ON staker_escrow_budget(currency);
"""

PAYOUT_WALLET_SCHEMA = """
CREATE TABLE IF NOT EXISTS payout_wallet (
    actor_id    TEXT NOT NULL,
    chain_id    INTEGER NOT NULL,
    address     TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    PRIMARY KEY (actor_id, chain_id)
);
"""

SETTLEMENT_SCHEMA = """
CREATE TABLE IF NOT EXISTS escrow_balance (
    escrow_id       TEXT PRIMARY KEY,
    node_id         TEXT NOT NULL,
    run_id          TEXT NOT NULL,
    staker_id       TEXT NOT NULL,
    total_amount    INTEGER NOT NULL CHECK (total_amount >= 0),
    released_amount INTEGER NOT NULL DEFAULT 0 CHECK (released_amount >= 0),
    status          TEXT NOT NULL DEFAULT 'locked'
                        CHECK (status IN ('locked','released','refunded','partial')),
    locked_at       TEXT NOT NULL,
    resolved_at     TEXT,
    UNIQUE (node_id, run_id, staker_id)
);

CREATE INDEX IF NOT EXISTS idx_escrow_node
    ON escrow_balance(node_id);

CREATE INDEX IF NOT EXISTS idx_escrow_run
    ON escrow_balance(run_id);

CREATE TABLE IF NOT EXISTS pending_settlement (
    settlement_id   TEXT PRIMARY KEY,
    -- Soft reference to the originating lock. Settlements come from multiple
    -- lock sources (escrow_locks, gate_claims, paid bids), not just
    -- escrow_balance, so this is intentionally not a hard FK.
    escrow_id       TEXT NOT NULL,
    recipient_id    TEXT NOT NULL,
    amount          INTEGER NOT NULL CHECK (amount >= 0),
    treasury_fee    INTEGER NOT NULL DEFAULT 0 CHECK (treasury_fee >= 0),
    net_amount      INTEGER NOT NULL DEFAULT 0 CHECK (net_amount >= 0),
    status          TEXT NOT NULL DEFAULT 'pending'
                        CHECK (status IN ('pending','batched','settled','cancelled')),
    event_type      TEXT NOT NULL DEFAULT 'completion',
    settlement_key  TEXT NOT NULL UNIQUE,
    created_at      TEXT NOT NULL,
    settled_at      TEXT,
    batch_id        TEXT
);

CREATE INDEX IF NOT EXISTS idx_settlement_escrow
    ON pending_settlement(escrow_id);

CREATE INDEX IF NOT EXISTS idx_settlement_status
    ON pending_settlement(status);

CREATE TABLE IF NOT EXISTS settlement_batch (
    batch_id        TEXT PRIMARY KEY,
    recipient_id    TEXT NOT NULL,
    total_amount    INTEGER NOT NULL DEFAULT 0 CHECK (total_amount >= 0),
    total_fee       INTEGER NOT NULL DEFAULT 0 CHECK (total_fee >= 0),
    item_count      INTEGER NOT NULL DEFAULT 0,
    status          TEXT NOT NULL DEFAULT 'open'
                        CHECK (status IN
                            ('open','submitted','flushed','failed','in_doubt')),
    opened_at       TEXT NOT NULL,
    flushed_at      TEXT
);

CREATE INDEX IF NOT EXISTS idx_batch_recipient
    ON settlement_batch(recipient_id);

CREATE INDEX IF NOT EXISTS idx_batch_status
    ON settlement_batch(status);

CREATE TABLE IF NOT EXISTS transaction_log (
    tx_id           INTEGER PRIMARY KEY AUTOINCREMENT,
    kind            TEXT NOT NULL
                        CHECK (kind IN (
                            'lock','release','refund','fee',
                            'checkpoint_partial','batch_flush'
                        )),
    escrow_id       TEXT,
    settlement_id   TEXT,
    batch_id        TEXT,
    actor_id        TEXT NOT NULL,
    amount          INTEGER NOT NULL DEFAULT 0,
    recorded_at     TEXT NOT NULL,
    note            TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_txlog_escrow
    ON transaction_log(escrow_id);

CREATE INDEX IF NOT EXISTS idx_txlog_recorded
    ON transaction_log(recorded_at);
"""

# ── Dataclasses ───────────────────────────────────────────────────────────────

@dataclass
class StakerEscrowBudget:
    """Spendable and reserved escrow funds for one staker/currency pair."""

    staker_id: ActorId
    currency: str
    total_amount: MicroToken
    reserved_amount: MicroToken
    updated_at: str

    def __post_init__(self) -> None:
        if int(self.reserved_amount) > int(self.total_amount):
            raise ValueError(
                f"reserved_amount ({self.reserved_amount}) cannot exceed "
                f"total_amount ({self.total_amount})"
            )

    @property
    def spendable_amount(self) -> int:
        return int(self.total_amount) - int(self.reserved_amount)

    @classmethod
    def from_row(cls, row) -> "StakerEscrowBudget":  # type: ignore[no-untyped-def]
        d = dict(row)
        return cls(
            staker_id=ActorId(d["staker_id"]),
            currency=d["currency"],
            total_amount=MicroToken(int(d.get("total_amount") or 0)),
            reserved_amount=MicroToken(int(d.get("reserved_amount") or 0)),
            updated_at=d["updated_at"],
        )


@dataclass
class EscrowEntry:
    """One node's locked escrow balance."""

    escrow_id: str
    node_id: NodeId
    run_id: RunId
    staker_id: ActorId
    total_amount: MicroToken
    released_amount: MicroToken
    status: EscrowBalanceStatus
    locked_at: str
    resolved_at: str | None = None

    def __post_init__(self) -> None:
        if int(self.released_amount) > int(self.total_amount):
            raise ValueError(
                f"released_amount ({self.released_amount}) cannot exceed "
                f"total_amount ({self.total_amount})"
            )

    @property
    def remaining(self) -> MicroToken:
        return MicroToken(int(self.total_amount) - int(self.released_amount))

    @property
    def is_fully_released(self) -> bool:
        return int(self.released_amount) >= int(self.total_amount)

    @classmethod
    def from_row(cls, row: dict) -> EscrowEntry:
        return cls(
            escrow_id=row["escrow_id"],
            node_id=NodeId(row["node_id"]),
            run_id=RunId(row["run_id"]),
            staker_id=ActorId(row["staker_id"]),
            total_amount=MicroToken(int(row["total_amount"])),
            released_amount=MicroToken(int(row.get("released_amount") or 0)),
            status=row.get("status") or "locked",  # type: ignore[arg-type]
            locked_at=row["locked_at"],
            resolved_at=row.get("resolved_at"),
        )


@dataclass
class Settlement:
    """One pending or completed settlement event."""

    settlement_id: str
    escrow_id: str
    recipient_id: ActorId
    amount: MicroToken
    treasury_fee: MicroToken
    net_amount: MicroToken
    status: SettlementStatus
    event_type: str
    settlement_key: str
    created_at: str
    settled_at: str | None = None
    batch_id: str | None = None

    def __post_init__(self) -> None:
        expected_net = MicroToken(int(self.amount) - int(self.treasury_fee))
        if int(self.net_amount) != int(expected_net):
            raise ValueError(
                f"net_amount ({self.net_amount}) must equal "
                f"amount - treasury_fee ({self.amount} - {self.treasury_fee} "
                f"= {expected_net})"
            )

    @property
    def is_batchable(self) -> bool:
        return self.amount.is_batchable()

    @classmethod
    def build(
        cls,
        *,
        settlement_id: str,
        escrow_id: str,
        recipient_id: str,
        amount: int,
        event_type: str,
        settlement_key: str,
        created_at: str,
    ) -> Settlement:
        """Construct Settlement with auto-computed fee and net_amount."""
        amt = MicroToken(amount)
        fee = amt.treasury_fee()
        net = amt.net_after_fee()
        return cls(
            settlement_id=settlement_id,
            escrow_id=escrow_id,
            recipient_id=ActorId(recipient_id),
            amount=amt,
            treasury_fee=fee,
            net_amount=net,
            status="pending",
            event_type=event_type,
            settlement_key=settlement_key,
            created_at=created_at,
        )

    @classmethod
    def from_row(cls, row: dict) -> Settlement:
        return cls(
            settlement_id=row["settlement_id"],
            escrow_id=row["escrow_id"],
            recipient_id=ActorId(row["recipient_id"]),
            amount=MicroToken(int(row["amount"])),
            treasury_fee=MicroToken(int(row.get("treasury_fee") or 0)),
            net_amount=MicroToken(int(row.get("net_amount") or 0)),
            status=row.get("status") or "pending",  # type: ignore[arg-type]
            event_type=row.get("event_type") or "completion",
            settlement_key=row["settlement_key"],
            created_at=row["created_at"],
            settled_at=row.get("settled_at"),
            batch_id=row.get("batch_id"),
        )


@dataclass
class BatchedTransaction:
    """Grouped settlement batch for sub-threshold amounts."""

    batch_id: str
    recipient_id: ActorId
    total_amount: MicroToken
    total_fee: MicroToken
    item_count: int
    status: BatchStatus
    opened_at: str
    flushed_at: str | None = None
    items: list[str] = field(default_factory=list)

    @property
    def net_amount(self) -> MicroToken:
        return MicroToken(int(self.total_amount) - int(self.total_fee))

    @property
    def is_flushable(self) -> bool:
        return not self.total_amount.is_batchable()

    @classmethod
    def from_row(cls, row: dict) -> BatchedTransaction:
        return cls(
            batch_id=row["batch_id"],
            recipient_id=ActorId(row["recipient_id"]),
            total_amount=MicroToken(int(row.get("total_amount") or 0)),
            total_fee=MicroToken(int(row.get("total_fee") or 0)),
            item_count=int(row.get("item_count") or 0),
            status=row.get("status") or "open",  # type: ignore[arg-type]
            opened_at=row["opened_at"],
            flushed_at=row.get("flushed_at"),
        )


# ── Migration ─────────────────────────────────────────────────────────────────

# New (soft-ref) shape for pending_settlement — no hard FK on escrow_id, since
# settlements originate from multiple lock sources (escrow_locks, gate_claims,
# paid bids), not just escrow_balance. Used by the rebuild migration below.
_PENDING_SETTLEMENT_NEW_DDL = """
CREATE TABLE pending_settlement (
    settlement_id   TEXT PRIMARY KEY,
    escrow_id       TEXT NOT NULL,
    recipient_id    TEXT NOT NULL,
    amount          INTEGER NOT NULL CHECK (amount >= 0),
    treasury_fee    INTEGER NOT NULL DEFAULT 0 CHECK (treasury_fee >= 0),
    net_amount      INTEGER NOT NULL DEFAULT 0 CHECK (net_amount >= 0),
    status          TEXT NOT NULL DEFAULT 'pending'
                        CHECK (status IN ('pending','batched','settled','cancelled')),
    event_type      TEXT NOT NULL DEFAULT 'completion',
    settlement_key  TEXT NOT NULL UNIQUE,
    created_at      TEXT NOT NULL,
    settled_at      TEXT,
    batch_id        TEXT
);
"""

_PENDING_SETTLEMENT_COLUMNS = (
    "settlement_id", "escrow_id", "recipient_id", "amount", "treasury_fee",
    "net_amount", "status", "event_type", "settlement_key", "created_at",
    "settled_at", "batch_id",
)


def _pending_settlement_has_stale_fk(conn) -> bool:  # type: ignore[no-untyped-def]
    """True when an existing pending_settlement carries the legacy hard FK on
    escrow_id (``REFERENCES escrow_balance(escrow_id)``).

    DBs created before the soft-ref migration keep this FK, which rejects
    soft-ref settlement rows (lock_id / claim_id origins) under
    ``PRAGMA foreign_keys = ON``. Returns False if the table is absent.
    """
    exists = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='pending_settlement'"
    ).fetchone()
    if not exists:
        return False
    for fk in conn.execute("PRAGMA foreign_key_list(pending_settlement)").fetchall():
        # PRAGMA foreign_key_list columns: id, seq, table, from, to, ...
        # Index 3 == 'from' (local column), index 2 == referenced table.
        if (fk[3] == "escrow_id") or (fk[2] == "escrow_balance"):
            return True
    return False


# The CREATE for the scratch table, derived from the new-shape DDL. Held as a
# single statement so the rebuild can run it via conn.execute() inside an
# explicit transaction — conn.executescript() issues an implicit COMMIT, which
# would commit the CREATE outside the intended transaction and leave the
# scratch table behind on a mid-rebuild failure (slice1a review HIGH — r2).
_PENDING_SETTLEMENT_NEW_TABLE_DDL = _PENDING_SETTLEMENT_NEW_DDL.replace(
    "CREATE TABLE pending_settlement",
    "CREATE TABLE pending_settlement_new",
).strip()


def _rebuild_pending_settlement(conn) -> None:  # type: ignore[no-untyped-def]
    """Migrate an existing pending_settlement off the legacy hard FK.

    SQLite cannot drop a column-level FK in place, so this does the standard
    create-new + copy + drop + rename rebuild. Foreign keys are toggled off for
    the swap (SQLite requires FKs disabled to rename/drop a referenced table
    safely) and restored afterward.

    Atomicity (slice1a review HIGH — round 2): every step runs as an individual
    ``conn.execute()`` inside ONE explicit BEGIN/COMMIT transaction — never
    ``conn.executescript()``, which issues an implicit COMMIT and would commit
    the scratch-table CREATE outside the transaction. On any failure the
    transaction is rolled back AND the scratch table is dropped in a fresh
    transaction, so a partial failure leaves NO ``pending_settlement_new`` and
    the original ``pending_settlement`` intact and untouched. The whole rebuild
    is therefore safe to retry.
    """
    prev_fk = conn.execute("PRAGMA foreign_keys").fetchone()[0]
    # foreign_keys cannot be changed inside a transaction; toggle outside, and
    # ensure no implicit transaction is open before we BEGIN our own.
    if conn.in_transaction:
        conn.commit()
    conn.execute("PRAGMA foreign_keys = OFF")
    try:
        # Explicit single transaction. Individual conn.execute() statements only
        # — no executescript() (its implicit COMMIT would break atomicity).
        conn.execute("BEGIN")
        try:
            conn.execute("DROP TABLE IF EXISTS pending_settlement_new")
            conn.execute(_PENDING_SETTLEMENT_NEW_TABLE_DDL)
            cols = ", ".join(_PENDING_SETTLEMENT_COLUMNS)
            conn.execute(
                f"INSERT INTO pending_settlement_new ({cols}) "
                f"SELECT {cols} FROM pending_settlement"
            )
            conn.execute("DROP TABLE pending_settlement")
            conn.execute(
                "ALTER TABLE pending_settlement_new RENAME TO pending_settlement"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_settlement_escrow "
                "ON pending_settlement(escrow_id)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_settlement_status "
                "ON pending_settlement(status)"
            )
            conn.commit()
        except Exception:
            # Roll back the partial rebuild, then drop the scratch table in a
            # fresh transaction so a retry starts clean and the original
            # pending_settlement (restored by the rollback) is untouched.
            conn.rollback()
            try:
                conn.execute("DROP TABLE IF EXISTS pending_settlement_new")
                conn.commit()
            except Exception:
                conn.rollback()
            raise
    finally:
        conn.execute(f"PRAGMA foreign_keys = {'ON' if prev_fk else 'OFF'}")


_SETTLEMENT_BATCH_NEW_TABLE_DDL = """
CREATE TABLE settlement_batch_new (
    batch_id        TEXT PRIMARY KEY,
    recipient_id    TEXT NOT NULL,
    total_amount    INTEGER NOT NULL DEFAULT 0 CHECK (total_amount >= 0),
    total_fee       INTEGER NOT NULL DEFAULT 0 CHECK (total_fee >= 0),
    item_count      INTEGER NOT NULL DEFAULT 0,
    status          TEXT NOT NULL DEFAULT 'open'
                        CHECK (status IN
                            ('open','submitted','flushed','failed','in_doubt')),
    opened_at       TEXT NOT NULL,
    flushed_at      TEXT
)
""".strip()

_SETTLEMENT_BATCH_COLUMNS = (
    "batch_id", "recipient_id", "total_amount", "total_fee", "item_count",
    "status", "opened_at", "flushed_at",
)


def _settlement_batch_has_legacy_status_check(conn) -> bool:  # type: ignore[no-untyped-def]
    """True when an existing settlement_batch carries the legacy status CHECK
    (only ``open/flushed/failed``) that rejects the newer ``submitted`` and
    ``in_doubt`` states (slice1a review HIGH — round 2). Returns False if the
    table is absent or already accepts the new states.
    """
    row = conn.execute(
        "SELECT sql FROM sqlite_master "
        "WHERE type='table' AND name='settlement_batch'"
    ).fetchone()
    if not row:
        return False
    sql = (row[0] if not isinstance(row, dict) else row.get("sql")) or ""
    # The new states are absent in a legacy CHECK. Either both present (already
    # migrated) or both absent (legacy); checking one is sufficient.
    return "in_doubt" not in sql


def _rebuild_settlement_batch(conn) -> None:  # type: ignore[no-untyped-def]
    """Migrate a legacy settlement_batch to the wider status CHECK.

    Same atomicity contract as ``_rebuild_pending_settlement`` (slice1a review
    HIGH — round 2): individual ``conn.execute()`` statements inside ONE
    explicit BEGIN/COMMIT, never ``conn.executescript()``. On failure the
    transaction rolls back and the scratch table is dropped, leaving the
    original settlement_batch intact and the rebuild safe to retry.
    """
    if conn.in_transaction:
        conn.commit()
    conn.execute("BEGIN")
    try:
        conn.execute("DROP TABLE IF EXISTS settlement_batch_new")
        conn.execute(_SETTLEMENT_BATCH_NEW_TABLE_DDL)
        cols = ", ".join(_SETTLEMENT_BATCH_COLUMNS)
        conn.execute(
            f"INSERT INTO settlement_batch_new ({cols}) "
            f"SELECT {cols} FROM settlement_batch"
        )
        conn.execute("DROP TABLE settlement_batch")
        conn.execute("ALTER TABLE settlement_batch_new RENAME TO settlement_batch")
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_batch_recipient "
            "ON settlement_batch(recipient_id)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_batch_status "
            "ON settlement_batch(status)"
        )
        conn.commit()
    except Exception:
        conn.rollback()
        try:
            conn.execute("DROP TABLE IF EXISTS settlement_batch_new")
            conn.commit()
        except Exception:
            conn.rollback()
        raise


def migrate_settlement_schema(conn) -> None:  # type: ignore[no-untyped-def]
    """Create settlement tables if absent, and migrate legacy schemas. Idempotent.

    Safe on both fresh DBs (creates everything) and existing DBs:
      * rebuilds a legacy pending_settlement that still carries the hard
        escrow_id FK so it accepts soft-ref rows (slice1a review HIGH 3);
      * rebuilds a legacy settlement_batch whose status CHECK predates the
        ``submitted`` / ``in_doubt`` states (slice1a review HIGH — round 2).
    """
    # Rebuild legacy tables BEFORE the CREATE-IF-NOT-EXISTS run, since the
    # IF NOT EXISTS would otherwise leave the stale-constraint table in place.
    if _pending_settlement_has_stale_fk(conn):
        _rebuild_pending_settlement(conn)
    if _settlement_batch_has_legacy_status_check(conn):
        _rebuild_settlement_batch(conn)
    conn.executescript(
        STAKER_ESCROW_BUDGET_SCHEMA + "\n"
        + PAYOUT_WALLET_SCHEMA + "\n"
        + SETTLEMENT_SCHEMA
    )
