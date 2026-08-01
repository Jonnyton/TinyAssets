"""Composable public agent definitions and private universe bindings.

This module owns the durable custom-agent domain model.  Public definitions
are immutable commons artifacts; universe bindings are private operational
configuration.  Runtime activation intentionally lives elsewhere.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import re
import sqlite3
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from tinyassets.ids import new_ulid
from tinyassets.storage import db_path

AGENT_SCHEMA_VERSION = 1
MAX_AGENT_JSON_BYTES = 256 * 1024
MAX_COMPONENTS = 64
MAX_LINEAGE_DEPTH = 50

_COMPONENT_KEY = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
_CONTENT_FINGERPRINT = re.compile(r"^[0-9a-f]{64}$")
_SECRET_FIELD_NAMES = frozenset(
    {
        "access_token",
        "api_key",
        "apikey",
        "client_secret",
        "credential",
        "password",
        "private_key",
        "refresh_token",
        "secret",
    }
)
_FORBIDDEN_BINDING_CONTENT_FIELDS = frozenset(
    {
        "conversation",
        "conversation_history",
        "conversations",
        "effect_payload",
        "effect_payloads",
        "external_write_results",
        "message_history",
        "messages",
        "run_state",
        "runtime_state",
        "transcript",
        "transcripts",
    }
)
_SCHEMA_LOCK = threading.Lock()
_SCHEMA_INITIALIZED: set[str] = set()

_SCHEMA = """
CREATE TABLE IF NOT EXISTS agent_definitions (
    agent_definition_id TEXT PRIMARY KEY,
    author_id TEXT NOT NULL,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    schema_version INTEGER NOT NULL CHECK (schema_version = 1),
    tags_json TEXT NOT NULL DEFAULT '[]',
    components_json TEXT NOT NULL,
    external_origins_json TEXT NOT NULL DEFAULT '[]',
    portable_json TEXT NOT NULL,
    content_fingerprint TEXT NOT NULL,
    idempotency_key TEXT NOT NULL DEFAULT '',
    created_at REAL NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_agent_definition_idempotency
    ON agent_definitions(author_id, idempotency_key)
    WHERE idempotency_key <> '';

CREATE INDEX IF NOT EXISTS idx_agent_definition_created
    ON agent_definitions(created_at DESC);

CREATE INDEX IF NOT EXISTS idx_agent_definition_author
    ON agent_definitions(author_id, created_at DESC);

CREATE TABLE IF NOT EXISTS agent_component_lineage (
    child_definition_id TEXT NOT NULL,
    child_component_key TEXT NOT NULL,
    parent_definition_id TEXT NOT NULL,
    parent_component_key TEXT NOT NULL,
    credit_share REAL NOT NULL
        CHECK (credit_share >= 0.0 AND credit_share <= 1.0),
    generation_depth INTEGER NOT NULL
        CHECK (generation_depth >= 1 AND generation_depth <= 50),
    created_at REAL NOT NULL,
    PRIMARY KEY (
        child_definition_id,
        child_component_key,
        parent_definition_id,
        parent_component_key
    ),
    FOREIGN KEY(child_definition_id)
        REFERENCES agent_definitions(agent_definition_id) ON DELETE CASCADE,
    FOREIGN KEY(parent_definition_id)
        REFERENCES agent_definitions(agent_definition_id) ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS idx_agent_lineage_parent
    ON agent_component_lineage(parent_definition_id, parent_component_key);

CREATE TABLE IF NOT EXISTS agent_bindings (
    agent_binding_id TEXT PRIMARY KEY,
    universe_id TEXT NOT NULL,
    agent_definition_id TEXT NOT NULL,
    configuration_json TEXT NOT NULL,
    revision INTEGER NOT NULL DEFAULT 1 CHECK (revision >= 1),
    status TEXT NOT NULL DEFAULT 'configured'
        CHECK (status IN ('configured')),
    created_by TEXT NOT NULL,
    updated_by TEXT NOT NULL,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    FOREIGN KEY(agent_definition_id)
        REFERENCES agent_definitions(agent_definition_id) ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS idx_agent_binding_universe
    ON agent_bindings(universe_id, updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_agent_binding_definition
    ON agent_bindings(agent_definition_id);
"""


class AgentValidationError(ValueError):
    """An agent document violates the public persistence contract."""


class AgentConflictError(AgentValidationError):
    """An idempotency or revision precondition conflicts with stored state."""


class AgentNotFoundError(LookupError):
    """A requested definition or universe-scoped binding does not exist."""


def _canonical_json(value: Any) -> str:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise AgentValidationError(f"payload must be JSON-compatible: {exc}") from exc


def _json_clone(value: Any) -> Any:
    return json.loads(_canonical_json(value))


def _fingerprint(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _check_size(value: Any) -> None:
    size = len(_canonical_json(value).encode("utf-8"))
    if size > MAX_AGENT_JSON_BYTES:
        raise AgentValidationError(
            f"payload exceeds {MAX_AGENT_JSON_BYTES} bytes of canonical JSON"
        )


def _check_secret_fields(value: Any, path: str = "") -> None:
    if isinstance(value, dict):
        for raw_key, child in value.items():
            key = str(raw_key)
            child_path = f"{path}.{key}" if path else key
            if key.strip().lower() in _SECRET_FIELD_NAMES:
                raise AgentValidationError(
                    f"{child_path} contains a forbidden secret-bearing field"
                )
            _check_secret_fields(child, child_path)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _check_secret_fields(child, f"{path}[{index}]")


def _check_binding_content_fields(value: Any, path: str = "") -> None:
    if isinstance(value, dict):
        for raw_key, child in value.items():
            key = str(raw_key)
            child_path = f"{path}.{key}" if path else key
            if key.strip().lower() in _FORBIDDEN_BINDING_CONTENT_FIELDS:
                raise AgentValidationError(
                    f"{child_path} is private operational content, "
                    "not binding configuration"
                )
            _check_binding_content_fields(child, child_path)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _check_binding_content_fields(child, f"{path}[{index}]")


def _normalize_tags(raw: Any) -> list[str]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise AgentValidationError("tags must be a JSON list")
    if len(raw) > 32:
        raise AgentValidationError("tags may contain at most 32 values")
    tags: list[str] = []
    for index, value in enumerate(raw):
        if not isinstance(value, str) or not value.strip():
            raise AgentValidationError(f"tags[{index}] must be a non-empty string")
        tag = value.strip()
        if len(tag) > 64:
            raise AgentValidationError(f"tags[{index}] exceeds 64 characters")
        if tag not in tags:
            tags.append(tag)
    return tags


def _normalize_components(raw: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(raw, dict) or not raw:
        raise AgentValidationError("components must be a non-empty JSON object")
    if len(raw) > MAX_COMPONENTS:
        raise AgentValidationError(f"components may contain at most {MAX_COMPONENTS} entries")
    components: dict[str, dict[str, Any]] = {}
    for raw_key, raw_component in raw.items():
        key = str(raw_key)
        path = f"components.{key}"
        if not _COMPONENT_KEY.fullmatch(key):
            raise AgentValidationError(f"{path} is not a valid component key")
        if not isinstance(raw_component, dict):
            raise AgentValidationError(f"{path} must be a JSON object")
        component = _json_clone(raw_component)
        kind = component.get("kind")
        if not isinstance(kind, str) or not kind.strip():
            raise AgentValidationError(f"{path}.kind must be a non-empty string")
        component["kind"] = kind.strip()
        components[key] = component
    return components


def _normalize_lineage(
    raw: Any,
    components: dict[str, dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise AgentValidationError("lineage must be a JSON object")
    lineage: dict[str, list[dict[str, Any]]] = {}
    for raw_child_key, raw_sources in raw.items():
        child_key = str(raw_child_key)
        path = f"lineage.{child_key}"
        if child_key not in components:
            raise AgentValidationError(f"{path} names no child component")
        if not isinstance(raw_sources, list) or not raw_sources:
            raise AgentValidationError(f"{path} must be a non-empty JSON list")
        sources: list[dict[str, Any]] = []
        total = 0.0
        seen: set[tuple[str, str]] = set()
        for index, raw_source in enumerate(raw_sources):
            source_path = f"{path}[{index}]"
            if not isinstance(raw_source, dict):
                raise AgentValidationError(f"{source_path} must be a JSON object")
            definition_id = str(raw_source.get("definition_id") or "").strip()
            component_key = str(raw_source.get("component_key") or "").strip()
            if not definition_id:
                raise AgentValidationError(f"{source_path}.definition_id is required")
            if not _COMPONENT_KEY.fullmatch(component_key):
                raise AgentValidationError(f"{source_path}.component_key is invalid")
            try:
                share = float(raw_source.get("credit_share"))
            except (TypeError, ValueError) as exc:
                raise AgentValidationError(
                    f"{source_path}.credit_share must be a finite number"
                ) from exc
            if not math.isfinite(share) or share < 0.0 or share > 1.0:
                raise AgentValidationError(f"{source_path}.credit_share must be within [0, 1]")
            source_key = (definition_id, component_key)
            if source_key in seen:
                raise AgentValidationError(f"{source_path} duplicates a source")
            seen.add(source_key)
            total += share
            source = {
                "definition_id": definition_id,
                "component_key": component_key,
                "credit_share": share,
            }
            definition_fingerprint = str(
                raw_source.get("definition_fingerprint") or ""
            ).strip()
            component_fingerprint = str(
                raw_source.get("component_fingerprint") or ""
            ).strip()
            if bool(definition_fingerprint) != bool(component_fingerprint):
                raise AgentValidationError(
                    f"{source_path} must supply both lineage fingerprints"
                )
            if definition_fingerprint:
                if not _CONTENT_FINGERPRINT.fullmatch(definition_fingerprint):
                    raise AgentValidationError(
                        f"{source_path}.definition_fingerprint is invalid"
                    )
                if not _CONTENT_FINGERPRINT.fullmatch(component_fingerprint):
                    raise AgentValidationError(
                        f"{source_path}.component_fingerprint is invalid"
                    )
                source["definition_fingerprint"] = definition_fingerprint
                source["component_fingerprint"] = component_fingerprint
            sources.append(source)
        if total > 1.0 + 1e-9:
            raise AgentValidationError(f"{path} credit shares total {total:g}, exceeding 1.0")
        lineage[child_key] = sorted(
            sources,
            key=lambda item: (
                item["definition_id"],
                item["component_key"],
            ),
        )
    return dict(sorted(lineage.items()))


def _normalize_definition_payload(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise AgentValidationError("definition payload must be a JSON object")
    cloned = _json_clone(payload)
    schema_version = cloned.get("schema_version")
    if isinstance(schema_version, bool) or schema_version != AGENT_SCHEMA_VERSION:
        raise AgentValidationError(f"schema_version must equal {AGENT_SCHEMA_VERSION}")
    name = cloned.get("name")
    if not isinstance(name, str) or not name.strip():
        raise AgentValidationError("name must be a non-empty string")
    name = name.strip()
    if len(name) > 120:
        raise AgentValidationError("name exceeds 120 characters")
    description = cloned.get("description", "")
    if not isinstance(description, str):
        raise AgentValidationError("description must be a string")
    if len(description) > 4000:
        raise AgentValidationError("description exceeds 4000 characters")

    components = _normalize_components(cloned.get("components"))
    lineage = _normalize_lineage(cloned.get("lineage"), components)
    external_origins = cloned.get("external_origins", [])
    if not isinstance(external_origins, list):
        raise AgentValidationError("external_origins must be a JSON list")
    external_origins = _json_clone(external_origins)

    normalized = {
        "schema_version": AGENT_SCHEMA_VERSION,
        "name": name,
        "description": description,
        "tags": _normalize_tags(cloned.get("tags")),
        "components": components,
        "lineage": lineage,
        "external_origins": external_origins,
    }
    _check_secret_fields(normalized)
    _check_size(normalized)
    return normalized


def _normalize_binding_payload(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise AgentValidationError("binding payload must be a JSON object")
    cloned = _json_clone(payload)
    schema_version = cloned.get("schema_version")
    if isinstance(schema_version, bool) or schema_version != AGENT_SCHEMA_VERSION:
        raise AgentValidationError(f"schema_version must equal {AGENT_SCHEMA_VERSION}")
    name = cloned.get("name")
    if not isinstance(name, str) or not name.strip():
        raise AgentValidationError("name must be a non-empty string")
    cloned["name"] = name.strip()
    if len(cloned["name"]) > 120:
        raise AgentValidationError("name exceeds 120 characters")
    reserved = {
        "agent_binding_id",
        "agent_definition_id",
        "created_at",
        "created_by",
        "revision",
        "status",
        "universe_id",
        "updated_at",
        "updated_by",
    }
    collision = sorted(reserved.intersection(cloned))
    if collision:
        raise AgentValidationError(f"binding payload contains reserved field {collision[0]}")
    _check_secret_fields(cloned)
    _check_binding_content_fields(cloned)
    _check_size(cloned)
    return cloned


def _ensure_schema(base_path: str | Path) -> Path:
    path = db_path(base_path)
    key = str(path)
    if key in _SCHEMA_INITIALIZED:
        return path
    with _SCHEMA_LOCK:
        if key in _SCHEMA_INITIALIZED:
            return path
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(path, timeout=30.0)
        try:
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA busy_timeout = 30000")
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute("PRAGMA journal_mode = WAL")
            with conn:
                conn.executescript(_SCHEMA)
        finally:
            conn.close()
        _SCHEMA_INITIALIZED.add(key)
    return path


@contextmanager
def _agent_connect(
    base_path: str | Path,
) -> Iterator[sqlite3.Connection]:
    path = _ensure_schema(base_path)
    conn = sqlite3.connect(path, timeout=30.0)
    try:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout = 30000")
        conn.execute("PRAGMA foreign_keys = ON")
        with conn:
            yield conn
    finally:
        conn.close()


def _lineage_rows(
    conn: sqlite3.Connection,
    definition_id: str,
) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT child_component_key, parent_definition_id,
               parent_component_key, credit_share, generation_depth
        FROM agent_component_lineage
        WHERE child_definition_id = ?
        ORDER BY child_component_key, parent_definition_id,
                 parent_component_key
        """,
        (definition_id,),
    ).fetchall()
    return [
        {
            "child_component_key": str(row["child_component_key"]),
            "parent_definition_id": str(row["parent_definition_id"]),
            "parent_component_key": str(row["parent_component_key"]),
            "credit_share": float(row["credit_share"]),
            "generation_depth": int(row["generation_depth"]),
        }
        for row in rows
    ]


def _definition_from_row(
    conn: sqlite3.Connection,
    row: sqlite3.Row,
) -> dict[str, Any]:
    portable = json.loads(str(row["portable_json"]))
    portable["content_fingerprint"] = str(row["content_fingerprint"])
    return {
        "agent_definition_id": str(row["agent_definition_id"]),
        "author_id": str(row["author_id"]),
        "schema_version": int(row["schema_version"]),
        "name": str(row["name"]),
        "description": str(row["description"]),
        "tags": json.loads(str(row["tags_json"])),
        "components": json.loads(str(row["components_json"])),
        "external_origins": json.loads(str(row["external_origins_json"])),
        "content_fingerprint": str(row["content_fingerprint"]),
        "created_at": float(row["created_at"]),
        "lineage": _lineage_rows(conn, str(row["agent_definition_id"])),
        "portable_definition": portable,
    }


def _read_definition_row(
    conn: sqlite3.Connection,
    definition_id: str,
) -> sqlite3.Row | None:
    return conn.execute(
        """
        SELECT *
        FROM agent_definitions
        WHERE agent_definition_id = ?
        """,
        (definition_id,),
    ).fetchone()


def _lineage_edge(
    conn: sqlite3.Connection,
    *,
    child_key: str,
    source: dict[str, Any],
    parent_id: str,
) -> dict[str, Any]:
    parent_key = source["component_key"]
    depth_row = conn.execute(
        """
        SELECT MAX(generation_depth) AS depth
        FROM agent_component_lineage
        WHERE child_definition_id = ?
          AND child_component_key = ?
        """,
        (parent_id, parent_key),
    ).fetchone()
    generation_depth = int(depth_row["depth"] or 0) + 1
    if generation_depth > MAX_LINEAGE_DEPTH:
        raise AgentValidationError(
            f"lineage may not exceed {MAX_LINEAGE_DEPTH} generations"
        )
    return {
        "child_component_key": child_key,
        "parent_definition_id": parent_id,
        "parent_component_key": parent_key,
        "credit_share": float(source["credit_share"]),
        "generation_depth": generation_depth,
    }


def _parent_component(
    parent: sqlite3.Row,
    component_key: str,
) -> dict[str, Any] | None:
    components = json.loads(str(parent["components_json"]))
    component = components.get(component_key)
    return component if isinstance(component, dict) else None


def _enrich_local_lineage(
    conn: sqlite3.Connection,
    normalized: dict[str, Any],
) -> dict[str, Any]:
    enriched = copy.deepcopy(normalized)
    for sources in enriched["lineage"].values():
        for source in sources:
            parent_id = source["definition_id"]
            parent_key = source["component_key"]
            parent = _read_definition_row(conn, parent_id)
            component = (
                _parent_component(parent, parent_key) if parent is not None else None
            )
            if parent is None or component is None:
                raise AgentValidationError(
                    f"parent component {parent_id}.{parent_key} does not exist"
                )
            definition_fingerprint = str(parent["content_fingerprint"])
            component_fingerprint = _fingerprint(component)
            supplied_definition = source.get("definition_fingerprint")
            supplied_component = source.get("component_fingerprint")
            if supplied_definition and supplied_definition != definition_fingerprint:
                raise AgentValidationError(
                    f"parent definition fingerprint does not match {parent_id}"
                )
            if supplied_component and supplied_component != component_fingerprint:
                raise AgentValidationError(
                    f"parent component fingerprint does not match {parent_id}.{parent_key}"
                )
            source["definition_fingerprint"] = definition_fingerprint
            source["component_fingerprint"] = component_fingerprint
    _check_size(enriched)
    return enriched


def _verified_local_lineage(
    conn: sqlite3.Connection,
    lineage: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    verified: list[dict[str, Any]] = []
    for child_key, sources in lineage.items():
        for source in sources:
            parent_id = source["definition_id"]
            parent_key = source["component_key"]
            parent = _read_definition_row(conn, parent_id)
            component = (
                _parent_component(parent, parent_key) if parent is not None else None
            )
            if parent is None or component is None:
                raise AgentValidationError(
                    f"parent component {parent_id}.{parent_key} does not exist"
                )
            verified.append(
                _lineage_edge(
                    conn,
                    child_key=child_key,
                    source=source,
                    parent_id=parent_id,
                )
            )
    return verified


def _verified_import_lineage(
    conn: sqlite3.Connection,
    lineage: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    verified: list[dict[str, Any]] = []
    for child_key, sources in lineage.items():
        for source in sources:
            parent_key = source["component_key"]
            definition_fingerprint = source.get("definition_fingerprint")
            component_fingerprint = source.get("component_fingerprint")
            if not definition_fingerprint or not component_fingerprint:
                continue
            rows = conn.execute(
                """
                SELECT *
                FROM agent_definitions
                WHERE content_fingerprint = ?
                ORDER BY agent_definition_id
                """,
                (definition_fingerprint,),
            ).fetchall()
            matches = [
                row
                for row in rows
                if (
                    (component := _parent_component(row, parent_key)) is not None
                    and _fingerprint(component) == component_fingerprint
                )
            ]
            if len(matches) == 1:
                verified.append(
                    _lineage_edge(
                        conn,
                        child_key=child_key,
                        source=source,
                        parent_id=str(matches[0]["agent_definition_id"]),
                    )
                )
    return verified


def _author_and_key(author_id: str, idempotency_key: str) -> tuple[str, str]:
    actor = (author_id or "").strip()
    if not actor or actor == "anonymous":
        raise AgentValidationError("an authenticated author_id is required")
    key = (idempotency_key or "").strip()
    if len(key) > 128:
        raise AgentValidationError("idempotency_key exceeds 128 characters")
    return actor, key


def _publish_normalized(
    conn: sqlite3.Connection,
    *,
    actor: str,
    normalized: dict[str, Any],
    key: str,
    imported: bool,
) -> dict[str, Any]:
    stored = copy.deepcopy(normalized) if imported else _enrich_local_lineage(conn, normalized)
    content_fingerprint = _fingerprint(stored)

    if key:
        existing = conn.execute(
            """
            SELECT *
            FROM agent_definitions
            WHERE author_id = ? AND idempotency_key = ?
            """,
            (actor, key),
        ).fetchone()
        if existing is not None:
            if existing["content_fingerprint"] != content_fingerprint:
                raise AgentConflictError(
                    "idempotency_key was already used for different content"
                )
            return _definition_from_row(conn, existing)

    verified_lineage = (
        _verified_import_lineage(conn, stored["lineage"])
        if imported
        else _verified_local_lineage(conn, stored["lineage"])
    )
    definition_id = f"agent_{new_ulid()}"
    created_at = time.time()
    insert_sql = """
        INSERT INTO agent_definitions (
            agent_definition_id, author_id, name, description,
            schema_version, tags_json, components_json,
            external_origins_json, portable_json, content_fingerprint,
            idempotency_key, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """
    if key:
        insert_sql += " ON CONFLICT DO NOTHING"
    cursor = conn.execute(
        insert_sql,
        (
            definition_id,
            actor,
            stored["name"],
            stored["description"],
            AGENT_SCHEMA_VERSION,
            _canonical_json(stored["tags"]),
            _canonical_json(stored["components"]),
            _canonical_json(stored["external_origins"]),
            _canonical_json(stored),
            content_fingerprint,
            key,
            created_at,
        ),
    )
    if cursor.rowcount == 0:
        existing = conn.execute(
            """
            SELECT *
            FROM agent_definitions
            WHERE author_id = ? AND idempotency_key = ?
            """,
            (actor, key),
        ).fetchone()
        if existing is None:
            raise AgentConflictError("definition write conflicted")
        if existing["content_fingerprint"] != content_fingerprint:
            raise AgentConflictError(
                "idempotency_key was already used for different content"
            )
        return _definition_from_row(conn, existing)
    for edge in verified_lineage:
        conn.execute(
            """
            INSERT INTO agent_component_lineage (
                child_definition_id, child_component_key,
                parent_definition_id, parent_component_key,
                credit_share, generation_depth, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                definition_id,
                edge["child_component_key"],
                edge["parent_definition_id"],
                edge["parent_component_key"],
                edge["credit_share"],
                edge["generation_depth"],
                created_at,
            ),
        )
    row = _read_definition_row(conn, definition_id)
    assert row is not None
    return _definition_from_row(conn, row)


def publish_definition(
    base_path: str | Path,
    *,
    author_id: str,
    payload: dict[str, Any],
    idempotency_key: str = "",
) -> dict[str, Any]:
    """Publish one immutable public definition and verified lineage."""

    actor, key = _author_and_key(author_id, idempotency_key)
    normalized = _normalize_definition_payload(payload)
    with _agent_connect(base_path) as conn:
        return _publish_normalized(
            conn,
            actor=actor,
            normalized=normalized,
            key=key,
            imported=False,
        )


def get_definition(
    base_path: str | Path,
    definition_id: str,
) -> dict[str, Any] | None:
    with _agent_connect(base_path) as conn:
        row = _read_definition_row(conn, (definition_id or "").strip())
        return _definition_from_row(conn, row) if row is not None else None


def list_definitions(
    base_path: str | Path,
    *,
    query: str = "",
    tags: list[str] | tuple[str, ...] = (),
    author_id: str = "",
    limit: int = 30,
) -> list[dict[str, Any]]:
    bounded_limit = max(1, min(int(limit), 100))
    wanted_query = (query or "").strip().casefold()
    wanted_tags = {str(tag).strip() for tag in tags if str(tag).strip()}
    wanted_author = (author_id or "").strip()

    with _agent_connect(base_path) as conn:
        rows = conn.execute(
            """
            SELECT *
            FROM agent_definitions
            ORDER BY created_at DESC, agent_definition_id DESC
            """
        ).fetchall()
        results: list[dict[str, Any]] = []
        for row in rows:
            if wanted_author and row["author_id"] != wanted_author:
                continue
            row_tags = set(json.loads(str(row["tags_json"])))
            if wanted_tags and not wanted_tags.issubset(row_tags):
                continue
            if wanted_query:
                haystack = f"{row['name']} {row['description']}".casefold()
                if wanted_query not in haystack:
                    continue
            results.append(_definition_from_row(conn, row))
            if len(results) >= bounded_limit:
                break
        return results


def import_definition(
    base_path: str | Path,
    *,
    author_id: str,
    portable_definition: dict[str, Any],
    idempotency_key: str = "",
) -> dict[str, Any]:
    """Validate a portable export and republish it into the local commons."""

    if not isinstance(portable_definition, dict):
        raise AgentValidationError("portable_definition must be a JSON object")
    supplied = _json_clone(portable_definition)
    supplied_fingerprint = str(supplied.pop("content_fingerprint", "")).strip()
    normalized = _normalize_definition_payload(supplied)
    if supplied_fingerprint and supplied_fingerprint != _fingerprint(normalized):
        raise AgentValidationError("portable definition fingerprint does not match")
    actor, key = _author_and_key(author_id, idempotency_key)
    with _agent_connect(base_path) as conn:
        return _publish_normalized(
            conn,
            actor=actor,
            normalized=normalized,
            key=key,
            imported=True,
        )


def _binding_from_row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "agent_binding_id": str(row["agent_binding_id"]),
        "universe_id": str(row["universe_id"]),
        "agent_definition_id": str(row["agent_definition_id"]),
        "configuration": json.loads(str(row["configuration_json"])),
        "revision": int(row["revision"]),
        "status": str(row["status"]),
        "created_by": str(row["created_by"]),
        "updated_by": str(row["updated_by"]),
        "created_at": float(row["created_at"]),
        "updated_at": float(row["updated_at"]),
    }


def _read_binding_row(
    conn: sqlite3.Connection,
    *,
    universe_id: str,
    binding_id: str,
) -> sqlite3.Row | None:
    return conn.execute(
        """
        SELECT *
        FROM agent_bindings
        WHERE universe_id = ? AND agent_binding_id = ?
        """,
        (universe_id, binding_id),
    ).fetchone()


def _require_definition(
    conn: sqlite3.Connection,
    definition_id: str,
) -> None:
    if _read_definition_row(conn, definition_id) is None:
        raise AgentNotFoundError(f"agent definition {definition_id!r} was not found")


def create_binding(
    base_path: str | Path,
    *,
    universe_id: str,
    definition_id: str,
    created_by: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Create private universe configuration for a public definition."""

    uid = (universe_id or "").strip()
    did = (definition_id or "").strip()
    actor = (created_by or "").strip()
    if not uid:
        raise AgentValidationError("universe_id is required")
    if not did:
        raise AgentValidationError("definition_id is required")
    if not actor or actor == "anonymous":
        raise AgentValidationError("an authenticated created_by actor is required")
    configuration = _normalize_binding_payload(payload)
    binding_id = f"agent_binding_{new_ulid()}"
    created_at = time.time()

    with _agent_connect(base_path) as conn:
        _require_definition(conn, did)
        conn.execute(
            """
            INSERT INTO agent_bindings (
                agent_binding_id, universe_id, agent_definition_id,
                configuration_json, revision, status, created_by, updated_by,
                created_at, updated_at
            )
            VALUES (?, ?, ?, ?, 1, 'configured', ?, ?, ?, ?)
            """,
            (
                binding_id,
                uid,
                did,
                _canonical_json(configuration),
                actor,
                actor,
                created_at,
                created_at,
            ),
        )
        row = _read_binding_row(
            conn,
            universe_id=uid,
            binding_id=binding_id,
        )
        assert row is not None
        return _binding_from_row(row)


def get_binding(
    base_path: str | Path,
    *,
    universe_id: str,
    binding_id: str,
) -> dict[str, Any] | None:
    with _agent_connect(base_path) as conn:
        row = _read_binding_row(
            conn,
            universe_id=(universe_id or "").strip(),
            binding_id=(binding_id or "").strip(),
        )
        return _binding_from_row(row) if row is not None else None


def list_bindings(
    base_path: str | Path,
    *,
    universe_id: str,
    limit: int = 30,
) -> list[dict[str, Any]]:
    uid = (universe_id or "").strip()
    bounded_limit = max(1, min(int(limit), 100))
    with _agent_connect(base_path) as conn:
        rows = conn.execute(
            """
            SELECT *
            FROM agent_bindings
            WHERE universe_id = ?
            ORDER BY updated_at DESC, agent_binding_id DESC
            LIMIT ?
            """,
            (uid, bounded_limit),
        ).fetchall()
        return [_binding_from_row(row) for row in rows]


def update_binding(
    base_path: str | Path,
    *,
    universe_id: str,
    binding_id: str,
    expected_revision: int,
    updated_by: str,
    payload: dict[str, Any],
    definition_id: str = "",
) -> dict[str, Any]:
    """Replace binding configuration using an atomic revision precondition."""

    uid = (universe_id or "").strip()
    bid = (binding_id or "").strip()
    actor = (updated_by or "").strip()
    if not uid or not bid:
        raise AgentValidationError("universe_id and binding_id are required")
    if (
        isinstance(expected_revision, bool)
        or not isinstance(expected_revision, int)
        or expected_revision < 1
    ):
        raise AgentValidationError("expected_revision must be a positive integer")
    if not actor or actor == "anonymous":
        raise AgentValidationError("an authenticated updated_by actor is required")
    configuration = _normalize_binding_payload(payload)
    requested_definition = (definition_id or "").strip()
    updated_at = time.time()

    with _agent_connect(base_path) as conn:
        current = _read_binding_row(
            conn,
            universe_id=uid,
            binding_id=bid,
        )
        if current is None:
            raise AgentNotFoundError(f"agent binding {bid!r} was not found")
        selected_definition = requested_definition or str(current["agent_definition_id"])
        _require_definition(conn, selected_definition)
        cursor = conn.execute(
            """
            UPDATE agent_bindings
            SET agent_definition_id = ?,
                configuration_json = ?,
                revision = revision + 1,
                updated_by = ?,
                updated_at = ?
            WHERE universe_id = ?
              AND agent_binding_id = ?
              AND revision = ?
            """,
            (
                selected_definition,
                _canonical_json(configuration),
                actor,
                updated_at,
                uid,
                bid,
                expected_revision,
            ),
        )
        if cursor.rowcount != 1:
            actual = _read_binding_row(
                conn,
                universe_id=uid,
                binding_id=bid,
            )
            actual_revision = int(actual["revision"]) if actual is not None else None
            raise AgentConflictError(
                f"binding revision conflict: expected {expected_revision}, found {actual_revision}"
            )
        updated = _read_binding_row(
            conn,
            universe_id=uid,
            binding_id=bid,
        )
        assert updated is not None
        return _binding_from_row(updated)


__all__ = [
    "AGENT_SCHEMA_VERSION",
    "AgentConflictError",
    "AgentNotFoundError",
    "AgentValidationError",
    "MAX_AGENT_JSON_BYTES",
    "MAX_COMPONENTS",
    "MAX_LINEAGE_DEPTH",
    "create_binding",
    "get_binding",
    "get_definition",
    "import_definition",
    "list_bindings",
    "list_definitions",
    "publish_definition",
    "update_binding",
]
