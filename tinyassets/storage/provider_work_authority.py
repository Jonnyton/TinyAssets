"""SQLite persistence for dark requester-owned provider bindings."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterator

from tinyassets.provider_work_authority import (
    ProviderWorkAuthorityWriteOutcome,
    ProviderWorkBinding,
    ProviderWorkBindingFence,
    ProviderWorkBindingSeed,
    ProviderWorkBindingState,
    ProviderWorkBindingWriteResult,
    _from_seed,
    provider_work_binding_id,
)
from tinyassets.storage import db_path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS provider_work_bindings (
    binding_id TEXT PRIMARY KEY,
    generation INTEGER NOT NULL CHECK (generation >= 1),
    state TEXT NOT NULL CHECK (state IN ('active', 'revoked', 'expired')),
    owner_user_id TEXT NOT NULL,
    universe_id TEXT NOT NULL,
    provider TEXT NOT NULL,
    binding_digest TEXT NOT NULL,
    record_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_provider_work_bindings_scope
ON provider_work_bindings(owner_user_id, universe_id, provider, state);
"""


def _record(row: sqlite3.Row) -> ProviderWorkBinding:
    try:
        binding = ProviderWorkBinding.from_dict(json.loads(row["record_json"]))
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError("persisted provider binding is invalid") from exc
    exact = (
        binding.binding_id == row["binding_id"],
        binding.generation == row["generation"],
        binding.state.value == row["state"],
        binding.owner_user_id == row["owner_user_id"],
        binding.universe_id == row["universe_id"],
        binding.provider == row["provider"],
        binding.binding_digest == row["binding_digest"],
        binding.expected_digest() == binding.binding_digest,
    )
    if not all(exact):
        raise ValueError("persisted provider binding failed integrity validation")
    return binding


def _payload(binding: ProviderWorkBinding) -> tuple[object, ...]:
    return (
        binding.binding_id,
        binding.generation,
        binding.state.value,
        binding.owner_user_id,
        binding.universe_id,
        binding.provider,
        binding.binding_digest,
        json.dumps(binding.to_dict(), ensure_ascii=False, separators=(",", ":"), sort_keys=True),
    )


def _same_creation_intent(
    current: ProviderWorkBinding,
    candidate: ProviderWorkBinding,
) -> bool:
    """Compare immutable seed facts while ignoring server clock differences."""

    current_payload = current.to_dict()
    candidate_payload = candidate.to_dict()
    for field in ("binding_digest", "created_at", "updated_at"):
        current_payload.pop(field)
        candidate_payload.pop(field)
    return current_payload == candidate_payload


