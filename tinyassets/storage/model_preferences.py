"""Owner/universe CAS preferences in the canonical database; no provider authority."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from tinyassets.providers.model_preferences import (
    MAX_GENERATION,
    ModelPreferences,
    exact_generation,
    strict_json,
)
from tinyassets.storage.current_home import (
    CurrentHomeChanged,
)
from tinyassets.storage.current_home import (
    check_current_home as _check_home,
)
from tinyassets.storage.provider_work_authority import SQLiteProviderWorkAuthorityStore

# Preserve the existing route's exception contract while sharing the guard.
PreferenceHomeChanged = CurrentHomeChanged


class PreferenceStoreUnavailable(RuntimeError):
    """An unreadable row is held, never treated as absent/defaulted."""


@dataclass(frozen=True, slots=True)
class PreferenceSnapshot:
    generation: int = 0
    policy: ModelPreferences | None = None
    updated_at: str | None = None

    def document(self) -> dict:
        return {
            "generation": self.generation,
            "policy": None if self.policy is None else self.policy.document(),
            "updated_at": self.updated_at,
        }


class PreferenceConflict(RuntimeError):
    def __init__(self, current: PreferenceSnapshot):
        super().__init__("model preferences changed")
        self.current = current


def _scope(owner: str, universe: str) -> None:
    for value in (owner, universe):
        if (
            not isinstance(value, str)
            or not value
            or len(value) > 400
            or value != value.strip()
            or not value.isprintable()
        ):
            raise ValueError("invalid preference scope")


def _read(conn: sqlite3.Connection, owner: str, universe: str) -> PreferenceSnapshot:
    row = conn.execute(
        "SELECT generation, policy_json, updated_at FROM universe_model_preferences "
        "WHERE owner_user_id = ? AND universe_id = ?",
        (owner, universe),
    ).fetchone()
    if row is None:
        return PreferenceSnapshot()
    try:
        generation = exact_generation(row["generation"])
        if not generation:
            raise ValueError("invalid stored generation")
        updated_at = row["updated_at"]
        if not isinstance(updated_at, str) or not updated_at.endswith("Z"):
            raise ValueError("invalid preference timestamp")
        datetime.fromisoformat(updated_at[:-1] + "+00:00")
        policy = ModelPreferences.from_document(strict_json(row["policy_json"]))
        return PreferenceSnapshot(generation, policy, updated_at)
    except (ValueError, TypeError, OverflowError) as exc:
        raise PreferenceStoreUnavailable("model preference record unavailable") from exc


class ModelPreferenceStore:
    """Internal persistence. Callers must derive owner/universe from authenticated scope."""

    def __init__(self, base_path: str | Path) -> None:
        self._ledger = SQLiteProviderWorkAuthorityStore(base_path)

    def get(
        self,
        owner: str,
        universe: str,
        *,
        require_current_home: bool = False,
    ) -> PreferenceSnapshot:
        _scope(owner, universe)
        with self._ledger.connection() as conn:
            if require_current_home:
                conn.execute("BEGIN")
                _check_home(conn, owner, universe)
            return _read(conn, owner, universe)

    def save(
        self,
        owner: str,
        universe: str,
        *,
        expected_generation: int,
        policy: ModelPreferences,
        require_current_home: bool = False,
    ) -> PreferenceSnapshot:
        _scope(owner, universe)
        exact_generation(expected_generation)
        if type(policy) is not ModelPreferences:
            raise ValueError("invalid model preferences")
        with self._ledger.connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                if require_current_home:
                    _check_home(conn, owner, universe)
                # Decode before comparing: corrupt data cannot become a reset or conflict default.
                current = _read(conn, owner, universe)
                if current.generation != expected_generation:
                    raise PreferenceConflict(current)
                if current.generation == MAX_GENERATION:
                    raise PreferenceStoreUnavailable("model preference generation exhausted")
                updated = PreferenceSnapshot(
                    current.generation + 1, policy, self._ledger.timestamp()
                )
                if current.generation == 0:
                    conn.execute(
                        "INSERT INTO universe_model_preferences "
                        "(owner_user_id, universe_id, generation, policy_json, updated_at) "
                        "VALUES (?, ?, ?, ?, ?)",
                        (
                            owner,
                            universe,
                            updated.generation,
                            policy.canonical_json(),
                            updated.updated_at,
                        ),
                    )
                else:
                    changed = conn.execute(
                        "UPDATE universe_model_preferences SET generation = ?, policy_json = ?, "
                        "updated_at = ? WHERE owner_user_id = ? AND universe_id = ? "
                        "AND generation = ?",
                        (
                            updated.generation,
                            policy.canonical_json(),
                            updated.updated_at,
                            owner,
                            universe,
                            current.generation,
                        ),
                    ).rowcount
                    if changed != 1:
                        raise PreferenceStoreUnavailable("model preference update unavailable")
                conn.commit()
                return updated
            except Exception:
                conn.rollback()
                raise
