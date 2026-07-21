"""Host-local values for repo-blind branch-design binding slots.

Shared branch rows and portable artifacts carry only ``is_binding`` schema.
Values live in the bound universe's private SQLite store and are projected into
execution only after author/universe authorization. Credentials are never
accepted here; effectors resolve them from the credential broker by destination.
"""

from __future__ import annotations

import json
import math
import os
import re
import sqlite3
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_DB_FILENAME = ".branch-bindings.db"
_SUPPORTED_BINDING_FIELDS = frozenset({"target_repo", "merge_policy"})
_MAX_VALUE_BYTES = 8192
_TARGET_REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_CONNECT_LOCK = threading.Lock()


class BranchBindingError(ValueError):
    """A binding request is invalid or its private store is unreadable."""


def declared_binding_fields(state_schema: Any) -> set[str]:
    fields: set[str] = set()
    for raw in state_schema or []:
        if not isinstance(raw, dict) or not raw.get("is_binding"):
            continue
        name = raw.get("name")
        if isinstance(name, str) and name.strip():
            fields.add(name.strip())
    return fields


def _db_path(universe_dir: str | Path) -> Path:
    root = Path(universe_dir)
    if not root.is_dir():
        raise BranchBindingError("bound universe directory does not exist")
    return root / _DB_FILENAME


def _connect(universe_dir: str | Path) -> sqlite3.Connection:
    path = _db_path(universe_dir)
    conn = sqlite3.connect(path, timeout=30.0, isolation_level=None)
    conn.execute("PRAGMA busy_timeout = 30000")
    with _CONNECT_LOCK:
        deadline = time.monotonic() + 30.0
        while True:
            try:
                conn.execute("PRAGMA journal_mode = WAL")
                break
            except sqlite3.OperationalError as exc:
                if "locked" not in str(exc).lower() or time.monotonic() >= deadline:
                    conn.close()
                    raise
                time.sleep(0.05)
        conn.execute("PRAGMA synchronous = FULL")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS branch_bindings (
                branch_def_id TEXT NOT NULL,
                field_name TEXT NOT NULL,
                value_json TEXT NOT NULL,
                updated_by TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (branch_def_id, field_name)
            )
            """
        )
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return conn


def _encode_value(field_name: str, value: Any) -> str:
    if field_name not in _SUPPORTED_BINDING_FIELDS:
        raise BranchBindingError(
            f"binding field {field_name!r} is unsupported; only target_repo and "
            "merge_policy are accepted. Deposit credentials through the "
            "encrypted broker instead"
        )
    if field_name == "target_repo" and (
        not isinstance(value, str) or not _TARGET_REPO_RE.fullmatch(value)
    ):
        raise BranchBindingError(
            "target_repo must be a plain owner/repo name with no URL, userinfo, "
            "query, fragment, or credential material"
        )
    if isinstance(value, float) and not math.isfinite(value):
        raise BranchBindingError(f"binding field {field_name!r} must be finite")
    try:
        encoded = json.dumps(value, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise BranchBindingError(
            f"binding field {field_name!r} is not JSON-serializable"
        ) from exc
    if len(encoded.encode("utf-8")) > _MAX_VALUE_BYTES:
        raise BranchBindingError(
            f"binding field {field_name!r} exceeds {_MAX_VALUE_BYTES} bytes"
        )
    if value in (None, ""):
        raise BranchBindingError(f"binding field {field_name!r} cannot be empty")
    if field_name == "merge_policy" and (
        not isinstance(value, str) or value not in {"manual", "auto", "timer"}
    ):
        raise BranchBindingError(
            "merge_policy must be one of: manual, auto, timer"
        )
    return encoded


def bind_branch_values(
    universe_dir: str | Path,
    branch_def_id: str,
    state_schema: Any,
    values: dict[str, Any],
    *,
    actor: str,
) -> dict[str, list[str]]:
    branch_id = (branch_def_id or "").strip()
    if not branch_id:
        raise BranchBindingError("branch_def_id is required")
    if not isinstance(values, dict) or not values:
        raise BranchBindingError("binding values must be a non-empty JSON object")
    declared = declared_binding_fields(state_schema)
    unsupported = sorted(set(values) - _SUPPORTED_BINDING_FIELDS)
    if unsupported:
        raise BranchBindingError(
            f"unsupported binding fields: {unsupported}; credentials belong in "
            "the encrypted broker"
        )
    unknown = sorted(set(values) - declared)
    if unknown:
        raise BranchBindingError(
            f"binding fields are not declared by the design: {unknown}"
        )
    encoded = {name: _encode_value(name, value) for name, value in values.items()}
    now = datetime.now(timezone.utc).isoformat()
    with _connect(universe_dir) as conn:
        conn.execute("BEGIN IMMEDIATE")
        for name, value_json in encoded.items():
            conn.execute(
                """
                INSERT INTO branch_bindings
                    (branch_def_id, field_name, value_json, updated_by, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(branch_def_id, field_name) DO UPDATE SET
                    value_json = excluded.value_json,
                    updated_by = excluded.updated_by,
                    updated_at = excluded.updated_at
                """,
                (branch_id, name, value_json, actor or "anonymous", now),
            )
    present = sorted(load_branch_values(universe_dir, branch_id, state_schema))
    return {"bound_fields": present, "missing_fields": sorted(declared - set(present))}


def load_branch_values(
    universe_dir: str | Path,
    branch_def_id: str,
    state_schema: Any,
) -> dict[str, Any]:
    declared = declared_binding_fields(state_schema)
    if not declared:
        return {}
    with _connect(universe_dir) as conn:
        rows = conn.execute(
            "SELECT field_name, value_json FROM branch_bindings "
            "WHERE branch_def_id = ?",
            ((branch_def_id or "").strip(),),
        ).fetchall()
    values: dict[str, Any] = {}
    for field_name, value_json in rows:
        if field_name not in declared:
            continue
        try:
            values[field_name] = json.loads(value_json)
        except (TypeError, json.JSONDecodeError) as exc:
            raise BranchBindingError(
                f"binding field {field_name!r} is corrupt"
            ) from exc
    return values
