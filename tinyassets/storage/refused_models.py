"""An owner's recently refused models, remembered across turns.

Live 2026-09-28, the free-only account: a source refused one model (HTTP 403)
and had withdrawn another (404), and every turn spent a request rediscovering
both before reaching a model that answered. #4078 moves ONE turn past a refused
model; this remembers the refusal so the next turn's order puts that model last.

Per owner and connection, never shared: a refusal is what THIS owner's key was
told. Time-limited, because a refusal is often temporary (a privacy setting the
owner changes, a model the source restores); a mark past its expiry is ignored
and replaced by the next refusal. The reason is kept -- the source's own words,
scrubbed again here -- so a surface can say why a model was skipped.

Best-effort both ways. A write that fails costs one wasted request next turn,
never the turn that discovered the refusal; a read that fails orders as before.
"""

from __future__ import annotations

import logging
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from tinyassets.storage import db_path

logger = logging.getLogger(__name__)

_SCHEMA = """CREATE TABLE IF NOT EXISTS refused_model_marks (
  -- Named owner_user_id because account deletion finds per-user rows BY COLUMN
  -- NAME (account_deletion.PRINCIPAL_KEYS). No universe column: a refusal is the
  -- owner's key's, wherever it is used.
  owner_user_id TEXT NOT NULL,
  connection_id TEXT NOT NULL,
  model_id TEXT NOT NULL,
  failure_class TEXT NOT NULL,
  detail TEXT NOT NULL,
  refused_at TEXT NOT NULL,
  expires_at TEXT NOT NULL,
  PRIMARY KEY(owner_user_id, connection_id, model_id))"""

#: How long a refusal is remembered. The refusals met so far are durable gates,
#: not blips: live 2026-09-29, OpenRouter answered a free model with "only
#: available on agentic harnesses" (routing step "Gate Free Endpoints by Agentic
#: Harness") on every turn. A day stops that costing a request per turn while a
#: model the owner or source re-enables still comes back without anyone
#: clearing anything; choosing it for a turn retries it at once.
REFUSAL_TTL = timedelta(hours=24)

_BUSY_WAIT_MS = 250
_IDENTIFIER = re.compile(r"\A[\x21-\x7e]{1,300}\Z", re.ASCII)
_DETAIL_LIMIT = 200


@dataclass(frozen=True, slots=True)
class RefusedModel:
    connection_id: str
    model_id: str
    failure_class: str
    detail: str
    refused_at: str
    expires_at: str


def _stamp(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _connect(base_path: str | Path, *, create: bool) -> sqlite3.Connection | None:
    path = db_path(Path(base_path))
    if not create and not path.exists():
        return None
    if create:
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(path, timeout=_BUSY_WAIT_MS / 1000, isolation_level=None)
    else:
        # `mode=rw`, never `mode=ro`: a WAL database missing its -shm cannot be
        # opened read-only, and an observational read must not create a file.
        conn = sqlite3.connect(path.as_uri() + "?mode=rw", uri=True,
                               timeout=_BUSY_WAIT_MS / 1000, isolation_level=None)
    conn.execute(f"PRAGMA busy_timeout = {_BUSY_WAIT_MS}")
    return conn


def record_refused_model(
    base_path: str | Path, *, owner_user_id: str, connection_id: str, model_id: str,
    failure_class: str, detail: str, now: datetime | None = None,
) -> bool:
    """Remember that the owner's source refused this model. Never raises."""
    from tinyassets.providers.diagnostics import redacted_failure_detail

    owner, connection, model = (str(v or "").strip() for v in (owner_user_id, connection_id,
                                                                model_id))
    if not all(_IDENTIFIER.match(v) for v in (owner, connection)) or not model or len(model) > 300:
        return False
    moment = now or datetime.now(timezone.utc)
    reason = redacted_failure_detail(str(detail or ""), limit=_DETAIL_LIMIT)
    conn = None
    try:
        conn = _connect(base_path, create=True)
        conn.execute(_SCHEMA)
        conn.execute(
            """
            INSERT INTO refused_model_marks VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(owner_user_id, connection_id, model_id) DO UPDATE SET
                failure_class = excluded.failure_class, detail = excluded.detail,
                refused_at = excluded.refused_at, expires_at = excluded.expires_at
            """,
            (owner, connection, model, str(failure_class or ""), reason,
             _stamp(moment), _stamp(moment + REFUSAL_TTL)),
        )
        return True
    except sqlite3.Error:
        logger.warning("could not remember a refused model")
        return False
    finally:
        if conn is not None:
            conn.close()


def clear_refused_model(
    base_path: str | Path, *, owner_user_id: str, connection_id: str, model_id: str,
) -> None:
    """Forget a mark: the model just answered this owner. Never raises."""
    conn = None
    try:
        conn = _connect(base_path, create=False)
        if conn is None:
            return
        conn.execute(
            "DELETE FROM refused_model_marks "
            "WHERE owner_user_id = ? AND connection_id = ? AND model_id = ?",
            (str(owner_user_id).strip(), str(connection_id).strip(), str(model_id).strip()),
        )
    except sqlite3.Error:
        # No table yet is "nothing to forget".
        pass
    finally:
        if conn is not None:
            conn.close()


def active_refused_models(
    base_path: str | Path, *, owner_user_id: str, now: datetime | None = None,
) -> tuple[RefusedModel, ...]:
    """This owner's unexpired marks. Empty on any failure to read."""
    conn = None
    try:
        conn = _connect(base_path, create=False)
        if conn is None:
            return ()
        rows = conn.execute(
            "SELECT connection_id, model_id, failure_class, detail, refused_at, expires_at "
            "FROM refused_model_marks WHERE owner_user_id = ? AND expires_at > ? "
            "ORDER BY refused_at",
            (str(owner_user_id).strip(), _stamp(now or datetime.now(timezone.utc))),
        ).fetchall()
    except sqlite3.Error:
        return ()
    finally:
        if conn is not None:
            conn.close()
    return tuple(RefusedModel(*row) for row in rows)
