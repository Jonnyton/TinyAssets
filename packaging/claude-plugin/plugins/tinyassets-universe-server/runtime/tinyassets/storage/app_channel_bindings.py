"""Which universe answers where, on an external chat surface.

Separate from :mod:`tinyassets.storage.app_principal_mappings` because they
answer different questions, and conflating them is what capped a user at one
universe:

``app_principal_mappings``
    *Who is this sender?* An identity fact. A person is the same person in
    every channel, so this is deliberately channel-independent.

``app_channel_bindings`` (here)
    *Which universe answers here?* A routing fact. Users keep several
    universes — work, personal, hobby — and a single Slack workspace may need
    to reach more than one of them.

One row per scope, and the scope is either a channel or the whole workspace.
``channel_id = ''`` IS the workspace-wide row rather than a separate table:
one primary key, and "most specific wins" becomes a two-key lookup instead of
a join. The empty string can never collide with a real Slack channel id.
"""

from __future__ import annotations

import re
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterator

from tinyassets.ids import new_ulid
from tinyassets.storage import db_path

_IDENTIFIER = re.compile(r"[A-Za-z0-9._:-]+\Z")

#: The scope meaning "everywhere in this workspace that no channel row covers".
WORKSPACE_SCOPE = ""

_SCHEMA = """
CREATE TABLE IF NOT EXISTS app_channel_bindings (
    binding_row_id TEXT PRIMARY KEY,
    provider TEXT NOT NULL,
    installation_id TEXT NOT NULL,
    workspace_id TEXT NOT NULL,
    channel_id TEXT NOT NULL,
    universe_id TEXT NOT NULL,
    agent_binding_id TEXT NOT NULL,
    binding_revision INTEGER NOT NULL CHECK (binding_revision >= 1),
    bound_by TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE (provider, installation_id, workspace_id, channel_id)
);

CREATE INDEX IF NOT EXISTS idx_app_channel_bindings_universe
    ON app_channel_bindings(universe_id);
"""


class AppChannelBindingError(ValueError):
    """A channel binding could not be written as asked."""


@dataclass(frozen=True, slots=True)
class AppChannelBinding:
    binding_row_id: str
    provider: str
    installation_id: str
    workspace_id: str
    channel_id: str
    universe_id: str
    agent_binding_id: str
    binding_revision: int
    bound_by: str
    created_at: str

    @property
    def is_workspace_default(self) -> bool:
        return self.channel_id == WORKSPACE_SCOPE


