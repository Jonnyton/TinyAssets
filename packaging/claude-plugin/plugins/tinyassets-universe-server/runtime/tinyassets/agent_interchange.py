"""Private staging and loss-aware interchange for portable agent definitions."""

from __future__ import annotations

import hashlib
import hmac
import json
import math
import os
import re
import sqlite3
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from tinyassets.custom_agents import (
    AgentConflictError,
    AgentNotFoundError,
    AgentValidationError,
    _author_and_key,
    _canonical_json,
    _definition_from_row,
    _ensure_schema,
    _fingerprint,
    _normalize_definition_payload,
    _publish_normalized,
    _read_definition_row,
)
from tinyassets.ids import new_ulid

ADAPTER_SCHEMA = "agent-interchange-adapter/v1"
MAX_SOURCE_BYTES = 1024 * 1024
MAX_MAPPING_BYTES = 128 * 1024
MAX_MAPPING_RULES = 512
MAX_REPORT_ITEMS = 4096
MAX_DEPTH = 32
STAGE_TTL_SECONDS = 24 * 60 * 60
_HMAC_ENV = "TINYASSETS_AGENT_INTERCHANGE_HMAC_KEY"
_REASON_CODE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_SECRET_FIELDS = frozenset(
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
_CLASSIFICATIONS = frozenset(
    {
        "preserved",
        "normalized",
        "unsupported",
        "omitted_secret",
        "requires_private_binding",
        "requires_runtime",
    }
)
_SCHEMA_LOCK = threading.Lock()
_SCHEMA_INITIALIZED: set[str] = set()

_SCHEMA = """
CREATE TABLE IF NOT EXISTS agent_import_stages (
    stage_id TEXT PRIMARY KEY,
    actor_id TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('staged', 'published')),
    direction TEXT NOT NULL CHECK (direction IN ('import', 'export')),
    source_media_type TEXT NOT NULL,
    sanitized_source_digest TEXT NOT NULL,
    source_commitment TEXT NOT NULL,
    adapter_ref TEXT NOT NULL,
    adapter_version TEXT NOT NULL,
    adapter_digest TEXT NOT NULL,
    candidate_json TEXT NOT NULL,
    report_json TEXT NOT NULL,
    receipt_json TEXT NOT NULL,
    created_at REAL NOT NULL,
    expires_at REAL NOT NULL,
    published_definition_id TEXT,
    FOREIGN KEY(published_definition_id)
        REFERENCES agent_definitions(agent_definition_id) ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS idx_agent_import_stage_actor
    ON agent_import_stages(actor_id, created_at DESC);

CREATE TABLE IF NOT EXISTS agent_interchange_idempotency (
    actor_id TEXT NOT NULL,
    operation TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    request_digest TEXT NOT NULL,
    resource_id TEXT NOT NULL,
    created_at REAL NOT NULL,
    PRIMARY KEY(actor_id, operation, idempotency_key)
);

CREATE TABLE IF NOT EXISTS agent_conversion_receipts (
    receipt_digest TEXT PRIMARY KEY,
    actor_id TEXT NOT NULL,
    stage_id TEXT,
    receipt_json TEXT NOT NULL,
    created_at REAL NOT NULL,
    FOREIGN KEY(stage_id) REFERENCES agent_import_stages(stage_id) ON DELETE SET NULL
);
"""


class InterchangeValidationError(AgentValidationError):
    """An interchange envelope violates the bounded public contract."""


class InterchangeConflictError(AgentConflictError):
    """An actor-scoped interchange idempotency identity conflicts."""


class InterchangeNotFoundError(AgentNotFoundError):
    """A private stage is absent, expired, or invisible to the caller."""


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _json_clone(value: Any) -> Any:
    return json.loads(_canonical_json(value))


def _check_depth(value: Any, *, depth: int = 0) -> None:
    if depth > MAX_DEPTH:
        raise InterchangeValidationError(f"payload nesting exceeds {MAX_DEPTH}")
    if isinstance(value, dict):
        for nested in value.values():
            _check_depth(nested, depth=depth + 1)
    elif isinstance(value, list):
        for nested in value:
            _check_depth(nested, depth=depth + 1)


def _bounded_json(value: Any, *, limit: int, label: str) -> Any:
    cloned = _json_clone(value)
    _check_depth(cloned)
    size = len(_canonical_json(cloned).encode("utf-8"))
    if size > limit:
        raise InterchangeValidationError(f"{label} exceeds {limit} bytes")
    return cloned


def _pointer_segment(value: str) -> str:
    return value.replace("~", "~0").replace("/", "~1")


def _pointer_parts(pointer: str) -> list[str]:
    if pointer == "":
        return []
    if not isinstance(pointer, str) or not pointer.startswith("/") or len(pointer) > 512:
        raise InterchangeValidationError("JSON Pointer is invalid or exceeds 512 characters")
    return [part.replace("~1", "/").replace("~0", "~") for part in pointer[1:].split("/")]


def enumerate_json_inventory(value: Any, pointer: str = "") -> list[str]:
    """Return canonical RFC 6901 paths for scalar leaves and empty containers."""

    if isinstance(value, dict):
        if not value:
            return [pointer]
        paths: list[str] = []
        for key in sorted(value):
            child = f"{pointer}/{_pointer_segment(str(key))}"
            paths.extend(enumerate_json_inventory(value[key], child))
        return paths
    if isinstance(value, list):
        if not value:
            return [pointer]
        paths = []
        for index, item in enumerate(value):
            paths.extend(enumerate_json_inventory(item, f"{pointer}/{index}"))
        return paths
    return [pointer]


def _pointer_get(value: Any, pointer: str) -> Any:
    current = value
    for part in _pointer_parts(pointer):
        if isinstance(current, dict) and part in current:
            current = current[part]
        elif isinstance(current, list) and part.isdigit() and int(part) < len(current):
            current = current[int(part)]
        else:
            raise InterchangeValidationError(f"source path {pointer} does not exist")
    return _json_clone(current)


def _pointer_set(root: dict[str, Any], pointer: str, value: Any) -> None:
    parts = _pointer_parts(pointer)
    if not parts:
        if not isinstance(value, dict):
            raise InterchangeValidationError("root adapter output must be a JSON object")
        root.clear()
        root.update(_json_clone(value))
        return
    current = root
    for part in parts[:-1]:
        nested = current.setdefault(part, {})
        if not isinstance(nested, dict):
            raise InterchangeValidationError(f"target path {pointer} collides")
        current = nested
    current[parts[-1]] = _json_clone(value)


def _is_secret_path(pointer: str) -> bool:
    return any(part.casefold() in _SECRET_FIELDS for part in _pointer_parts(pointer))


def _sanitize(value: Any, pointer: str = "") -> Any:
    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        for key, nested in value.items():
            child = f"{pointer}/{_pointer_segment(str(key))}"
            sanitized[key] = (
                "[omitted_secret]"
                if _is_secret_path(child)
                else _sanitize(nested, child)
            )
        return sanitized
    if isinstance(value, list):
        return [_sanitize(item, f"{pointer}/{index}") for index, item in enumerate(value)]
    return _json_clone(value)


def _matching_rule(path: str, rules: list[dict[str, Any]]) -> dict[str, Any]:
    matches = []
    for rule in rules:
        source_path = rule.get("source_path")
        if isinstance(source_path, str) and (
            path == source_path or path.startswith(f"{source_path}/")
        ):
            matches.append(rule)
    if len(matches) != 1:
        suffix = "is missing" if not matches else "is covered more than once"
        raise InterchangeValidationError(f"inventory path {path} {suffix}")
    return matches[0]


def _adapter_metadata(adapter: dict[str, Any]) -> tuple[dict[str, Any], str]:
    document = _bounded_json(adapter, limit=MAX_MAPPING_BYTES, label="adapter mapping")
    if document.get("schema_version") != ADAPTER_SCHEMA:
        raise InterchangeValidationError(f"adapter schema_version must equal {ADAPTER_SCHEMA}")
    adapter_ref = str(document.get("adapter_ref") or "").strip()
    adapter_version = str(document.get("adapter_version") or "").strip()
    if not adapter_ref or len(adapter_ref) > 256:
        raise InterchangeValidationError("adapter_ref is required and bounded to 256 characters")
    if not adapter_version or len(adapter_version) > 64:
        raise InterchangeValidationError("adapter_version is required and bounded to 64 characters")
    rules = document.get("rules")
    if not isinstance(rules, list) or len(rules) > MAX_MAPPING_RULES:
        raise InterchangeValidationError(
            f"adapter rules must be a list of at most {MAX_MAPPING_RULES}"
        )
    return document, _sha256(document)


def convert_declarative_json(
    source_json: dict[str, Any],
    adapter: dict[str, Any],
) -> dict[str, Any]:
    """Apply the closed declarative JSON mapping grammar."""

    source = _bounded_json(source_json, limit=MAX_SOURCE_BYTES, label="source")
    mapping, adapter_digest = _adapter_metadata(adapter)
    rules: list[dict[str, Any]] = mapping["rules"]
    inventory = enumerate_json_inventory(source)
    if len(inventory) > MAX_REPORT_ITEMS:
        raise InterchangeValidationError(f"source inventory exceeds {MAX_REPORT_ITEMS} items")
    sanitized = _sanitize(source)
    candidate: dict[str, Any] = {}
    for rule in rules:
        op = str(rule.get("op") or "")
        if op not in {"constant", "copy", "namespace_preserve", "omit"}:
            raise InterchangeValidationError("adapter rule uses unsupported operation")

    items: list[dict[str, Any]] = []
    for path in inventory:
        rule = _matching_rule(path, rules)
        op = str(rule.get("op") or "")
        classification = str(rule.get("classification") or "")
        if classification not in _CLASSIFICATIONS:
            raise InterchangeValidationError(f"inventory path {path} has invalid classification")
        secret_path = _is_secret_path(path)
        if secret_path and (
            op != "omit" or classification not in {"omitted_secret", "requires_private_binding"}
        ):
            raise InterchangeValidationError(f"secret inventory path {path} must be omitted")
        source_path = str(rule.get("source_path"))
        target_path = str(rule.get("target_path") or "")
        item = {
            "source_path": path,
            "classification": classification,
            "reason_code": str(rule.get("reason_code") or classification),
        }
        if not _REASON_CODE.fullmatch(item["reason_code"]):
            raise InterchangeValidationError(f"inventory path {path} has invalid reason_code")
        if target_path:
            suffix = path[len(source_path) :]
            item["target_path"] = f"{target_path}{suffix}"
        items.append(item)

    for rule in rules:
        if rule.get("op") in {"copy", "namespace_preserve"}:
            _pointer_set(
                candidate,
                str(rule.get("target_path") or ""),
                _pointer_get(sanitized, str(rule.get("source_path") or "")),
            )
    for rule in rules:
        if rule.get("op") == "constant":
            _pointer_set(
                candidate,
                str(rule.get("target_path") or ""),
                rule.get("value"),
            )

    normalized = _normalize_definition_payload(candidate)
    report = {
        "schema_version": 1,
        "direction": "import",
        "inventory_verification": "core_json",
        "exhaustive": True,
        "lossless": all(item["classification"] == "preserved" for item in items),
        "items": items,
    }
    return {
        "candidate": normalized,
        "report": report,
        "sanitized_source": sanitized,
        "adapter_ref": mapping["adapter_ref"],
        "adapter_version": mapping["adapter_version"],
        "adapter_digest": adapter_digest,
    }


def _ensure_interchange_schema(base_path: str | Path) -> Path:
    path = _ensure_schema(base_path)
    key = str(path)
    if key in _SCHEMA_INITIALIZED:
        return path
    with _SCHEMA_LOCK:
        if key in _SCHEMA_INITIALIZED:
            return path
        conn = sqlite3.connect(path, timeout=30.0)
        try:
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
def _interchange_connect(base_path: str | Path) -> Iterator[sqlite3.Connection]:
    path = _ensure_interchange_schema(base_path)
    conn = sqlite3.connect(path, timeout=30.0)
    try:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout = 30000")
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("BEGIN IMMEDIATE")
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _source_commitment(source: Any) -> str:
    key = os.environ.get(_HMAC_ENV, "").encode("utf-8")
    if len(key) < 32:
        raise InterchangeValidationError(f"{_HMAC_ENV} must contain at least 32 bytes")
    return hmac.new(key, _canonical_json(source).encode("utf-8"), hashlib.sha256).hexdigest()


def _receipt(
    *,
    conversion: dict[str, Any],
    sanitized_source_digest: str,
    created_at: float,
) -> dict[str, Any]:
    candidate_fingerprint = _fingerprint(conversion["candidate"])
    report_digest = _sha256(conversion["report"])
    receipt = {
        "schema_version": 1,
        "direction": "import",
        "sanitized_source_digest_algorithm": "sha256",
        "sanitized_source_digest": sanitized_source_digest,
        "adapter_ref": conversion["adapter_ref"],
        "adapter_version": conversion["adapter_version"],
        "adapter_digest_algorithm": "sha256",
        "adapter_digest": conversion["adapter_digest"],
        "output_kind": "canonical_definition",
        "output_digest_algorithm": "sha256",
        "output_digest": candidate_fingerprint,
        "content_fingerprint": candidate_fingerprint,
        "report_digest_algorithm": "sha256",
        "report_digest": report_digest,
        "created_at": created_at,
        "receipt_digest_algorithm": "sha256",
    }
    receipt["receipt_digest"] = _sha256(receipt)
    return receipt


def verify_conversion_receipt(receipt: dict[str, Any]) -> bool:
    document = _bounded_json(receipt, limit=MAX_SOURCE_BYTES, label="receipt")
    supplied = str(document.pop("receipt_digest", ""))
    if document.get("receipt_digest_algorithm") != "sha256":
        raise InterchangeValidationError("receipt digest algorithm must equal sha256")
    if not re.fullmatch(r"[0-9a-f]{64}", supplied) or supplied != _sha256(document):
        raise InterchangeValidationError("receipt digest does not match")
    return True


def _stage_from_row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "stage_id": str(row["stage_id"]),
        "actor_id": str(row["actor_id"]),
        "status": str(row["status"]),
        "direction": str(row["direction"]),
        "source_media_type": str(row["source_media_type"]),
        "sanitized_source_digest_algorithm": "sha256",
        "sanitized_source_digest": str(row["sanitized_source_digest"]),
        "source_commitment_algorithm": "hmac-sha256",
        "source_commitment": str(row["source_commitment"]),
        "adapter_ref": str(row["adapter_ref"]),
        "adapter_version": str(row["adapter_version"]),
        "adapter_digest_algorithm": "sha256",
        "adapter_digest": str(row["adapter_digest"]),
        "candidate": json.loads(str(row["candidate_json"])),
        "report": json.loads(str(row["report_json"])),
        "receipt": json.loads(str(row["receipt_json"])),
        "created_at": float(row["created_at"]),
        "expires_at": float(row["expires_at"]),
        "published_definition_id": row["published_definition_id"],
    }


