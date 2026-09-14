"""Shared transaction-local owner home/deletion guard, not authentication."""

from __future__ import annotations

import sqlite3


class CurrentHomeChanged(RuntimeError):
    """The authenticated caller's home was removed, rebound or deleted."""


def check_current_home(conn: sqlite3.Connection, owner: str, universe: str) -> None:
    from tinyassets.account_deletion import principal_digest

    if not conn.in_transaction:
        raise RuntimeError("current home check requires a transaction")
    home = conn.execute(
        "SELECT universe_id FROM founder_home WHERE founder_sub = ?",
        (owner,),
    ).fetchone()
    deleted = conn.execute(
        "SELECT 1 FROM deleted_principals WHERE founder_sub = ?",
        (principal_digest(owner),),
    ).fetchone()
    if home is None or home[0] != universe or deleted is not None:
        raise CurrentHomeChanged("current universe home changed")
