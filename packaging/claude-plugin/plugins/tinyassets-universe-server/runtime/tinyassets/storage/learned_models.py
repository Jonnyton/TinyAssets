"""Platform-wide record of model ids that have actually worked, per source KIND.

The first store in this repo that is deliberately shared across users, so the
floor is the whole design: **it carries no user data**. Three columns, and the
reason each one is safe to share is written next to it. Reading the whole table
tells you which model ids work for a kind of source; it cannot tell you who used
one, from which universe, when they used it, or what they asked.

Why it exists: a source that cannot enumerate its own catalogue could only ever
offer ids its owner had typed by hand, so a newly released model was invisible
until someone shipped a patch. Founder, 2026-09-26: "we also should not have to
put out new patches for providers ... always updates for users once one user adds
the newly available model." One verified call teaches the platform; every user
with that kind of source benefits.

A row is EVIDENCE THAT AN ID EXISTS AND WORKED, never permission to use it.
Serving still requires the reading universe's own accepted model access.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from tinyassets.storage import db_path

_SCHEMA = """CREATE TABLE IF NOT EXISTS learned_models (
  -- The KIND of source (subscription_cli, api_key_http, ...), never a connection
  -- id and never a provider account: two users on the same kind of source are
  -- exactly the ones who should share this evidence.
  source_kind TEXT NOT NULL,
  -- The model id that worked. A public name, not a secret.
  model_id TEXT NOT NULL,
  -- When this platform FIRST saw this id work at all. A property of the id, not
  -- of a person; it exists only to break a version tie.
  first_verified_at TEXT NOT NULL,
  PRIMARY KEY(source_kind, model_id))"""

#: Every column there will ever be. A test asserts the shipped table matches, so
#: adding a fourth column has to be a deliberate act that updates this tuple and
#: argues with the cross-user floor.
COLUMNS = ("source_kind", "model_id", "first_verified_at")

#: What must never appear in this table, by name. A counter of verifications is on
#: the list because "3 universes verified this" is a population fact about users
#: and, with timing, narrows who they are.
FORBIDDEN_COLUMNS = frozenset(
    {"owner_user_id", "universe_id", "connection_id", "actor_id", "principal_id",
     "user_id", "prompt", "reply", "credential", "verified_count", "count"}
)


@dataclass(frozen=True, slots=True)
class LearnedModel:
    source_kind: str
    model_id: str
    first_verified_at: str


def _clean(value: object, field: str) -> str:
    if type(value) is not str or not value.strip() or len(value) > 200:
        raise ValueError(f"invalid learned model {field}")
    text = value.strip()
    if not text.isprintable():
        raise ValueError(f"invalid learned model {field}")
    return text


class LearnedModelCatalog:
    """Read/record verified model ids. Shared across users by design."""

    def __init__(self, base_path: str | Path) -> None:
        self.base_path = Path(base_path)

    def _connect(self, *, create: bool) -> sqlite3.Connection:
        path = db_path(self.base_path)
        if not create and not path.exists():
            return None
        if create:
            path.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(path, timeout=30.0, isolation_level=None)
        else:
            # Non-creating: an observational read must not bring a database into
            # being. `mode=rw` opens an existing file and refuses to create one,
            # which also closes the gap after the exists() check above.
            conn = sqlite3.connect(path.as_uri() + "?mode=rw", uri=True,
                                   timeout=30.0, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout = 30000")
        return conn

    def record(self, *, source_kind: str, model_id: str, now: datetime | None = None) -> bool:
        """Record one verified id. Returns whether this call created the row.

        Idempotent by primary key: a second verification of a known id changes
        nothing, so the table cannot accumulate a count of who has used what.

        Callers treat this as best-effort -- failing to learn must never fail the
        call that succeeded -- but the failure is raised here rather than
        swallowed, so the caller decides that explicitly at its own site.
        """
        kind = _clean(source_kind, "source kind")
        model = _clean(model_id, "model id")
        stamp = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        conn = self._connect(create=True)
        try:
            conn.execute(_SCHEMA)
            changed = conn.execute(
                "INSERT OR IGNORE INTO learned_models VALUES (?, ?, ?)",
                (kind, model, stamp.isoformat(timespec="microseconds").replace("+00:00", "Z")),
            ).rowcount
            return changed == 1
        finally:
            conn.close()

    def for_source_kind(self, source_kind: str) -> list[LearnedModel]:
        """Every verified id for one kind of source, oldest verification first."""
        kind = _clean(source_kind, "source kind")
        conn = self._connect(create=False)
        if conn is None:
            return []
        try:
            if not conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' "
                "AND name = 'learned_models'"
            ).fetchone():
                return []
            rows = conn.execute(
                "SELECT source_kind, model_id, first_verified_at FROM learned_models "
                "WHERE source_kind = ? ORDER BY first_verified_at, model_id",
                (kind,),
            ).fetchall()
        finally:
            conn.close()
        return [LearnedModel(row["source_kind"], row["model_id"], row["first_verified_at"])
                for row in rows]

    def newest_for_source_kind(self, source_kind: str) -> list[LearnedModel]:
        """The newest verified model of each class for one kind of source."""
        from tinyassets.providers.model_class import newest_per_class

        return newest_per_class(self.for_source_kind(source_kind))


def record_verified_model(base_path, *, source_kind, model_id) -> bool:
    """Best-effort learn, for a caller that has already succeeded.

    The one place the failure IS swallowed, and only here, because the caller is
    always a turn that has already produced a result: a catalog write must not turn
    a delivered reply into an error. Anything a caller wants to fail on should use
    ``LearnedModelCatalog.record`` directly.
    """
    import logging

    try:
        return LearnedModelCatalog(base_path).record(
            source_kind=source_kind, model_id=model_id)
    except Exception as exc:  # noqa: BLE001 - never fail a call that already worked
        logging.getLogger("universe_server.learned_models").warning(
            "could not record a verified model id: %s", type(exc).__name__)
        return False
