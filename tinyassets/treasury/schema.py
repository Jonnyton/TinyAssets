"""Treasury schema — DDL and dataclasses for the platform fee + bounty-pool model.

Spec: project_monetization_crypto_1pct + project_designer_royalties_and_bounties.

Four tables:
  treasury_balance    — running total of platform-take funds
  bounty_pool_balance — 50% of treasury inflow earmarked for bug/feature bounties
  royalty_payout      — per-settlement designer royalty events
  take_rate_log       — immutable audit trail for take-rate changes (governance)

Take rate: 1% (100 basis points) of every settlement flows to treasury.
Bounty pool: 50% of the 1% take (= 0.5% of settlement total).
All amounts stored as INTEGER (MicroTokens) — never REAL/FLOAT.
"""

from __future__ import annotations

from dataclasses import dataclass

# ── Status enums ──────────────────────────────────────────────────────────────

PayoutStatus = str  # "pending" | "settled" | "refunded"

# ── DDL ───────────────────────────────────────────────────────────────────────

TREASURY_SCHEMA = """
CREATE TABLE IF NOT EXISTS treasury_balance (
    entry_id        TEXT PRIMARY KEY,
    source_tx_id    TEXT NOT NULL,
    amount          INTEGER NOT NULL CHECK (amount >= 0),
    take_rate_bp    INTEGER NOT NULL CHECK (take_rate_bp >= 0),
    fee_collected   INTEGER NOT NULL CHECK (fee_collected >= 0),
    bounty_share    INTEGER NOT NULL DEFAULT 0 CHECK (bounty_share >= 0),
    recorded_at     TEXT NOT NULL,
    note            TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_treasury_recorded
    ON treasury_balance(recorded_at);

CREATE TABLE IF NOT EXISTS bounty_pool_balance (
    pool_entry_id   TEXT PRIMARY KEY,
    treasury_entry_id TEXT NOT NULL REFERENCES treasury_balance(entry_id),
    allocated       INTEGER NOT NULL CHECK (allocated >= 0),
    disbursed       INTEGER NOT NULL DEFAULT 0 CHECK (disbursed >= 0),
    status          TEXT NOT NULL DEFAULT 'pending'
                        CHECK (status IN ('pending', 'settled', 'refunded')),
    recorded_at     TEXT NOT NULL,
    disbursed_at    TEXT
);

CREATE INDEX IF NOT EXISTS idx_bounty_treasury
    ON bounty_pool_balance(treasury_entry_id);

CREATE INDEX IF NOT EXISTS idx_bounty_status
    ON bounty_pool_balance(status);

CREATE TABLE IF NOT EXISTS royalty_payout (
    payout_id       TEXT PRIMARY KEY,
    artifact_id     TEXT NOT NULL,
    artifact_kind   TEXT NOT NULL DEFAULT 'node'
                        CHECK (artifact_kind IN ('node', 'branch')),
    designer_id     TEXT NOT NULL,
    settlement_id   TEXT NOT NULL,
    gross_amount    INTEGER NOT NULL CHECK (gross_amount >= 0),
    royalty_share   REAL NOT NULL CHECK (royalty_share >= 0.0 AND royalty_share <= 1.0),
    royalty_amount  INTEGER NOT NULL CHECK (royalty_amount >= 0),
    status          TEXT NOT NULL DEFAULT 'pending'
                        CHECK (status IN ('pending', 'settled', 'refunded')),
    created_at      TEXT NOT NULL,
    settled_at      TEXT
);

CREATE INDEX IF NOT EXISTS idx_royalty_artifact
    ON royalty_payout(artifact_id);

CREATE INDEX IF NOT EXISTS idx_royalty_designer
    ON royalty_payout(designer_id);

CREATE INDEX IF NOT EXISTS idx_royalty_status
    ON royalty_payout(status);

CREATE TABLE IF NOT EXISTS take_rate_log (
    log_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    take_rate_bp    INTEGER NOT NULL CHECK (take_rate_bp >= 0),
    bounty_pool_bp  INTEGER NOT NULL CHECK (bounty_pool_bp >= 0),
    authorized_by   TEXT NOT NULL,
    effective_at    TEXT NOT NULL,
    note            TEXT NOT NULL DEFAULT ''
);
"""

# ── Dataclasses ───────────────────────────────────────────────────────────────

