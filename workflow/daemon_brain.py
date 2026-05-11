"""Daemon-scoped atomic memory store.

The daemon wiki remains the curated, human-readable learning surface. This
module stores smaller searchable memory entries underneath that wiki and logs
observable memory events so prompt-time memory use can be inspected later.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import uuid
from collections.abc import Callable, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
DEFAULT_BRAIN_PACKET_CHARS = 1600

VALID_MEMORY_KINDS = {
    "semantic",
    "episodic",
    "procedural",
    "policy",
    "claim",
    "preference",
    "failure_mode",
    "open_loop",
    "contradiction",
    "soul_proposal",
}
VALID_PROMOTION_STATES = {
    "candidate",
    "accepted",
    "promoted",
    "superseded",
    "rejected",
}
VALID_VISIBILITIES = {
    "host_private",
    "borrowable_role_context",
    "published",
}
VALID_EVENT_TYPES = {
    "daemon.memory.query",
    "daemon.memory.retrieve",
    "daemon.memory.inject",
    "daemon.memory.write_candidate",
    "daemon.memory.accept",
    "daemon.memory.reject",
    "daemon.memory.promote_to_wiki",
    "daemon.memory.supersede",
    "daemon.memory.compact",
    "daemon.memory.low_confidence_skip",
    "daemon.memory.eval",
}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _stamp(value: datetime | None = None) -> str:
    current = value or _utc_now()
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    return current.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def daemon_brain_db_path(base_path: str | Path) -> Path:
    """Return the additive daemon-brain SQLite path for this host data root."""
    return Path(base_path) / "daemon_brain.db"


def _connect(base_path: str | Path) -> sqlite3.Connection:
    db_path = daemon_brain_db_path(base_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), timeout=30.0)
    conn.row_factory = sqlite3.Row
    initialize_daemon_brain(conn)
    return conn


def initialize_daemon_brain(conn: sqlite3.Connection) -> None:
    """Create daemon brain tables if missing."""
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS daemon_brain_entries (
            entry_id TEXT PRIMARY KEY,
            daemon_id TEXT NOT NULL,
            memory_kind TEXT NOT NULL,
            content TEXT NOT NULL,
            content_fingerprint TEXT NOT NULL,
            source_type TEXT NOT NULL,
            source_id TEXT NOT NULL,
            source_path TEXT NOT NULL DEFAULT '',
            source_hash TEXT NOT NULL DEFAULT '',
            reliability TEXT NOT NULL,
            temporal_bounds_json TEXT NOT NULL,
            language_type TEXT NOT NULL,
            confidence REAL NOT NULL,
            importance REAL NOT NULL,
            sensitivity_tier TEXT NOT NULL,
            visibility TEXT NOT NULL,
            promotion_state TEXT NOT NULL,
            supersedes_entry_id TEXT,
            superseded_by_entry_id TEXT,
            metadata_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            schema_version INTEGER NOT NULL DEFAULT 1,
            UNIQUE (daemon_id, content_fingerprint)
        );

        CREATE INDEX IF NOT EXISTS idx_daemon_brain_entries_daemon
            ON daemon_brain_entries (daemon_id, promotion_state, updated_at);
        CREATE INDEX IF NOT EXISTS idx_daemon_brain_entries_kind
            ON daemon_brain_entries (daemon_id, memory_kind, promotion_state);
        CREATE INDEX IF NOT EXISTS idx_daemon_brain_entries_source
            ON daemon_brain_entries (daemon_id, source_type, source_id);

        CREATE VIRTUAL TABLE IF NOT EXISTS daemon_brain_entries_fts
            USING fts5(entry_id UNINDEXED, daemon_id UNINDEXED, content);

        CREATE TABLE IF NOT EXISTS daemon_memory_events (
            event_id TEXT PRIMARY KEY,
            daemon_id TEXT NOT NULL,
            event_type TEXT NOT NULL,
            trace_id TEXT NOT NULL,
            source_type TEXT NOT NULL DEFAULT '',
            source_id TEXT NOT NULL DEFAULT '',
            query_text TEXT NOT NULL DEFAULT '',
            entry_ids_json TEXT NOT NULL,
            metadata_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            schema_version INTEGER NOT NULL DEFAULT 1
        );

        CREATE INDEX IF NOT EXISTS idx_daemon_memory_events_daemon
            ON daemon_memory_events (daemon_id, created_at);
        CREATE INDEX IF NOT EXISTS idx_daemon_memory_events_type
            ON daemon_memory_events (daemon_id, event_type, created_at);

        CREATE TABLE IF NOT EXISTS daemon_memory_promotions (
            promotion_id TEXT PRIMARY KEY,
            daemon_id TEXT NOT NULL,
            entry_ids_json TEXT NOT NULL,
            target_path TEXT NOT NULL,
            summary TEXT NOT NULL,
            promoted_at TEXT NOT NULL,
            metadata_json TEXT NOT NULL,
            schema_version INTEGER NOT NULL DEFAULT 1
        );
        """
    )


def _validate_daemon(base_path: str | Path, daemon_id: str) -> dict[str, Any]:
    from workflow.daemon_registry import get_daemon

    daemon = get_daemon(base_path, daemon_id=daemon_id, include_soul=False)
    if not daemon.get("has_soul"):
        raise ValueError("daemon mini-brain requires a soul-bearing daemon")
    return daemon


