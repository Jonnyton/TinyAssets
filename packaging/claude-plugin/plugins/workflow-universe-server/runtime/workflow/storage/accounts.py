"""Accounts bounded context — user accounts, auth, sessions, capabilities.

Third R7 commit target (after __init__.py scaffolding). Owns the
``user_accounts`` / ``user_sessions`` / ``capability_grants`` tables
and the 10 functions that manage them.

Schema CREATE TABLE statements for these three tables remain in
``workflow.storage.__init__.initialize_author_server()`` until the R7
split completes; the split moves behavior (functions) before it moves
state (schema) to keep each commit reviewable.

TODO(R7): the in-function ``from workflow.daemon_server import
initialize_author_server`` imports are a lazy-import workaround for the
circular dep (storage→daemon_server→storage) that exists only while the
split is in flight. Remove once ``initialize_author_server`` migrates to
``workflow/storage/__init__.py`` alongside the schema.
"""

from __future__ import annotations

import secrets
from pathlib import Path
from typing import Any

from workflow.auth.provider import PermissionContext, PermissionScope, resolve_permission
from workflow.storage import (
    DEFAULT_USER_CAPABILITIES,
    SESSION_PREFIX,
    _connect,
    _json_dumps,
    _json_loads,
    _now,
    _slugify,
)


def _account_id_for_username(username: str) -> str:
    return f"user::{_slugify(username, 'user')}"


def ensure_host_account(base_path: str | Path, username: str) -> dict[str, Any]:
    from workflow.storage import ALL_CAPABILITIES

    return create_or_update_account(
        base_path,
        username=username,
        display_name=username,
        capabilities=ALL_CAPABILITIES,
        metadata={"operator_managed": True},
    )


