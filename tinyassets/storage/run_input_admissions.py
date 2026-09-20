"""Receiver-owned immutable execution envelopes in the existing runs store.

Internal persistence only. Current execution/branch authority and the author
tombstone fence belong to the admission service. Inputs remain in runs.inputs_json.
This persistence module does not schedule work, migrate legacy delivery workers,
or authorize replay. Start-state changes require the common run-keyed worker
guard and current service authority; there is no unguarded start API.
"""

from __future__ import annotations

import hashlib
import json
import time
import uuid

_SCHEMA = """CREATE TABLE IF NOT EXISTS run_input_admissions (
    run_id TEXT PRIMARY KEY REFERENCES runs(run_id),
    owner_id TEXT NOT NULL,
    universe_id TEXT NOT NULL,
    branch_def_id TEXT NOT NULL,
    branch_version_id TEXT REFERENCES branch_versions(branch_version_id),
    snapshot_json TEXT,
    snapshot_sha256 TEXT NOT NULL,
    execution_started_at REAL,
    claim_token TEXT,
    origin_kind TEXT NOT NULL DEFAULT '',
    origin_version INTEGER NOT NULL DEFAULT 0,
    origin_options_json TEXT NOT NULL DEFAULT '{}',
    CHECK ((branch_version_id IS NULL) != (snapshot_json IS NULL))
)"""


class RunInputRefused(ValueError):
    """Stable envelope integrity/authority refusal."""


def ensure_schema(conn):
    """Additive only; never commits the caller's transaction."""
    conn.execute(_SCHEMA)
    columns = {row[1] for row in conn.execute("PRAGMA table_info(run_input_admissions)")}
    for name, definition in (
        ("origin_kind", "TEXT NOT NULL DEFAULT ''"),
        ("origin_version", "INTEGER NOT NULL DEFAULT 0"),
        ("origin_options_json", "TEXT NOT NULL DEFAULT '{}'"),
    ):
        if name not in columns:
            conn.execute(f"ALTER TABLE run_input_admissions ADD COLUMN {name} {definition}")


def _owned_run(conn, run_id, owner_id, universe_id):
    if not conn.in_transaction:
        raise ValueError("run input admission requires a caller-owned transaction")
    row = conn.execute(
        "SELECT * FROM runs WHERE run_id=? AND owner_user_id=? AND queue_universe_id=?",
        (run_id, owner_id, universe_id),
    ).fetchone()
    if not owner_id or not universe_id or row is None:
        raise RunInputRefused("run_input_not_found")
    return row


def _encode(snapshot):
    try:
        if not isinstance(snapshot, dict):
            raise ValueError("snapshot must be an object")
        encoded = json.dumps(snapshot, sort_keys=True, allow_nan=False)
        if json.loads(encoded) != snapshot:
            raise ValueError("lossy snapshot")
        return encoded
    except (TypeError, ValueError, RecursionError) as exc:
        raise RunInputRefused("run_input_snapshot_invalid") from exc


def _digest(encoded):
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _version(conn, version_id):
    row = conn.execute(
        "SELECT branch_def_id,snapshot_json,content_hash FROM branch_versions "
        "WHERE branch_version_id=?",
        (version_id,),
    ).fetchone()
    if row is None:
        raise RunInputRefused("run_input_version_not_found")
    try:
        snapshot = json.loads(row["snapshot_json"])
        encoded = _encode(snapshot)
        if _digest(encoded) != row["content_hash"]:
            raise ValueError("version hash changed")
    except (TypeError, ValueError) as exc:
        raise RunInputRefused("run_input_snapshot_integrity") from exc
    return row["branch_def_id"], snapshot, encoded


def accept_in_transaction(
    conn,
    *,
    run_id,
    owner_id,
    universe_id,
    snapshot=None,
    branch_version_id=None,
    origin_kind="",
    origin_version=0,
    origin_options=None,
):
    """Freeze one admitted execution target; never copy run inputs or sender grants."""
    run = _owned_run(conn, run_id, owner_id, universe_id)
    from tinyassets.run_input_origin import encode_origin

    origin_json = encode_origin(
        origin_kind, origin_version, {} if origin_options is None else origin_options,
        allow_legacy=True,
    )
    if (snapshot is None) == (branch_version_id is None):
        raise RunInputRefused("run_input_target_ambiguous")
    if branch_version_id is not None:
        branch_id, parsed, encoded = _version(conn, branch_version_id)
    else:
        encoded = _encode(snapshot)
        parsed = snapshot
        branch_id = parsed.get("branch_def_id")
    if not branch_id or branch_id != run["branch_def_id"]:
        raise RunInputRefused("run_input_branch_mismatch")
    if parsed.get("branch_def_id") != branch_id:
        raise RunInputRefused("run_input_branch_mismatch")
    digest = _digest(encoded)
    stored_snapshot = None if branch_version_id is not None else encoded
    prior = conn.execute("SELECT * FROM run_input_admissions WHERE run_id=?", (run_id,)).fetchone()
    if prior is not None:
        expected = (owner_id, universe_id, branch_id, branch_version_id, stored_snapshot, digest,
                    origin_kind, origin_version, origin_json)
        observed = tuple(
            prior[key]
            for key in (
                "owner_id",
                "universe_id",
                "branch_def_id",
                "branch_version_id",
                "snapshot_json",
                "snapshot_sha256",
                "origin_kind",
                "origin_version",
                "origin_options_json",
            )
        )
        if observed != expected:
            raise RunInputRefused("run_input_conflict")
        return dict(prior)
    if run["status"] != "queued":
        raise RunInputRefused("run_input_already_started")
    conn.execute(
        "INSERT INTO run_input_admissions(run_id,owner_id,universe_id,branch_def_id,"
        "branch_version_id,snapshot_json,snapshot_sha256,origin_kind,origin_version,"
        "origin_options_json) VALUES(?,?,?,?,?,?,?,?,?,?)",
        (run_id, owner_id, universe_id, branch_id, branch_version_id, stored_snapshot, digest,
         origin_kind, origin_version, origin_json),
    )
    return dict(
        conn.execute("SELECT * FROM run_input_admissions WHERE run_id=?", (run_id,)).fetchone()
    )