def _idempotent_resource(
    conn: sqlite3.Connection,
    *,
    actor: str,
    operation: str,
    key: str,
    request_digest: str,
) -> str | None:
    if not key:
        return None
    row = conn.execute(
        """
        SELECT request_digest, resource_id
        FROM agent_interchange_idempotency
        WHERE actor_id = ? AND operation = ? AND idempotency_key = ?
        """,
        (actor, operation, key),
    ).fetchone()
    if row is None:
        return None
    if row["request_digest"] != request_digest:
        raise InterchangeConflictError("idempotency key was used for different input")
    return str(row["resource_id"])


def stage_import(
    base_path: str | Path,
    *,
    actor_id: str,
    source_json: dict[str, Any],
    adapter: dict[str, Any],
    idempotency_key: str = "",
    now: float | None = None,
) -> dict[str, Any]:
    actor, key = _author_and_key(actor_id, idempotency_key)
    created_at = time.time() if now is None else float(now)
    if not math.isfinite(created_at):
        raise InterchangeValidationError("now must be finite")
    source = _bounded_json(source_json, limit=MAX_SOURCE_BYTES, label="source")
    commitment = _source_commitment(source)
    conversion = convert_declarative_json(source, adapter)
    sanitized_digest = _sha256(conversion["sanitized_source"])
    receipt = _receipt(
        conversion=conversion,
        sanitized_source_digest=sanitized_digest,
        created_at=created_at,
    )
    request_digest = _sha256(
        {
            "source_commitment": commitment,
            "adapter_digest": conversion["adapter_digest"],
            "direction": "import",
        }
    )
    with _interchange_connect(base_path) as conn:
        existing_id = _idempotent_resource(
            conn,
            actor=actor,
            operation="stage_import",
            key=key,
            request_digest=request_digest,
        )
        if existing_id:
            row = conn.execute(
                "SELECT * FROM agent_import_stages WHERE stage_id = ? AND actor_id = ?",
                (existing_id, actor),
            ).fetchone()
            if row is None:
                raise InterchangeNotFoundError("import stage is unavailable")
            return _stage_from_row(row)
        stage_id = f"agent_stage_{new_ulid()}"
        expires_at = created_at + STAGE_TTL_SECONDS
        conn.execute(
            """
            INSERT INTO agent_import_stages (
                stage_id, actor_id, status, direction, source_media_type,
                sanitized_source_digest, source_commitment, adapter_ref,
                adapter_version, adapter_digest, candidate_json, report_json,
                receipt_json, created_at, expires_at
            ) VALUES (?, ?, 'staged', 'import', 'application/json', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                stage_id,
                actor,
                sanitized_digest,
                commitment,
                conversion["adapter_ref"],
                conversion["adapter_version"],
                conversion["adapter_digest"],
                _canonical_json(conversion["candidate"]),
                _canonical_json(conversion["report"]),
                _canonical_json(receipt),
                created_at,
                expires_at,
            ),
        )
        if key:
            conn.execute(
                """
                INSERT INTO agent_interchange_idempotency (
                    actor_id, operation, idempotency_key,
                    request_digest, resource_id, created_at
                ) VALUES (?, 'stage_import', ?, ?, ?, ?)
                """,
                (actor, key, request_digest, stage_id, created_at),
            )
        row = conn.execute(
            "SELECT * FROM agent_import_stages WHERE stage_id = ?",
            (stage_id,),
        ).fetchone()
        assert row is not None
        return _stage_from_row(row)


def get_import_stage(
    base_path: str | Path,
    *,
    actor_id: str,
    stage_id: str,
    now: float | None = None,
) -> dict[str, Any] | None:
    actor = (actor_id or "").strip()
    current = time.time() if now is None else float(now)
    with _interchange_connect(base_path) as conn:
        row = conn.execute(
            "SELECT * FROM agent_import_stages WHERE stage_id = ? AND actor_id = ?",
            ((stage_id or "").strip(), actor),
        ).fetchone()
        if row is None:
            return None
        if row["status"] == "staged" and float(row["expires_at"]) <= current:
            conn.execute(
                "DELETE FROM agent_interchange_idempotency WHERE resource_id = ?",
                (stage_id,),
            )
            conn.execute("DELETE FROM agent_import_stages WHERE stage_id = ?", (stage_id,))
            return None
        return _stage_from_row(row)


def publish_import_stage(
    base_path: str | Path,
    *,
    actor_id: str,
    stage_id: str,
    idempotency_key: str = "",
    now: float | None = None,
) -> dict[str, Any]:
    actor, key = _author_and_key(actor_id, idempotency_key)
    current = time.time() if now is None else float(now)
    with _interchange_connect(base_path) as conn:
        row = conn.execute(
            "SELECT * FROM agent_import_stages WHERE stage_id = ? AND actor_id = ?",
            ((stage_id or "").strip(), actor),
        ).fetchone()
        if row is None or (row["status"] == "staged" and float(row["expires_at"]) <= current):
            raise InterchangeNotFoundError("import stage is unavailable")
        candidate = json.loads(str(row["candidate_json"]))
        normalized = _normalize_definition_payload(candidate)
        request_digest = _sha256(
            {"stage_id": stage_id, "candidate_fingerprint": _fingerprint(normalized)}
        )
        existing_id = _idempotent_resource(
            conn,
            actor=actor,
            operation="publish_stage",
            key=key,
            request_digest=request_digest,
        )
        if existing_id:
            existing = _read_definition_row(conn, existing_id)
            if existing is None:
                raise InterchangeNotFoundError("published definition is unavailable")
            return _definition_from_row(conn, existing)
        if row["status"] == "published":
            existing = _read_definition_row(conn, str(row["published_definition_id"]))
            if existing is None:
                raise InterchangeNotFoundError("published definition is unavailable")
            return _definition_from_row(conn, existing)
        published = _publish_normalized(
            conn,
            actor=actor,
            normalized=normalized,
            key="",
            imported=True,
        )
        receipt = json.loads(str(row["receipt_json"]))
        conn.execute(
            """
            INSERT OR IGNORE INTO agent_conversion_receipts (
                receipt_digest, actor_id, stage_id, receipt_json, created_at
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                receipt["receipt_digest"],
                actor,
                stage_id,
                _canonical_json(receipt),
                current,
            ),
        )
        conn.execute(
            """
            UPDATE agent_import_stages
            SET status = 'published', published_definition_id = ?
            WHERE stage_id = ?
            """,
            (published["agent_definition_id"], stage_id),
        )
        if key:
            conn.execute(
                """
                INSERT INTO agent_interchange_idempotency (
                    actor_id, operation, idempotency_key,
                    request_digest, resource_id, created_at
                ) VALUES (?, 'publish_stage', ?, ?, ?, ?)
                """,
                (
                    actor,
                    key,
                    request_digest,
                    published["agent_definition_id"],
                    current,
                ),
            )
        return published


__all__ = [
    "InterchangeConflictError",
    "InterchangeNotFoundError",
    "InterchangeValidationError",
    "convert_declarative_json",
    "enumerate_json_inventory",
    "get_import_stage",
    "publish_import_stage",
    "stage_import",
    "verify_conversion_receipt",
]