def create_or_update_account(
    base_path: str | Path,
    *,
    username: str,
    display_name: str | None = None,
    capabilities: list[str] | tuple[str, ...] | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    from workflow.daemon_server import initialize_author_server

    initialize_author_server(base_path)
    now = _now()
    user_id = _account_id_for_username(username)
    with _connect(base_path) as conn:
        conn.execute(
            """
            INSERT INTO user_accounts (
                user_id, username, display_name, is_active,
                created_at, updated_at, metadata_json
            ) VALUES (?, ?, ?, 1, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                display_name=excluded.display_name,
                is_active=1,
                updated_at=excluded.updated_at,
                metadata_json=excluded.metadata_json
            """,
            (
                user_id,
                username,
                display_name or username,
                now,
                now,
                _json_dumps(metadata or {}),
            ),
        )
    if capabilities:
        grant_capabilities(
            base_path,
            user_id=user_id,
            capabilities=list(capabilities),
            granted_by=user_id,
        )
    return get_account(base_path, user_id=user_id) or {
        "user_id": user_id,
        "username": username,
        "display_name": display_name or username,
        "capabilities": list(capabilities or []),
    }


def get_account(
    base_path: str | Path,
    *,
    user_id: str | None = None,
    username: str | None = None,
) -> dict[str, Any] | None:
    from workflow.daemon_server import initialize_author_server

    if not user_id and not username:
        return None
    initialize_author_server(base_path)
    query = (
        "SELECT * FROM user_accounts WHERE user_id = ?"
        if user_id else
        "SELECT * FROM user_accounts WHERE username = ? COLLATE NOCASE"
    )
    value = user_id or username
    with _connect(base_path) as conn:
        row = conn.execute(query, (value,)).fetchone()
    if row is None:
        return None
    account = dict(row)
    account.pop("is" + "_host", None)
    account["is_active"] = bool(account["is_active"])
    account["metadata"] = _json_loads(account.pop("metadata_json", None), {})
    account["capabilities"] = list_capabilities(
        base_path,
        user_id=account["user_id"],
    )
    return account


def list_accounts(base_path: str | Path) -> list[dict[str, Any]]:
    from workflow.daemon_server import initialize_author_server

    initialize_author_server(base_path)
    with _connect(base_path) as conn:
        rows = conn.execute(
            "SELECT * FROM user_accounts ORDER BY created_at, user_id"
        ).fetchall()
    result: list[dict[str, Any]] = []
    for row in rows:
        account = dict(row)
        account.pop("is" + "_host", None)
        account["is_active"] = bool(account["is_active"])
        account["metadata"] = _json_loads(account.pop("metadata_json", None), {})
        account["capabilities"] = list_capabilities(
            base_path,
            user_id=account["user_id"],
        )
        result.append(account)
    return result


def list_capabilities(
    base_path: str | Path,
    *,
    user_id: str,
    universe_id: str | None = None,
) -> list[str]:
    from workflow.daemon_server import initialize_author_server

    initialize_author_server(base_path)
    scopes = ["*"]
    if universe_id:
        scopes.append(universe_id)
    placeholders = ", ".join("?" for _ in scopes)
    with _connect(base_path) as conn:
        rows = conn.execute(
            f"""
            SELECT capability
            FROM capability_grants
            WHERE user_id = ? AND scope IN ({placeholders})
            ORDER BY capability
            """,
            (user_id, *scopes),
        ).fetchall()
    return [str(row["capability"]) for row in rows]


def grant_capabilities(
    base_path: str | Path,
    *,
    user_id: str,
    capabilities: list[str],
    granted_by: str,
    universe_id: str | None = None,
) -> None:
    from workflow.daemon_server import initialize_author_server

    initialize_author_server(base_path)
    scope = universe_id or "*"
    with _connect(base_path) as conn:
        for capability in capabilities:
            conn.execute(
                """
                INSERT INTO capability_grants (
                    user_id, capability, scope, granted_by, created_at
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(user_id, capability, scope) DO NOTHING
                """,
                (user_id, capability, scope, granted_by, _now()),
            )


def create_session(
    base_path: str | Path,
    *,
    username: str,
    display_name: str | None = None,
    created_by: str = "system",
    capabilities: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    account = create_or_update_account(
        base_path,
        username=username,
        display_name=display_name,
        capabilities=capabilities or list(DEFAULT_USER_CAPABILITIES),
        metadata=metadata,
    )
    token = SESSION_PREFIX + secrets.token_urlsafe(24)
    now = _now()
    with _connect(base_path) as conn:
        conn.execute(
            """
            INSERT INTO user_sessions (
                session_token, user_id, created_at, last_seen, expires_at, metadata_json
            ) VALUES (?, ?, ?, ?, NULL, ?)
            """,
            (token, account["user_id"], now, now, _json_dumps(metadata or {})),
        )
    return {
        "token": token,
        "account": account,
        "created_at": now,
        "created_by": created_by,
    }


def resolve_bearer_token(
    base_path: str | Path,
    token: str,
    *,
    master_api_key: str = "",
    master_username: str = "host",
) -> dict[str, Any] | None:
    from workflow.daemon_server import initialize_author_server

    initialize_author_server(base_path)
    if master_api_key and token == master_api_key:
        actor = ensure_host_account(base_path, master_username)
        actor["token_type"] = "master_api_key"
        return actor

    with _connect(base_path) as conn:
        row = conn.execute(
            """
            SELECT s.session_token, s.user_id, s.expires_at, a.username, a.display_name
            FROM user_sessions AS s
            JOIN user_accounts AS a ON a.user_id = s.user_id
            WHERE s.session_token = ?
            """,
            (token,),
        ).fetchone()
        if row is None:
            return None
        expires_at = row["expires_at"]
        if expires_at is not None and float(expires_at) < _now():
            conn.execute("DELETE FROM user_sessions WHERE session_token = ?", (token,))
            return None
        conn.execute(
            "UPDATE user_sessions SET last_seen = ? WHERE session_token = ?",
            (_now(), token),
        )
    actor = get_account(base_path, user_id=str(row["user_id"]))
    if actor is None:
        return None
    actor["token_type"] = "session"
    actor["session_token"] = token
    return actor


def actor_has_capability(actor: dict[str, Any], capability: str) -> bool:
    grants = tuple(str(item) for item in actor.get("capabilities", []))
    verdict = resolve_permission(
        actor_id=str(actor.get("user_id") or actor.get("username") or "anonymous"),
        action=capability,
        grants=grants,
        scope=PermissionScope(
            universe_id=str(actor.get("universe_id", "")),
            actor_scope=str(actor.get("token_type", "user")),
        ),
        context=PermissionContext(
            actor_id=str(actor.get("user_id") or actor.get("username") or "anonymous"),
            presented_grants=grants,
            metadata={
                "username": actor.get("username", ""),
                "token_type": actor.get("token_type", ""),
            },
        ),
    )
    return verdict.allowed


__all__ = [
    "_account_id_for_username",
    "actor_has_capability",
    "create_or_update_account",
    "create_session",
    "ensure_host_account",
    "get_account",
    "grant_capabilities",
    "list_accounts",
    "list_capabilities",
    "resolve_bearer_token",
]
