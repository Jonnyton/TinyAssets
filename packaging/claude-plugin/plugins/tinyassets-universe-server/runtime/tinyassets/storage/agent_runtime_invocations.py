"""Read-only SQLite authority source for admitted custom-agent invocations."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from tinyassets.agent_runtime_invocation import (
    AgentInvocationEvent,
    AgentInvocationEventState,
    AgentInvocationIntegrityError,
    AgentInvocationRoot,
)
from tinyassets.agent_runtime_principal import AgentInvocationAuthorityEvidence
from tinyassets.storage import db_path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS agent_runtime_invocation_roots (
    invocation_id TEXT PRIMARY KEY,
    authorizing_subject_id TEXT NOT NULL,
    universe_id TEXT NOT NULL,
    agent_binding_id TEXT NOT NULL,
    command_id TEXT NOT NULL UNIQUE,
    provider_work_binding_id TEXT NOT NULL,
    admission_witness_id TEXT NOT NULL UNIQUE,
    root_digest TEXT NOT NULL UNIQUE,
    record_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_agent_invocation_idempotency
    ON agent_runtime_invocation_roots(
        authorizing_subject_id,
        json_extract(record_json, '$.idempotency_key_digest')
    );

CREATE TABLE IF NOT EXISTS agent_runtime_invocation_events (
    event_id TEXT PRIMARY KEY,
    invocation_id TEXT NOT NULL,
    generation INTEGER NOT NULL CHECK (generation >= 1),
    state TEXT NOT NULL CHECK (state IN ('admitted', 'invalidated')),
    previous_event_digest TEXT,
    root_digest TEXT NOT NULL,
    event_digest TEXT NOT NULL UNIQUE,
    record_json TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    UNIQUE (invocation_id, generation),
    FOREIGN KEY (invocation_id)
        REFERENCES agent_runtime_invocation_roots(invocation_id)
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


def _root(row: sqlite3.Row) -> AgentInvocationRoot:
    try:
        raw = str(row["record_json"])
        record = AgentInvocationRoot.from_dict(json.loads(raw))
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise AgentInvocationIntegrityError("persisted invocation root is invalid") from exc
    exact = (
        record.invocation_id == row["invocation_id"],
        record.authorizing_subject_id == row["authorizing_subject_id"],
        record.universe_id == row["universe_id"],
        record.agent_binding_id == row["agent_binding_id"],
        record.command_id == row["command_id"],
        record.provider_work_binding_id == row["provider_work_binding_id"],
        record.admission_witness_id == row["admission_witness_id"],
        record.root_digest == row["root_digest"],
        record.created_at == row["created_at"],
        raw == _canonical_json(record.to_dict()),
    )
    if not all(exact):
        raise AgentInvocationIntegrityError("persisted invocation root failed integrity checks")
    return record


def _event(row: sqlite3.Row) -> AgentInvocationEvent:
    try:
        raw = str(row["record_json"])
        record = AgentInvocationEvent.from_dict(json.loads(raw))
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise AgentInvocationIntegrityError("persisted invocation event is invalid") from exc
    exact = (
        record.event_id == row["event_id"],
        record.invocation_id == row["invocation_id"],
        record.generation == row["generation"],
        record.state.value == row["state"],
        record.previous_event_digest == row["previous_event_digest"],
        record.root_digest == row["root_digest"],
        record.event_digest == row["event_digest"],
        record.occurred_at == row["occurred_at"],
        raw == _canonical_json(record.to_dict()),
    )
    if not all(exact):
        raise AgentInvocationIntegrityError("persisted invocation event failed integrity checks")
    return record


def _validated_chain(
    root: AgentInvocationRoot,
    events: tuple[AgentInvocationEvent, ...],
) -> None:
    if not events:
        raise AgentInvocationIntegrityError("invocation event chain is missing")
    previous: AgentInvocationEvent | None = None
    terminal = False
    for expected_generation, event in enumerate(events, start=1):
        if (
            event.invocation_id != root.invocation_id
            or event.root_digest != root.root_digest
            or event.generation != expected_generation
            or event.previous_event_digest != (None if previous is None else previous.event_digest)
        ):
            raise AgentInvocationIntegrityError("invocation event chain is invalid")
        if previous is None:
            if (
                event.state is not AgentInvocationEventState.ADMITTED
                or event.reason_code is not None
            ):
                raise AgentInvocationIntegrityError("invocation initial transition is invalid")
        elif terminal or event.state is not AgentInvocationEventState.INVALIDATED:
            raise AgentInvocationIntegrityError("invocation transition is invalid")
        else:
            if event.reason_code is None:
                raise AgentInvocationIntegrityError("invocation invalidation reason is missing")
            terminal = True
        previous = event


class AgentRuntimeInvocationStore:
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
            conn.execute("PRAGMA foreign_keys = ON")
            conn.executescript(_SCHEMA)
            yield conn
        finally:
            conn.close()

    def _load(
        self,
        invocation_id: str,
    ) -> tuple[AgentInvocationRoot, tuple[AgentInvocationEvent, ...]] | None:
        with self._connection() as conn:
            row = conn.execute(
                "SELECT * FROM agent_runtime_invocation_roots WHERE invocation_id = ?",
                (invocation_id,),
            ).fetchone()
            if row is None:
                return None
            root = _root(row)
            events = tuple(
                _event(event_row)
                for event_row in conn.execute(
                    """
                    SELECT * FROM agent_runtime_invocation_events
                    WHERE invocation_id = ?
                    ORDER BY generation ASC
                    """,
                    (invocation_id,),
                ).fetchall()
            )
        _validated_chain(root, events)
        return root, events

    def resolve_current(
        self,
        *,
        invocation_id: str,
    ) -> AgentInvocationAuthorityEvidence | None:
        if not isinstance(invocation_id, str) or not invocation_id.strip():
            raise ValueError("invocation_id must be a non-empty string")
        if not invocation_id.startswith("agent_invocation_"):
            raise ValueError("invocation_id is not an agent invocation")
        loaded = self._load(invocation_id)
        if loaded is None:
            return None
        # A structurally valid row is not admission authority. Positive resolution
        # stays impossible until the canonical command/provider-binding owner can
        # return and revalidate a sealed typed witness in the same authority flow.
        return None


__all__ = [
    "AgentRuntimeInvocationStore",
]