def load_in_transaction(conn, *, run_id, owner_id, universe_id):
    """Current run ownership precedes reading/deserializing any private body."""
    run = _owned_run(conn, run_id, owner_id, universe_id)
    row = conn.execute(
        "SELECT * FROM run_input_admissions WHERE run_id=? AND owner_id=? AND universe_id=?",
        (run_id, owner_id, universe_id),
    ).fetchone()
    if row is None or row["branch_def_id"] != run["branch_def_id"]:
        raise RunInputRefused("run_input_not_found")
    try:
        if row["branch_version_id"] is not None:
            branch_id, snapshot, encoded = _version(conn, row["branch_version_id"])
        else:
            snapshot = json.loads(row["snapshot_json"])
            encoded = _encode(snapshot)
            branch_id = snapshot.get("branch_def_id")
        if branch_id != row["branch_def_id"] or _digest(encoded) != row["snapshot_sha256"]:
            raise ValueError("snapshot changed")
        inputs = json.loads(run["inputs_json"])
        if not isinstance(inputs, dict):
            raise ValueError("run inputs must be an object")
    except (TypeError, ValueError) as exc:
        raise RunInputRefused("run_input_snapshot_integrity") from exc
    return {**dict(row), "snapshot": snapshot, "inputs": inputs}


def recovery_state_in_transaction(conn, guard, *, owner_id, universe_id):
    """Classify while holding execution ownership; never infer death from a Future.

    No mutation here. The runtime must persist ambiguous interruption through
    the exact managed recovery lifecycle, including namespace cleanup. An
    interrupted row is terminal even without a marker; no late pool worker may
    undo retirement. Legacy startup-restoration belongs only to explicit migration.
    """
    from .run_execution_lock import RunExecutionGuard

    if type(guard) is not RunExecutionGuard:
        raise RuntimeError("a held run execution guard is required")
    guard.require_held(conn)
    envelope = load_in_transaction(
        conn, run_id=guard.run_id, owner_id=owner_id, universe_id=universe_id
    )
    run = _owned_run(conn, guard.run_id, owner_id, universe_id)
    started = envelope["execution_started_at"] is not None
    claimed = envelope["claim_token"] is not None
    if started != claimed:
        raise RunInputRefused("run_input_start_integrity")
    if run["status"] in {"completed", "failed", "cancelled", "interrupted", "resumed"}:
        return "terminal"
    if not started and run["status"] == "queued":
        if conn.execute("SELECT 1 FROM run_cancels WHERE run_id=?", (guard.run_id,)).fetchone():
            return "cancelled"
        return "pending"
    if run["status"] in {"queued", "running"}:
        return "interrupted"
    raise RunInputRefused("run_input_status_invalid")


def start_in_transaction(conn, guard, *, owner_id, universe_id):
    """Commit-before-effects marker; caller already fenced current origin authority.

    Guard remains held through execution. This is not a grant, retry or queue;
    a marker survives every failure after this commit, even before first effect.
    """
    if (
        recovery_state_in_transaction(conn, guard, owner_id=owner_id, universe_id=universe_id)
        != "pending"
    ):
        return None
    prior = _owned_run(conn, guard.run_id, owner_id, universe_id)
    token = uuid.uuid4().hex
    changed = conn.execute(
        "UPDATE run_input_admissions SET execution_started_at=?,claim_token=? "
        "WHERE run_id=? AND execution_started_at IS NULL AND claim_token IS NULL "
        "AND NOT EXISTS (SELECT 1 FROM run_cancels WHERE run_id=run_input_admissions.run_id) "
        "AND EXISTS (SELECT 1 FROM runs WHERE runs.run_id=run_input_admissions.run_id "
        "AND status=? AND owner_user_id=? AND queue_universe_id=?)",
        (time.time(), token, guard.run_id, prior["status"], owner_id, universe_id),
    ).rowcount
    if changed != 1:
        return None
    changed = conn.execute(
        "UPDATE runs SET status='queued',error='',finished_at=NULL WHERE run_id=? "
        "AND status=? AND owner_user_id=? AND queue_universe_id=? "
        "AND EXISTS (SELECT 1 FROM run_input_admissions "
        "WHERE run_id=runs.run_id AND claim_token=?)",
        (guard.run_id, prior["status"], owner_id, universe_id, token),
    ).rowcount
    if changed != 1:
        raise RunInputRefused("run_input_claim_lost")
    return token
