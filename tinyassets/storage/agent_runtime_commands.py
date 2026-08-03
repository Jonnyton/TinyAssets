"""Read-only SQLite source for custom-agent invocation commands."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from tinyassets.agent_runtime_command import (
    AgentInvocationCommand,
    AgentInvocationCommandIntegrityError,
)
from tinyassets.storage import db_path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS agent_runtime_invocation_commands (
    command_id TEXT PRIMARY KEY,
    invocation_id TEXT NOT NULL UNIQUE,
    authorizing_subject_id TEXT NOT NULL,
    universe_id TEXT NOT NULL,
    agent_binding_id TEXT NOT NULL,
    provider_work_binding_id TEXT NOT NULL,
    admission_witness_id TEXT NOT NULL UNIQUE,
    command_digest TEXT NOT NULL UNIQUE,
    record_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_agent_invocation_command_idempotency
    ON agent_runtime_invocation_commands(
        authorizing_subject_id,
        universe_id,
        json_extract(record_json, '$.idempotency_key_digest')
    );
"""


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _command(row: sqlite3.Row) -> AgentInvocationCommand:
    try:
        raw = str(row["record_json"])
        record = AgentInvocationCommand.from_dict(json.loads(raw))
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise AgentInvocationCommandIntegrityError(
            "persisted invocation command is invalid"
        ) from exc
    exact = (
        record.command_id == row["command_id"],
        record.invocation_id == row["invocation_id"],
        record.authorizing_subject_id == row["authorizing_subject_id"],
        record.universe_id == row["universe_id"],
        record.agent_binding_id == row["agent_binding_id"],
        record.provider_work_binding_id == row["provider_work_binding_id"],
        record.admission_witness_id == row["admission_witness_id"],
        record.command_digest == row["command_digest"],
        record.created_at == row["created_at"],
        raw == _canonical_json(record.to_dict()),
    )
    if not all(exact):
        raise AgentInvocationCommandIntegrityError(
            "persisted invocation command failed integrity checks"
        )
    return record


class AgentRuntimeCommandStore:
    """Tamper-detecting source; this slice intentionally has no writer API."""

    def __init__(
        self,
        base_path: str | Path,
        *,
        busy_timeout_ms: int = 30_000,
    ) -> None:
        self.base_path = Path(base_path)
        self._busy_timeout_ms = int(busy_timeout_ms)
        if self._busy_timeout_ms < 0:
            raise ValueError("busy_timeout_ms must be non-negative")

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        path = db_path(self.base_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(path, timeout=self._busy_timeout_ms / 1000)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute(f"PRAGMA busy_timeout = {self._busy_timeout_ms}")
            conn.executescript(_SCHEMA)
            yield conn
        finally:
            conn.close()

    def _load(self, command_id: str) -> AgentInvocationCommand | None:
        with self._connection() as conn:
            row = conn.execute(
                "SELECT * FROM agent_runtime_invocation_commands WHERE command_id = ?",
                (command_id,),
            ).fetchone()
        return None if row is None else _command(row)

    def resolve_current(self, *, command_id: str) -> AgentInvocationCommand | None:
        if not isinstance(command_id, str) or not command_id.strip():
            raise ValueError("command_id must be a non-empty string")
        if not command_id.startswith("agent_invocation_command_"):
            raise ValueError("command_id is not an agent invocation command")
        loaded = self._load(command_id)
        if loaded is None:
            return None
        # A valid record is still only inert input. Positive resolution stays
        # impossible until the future atomic admission owner revalidates the
        # request grant, binding, live grants, provider envelope, and witness.
        return None


__all__ = ["AgentRuntimeCommandStore"]