class _Transaction:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def _insert(self, binding: ProviderWorkBinding) -> ProviderWorkBindingWriteResult:
        if not isinstance(binding, ProviderWorkBinding):
            raise ValueError("binding must be a ProviderWorkBinding")
        if binding.binding_id != provider_work_binding_id(
            owner_user_id=binding.owner_user_id,
            universe_id=binding.universe_id,
            provider=binding.provider,
        ) or binding.binding_digest != binding.expected_digest():
            raise ValueError("provider binding identity or digest is invalid")
        row = self._conn.execute(
            "SELECT * FROM provider_work_bindings WHERE binding_id = ?",
            (binding.binding_id,),
        ).fetchone()
        if row is not None:
            current = _record(row)
            return ProviderWorkBindingWriteResult(
                (
                    ProviderWorkAuthorityWriteOutcome.REPLAYED
                    if _same_creation_intent(current, binding)
                    else ProviderWorkAuthorityWriteOutcome.CONFLICT
                ),
                current,
            )
        self._conn.execute(
            """
            INSERT INTO provider_work_bindings (
                binding_id, generation, state, owner_user_id, universe_id,
                provider, binding_digest, record_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            _payload(binding),
        )
        return ProviderWorkBindingWriteResult(
            ProviderWorkAuthorityWriteOutcome.APPLIED,
            binding,
        )

    def compare_and_swap(
        self,
        expected: ProviderWorkBindingFence,
        replacement: ProviderWorkBinding,
    ) -> ProviderWorkBindingWriteResult:
        current_expected = expected.expected_record
        if replacement.binding_id != current_expected.binding_id:
            raise ValueError("provider binding CAS identities must match")
        row = self._conn.execute(
            "SELECT * FROM provider_work_bindings WHERE binding_id = ?",
            (replacement.binding_id,),
        ).fetchone()
        if row is None:
            return ProviderWorkBindingWriteResult(
                ProviderWorkAuthorityWriteOutcome.MISSING,
                None,
            )
        current = _record(row)
        if current == replacement:
            return ProviderWorkBindingWriteResult(
                ProviderWorkAuthorityWriteOutcome.REPLAYED,
                current,
            )
        if current != current_expected:
            return ProviderWorkBindingWriteResult(
                (
                    ProviderWorkAuthorityWriteOutcome.GENERATION_MISMATCH
                    if current.generation != current_expected.generation
                    else ProviderWorkAuthorityWriteOutcome.CONFLICT
                ),
                current,
            )
        immutable_fields = (
            "schema_version",
            "binding_id",
            "owner_user_id",
            "universe_id",
            "provider",
            "credential_reference_digest",
            "allowed_operations",
            "allowed_roles",
            "assignment_generation",
            "assignment_digest",
            "max_invocations",
            "max_tokens",
            "max_cost_microunits",
            "expires_at",
            "created_at",
        )
        immutable = all(
            getattr(replacement, field) == getattr(current, field)
            for field in immutable_fields
        )
        legal_transition = (
            immutable,
            current.state is ProviderWorkBindingState.ACTIVE,
            replacement.state is ProviderWorkBindingState.REVOKED,
            replacement.generation == current.generation + 1,
            replacement.revocation_generation
            == current.revocation_generation + 1,
            replacement.binding_id
            == provider_work_binding_id(
                owner_user_id=replacement.owner_user_id,
                universe_id=replacement.universe_id,
                provider=replacement.provider,
            ),
            replacement.binding_digest == replacement.expected_digest(),
            replacement.updated_at >= current.updated_at,
        )
        if not all(legal_transition):
            raise ValueError(
                "provider binding transition must preserve immutable authority"
            )
        self._conn.execute(
            """
            UPDATE provider_work_bindings
               SET generation = ?, state = ?, owner_user_id = ?,
                   universe_id = ?, provider = ?, binding_digest = ?,
                   record_json = ?
             WHERE binding_id = ?
            """,
            (*_payload(replacement)[1:], replacement.binding_id),
        )
        return ProviderWorkBindingWriteResult(
            ProviderWorkAuthorityWriteOutcome.APPLIED,
            replacement,
        )


class SQLiteProviderWorkAuthorityStore:
    def __init__(
        self,
        base_path: str | Path,
        *,
        busy_timeout_ms: int = 30_000,
        clock: Callable[[], datetime] | None = None,
        allow_test_fixtures: bool = False,
    ) -> None:
        self.base_path = Path(base_path)
        self._busy_timeout_ms = int(busy_timeout_ms)
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._allow_test_fixtures = bool(allow_test_fixtures)
        if self._busy_timeout_ms < 0:
            raise ValueError("busy_timeout_ms must be non-negative")

    def timestamp(self) -> str:
        value = self._clock()
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("clock must return a timezone-aware datetime")
        return value.astimezone(timezone.utc).isoformat(timespec="microseconds").replace(
            "+00:00", "Z"
        )

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        path = db_path(self.base_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(
            path,
            timeout=self._busy_timeout_ms / 1000,
            isolation_level=None,
        )
        conn.row_factory = sqlite3.Row
        try:
            conn.execute(f"PRAGMA busy_timeout = {self._busy_timeout_ms}")
            try:
                conn.execute("PRAGMA journal_mode = WAL")
            except sqlite3.OperationalError as exc:
                if "locked" not in str(exc).lower():
                    raise
            conn.executescript(_SCHEMA)
            yield conn
        finally:
            conn.close()

    @contextmanager
    def transaction(self) -> Iterator[_Transaction]:
        with self.connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                yield _Transaction(conn)
                conn.commit()
            except Exception:
                conn.rollback()
                raise

    def get(self, binding_id: str) -> ProviderWorkBinding | None:
        with self.connection() as conn:
            row = conn.execute(
                "SELECT * FROM provider_work_bindings WHERE binding_id = ?",
                (binding_id,),
            ).fetchone()
        return _record(row) if row is not None else None

    def install_test_binding(
        self,
        seed: ProviderWorkBindingSeed,
    ) -> ProviderWorkBindingWriteResult:
        """Install inert test data only; production has no issuance root yet."""

        if not self._allow_test_fixtures:
            raise PermissionError("provider binding test fixtures are disabled")
        if not isinstance(seed, ProviderWorkBindingSeed):
            raise ValueError("seed must be a ProviderWorkBindingSeed")
        binding = _from_seed(seed, created_at=self.timestamp())
        with self.transaction() as transaction:
            return transaction._insert(binding)

    def validate_in_transaction(
        self,
        conn: sqlite3.Connection,
        *,
        binding_id: str,
        binding_generation: int,
        binding_digest: str,
        owner_user_id: str,
        universe_id: str,
        provider: str,
        operation: str,
        role: str,
    ) -> bool:
        """Validate exact current state without minting provider authority."""

        try:
            row = conn.execute(
                "SELECT * FROM provider_work_bindings WHERE binding_id = ?",
                (binding_id,),
            ).fetchone()
            if row is None:
                return False
            binding = _record(row)
            expires_at = datetime.fromisoformat(
                binding.expires_at.removesuffix("Z") + "+00:00"
            )
            now = self._clock().astimezone(timezone.utc)
        except (TypeError, ValueError, sqlite3.Error):
            return False
        return all(
            (
                binding.state is ProviderWorkBindingState.ACTIVE,
                binding.generation == binding_generation,
                binding.binding_digest == binding_digest,
                binding.owner_user_id == owner_user_id,
                binding.universe_id == universe_id,
                binding.provider == provider,
                operation in binding.allowed_operations,
                role in binding.allowed_roles,
                expires_at > now,
            )
        )


__all__ = ["SQLiteProviderWorkAuthorityStore"]
