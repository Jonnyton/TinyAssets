"""Publication-readiness records for research Goal gate claims.

These records are structured evidence for publication-rung claims. They are
stored in the runs database because they support gate/run evidence rather than
the Git-backed Goal catalog itself.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

READINESS_SCHEMA = """
CREATE TABLE IF NOT EXISTS publication_readiness (
    readiness_id              TEXT PRIMARY KEY,
    goal_id                   TEXT NOT NULL,
    branch_def_id             TEXT NOT NULL DEFAULT '',
    target_venue              TEXT NOT NULL,
    target_rung               TEXT NOT NULL DEFAULT '',
    manifest_json             TEXT NOT NULL,
    status                    TEXT NOT NULL CHECK (status IN ('ready','blocked')),
    blockers_json             TEXT NOT NULL DEFAULT '[]',
    created_by                TEXT NOT NULL,
    created_at                TEXT NOT NULL,
    updated_at                TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_publication_readiness_goal
    ON publication_readiness(goal_id);
CREATE INDEX IF NOT EXISTS idx_publication_readiness_branch
    ON publication_readiness(branch_def_id);
"""


@dataclass(frozen=True)
class PublicationReadiness:
    readiness_id: str
    goal_id: str
    branch_def_id: str
    target_venue: str
    target_rung: str
    manifest: dict[str, Any]
    status: str
    blockers: list[str]
    created_by: str
    created_at: str
    updated_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "readiness_id": self.readiness_id,
            "goal_id": self.goal_id,
            "branch_def_id": self.branch_def_id,
            "target_venue": self.target_venue,
            "target_rung": self.target_rung,
            "manifest": self.manifest,
            "status": self.status,
            "blockers": self.blockers,
            "created_by": self.created_by,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _runs_db(base_path: str | Path) -> Path:
    from workflow.runs import runs_db_path

    return runs_db_path(base_path)


def _connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path), timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 30000")
    return conn


def migrate_publication_readiness_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(READINESS_SCHEMA)


def _ensure_schema(base_path: str | Path) -> Path:
    db = _runs_db(base_path)
    db.parent.mkdir(parents=True, exist_ok=True)
    with _connect(db) as conn:
        migrate_publication_readiness_schema(conn)
    return db


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _non_empty(value: Any) -> bool:
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, dict)):
        return bool(value)
    return value is not None


def validate_manifest(manifest: dict[str, Any]) -> list[str]:
    """Return blocker strings for missing publication-readiness evidence."""
    blockers: list[str] = []
    required_paths = (
        ("target_venue", manifest.get("target_venue")),
        ("policy_requirements", manifest.get("policy_requirements")),
        ("artifact_manifest", manifest.get("artifact_manifest")),
        ("code_data_release", manifest.get("code_data_release")),
        ("reproducibility_checks", manifest.get("reproducibility_checks")),
        ("empirical_anchor_status", manifest.get("empirical_anchor_status")),
        ("disclosures.author_contributor", (
            manifest.get("disclosures") or {}
        ).get("author_contributor") if isinstance(manifest.get("disclosures"), dict) else None),
        ("disclosures.ai_use", (
            manifest.get("disclosures") or {}
        ).get("ai_use") if isinstance(manifest.get("disclosures"), dict) else None),
    )
    for name, value in required_paths:
        if not _non_empty(value):
            blockers.append(f"missing:{name}")

    for idx, check in enumerate(_as_list(manifest.get("reproducibility_checks"))):
        if not isinstance(check, dict):
            blockers.append(f"invalid:reproducibility_checks[{idx}]")
            continue
        status = str(check.get("status") or "").strip().lower()
        if status not in {"pass", "passed", "complete", "completed"}:
            blockers.append(f"failing:reproducibility_checks[{idx}]")

    explicit_blockers = manifest.get("blockers")
    if explicit_blockers:
        for blocker in _as_list(explicit_blockers):
            text = str(blocker).strip()
            if text:
                blockers.append(text)
    return blockers


def _from_row(row: sqlite3.Row) -> PublicationReadiness:
    return PublicationReadiness(
        readiness_id=row["readiness_id"],
        goal_id=row["goal_id"],
        branch_def_id=row["branch_def_id"],
        target_venue=row["target_venue"],
        target_rung=row["target_rung"],
        manifest=json.loads(row["manifest_json"] or "{}"),
        status=row["status"],
        blockers=list(json.loads(row["blockers_json"] or "[]")),
        created_by=row["created_by"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def record_publication_readiness(
    base_path: str | Path,
    *,
    goal_id: str,
    manifest: dict[str, Any],
    created_by: str,
    branch_def_id: str = "",
    target_rung: str = "",
) -> PublicationReadiness:
    if not goal_id:
        raise ValueError("goal_id is required")
    if not isinstance(manifest, dict):
        raise ValueError("manifest must be a JSON object")
    target_venue = str(manifest.get("target_venue") or "").strip()
    if not target_venue:
        raise ValueError("manifest.target_venue is required")
    target_rung = (target_rung or str(manifest.get("target_rung") or "")).strip()
    blockers = validate_manifest(manifest)
    status = "blocked" if blockers else "ready"
    now = _now()
    readiness_id = uuid.uuid4().hex[:16]
    db = _ensure_schema(base_path)
    with _connect(db) as conn:
        conn.execute(
            """
            INSERT INTO publication_readiness (
                readiness_id, goal_id, branch_def_id, target_venue,
                target_rung, manifest_json, status, blockers_json,
                created_by, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                readiness_id,
                goal_id,
                branch_def_id,
                target_venue,
                target_rung,
                json.dumps(manifest, sort_keys=True),
                status,
                json.dumps(blockers),
                created_by,
                now,
                now,
            ),
        )
        row = conn.execute(
            "SELECT * FROM publication_readiness WHERE readiness_id = ?",
            (readiness_id,),
        ).fetchone()
    return _from_row(row)


def get_publication_readiness(
    base_path: str | Path,
    readiness_id: str,
) -> PublicationReadiness | None:
    if not readiness_id:
        return None
    db = _ensure_schema(base_path)
    with _connect(db) as conn:
        row = conn.execute(
            "SELECT * FROM publication_readiness WHERE readiness_id = ?",
            (readiness_id,),
        ).fetchone()
    return _from_row(row) if row is not None else None


def list_publication_readiness(
    base_path: str | Path,
    *,
    goal_id: str = "",
    branch_def_id: str = "",
    limit: int = 50,
) -> list[PublicationReadiness]:
    db = _ensure_schema(base_path)
    clauses: list[str] = []
    params: list[Any] = []
    if goal_id:
        clauses.append("goal_id = ?")
        params.append(goal_id)
    if branch_def_id:
        clauses.append("branch_def_id = ?")
        params.append(branch_def_id)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    with _connect(db) as conn:
        rows = conn.execute(
            f"SELECT * FROM publication_readiness {where} "
            "ORDER BY updated_at DESC LIMIT ?",
            (*params, min(max(1, int(limit)), 500)),
        ).fetchall()
    return [_from_row(row) for row in rows]


def rung_requires_publication_readiness(
    rung_key: str,
    ladder: list[dict[str, Any]],
) -> bool:
    for rung in ladder:
        if rung.get("rung_key") != rung_key:
            continue
        return bool(
            rung.get("requires_publication_readiness")
            or rung.get("publication_readiness_required")
        )
    return False