class AppChannelBindingStore:
    """Persist and resolve channel-to-universe routing."""

    def __init__(
        self,
        base_path: str | Path,
        *,
        busy_timeout_ms: int = 30_000,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.database_path = db_path(Path(base_path))
        if not isinstance(busy_timeout_ms, int) or isinstance(busy_timeout_ms, bool):
            raise ValueError("busy_timeout_ms must be an integer")
        if busy_timeout_ms < 0:
            raise ValueError("busy_timeout_ms must be non-negative")
        self._busy_timeout_ms = busy_timeout_ms
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(
            self.database_path,
            timeout=self._busy_timeout_ms / 1000,
            isolation_level=None,
        )
        conn.row_factory = sqlite3.Row
        try:
            conn.execute(f"PRAGMA busy_timeout = {self._busy_timeout_ms}")
            try:
                conn.execute("PRAGMA journal_mode = WAL")
            except sqlite3.OperationalError as exc:
                if "locked" not in str(exc).casefold():
                    raise
            conn.executescript(_SCHEMA)
            yield conn
        finally:
            conn.close()

    def bind(
        self,
        *,
        provider: str,
        installation_id: str,
        workspace_id: str,
        channel_id: str,
        universe_id: str,
        agent_binding_id: str,
        binding_revision: int,
        bound_by: str,
    ) -> AppChannelBinding:
        """Create or replace the binding for one scope.

        Re-binding a scope REPLACES it. "Point #alpha at my other universe"
        is an ordinary thing to want, and making the caller delete first would
        leave a window where the channel routes nowhere.
        """
        values = _validated(
            provider=provider,
            installation_id=installation_id,
            workspace_id=workspace_id,
            channel_id=channel_id,
            universe_id=universe_id,
            agent_binding_id=agent_binding_id,
            binding_revision=binding_revision,
            bound_by=bound_by,
        )
        created_at = _timestamp(self._clock())
        row_id = f"app_channel_binding_{new_ulid()}"
        with self.connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                conn.execute(
                    """
                    DELETE FROM app_channel_bindings
                    WHERE provider = ? AND installation_id = ?
                      AND workspace_id = ? AND channel_id = ?
                    """,
                    (
                        values["provider"],
                        values["installation_id"],
                        values["workspace_id"],
                        values["channel_id"],
                    ),
                )
                conn.execute(
                    """
                    INSERT INTO app_channel_bindings (
                        binding_row_id, provider, installation_id, workspace_id,
                        channel_id, universe_id, agent_binding_id,
                        binding_revision, bound_by, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        row_id,
                        values["provider"],
                        values["installation_id"],
                        values["workspace_id"],
                        values["channel_id"],
                        values["universe_id"],
                        values["agent_binding_id"],
                        values["binding_revision"],
                        values["bound_by"],
                        created_at,
                    ),
                )
                conn.commit()
            except BaseException:
                conn.rollback()
                raise
        return AppChannelBinding(
            binding_row_id=row_id,
            created_at=created_at,
            **values,
        )

    def unbind(
        self,
        *,
        provider: str,
        installation_id: str,
        workspace_id: str,
        channel_id: str,
    ) -> bool:
        """Remove one scope's binding. Returns whether a row was removed."""
        with self.connection() as conn:
            cursor = conn.execute(
                """
                DELETE FROM app_channel_bindings
                WHERE provider = ? AND installation_id = ?
                  AND workspace_id = ? AND channel_id = ?
                """,
                (provider, installation_id, workspace_id, channel_id),
            )
            conn.commit()
            return cursor.rowcount > 0

    def resolve(
        self,
        *,
        provider: str,
        installation_id: str,
        workspace_id: str,
        channel_id: str,
    ) -> AppChannelBinding | None:
        """The binding for this channel, else the workspace default, else None.

        Most specific wins. Ordering by ``channel_id DESC`` puts any real
        channel id ahead of the empty workspace scope, so one query answers
        both — and a channel row can never be shadowed by the default.
        """
        scopes = [channel_id, WORKSPACE_SCOPE]
        if not isinstance(channel_id, str) or not channel_id.strip():
            scopes = [WORKSPACE_SCOPE]
        with self.connection() as conn:
            row = conn.execute(
                """
                SELECT * FROM app_channel_bindings
                WHERE provider = ? AND installation_id = ? AND workspace_id = ?
                  AND channel_id IN (?, ?)
                ORDER BY channel_id DESC
                LIMIT 1
                """,
                (
                    provider,
                    installation_id,
                    workspace_id,
                    scopes[0],
                    scopes[-1],
                ),
            ).fetchone()
        return _record(row) if row is not None else None

    def list_for_workspace(
        self,
        *,
        provider: str,
        installation_id: str,
        workspace_id: str,
    ) -> list[AppChannelBinding]:
        """Every binding in this workspace, workspace default first.

        This is what an "and here is where I will answer" confirmation reads:
        the user's intent is only verifiable against the RESOLVED routing, not
        against the one row they just wrote.
        """
        with self.connection() as conn:
            rows = conn.execute(
                """
                SELECT * FROM app_channel_bindings
                WHERE provider = ? AND installation_id = ? AND workspace_id = ?
                ORDER BY channel_id ASC
                """,
                (provider, installation_id, workspace_id),
            ).fetchall()
        return [_record(row) for row in rows]


def _validated(**values: object) -> dict:
    out: dict = {}
    for name in (
        "provider",
        "installation_id",
        "workspace_id",
        "universe_id",
        "agent_binding_id",
        "bound_by",
    ):
        value = values[name]
        if not isinstance(value, str) or not value or value != value.strip():
            raise AppChannelBindingError(f"{name} must be a non-empty identifier")
        if len(value) > 257 or _IDENTIFIER.fullmatch(value) is None:
            raise AppChannelBindingError(f"{name} is malformed")
        out[name] = value

    channel = values["channel_id"]
    if not isinstance(channel, str) or channel != channel.strip():
        raise AppChannelBindingError("channel_id must be a string without padding")
    if channel and (len(channel) > 128 or _IDENTIFIER.fullmatch(channel) is None):
        raise AppChannelBindingError("channel_id is malformed")
    out["channel_id"] = channel

    revision = values["binding_revision"]
    if not isinstance(revision, int) or isinstance(revision, bool) or revision < 1:
        raise AppChannelBindingError("binding_revision must be a positive integer")
    out["binding_revision"] = revision
    return out


def _timestamp(value: datetime) -> str:
    if value.tzinfo is None:
        raise AppChannelBindingError("clock must return an aware datetime")
    return (
        value.astimezone(timezone.utc)
        .isoformat(timespec="microseconds")
        .replace("+00:00", "Z")
    )


def _record(row: sqlite3.Row) -> AppChannelBinding:
    return AppChannelBinding(
        binding_row_id=str(row["binding_row_id"]),
        provider=str(row["provider"]),
        installation_id=str(row["installation_id"]),
        workspace_id=str(row["workspace_id"]),
        channel_id=str(row["channel_id"]),
        universe_id=str(row["universe_id"]),
        agent_binding_id=str(row["agent_binding_id"]),
        binding_revision=int(row["binding_revision"]),
        bound_by=str(row["bound_by"]),
        created_at=str(row["created_at"]),
    )


__all__ = [
    "AppChannelBinding",
    "AppChannelBindingError",
    "AppChannelBindingStore",
    "WORKSPACE_SCOPE",
]
