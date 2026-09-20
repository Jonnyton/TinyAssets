"""Exact canonical payload expiry within the existing scoped-reset operation.

Not a reset entry point: only the existing reviewed plan, maintenance barrier and
committed witness authorize the caller. No home database is newly resettable.
"""

import sqlite3
import time

TABLE = "conversation_run_admissions"
_COLUMNS = frozenset({
    "admission_id", "owner_user_id", "universe_id", "session_id", "request_key_hash",
    "intent_digest", "intent_json", "context_json", "selection_json", "run_id",
    "terminal_json", "projection_state", "conversation_turn_no", "created_at", "updated_at",
})


def _validate(conn):
    from tinyassets.scoped_reset import ScopedResetSchemaError

    columns = conn.execute(f"PRAGMA table_xinfo({TABLE})").fetchall()
    if ({row[1] for row in columns} != _COLUMNS or any(row[6] for row in columns)
            or conn.execute("SELECT 1 FROM sqlite_master WHERE type='trigger' AND tbl_name=?",
                            (TABLE,)).fetchone()):
        raise ScopedResetSchemaError("canonical conversation reset schema is unclassified")


def plan_action(root, *, fingerprint, home_id):
    """Content-free identity list; never emit a raw principal or private payload."""
    from tinyassets.scoped_reset import (
        ScopedResetSchemaError,
        _connect_read_only,
        _is_link_or_reparse,
        _principal_digest,
        _table_names,
    )

    path = root / ".runs.db"
    if home_id is None or not path.is_file():
        return []
    if _is_link_or_reparse(path) or path.stat().st_nlink != 1 or path.resolve() != path:
        raise ScopedResetSchemaError("canonical conversation run store is linked")
    conn = _connect_read_only(path)
    try:
        if TABLE not in _table_names(conn):
            return []
        _validate(conn)
        ids = [row[0] for row in conn.execute(
            f"SELECT admission_id,owner_user_id FROM {TABLE} WHERE universe_id=? "
            "ORDER BY admission_id", (home_id,)) if _principal_digest(row[1]) == fingerprint]
        return [{"action": "expire_conversation_admissions", "home_id": home_id,
                 "owner_principal_fingerprint": fingerprint, "admission_ids": ids}]
    finally:
        conn.close()


def expire_committed(root, operation, actions):
    """Idempotent post-witness step, before cleanup and before serving resumes."""
    from tinyassets.scoped_reset import (
        ScopedResetRecoveryError,
        _is_link_or_reparse,
        _principal_digest,
    )

    if not actions:
        return  # Legacy reset plans had no canonical table or payload action.
    if not operation["commit_witness"] or len(actions) != 1:
        raise ScopedResetRecoveryError("canonical expiry requires exact committed reset witness")
    action = actions[0]
    expected = {"action", "home_id", "owner_principal_fingerprint", "admission_ids"}
    if (not isinstance(action, dict) or set(action) != expected
            or action["action"] != "expire_conversation_admissions"
            or action["home_id"] != operation["home_id"]
            or not action["home_id"]
            or action["owner_principal_fingerprint"] != operation["principal_fingerprint"]
            or not isinstance(action["admission_ids"], list)
            or any(not isinstance(value, str) for value in action["admission_ids"])
            or action["admission_ids"] != sorted(set(action["admission_ids"]))):
        raise ScopedResetRecoveryError("canonical expiry action disagrees with reset scope")
    path = root / ".runs.db"
    if (not path.is_file() or _is_link_or_reparse(path) or path.stat().st_nlink != 1
            or path.resolve() != path):
        raise ScopedResetRecoveryError("canonical expiry run store is unavailable or linked")
    conn = sqlite3.connect(path.as_uri() + "?mode=rw", uri=True, timeout=5)
    try:
        conn.execute("BEGIN IMMEDIATE")
        _validate(conn)
        found = [row[0] for row in conn.execute(
            f"SELECT admission_id,owner_user_id FROM {TABLE} WHERE universe_id=? "
            "ORDER BY admission_id", (action["home_id"],))
            if _principal_digest(row[1]) == action["owner_principal_fingerprint"]]
        if found != action["admission_ids"]:
            raise ScopedResetRecoveryError("canonical expiry identity changed after reset plan")
        for admission_id in found:
            conn.execute(f"UPDATE {TABLE} SET projection_state='expired',intent_json=NULL,"
                         "context_json=NULL,terminal_json=NULL,selection_json='{}',"
                         "conversation_turn_no=NULL,updated_at=? WHERE admission_id=? "
                         "AND projection_state!='expired'", (time.time(), admission_id))
        conn.commit()
    finally:
        conn.close()