@dataclass
class TreasuryEntry:
    """One transaction's contribution to the treasury balance."""

    entry_id: str
    source_tx_id: str
    amount: int
    take_rate_bp: int
    fee_collected: int
    bounty_share: int
    recorded_at: str
    note: str = ""

    def __post_init__(self) -> None:
        if self.amount < 0:
            raise ValueError(f"amount must be >= 0, got {self.amount!r}")
        if self.take_rate_bp < 0:
            raise ValueError(f"take_rate_bp must be >= 0, got {self.take_rate_bp!r}")
        if self.fee_collected < 0:
            raise ValueError(f"fee_collected must be >= 0, got {self.fee_collected!r}")
        if self.bounty_share < 0:
            raise ValueError(f"bounty_share must be >= 0, got {self.bounty_share!r}")
        if self.bounty_share > self.fee_collected:
            raise ValueError(
                f"bounty_share ({self.bounty_share}) cannot exceed "
                f"fee_collected ({self.fee_collected})"
            )

    @property
    def treasury_retained(self) -> int:
        """Portion of the fee kept in treasury (not bounty pool)."""
        return self.fee_collected - self.bounty_share

    @classmethod
    def from_row(cls, row: dict) -> TreasuryEntry:
        return cls(
            entry_id=row["entry_id"],
            source_tx_id=row["source_tx_id"],
            amount=int(row["amount"]),
            take_rate_bp=int(row["take_rate_bp"]),
            fee_collected=int(row["fee_collected"]),
            bounty_share=int(row.get("bounty_share") or 0),
            recorded_at=row["recorded_at"],
            note=row.get("note") or "",
        )


@dataclass
class BountyAllocation:
    """Bounty-pool slice earmarked from a single treasury inflow."""

    pool_entry_id: str
    treasury_entry_id: str
    allocated: int
    disbursed: int
    status: PayoutStatus
    recorded_at: str
    disbursed_at: str | None = None

    def __post_init__(self) -> None:
        if self.allocated < 0:
            raise ValueError(f"allocated must be >= 0, got {self.allocated!r}")
        if self.disbursed < 0:
            raise ValueError(f"disbursed must be >= 0, got {self.disbursed!r}")
        if self.disbursed > self.allocated:
            raise ValueError(
                f"disbursed ({self.disbursed}) cannot exceed allocated ({self.allocated})"
            )
        if self.status not in ("pending", "settled", "refunded"):
            raise ValueError(f"status must be pending/settled/refunded, got {self.status!r}")

    @property
    def remaining(self) -> int:
        return self.allocated - self.disbursed

    @classmethod
    def from_row(cls, row: dict) -> BountyAllocation:
        return cls(
            pool_entry_id=row["pool_entry_id"],
            treasury_entry_id=row["treasury_entry_id"],
            allocated=int(row["allocated"]),
            disbursed=int(row.get("disbursed") or 0),
            status=row.get("status") or "pending",
            recorded_at=row["recorded_at"],
            disbursed_at=row.get("disbursed_at"),
        )


@dataclass
class RoyaltyPayment:
    """One designer's royalty from a specific settlement."""

    payout_id: str
    artifact_id: str
    artifact_kind: str
    designer_id: str
    settlement_id: str
    gross_amount: int
    royalty_share: float
    royalty_amount: int
    status: PayoutStatus
    created_at: str
    settled_at: str | None = None

    def __post_init__(self) -> None:
        if self.gross_amount < 0:
            raise ValueError(f"gross_amount must be >= 0, got {self.gross_amount!r}")
        if not 0.0 <= self.royalty_share <= 1.0:
            raise ValueError(f"royalty_share must be in [0.0, 1.0], got {self.royalty_share!r}")
        if self.royalty_amount < 0:
            raise ValueError(f"royalty_amount must be >= 0, got {self.royalty_amount!r}")
        if self.royalty_amount > self.gross_amount:
            raise ValueError(
                f"royalty_amount ({self.royalty_amount}) cannot exceed "
                f"gross_amount ({self.gross_amount})"
            )
        if self.artifact_kind not in ("node", "branch"):
            raise ValueError(
                f"artifact_kind must be 'node' or 'branch', got {self.artifact_kind!r}"
            )
        if self.status not in ("pending", "settled", "refunded"):
            raise ValueError(f"status must be pending/settled/refunded, got {self.status!r}")

    @classmethod
    def from_row(cls, row: dict) -> RoyaltyPayment:
        return cls(
            payout_id=row["payout_id"],
            artifact_id=row["artifact_id"],
            artifact_kind=row.get("artifact_kind") or "node",
            designer_id=row["designer_id"],
            settlement_id=row["settlement_id"],
            gross_amount=int(row["gross_amount"]),
            royalty_share=float(row.get("royalty_share") or 0.0),
            royalty_amount=int(row.get("royalty_amount") or 0),
            status=row.get("status") or "pending",
            created_at=row["created_at"],
            settled_at=row.get("settled_at"),
        )


# ── Migration ─────────────────────────────────────────────────────────────────

def migrate_treasury_schema(conn) -> None:  # type: ignore[no-untyped-def]
    """Create treasury tables if absent. Idempotent."""
    conn.executescript(TREASURY_SCHEMA)
