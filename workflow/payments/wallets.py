"""Payout-wallet registry — where an actor's settled balance lands on-chain.

Recipients self-register the address their withdrawals should pay out to, keyed
by (actor_id, chain_id). Address is stored verbatim after a light shape check
(0x + 40 hex). Schema lives in workflow.payments.schema (payout_wallet).
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass

from workflow.payments.schema import migrate_settlement_schema
from workflow.payments.settlement_backend import BASE_SEPOLIA_CHAIN_ID

_ADDRESS_RE = re.compile(r"^0x[0-9a-fA-F]{40}$")


class WalletError(Exception):
    """Raised on an invalid payout wallet registration."""


@dataclass
class PayoutWallet:
    actor_id: str
    chain_id: int
    address: str
    updated_at: str

    @classmethod
    def from_row(cls, row) -> "PayoutWallet":  # type: ignore[no-untyped-def]
        d = dict(row)
        return cls(
            actor_id=d["actor_id"],
            chain_id=int(d["chain_id"]),
            address=d["address"],
            updated_at=d["updated_at"],
        )


def ensure_wallet_schema(conn: sqlite3.Connection) -> None:
    """Idempotent — create the payout_wallet (+ settlement) tables."""
    migrate_settlement_schema(conn)


def is_valid_address(address: str) -> bool:
    return bool(_ADDRESS_RE.match(address or ""))


def set_payout_wallet(
    conn: sqlite3.Connection,
    *,
    actor_id: str,
    address: str,
    now_iso: str,
    chain_id: int = BASE_SEPOLIA_CHAIN_ID,
) -> PayoutWallet:
    """Register or replace an actor's payout address for a chain."""
    ensure_wallet_schema(conn)
    if not actor_id:
        raise WalletError("actor_id is required.")
    if not is_valid_address(address):
        raise WalletError(
            f"address must be a 0x-prefixed 40-hex string, got {address!r}."
        )
    conn.execute(
        """
        INSERT INTO payout_wallet (actor_id, chain_id, address, updated_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(actor_id, chain_id) DO UPDATE SET
            address = excluded.address,
            updated_at = excluded.updated_at
        """,
        (actor_id, chain_id, address, now_iso),
    )
    return get_payout_wallet(conn, actor_id=actor_id, chain_id=chain_id)  # type: ignore[return-value]


def get_payout_wallet(
    conn: sqlite3.Connection,
    *,
    actor_id: str,
    chain_id: int = BASE_SEPOLIA_CHAIN_ID,
) -> PayoutWallet | None:
    """Return the actor's payout wallet for a chain, or None."""
    ensure_wallet_schema(conn)
    row = conn.execute(
        "SELECT * FROM payout_wallet WHERE actor_id = ? AND chain_id = ?",
        (actor_id, chain_id),
    ).fetchone()
    return PayoutWallet.from_row(row) if row else None