def _json_dumps(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _json_loads(value: str, default: Any) -> Any:
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return default


def _clean_content(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _fingerprint(content: str) -> str:
    return hashlib.sha256(_clean_content(content).encode("utf-8")).hexdigest()


def _entry_id() -> str:
    return f"daemon-memory::{uuid.uuid4().hex}"


def _event_id() -> str:
    return f"daemon-memory-event::{uuid.uuid4().hex}"


def _trace_id() -> str:
    return f"daemon-memory-trace::{uuid.uuid4().hex}"


def _clamp(value: float, *, default: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        parsed = default
    return max(0.0, min(1.0, parsed))


def _validate_choice(value: str, choices: set[str], field: str) -> str:
    normalized = str(value or "").strip()
    if normalized not in choices:
        raise ValueError(f"{field} must be one of {sorted(choices)}")
    return normalized


def _require_text(value: str, field: str) -> str:
    cleaned = str(value or "").strip()
    if not cleaned:
        raise ValueError(f"{field} is required")
    return cleaned


def _safe_wiki_rel_path(value: str) -> str:
    raw = _require_text(value, "target_rel_path").replace("\\", "/")
    path = Path(raw)
    if path.is_absolute():
        raise ValueError("target_rel_path must be relative")
    parts = path.parts
    if any(part in {"", ".", ".."} for part in parts):
        raise ValueError("target_rel_path must not contain empty or parent segments")
    return path.as_posix()


def _row_to_entry(row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
    get = row.__getitem__
    return {
        "entry_id": get("entry_id"),
        "daemon_id": get("daemon_id"),
        "memory_kind": get("memory_kind"),
        "content": get("content"),
        "content_fingerprint": get("content_fingerprint"),
        "source_type": get("source_type"),
        "source_id": get("source_id"),
        "source_path": get("source_path"),
        "source_hash": get("source_hash"),
        "reliability": get("reliability"),
        "temporal_bounds": _json_loads(get("temporal_bounds_json"), {}),
        "language_type": get("language_type"),
        "confidence": float(get("confidence") or 0.0),
        "importance": float(get("importance") or 0.0),
        "sensitivity_tier": get("sensitivity_tier"),
        "visibility": get("visibility"),
        "promotion_state": get("promotion_state"),
        "supersedes_entry_id": get("supersedes_entry_id"),
        "superseded_by_entry_id": get("superseded_by_entry_id"),
        "metadata": _json_loads(get("metadata_json"), {}),
        "created_at": get("created_at"),
        "updated_at": get("updated_at"),
        "schema_version": int(get("schema_version") or SCHEMA_VERSION),
    }


def _record_event_conn(
    conn: sqlite3.Connection,
    *,
    daemon_id: str,
    event_type: str,
    trace_id: str,
    source_type: str = "",
    source_id: str = "",
    query_text: str = "",
    entry_ids: Sequence[str] | None = None,
    metadata: dict[str, Any] | None = None,
    created_at: datetime | None = None,
) -> dict[str, Any]:
    normalized_event = _validate_choice(event_type, VALID_EVENT_TYPES, "event_type")
    event = {
        "event_id": _event_id(),
        "daemon_id": daemon_id,
        "event_type": normalized_event,
        "trace_id": trace_id,
        "source_type": str(source_type or ""),
        "source_id": str(source_id or ""),
        "query_text": str(query_text or ""),
        "entry_ids": list(entry_ids or []),
        "metadata": dict(metadata or {}),
        "created_at": _stamp(created_at),
        "schema_version": SCHEMA_VERSION,
    }
    conn.execute(
        """
        INSERT INTO daemon_memory_events (
            event_id, daemon_id, event_type, trace_id, source_type, source_id,
            query_text, entry_ids_json, metadata_json, created_at, schema_version
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            event["event_id"],
            event["daemon_id"],
            event["event_type"],
            event["trace_id"],
            event["source_type"],
            event["source_id"],
            event["query_text"],
            _json_dumps(event["entry_ids"]),
            _json_dumps(event["metadata"]),
            event["created_at"],
            SCHEMA_VERSION,
        ),
    )
    return event


def record_daemon_memory_event(
    base_path: str | Path,
    *,
    daemon_id: str,
    event_type: str,
    trace_id: str | None = None,
    source_type: str = "",
    source_id: str = "",
    query_text: str = "",
    entry_ids: Sequence[str] | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Record an observable daemon-memory event."""
    _validate_daemon(base_path, daemon_id)
    with _connect(base_path) as conn:
        return _record_event_conn(
            conn,
            daemon_id=daemon_id,
            event_type=event_type,
            trace_id=trace_id or _trace_id(),
            source_type=source_type,
            source_id=source_id,
            query_text=query_text,
            entry_ids=entry_ids,
            metadata=metadata,
        )


def _insert_fts(conn: sqlite3.Connection, *, entry_id: str, daemon_id: str, content: str) -> None:
    conn.execute(
        """
        INSERT INTO daemon_brain_entries_fts (entry_id, daemon_id, content)
        VALUES (?, ?, ?)
        """,
        (entry_id, daemon_id, content),
    )


def _fetch_entry(conn: sqlite3.Connection, entry_id: str) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT * FROM daemon_brain_entries WHERE entry_id = ?",
        (entry_id,),
    ).fetchone()
    return _row_to_entry(row) if row is not None else None


def capture_daemon_memory(
    base_path: str | Path,
    *,
    daemon_id: str,
    content: str,
    memory_kind: str = "semantic",
    source_type: str = "manual",
    source_id: str = "manual",
    source_path: str = "",
    source_hash: str = "",
    reliability: str,
    temporal_bounds: dict[str, Any] | None = None,
    language_type: str,
    confidence: float = 0.5,
    importance: float = 0.5,
    sensitivity_tier: str = "normal",
    visibility: str = "host_private",
    promotion_state: str = "candidate",
    supersedes_entry_id: str | None = None,
    metadata: dict[str, Any] | None = None,
    embedding: Sequence[float] | None = None,
    created_at: datetime | None = None,
) -> dict[str, Any]:
    """Capture one atomic daemon memory entry.

    Duplicate content is deduped per daemon without rewriting the existing
    entry content. The returned dict includes ``deduped`` to make this visible.
    """
    _validate_daemon(base_path, daemon_id)
    clean = _clean_content(content)
    if not clean:
        raise ValueError("content is required")
    normalized_kind = _validate_choice(memory_kind, VALID_MEMORY_KINDS, "memory_kind")
    normalized_visibility = _validate_choice(visibility, VALID_VISIBILITIES, "visibility")
    normalized_state = _validate_choice(
        promotion_state,
        VALID_PROMOTION_STATES,
        "promotion_state",
    )
    clean_source_type = _require_text(source_type, "source_type")
    clean_source_id = _require_text(source_id, "source_id")
    clean_reliability = _require_text(reliability, "reliability")
    clean_language_type = _require_text(language_type, "language_type")
    bounds = temporal_bounds or {"kind": "unknown"}
    now = _stamp(created_at)
    fingerprint = _fingerprint(clean)
    trace = _trace_id()

    with _connect(base_path) as conn:
        existing = conn.execute(
            """
            SELECT * FROM daemon_brain_entries
            WHERE daemon_id = ? AND content_fingerprint = ?
            """,
            (daemon_id, fingerprint),
        ).fetchone()
        if existing is not None:
            conn.execute(
                """
                UPDATE daemon_brain_entries
                SET updated_at = ?
                WHERE entry_id = ?
                """,
                (now, existing["entry_id"]),
            )
            entry = _fetch_entry(conn, existing["entry_id"])
            assert entry is not None
            _record_event_conn(
                conn,
                daemon_id=daemon_id,
                event_type="daemon.memory.write_candidate",
                trace_id=trace,
                source_type=clean_source_type,
                source_id=clean_source_id,
                entry_ids=[entry["entry_id"]],
                metadata={"deduped": True},
            )
            entry["deduped"] = True
            return entry

        entry_id = _entry_id()
        conn.execute(
            """
            INSERT INTO daemon_brain_entries (
                entry_id, daemon_id, memory_kind, content, content_fingerprint,
                source_type, source_id, source_path, source_hash, reliability,
                temporal_bounds_json, language_type, confidence, importance,
                sensitivity_tier, visibility, promotion_state,
                supersedes_entry_id, superseded_by_entry_id, metadata_json,
                created_at, updated_at, schema_version
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                entry_id,
                daemon_id,
                normalized_kind,
                clean,
                fingerprint,
                clean_source_type,
                clean_source_id,
                str(source_path or ""),
                str(source_hash or ""),
                clean_reliability,
                _json_dumps(bounds),
                clean_language_type,
                _clamp(confidence, default=0.5),
                _clamp(importance, default=0.5),
                str(sensitivity_tier or "normal"),
                normalized_visibility,
                normalized_state,
                supersedes_entry_id,
                None,
                _json_dumps(dict(metadata or {})),
                now,
                now,
                SCHEMA_VERSION,
            ),
        )
        _insert_fts(conn, entry_id=entry_id, daemon_id=daemon_id, content=clean)
        if supersedes_entry_id:
            _supersede_conn(
                conn,
                daemon_id=daemon_id,
                entry_id=supersedes_entry_id,
                superseded_by_entry_id=entry_id,
                trace_id=trace,
            )
        _record_event_conn(
            conn,
            daemon_id=daemon_id,
            event_type="daemon.memory.write_candidate",
            trace_id=trace,
            source_type=clean_source_type,
            source_id=clean_source_id,
            entry_ids=[entry_id],
            metadata={"deduped": False, "memory_kind": normalized_kind},
        )
        entry = _fetch_entry(conn, entry_id)
        assert entry is not None

    if embedding is not None:
        _index_daemon_memory_vector(base_path, entry=entry, embedding=embedding)

    entry["deduped"] = False
    return entry


def _where_filters(
    *,
    include_superseded: bool,
    memory_kinds: Sequence[str] | None,
    visibility: str | None,
) -> tuple[str, list[Any]]:
    clauses: list[str] = ["e.daemon_id = ?"]
    params: list[Any] = []
    if not include_superseded:
        clauses.append("e.promotion_state NOT IN ('superseded', 'rejected')")
    if memory_kinds:
        kinds = [_validate_choice(kind, VALID_MEMORY_KINDS, "memory_kind") for kind in memory_kinds]
        clauses.append(f"e.memory_kind IN ({','.join('?' for _ in kinds)})")
        params.extend(kinds)
    if visibility:
        normalized_visibility = _validate_choice(visibility, VALID_VISIBILITIES, "visibility")
        clauses.append("e.visibility = ?")
        params.append(normalized_visibility)
    return " AND ".join(clauses), params


def _tokens(query: str) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for token in re.findall(r"[A-Za-z0-9_]{2,}", query.lower()):
        if token not in seen:
            seen.add(token)
            out.append(token)
    return out


def _fts_search(
    conn: sqlite3.Connection,
    *,
    daemon_id: str,
    query: str,
    limit: int,
    include_superseded: bool,
    memory_kinds: Sequence[str] | None,
    visibility: str | None,
) -> list[dict[str, Any]]:
    tokens = _tokens(query)
    if not tokens:
        return []
    filter_sql, filter_params = _where_filters(
        include_superseded=include_superseded,
        memory_kinds=memory_kinds,
        visibility=visibility,
    )
    fts_query = " OR ".join(tokens)
    rows = conn.execute(
        f"""
        SELECT e.*, bm25(daemon_brain_entries_fts) AS rank
        FROM daemon_brain_entries_fts
        JOIN daemon_brain_entries e
            ON e.entry_id = daemon_brain_entries_fts.entry_id
        WHERE daemon_brain_entries_fts MATCH ?
            AND {filter_sql}
        ORDER BY rank ASC, e.importance DESC, e.updated_at DESC
        LIMIT ?
        """,
        [fts_query, daemon_id, *filter_params, limit],
    ).fetchall()
    entries: list[dict[str, Any]] = []
    for row in rows:
        entry = _row_to_entry(row)
        rank = float(row["rank"] or 0.0)
        entry["retrieval_score"] = 1.0 / (1.0 + abs(rank))
        entry["retrieval_source"] = "fts"
        entries.append(entry)
    return entries


def _like_search(
    conn: sqlite3.Connection,
    *,
    daemon_id: str,
    query: str,
    limit: int,
    include_superseded: bool,
    memory_kinds: Sequence[str] | None,
    visibility: str | None,
) -> list[dict[str, Any]]:
    tokens = _tokens(query)
    filter_sql, filter_params = _where_filters(
        include_superseded=include_superseded,
        memory_kinds=memory_kinds,
        visibility=visibility,
    )
    like_clauses = []
    like_params = []
    for token in tokens:
        like_clauses.append("LOWER(e.content) LIKE ?")
        like_params.append(f"%{token}%")
    if like_clauses:
        filter_sql += " AND (" + " OR ".join(like_clauses) + ")"
    rows = conn.execute(
        f"""
        SELECT e.*
        FROM daemon_brain_entries e
        WHERE {filter_sql}
        ORDER BY e.importance DESC, e.updated_at DESC
        LIMIT ?
        """,
        [daemon_id, *filter_params, *like_params, limit],
    ).fetchall()
    entries = []
    token_count = max(1, len(tokens))
    for row in rows:
        entry = _row_to_entry(row)
        content = entry["content"].lower()
        hits = sum(1 for token in tokens if token in content)
        entry["retrieval_score"] = hits / token_count if tokens else entry["importance"]
        entry["retrieval_source"] = "like"
        entries.append(entry)
    return entries


def _recent_entries(
    conn: sqlite3.Connection,
    *,
    daemon_id: str,
    limit: int,
    include_superseded: bool,
    memory_kinds: Sequence[str] | None,
    visibility: str | None,
) -> list[dict[str, Any]]:
    filter_sql, filter_params = _where_filters(
        include_superseded=include_superseded,
        memory_kinds=memory_kinds,
        visibility=visibility,
    )
    rows = conn.execute(
        f"""
        SELECT e.*
        FROM daemon_brain_entries e
        WHERE {filter_sql}
        ORDER BY e.importance DESC, e.updated_at DESC
        LIMIT ?
        """,
        [daemon_id, *filter_params, limit],
    ).fetchall()
    entries = []
    for row in rows:
        entry = _row_to_entry(row)
        entry["retrieval_score"] = entry["importance"]
        entry["retrieval_source"] = "recent"
        entries.append(entry)
    return entries


def _index_daemon_memory_vector(
    base_path: str | Path,
    *,
    entry: dict[str, Any],
    embedding: Sequence[float],
) -> None:
    """Optionally index a memory entry in LanceDB using the shared singleton."""
    from workflow.retrieval.vector_store import get_db

    values = [float(item) for item in embedding]
    if not values:
        raise ValueError("embedding must contain at least one value")
    db_path = Path(base_path) / "lancedb"
    db = get_db(str(db_path))
    table_name = "daemon_brain_chunks"
    row = {
        "entry_id": entry["entry_id"],
        "daemon_id": entry["daemon_id"],
        "content": entry["content"],
        "memory_kind": entry["memory_kind"],
        "visibility": entry["visibility"],
        "promotion_state": entry["promotion_state"],
        "created_at": entry["created_at"],
        "embedding": values,
    }
    if table_name in db.list_tables():
        table = db.open_table(table_name)
    else:
        table = db.create_table(table_name, data=[row])
        return
    table.add([row])


def _vector_search(
    base_path: str | Path,
    *,
    daemon_id: str,
    query_embedding: Sequence[float] | None,
    limit: int,
) -> list[dict[str, Any]]:
    if query_embedding is None:
        return []
    from workflow.retrieval.vector_store import get_db

    db_path = Path(base_path) / "lancedb"
    db = get_db(str(db_path))
    table_name = "daemon_brain_chunks"
    if table_name not in db.list_tables():
        return []
    table = db.open_table(table_name)
    values = [float(item) for item in query_embedding]
    safe_daemon = daemon_id.replace("'", "''")
    rows = (
        table.search(values)
        .where(f"daemon_id = '{safe_daemon}'")
        .limit(limit)
        .to_list()
    )
    return [
        {
            "entry_id": str(row["entry_id"]),
            "retrieval_score": 1.0 / (1.0 + float(row.get("_distance") or 0.0)),
            "retrieval_source": "vector",
        }
        for row in rows
    ]


def search_daemon_memory(
    base_path: str | Path,
    *,
    daemon_id: str,
    query: str = "",
    limit: int = 5,
    min_score: float = 0.0,
    include_superseded: bool = False,
    memory_kinds: Sequence[str] | None = None,
    visibility: str | None = None,
    query_embedding: Sequence[float] | None = None,
    trace_id: str | None = None,
) -> dict[str, Any]:
    """Search one daemon's mini-brain.

    Cross-daemon search is deliberately absent. Borrowed-role use should pass
    the borrowed role daemon's ID explicitly and preserve executor identity in
    higher-level routing metadata.
    """
    _validate_daemon(base_path, daemon_id)
    bounded_limit = max(0, min(50, int(limit)))
    trace = trace_id or _trace_id()
    clean_query = str(query or "").strip()
    threshold = _clamp(min_score, default=0.0)

    with _connect(base_path) as conn:
        _record_event_conn(
            conn,
            daemon_id=daemon_id,
            event_type="daemon.memory.query",
            trace_id=trace,
            query_text=clean_query,
            metadata={
                "limit": bounded_limit,
                "min_score": threshold,
                "memory_kinds": list(memory_kinds or []),
                "visibility": visibility,
                "has_query_embedding": query_embedding is not None,
            },
        )
        entries: list[dict[str, Any]]
        if clean_query:
            try:
                entries = _fts_search(
                    conn,
                    daemon_id=daemon_id,
                    query=clean_query,
                    limit=bounded_limit,
                    include_superseded=include_superseded,
                    memory_kinds=memory_kinds,
                    visibility=visibility,
                )
            except sqlite3.OperationalError:
                entries = _like_search(
                    conn,
                    daemon_id=daemon_id,
                    query=clean_query,
                    limit=bounded_limit,
                    include_superseded=include_superseded,
                    memory_kinds=memory_kinds,
                    visibility=visibility,
                )
        else:
            entries = _recent_entries(
                conn,
                daemon_id=daemon_id,
                limit=bounded_limit,
                include_superseded=include_superseded,
                memory_kinds=memory_kinds,
                visibility=visibility,
            )

        vector_hits = _vector_search(
            base_path,
            daemon_id=daemon_id,
            query_embedding=query_embedding,
            limit=bounded_limit,
        )
        if vector_hits:
            by_id = {entry["entry_id"]: entry for entry in entries}
            for hit in vector_hits:
                if hit["entry_id"] in by_id:
                    by_id[hit["entry_id"]]["retrieval_score"] = max(
                        by_id[hit["entry_id"]]["retrieval_score"],
                        hit["retrieval_score"],
                    )
                    by_id[hit["entry_id"]]["retrieval_source"] += "+vector"
                else:
                    fetched = _fetch_entry(conn, hit["entry_id"])
                    if fetched and fetched["daemon_id"] == daemon_id:
                        fetched["retrieval_score"] = hit["retrieval_score"]
                        fetched["retrieval_source"] = hit["retrieval_source"]
                        entries.append(fetched)

        entries = [
            entry for entry in entries
            if float(entry.get("retrieval_score") or 0.0) >= threshold
        ]
        entries.sort(
            key=lambda entry: (
                float(entry.get("retrieval_score") or 0.0),
                entry["importance"],
                entry["updated_at"],
            ),
            reverse=True,
        )
        entries = entries[:bounded_limit]
        entry_ids = [entry["entry_id"] for entry in entries]
        _record_event_conn(
            conn,
            daemon_id=daemon_id,
            event_type="daemon.memory.retrieve",
            trace_id=trace,
            query_text=clean_query,
            entry_ids=entry_ids,
            metadata={"selected_count": len(entry_ids)},
        )
        if not entries and clean_query:
            _record_event_conn(
                conn,
                daemon_id=daemon_id,
                event_type="daemon.memory.low_confidence_skip",
                trace_id=trace,
                query_text=clean_query,
                metadata={"reason": "no_entries_above_threshold"},
            )

    return {
        "daemon_id": daemon_id,
        "host_local": True,
        "trace_id": trace,
        "query": clean_query,
        "count": len(entries),
        "entries": entries,
    }


def list_daemon_memory(
    base_path: str | Path,
    *,
    daemon_id: str,
    limit: int = 50,
    include_superseded: bool = False,
    memory_kinds: Sequence[str] | None = None,
) -> dict[str, Any]:
    """List recent mini-brain entries for one daemon."""
    _validate_daemon(base_path, daemon_id)
    bounded_limit = max(0, min(200, int(limit)))
    with _connect(base_path) as conn:
        entries = _recent_entries(
            conn,
            daemon_id=daemon_id,
            limit=bounded_limit,
            include_superseded=include_superseded,
            memory_kinds=memory_kinds,
            visibility=None,
        )
    return {
        "daemon_id": daemon_id,
        "host_local": True,
        "count": len(entries),
        "entries": entries,
    }


def _truncate_text(text: str, max_chars: int) -> tuple[str, bool]:
    if len(text) <= max_chars:
        return text, False
    marker = "\n[truncated]\n"
    if max_chars <= len(marker):
        return text[:max_chars], True
    return text[: max_chars - len(marker)].rstrip() + marker, True


def build_daemon_brain_packet(
    base_path: str | Path,
    *,
    daemon_id: str,
    query: str = "",
    max_chars: int = DEFAULT_BRAIN_PACKET_CHARS,
    limit: int = 5,
    min_score: float = 0.0,
    trace_id: str | None = None,
) -> dict[str, Any]:
    """Build a bounded mini-brain section for prompt composition."""
    budget = max(0, int(max_chars))
    trace = trace_id or _trace_id()
    results = search_daemon_memory(
        base_path,
        daemon_id=daemon_id,
        query=query,
        limit=limit,
        min_score=min_score,
        trace_id=trace,
    )
    lines = [
        "## Mini Brain Hits",
        "",
        f"- Trace: {trace}",
        f"- Query: {results['query'] or '[recent important memories]'}",
        f"- Selected: {results['count']}",
    ]
    for entry in results["entries"]:
        lines.extend([
            "",
            f"### {entry['entry_id']}",
            (
                f"- Kind: {entry['memory_kind']} | Reliability: "
                f"{entry['reliability']} | Confidence: {entry['confidence']:.2f} | "
                f"Score: {float(entry.get('retrieval_score') or 0.0):.2f}"
            ),
            f"- Source: {entry['source_type']}:{entry['source_id']}",
            f"- State: {entry['promotion_state']} | Visibility: {entry['visibility']}",
            entry["content"],
        ])
    context, truncated = _truncate_text("\n".join(lines).strip(), budget)
    with _connect(base_path) as conn:
        _record_event_conn(
            conn,
            daemon_id=daemon_id,
            event_type="daemon.memory.inject",
            trace_id=trace,
            query_text=results["query"],
            entry_ids=[entry["entry_id"] for entry in results["entries"]],
            metadata={
                "packet_chars": len(context),
                "max_chars": budget,
                "truncated": truncated,
            },
        )
    return {
        "daemon_id": daemon_id,
        "host_local": True,
        "trace_id": trace,
        "query": results["query"],
        "context": context,
        "max_chars": budget,
        "truncated": truncated,
        "selected_count": results["count"],
        "entries": results["entries"],
    }


def _output_text(output: Any) -> str:
    if isinstance(output, str):
        return output
    try:
        return json.dumps(output, sort_keys=True)
    except TypeError:
        return str(output)


def _score_from_signals(output: Any, expected_signals: Sequence[str]) -> dict[str, Any]:
    clean_signals = [str(signal).strip() for signal in expected_signals if str(signal).strip()]
    if not clean_signals:
        raise ValueError("expected_signals must contain at least one non-empty signal")
    haystack = _output_text(output).lower()
    matched = [signal for signal in clean_signals if signal.lower() in haystack]
    missing = [signal for signal in clean_signals if signal not in matched]
    return {
        "score": len(matched) / len(clean_signals),
        "matched_signals": matched,
        "missing_signals": missing,
    }


def _normalize_score(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        if "score" not in value:
            raise ValueError("score_fn result dict must include score")
        details = dict(value)
        details["score"] = _clamp(details["score"], default=0.0)
        return details
    return {"score": _clamp(value, default=0.0)}


def evaluate_daemon_memory_quality(
    base_path: str | Path,
    *,
    daemon_id: str,
    query: str,
    replay_fn: Callable[[dict[str, Any]], Any],
    expected_signals: Sequence[str] | None = None,
    score_fn: Callable[[Any], Any] | None = None,
    limit: int = 5,
    min_score: float = 0.0,
    max_chars: int = DEFAULT_BRAIN_PACKET_CHARS,
    baseline_context: str = "",
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Replay a task with and without selected daemon memory and score the delta.

    The caller owns the actual replay mechanics so this harness stays
    domain-neutral: pass a deterministic ``replay_fn`` that accepts a case dict
    and returns either text or a structured result. Scoring is either a custom
    ``score_fn`` or a simple expected-signal matcher.
    """
    _validate_daemon(base_path, daemon_id)
    if score_fn is None and expected_signals is None:
        raise ValueError("expected_signals or score_fn is required")
    trace = _trace_id()
    packet = build_daemon_brain_packet(
        base_path,
        daemon_id=daemon_id,
        query=query,
        max_chars=max_chars,
        limit=limit,
        min_score=min_score,
        trace_id=trace,
    )
    entry_ids = [entry["entry_id"] for entry in packet["entries"]]

    without_case = {
        "daemon_id": daemon_id,
        "trace_id": trace,
        "query": str(query or ""),
        "memory_enabled": False,
        "context": str(baseline_context or ""),
        "entry_ids": [],
        "entries": [],
    }
    with_case = {
        "daemon_id": daemon_id,
        "trace_id": trace,
        "query": packet["query"],
        "memory_enabled": True,
        "context": packet["context"],
        "entry_ids": entry_ids,
        "entries": packet["entries"],
    }
    without_output = replay_fn(without_case)
    with_output = replay_fn(with_case)

    if score_fn is not None:
        without_score = _normalize_score(score_fn(without_output))
        with_score = _normalize_score(score_fn(with_output))
    else:
        assert expected_signals is not None
        without_score = _score_from_signals(without_output, expected_signals)
        with_score = _score_from_signals(with_output, expected_signals)

    delta = round(float(with_score["score"]) - float(without_score["score"]), 6)
    if delta > 0:
        outcome = "improved"
    elif delta < 0:
        outcome = "regressed"
    else:
        outcome = "unchanged"

    with _connect(base_path) as conn:
        _record_event_conn(
            conn,
            daemon_id=daemon_id,
            event_type="daemon.memory.eval",
            trace_id=trace,
            query_text=packet["query"],
            entry_ids=entry_ids,
            metadata={
                "without_memory_score": without_score["score"],
                "with_memory_score": with_score["score"],
                "delta": delta,
                "outcome": outcome,
                "selected_count": packet["selected_count"],
                "replay_metadata": dict(metadata or {}),
            },
        )

    return {
        "daemon_id": daemon_id,
        "host_local": True,
        "trace_id": trace,
        "query": packet["query"],
        "entry_ids": entry_ids,
        "selected_count": packet["selected_count"],
        "without_memory": {
            **without_score,
            "output": without_output,
        },
        "with_memory": {
            **with_score,
            "output": with_output,
        },
        "delta": delta,
        "outcome": outcome,
    }


def _brain_review_header() -> str:
    today = _utc_now().date().isoformat()
    return (
        "---\n"
        "title: Brain Review\n"
        "type: brain_review\n"
        f"updated: {today}\n"
        "---\n\n"
        "# Brain Review\n\n"
        "Promoted mini-brain memories are summarized here. Entries remain in the "
        "daemon brain database; this page is the curated wiki face.\n"
    )


def promote_daemon_memory_to_wiki(
    base_path: str | Path,
    *,
    daemon_id: str,
    entry_ids: Sequence[str],
    summary: str,
    target_rel_path: str = "pages/brain/review.md",
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Promote selected mini-brain entries into the daemon wiki review page."""
    _validate_daemon(base_path, daemon_id)
    clean_ids = []
    seen_ids: set[str] = set()
    for entry_id in entry_ids:
        clean_id = str(entry_id).strip()
        if clean_id and clean_id not in seen_ids:
            clean_ids.append(clean_id)
            seen_ids.add(clean_id)
    if not clean_ids:
        raise ValueError("entry_ids is required")
    clean_summary = _require_text(summary, "summary")
    safe_target_rel_path = _safe_wiki_rel_path(target_rel_path)
    trace = _trace_id()
    stamp = _stamp()
    with _connect(base_path) as conn:
        rows = conn.execute(
            f"""
            SELECT *
            FROM daemon_brain_entries
            WHERE daemon_id = ?
                AND entry_id IN ({','.join('?' for _ in clean_ids)})
            ORDER BY updated_at DESC
            """,
            [daemon_id, *clean_ids],
        ).fetchall()
        entries = [_row_to_entry(row) for row in rows]
        found = {entry["entry_id"] for entry in entries}
        missing = [entry_id for entry_id in clean_ids if entry_id not in found]
        if missing:
            raise ValueError(f"entries not found for daemon: {', '.join(missing)}")
        conn.execute(
            f"""
            UPDATE daemon_brain_entries
            SET promotion_state = 'promoted', updated_at = ?
            WHERE daemon_id = ?
                AND entry_id IN ({','.join('?' for _ in clean_ids)})
            """,
            [stamp, daemon_id, *clean_ids],
        )
        promotion_id = f"daemon-memory-promotion::{uuid.uuid4().hex}"
        conn.execute(
            """
            INSERT INTO daemon_memory_promotions (
                promotion_id, daemon_id, entry_ids_json, target_path, summary,
                promoted_at, metadata_json, schema_version
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                promotion_id,
                daemon_id,
                _json_dumps(clean_ids),
                safe_target_rel_path,
                clean_summary,
                stamp,
                _json_dumps(dict(metadata or {})),
                SCHEMA_VERSION,
            ),
        )
        _record_event_conn(
            conn,
            daemon_id=daemon_id,
            event_type="daemon.memory.promote_to_wiki",
            trace_id=trace,
            entry_ids=clean_ids,
            metadata={"target_path": safe_target_rel_path, "promotion_id": promotion_id},
        )

    from workflow.daemon_wiki import daemon_wiki_root

    root = daemon_wiki_root(base_path, daemon_id)
    target = root / safe_target_rel_path
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        target.write_text(_brain_review_header(), encoding="utf-8", newline="\n")
    lines = [
        f"\n## [{stamp}] memory promotion",
        "",
        f"- Promotion: `{promotion_id}`",
        f"- Summary: {clean_summary}",
        "- Entries:",
    ]
    for entry in entries:
        lines.append(f"  - `{entry['entry_id']}` ({entry['memory_kind']}): {entry['content']}")
    with target.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write("\n".join(lines) + "\n")
    return {
        "daemon_id": daemon_id,
        "host_local": True,
        "promotion_id": promotion_id,
        "target_path": str(target),
        "promoted_count": len(clean_ids),
        "entry_ids": clean_ids,
        "trace_id": trace,
    }


def _supersede_conn(
    conn: sqlite3.Connection,
    *,
    daemon_id: str,
    entry_id: str,
    superseded_by_entry_id: str,
    trace_id: str,
) -> None:
    conn.execute(
        """
        UPDATE daemon_brain_entries
        SET promotion_state = 'superseded',
            superseded_by_entry_id = ?,
            updated_at = ?
        WHERE daemon_id = ? AND entry_id = ?
        """,
        (superseded_by_entry_id, _stamp(), daemon_id, entry_id),
    )
    _record_event_conn(
        conn,
        daemon_id=daemon_id,
        event_type="daemon.memory.supersede",
        trace_id=trace_id,
        entry_ids=[entry_id, superseded_by_entry_id],
    )


def supersede_daemon_memory(
    base_path: str | Path,
    *,
    daemon_id: str,
    entry_id: str,
    superseded_by_entry_id: str,
) -> dict[str, Any]:
    """Mark one entry superseded by another entry for the same daemon."""
    _validate_daemon(base_path, daemon_id)
    trace = _trace_id()
    with _connect(base_path) as conn:
        old = _fetch_entry(conn, entry_id)
        new = _fetch_entry(conn, superseded_by_entry_id)
        if old is None or old["daemon_id"] != daemon_id:
            raise ValueError("entry_id not found for daemon")
        if new is None or new["daemon_id"] != daemon_id:
            raise ValueError("superseded_by_entry_id not found for daemon")
        _supersede_conn(
            conn,
            daemon_id=daemon_id,
            entry_id=entry_id,
            superseded_by_entry_id=superseded_by_entry_id,
            trace_id=trace,
        )
    return {
        "daemon_id": daemon_id,
        "host_local": True,
        "entry_id": entry_id,
        "superseded_by_entry_id": superseded_by_entry_id,
        "trace_id": trace,
    }


def review_daemon_memory(
    base_path: str | Path,
    *,
    daemon_id: str,
    entry_id: str,
    decision: str,
    reviewer_id: str = "host",
    note: str = "",
    superseded_by_entry_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Accept, reject, or supersede one daemon memory entry."""
    _validate_daemon(base_path, daemon_id)
    normalized = str(decision or "").strip().lower()
    decision_to_state = {
        "accept": "accepted",
        "accepted": "accepted",
        "reject": "rejected",
        "rejected": "rejected",
        "supersede": "superseded",
        "superseded": "superseded",
    }
    state = decision_to_state.get(normalized)
    if state is None:
        raise ValueError("decision must be accept, reject, or supersede")
    if state == "superseded" and not str(superseded_by_entry_id or "").strip():
        raise ValueError("superseded_by_entry_id is required for supersede")

    trace = _trace_id()
    stamp = _stamp()
    with _connect(base_path) as conn:
        entry = _fetch_entry(conn, entry_id)
        if entry is None or entry["daemon_id"] != daemon_id:
            raise ValueError("entry_id not found for daemon")
        if state == "superseded":
            replacement_id = str(superseded_by_entry_id or "").strip()
            replacement = _fetch_entry(conn, replacement_id)
            if replacement is None or replacement["daemon_id"] != daemon_id:
                raise ValueError("superseded_by_entry_id not found for daemon")
        else:
            replacement_id = None

        entry_metadata = dict(entry.get("metadata") or {})
        review_record = {
            "decision": state,
            "reviewer_id": str(reviewer_id or "host"),
            "note": str(note or ""),
            "reviewed_at": stamp,
        }
        if replacement_id:
            review_record["superseded_by_entry_id"] = replacement_id
        if metadata:
            review_record["metadata"] = dict(metadata)
        history = list(entry_metadata.get("review_history") or [])
        history.append(review_record)
        entry_metadata["last_review"] = review_record
        entry_metadata["review_history"] = history

        conn.execute(
            """
            UPDATE daemon_brain_entries
            SET promotion_state = ?,
                superseded_by_entry_id = ?,
                metadata_json = ?,
                updated_at = ?
            WHERE daemon_id = ? AND entry_id = ?
            """,
            (
                state,
                replacement_id,
                _json_dumps(entry_metadata),
                stamp,
                daemon_id,
                entry_id,
            ),
        )
        event_type = {
            "accepted": "daemon.memory.accept",
            "rejected": "daemon.memory.reject",
            "superseded": "daemon.memory.supersede",
        }[state]
        event_entry_ids = [entry_id]
        if replacement_id:
            event_entry_ids.append(replacement_id)
        _record_event_conn(
            conn,
            daemon_id=daemon_id,
            event_type=event_type,
            trace_id=trace,
            entry_ids=event_entry_ids,
            metadata=review_record,
        )
        reviewed = _fetch_entry(conn, entry_id)
        assert reviewed is not None

    return {
        "daemon_id": daemon_id,
        "host_local": True,
        "entry_id": entry_id,
        "decision": state,
        "entry": reviewed,
        "trace_id": trace,
    }


def memory_observability_status(
    base_path: str | Path,
    *,
    daemon_id: str,
) -> dict[str, Any]:
    """Return counts that make daemon-memory behavior inspectable."""
    _validate_daemon(base_path, daemon_id)
    with _connect(base_path) as conn:
        entry_count = conn.execute(
            "SELECT COUNT(*) FROM daemon_brain_entries WHERE daemon_id = ?",
            (daemon_id,),
        ).fetchone()[0]
        event_count = conn.execute(
            "SELECT COUNT(*) FROM daemon_memory_events WHERE daemon_id = ?",
            (daemon_id,),
        ).fetchone()[0]
        promotion_count = conn.execute(
            "SELECT COUNT(*) FROM daemon_memory_promotions WHERE daemon_id = ?",
            (daemon_id,),
        ).fetchone()[0]
        states = {
            row["promotion_state"]: int(row["count"])
            for row in conn.execute(
                """
                SELECT promotion_state, COUNT(*) AS count
                FROM daemon_brain_entries
                WHERE daemon_id = ?
                GROUP BY promotion_state
                """,
                (daemon_id,),
            )
        }
        events = {
            row["event_type"]: int(row["count"])
            for row in conn.execute(
                """
                SELECT event_type, COUNT(*) AS count
                FROM daemon_memory_events
                WHERE daemon_id = ?
                GROUP BY event_type
                """,
                (daemon_id,),
            )
        }
    return {
        "daemon_id": daemon_id,
        "host_local": True,
        "db_path": str(daemon_brain_db_path(base_path)),
        "schema_version": SCHEMA_VERSION,
        "entry_count": int(entry_count),
        "event_count": int(event_count),
        "promotion_count": int(promotion_count),
        "promotion_states": states,
        "event_types": events,
        "candidate_backlog": int(states.get("candidate", 0) + states.get("accepted", 0)),
    }
