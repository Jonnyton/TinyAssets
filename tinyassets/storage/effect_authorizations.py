"""Durable grants, single-effect authorizations, and effect receipts."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from tinyassets.runtime.effect_authorization import (
        EffectReceipt,
        GitHubEffectAuthorization,
        GitHubOwnerGrant,
    )


StartDisposition = Literal["start", "reconcile", "in_flight", "stale", "succeeded"]


class EffectAuthorizationStore:
    """SQLite state machine committed before the first remote mutation."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS github_owner_grants (
                    grant_id TEXT PRIMARY KEY,
                    owner_user_id TEXT NOT NULL,
                    universe_id TEXT NOT NULL,
                    github_installation_id TEXT NOT NULL,
                    repository_node_id TEXT NOT NULL,
                    repository_full_name TEXT NOT NULL,
                    permitted_action TEXT NOT NULL,
                    permitted_base_ref TEXT NOT NULL,
                    required_head_prefix TEXT NOT NULL,
                    credential_binding_id TEXT NOT NULL,
                    generation INTEGER NOT NULL,
                    granted_at TEXT NOT NULL,
                    expires_at TEXT,
                    revoked_at TEXT
                );
                CREATE TABLE IF NOT EXISTS github_effect_authorizations (
                    authorization_id TEXT PRIMARY KEY,
                    effect_id TEXT NOT NULL UNIQUE,
                    grant_id TEXT NOT NULL,
                    grant_generation INTEGER NOT NULL,
                    job_id TEXT NOT NULL,
                    lease_fence INTEGER NOT NULL,
                    accepted_result_sha256 TEXT NOT NULL,
                    patch_blob_sha256 TEXT NOT NULL,
                    review_record_id TEXT NOT NULL,
                    base_commit TEXT NOT NULL,
                    base_tree TEXT NOT NULL,
                    resulting_tree TEXT NOT NULL,
                    expected_repository_head_sha TEXT NOT NULL,
                    authorized_by TEXT NOT NULL,
                    authorized_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    revoked_at TEXT,
                    state TEXT NOT NULL,
                    pr_number INTEGER,
                    pr_url TEXT,
                    head_ref TEXT NOT NULL,
                    remote_started_at TEXT
                );
                """
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path, timeout=30, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout = 30000")
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA synchronous = FULL")
        return connection

    @staticmethod
    def _time(value: datetime | None) -> str | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("effect timestamps must be timezone-aware")
        return value.isoformat()

    def put_owner_grant(self, grant: GitHubOwnerGrant) -> GitHubOwnerGrant:
        from tinyassets.runtime.effect_authorization import GitHubOwnerGrant

        if not isinstance(grant, GitHubOwnerGrant):
            raise TypeError("grant must be a GitHubOwnerGrant")
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            current = connection.execute(
                "SELECT * FROM github_owner_grants WHERE grant_id = ?",
                (grant.grant_id,),
            ).fetchone()
            if current is not None and grant.generation < current["generation"]:
                connection.rollback()
                raise ValueError("owner grant generation cannot decrease")
            if (
                current is not None
                and grant.generation == current["generation"]
                and grant != self._grant_from_row(current)
            ):
                connection.rollback()
                raise ValueError("owner grant changes require a new generation")
            connection.execute(
                """
                INSERT INTO github_owner_grants VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                )
                ON CONFLICT(grant_id) DO UPDATE SET
                    owner_user_id=excluded.owner_user_id,
                    universe_id=excluded.universe_id,
                    github_installation_id=excluded.github_installation_id,
                    repository_node_id=excluded.repository_node_id,
                    repository_full_name=excluded.repository_full_name,
                    permitted_action=excluded.permitted_action,
                    permitted_base_ref=excluded.permitted_base_ref,
                    required_head_prefix=excluded.required_head_prefix,
                    credential_binding_id=excluded.credential_binding_id,
                    generation=excluded.generation,
                    granted_at=excluded.granted_at,
                    expires_at=excluded.expires_at,
                    revoked_at=excluded.revoked_at
                """,
                (
                    grant.grant_id,
                    grant.owner_user_id,
                    grant.universe_id,
                    grant.github_installation_id,
                    grant.repository_node_id,
                    grant.repository_full_name,
                    grant.permitted_action,
                    grant.permitted_base_ref,
                    grant.required_head_prefix,
                    grant.credential_binding_id,
                    grant.generation,
                    self._time(grant.granted_at),
                    self._time(grant.expires_at),
                    self._time(grant.revoked_at),
                ),
            )
            connection.commit()
        return grant

    def get_owner_grant(self, grant_id: str) -> GitHubOwnerGrant | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM github_owner_grants WHERE grant_id = ?", (grant_id,)
            ).fetchone()
        return None if row is None else self._grant_from_row(row)

    def create(self, authorization: GitHubEffectAuthorization) -> GitHubEffectAuthorization:
        values = self._authorization_values(authorization)
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                """
                INSERT INTO github_effect_authorizations VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                ) ON CONFLICT(effect_id) DO NOTHING
                """,
                values,
            )
            row = connection.execute(
                "SELECT * FROM github_effect_authorizations WHERE effect_id = ?",
                (authorization.effect_id,),
            ).fetchone()
            connection.commit()
        stored = self._authorization_from_row(row)
        immutable = (
            "grant_id",
            "grant_generation",
            "job_id",
            "lease_fence",
            "accepted_result_sha256",
            "patch_blob_sha256",
            "review_record_id",
            "base_commit",
            "base_tree",
            "resulting_tree",
            "expected_repository_head_sha",
            "authorized_by",
            "head_ref",
        )
        if any(getattr(stored, key) != getattr(authorization, key) for key in immutable):
            raise ValueError("effect identity already exists with different immutable inputs")
        return stored

    def get(self, authorization_id: str) -> GitHubEffectAuthorization | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM github_effect_authorizations WHERE authorization_id = ?",
                (authorization_id,),
            ).fetchone()
        return None if row is None else self._authorization_from_row(row)

    def start(
        self,
        authorization_id: str,
        *,
        now: datetime,
        stale_after: timedelta = timedelta(minutes=5),
    ) -> tuple[StartDisposition, GitHubEffectAuthorization]:
        if now.tzinfo is None or stale_after <= timedelta(0):
            raise ValueError("effect reservation clock is invalid")
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM github_effect_authorizations WHERE authorization_id = ?",
                (authorization_id,),
            ).fetchone()
            if row is None:
                connection.rollback()
                raise KeyError(authorization_id)
            state = row["state"]
            if state == "succeeded":
                disposition: StartDisposition = "succeeded"
            elif state == "remote_started":
                started_at = datetime.fromisoformat(row["remote_started_at"])
                if now - started_at >= stale_after:
                    connection.execute(
                        "UPDATE github_effect_authorizations "
                        "SET state='needs_reconciliation' WHERE authorization_id=?",
                        (authorization_id,),
                    )
                    disposition = "stale"
                else:
                    disposition = "in_flight"
            elif state == "needs_reconciliation":
                connection.execute(
                    "UPDATE github_effect_authorizations "
                    "SET state='remote_started', remote_started_at=? "
                    "WHERE authorization_id=?",
                    (self._time(now), authorization_id),
                )
                disposition = "reconcile"
            elif state == "authorized":
                connection.execute(
                    "UPDATE github_effect_authorizations "
                    "SET state='remote_started', remote_started_at=? "
                    "WHERE authorization_id=?",
                    (self._time(now), authorization_id),
                )
                disposition = "start"
            else:
                connection.rollback()
                raise ValueError(f"authorization state {state!r} cannot start")
            row = connection.execute(
                "SELECT * FROM github_effect_authorizations WHERE authorization_id = ?",
                (authorization_id,),
            ).fetchone()
            connection.commit()
        return disposition, self._authorization_from_row(row)

    def mark_needs_reconciliation(self, authorization_id: str) -> None:
        self._set_state(authorization_id, "needs_reconciliation")

    def invalidate(
        self,
        authorization_id: str,
        *,
        revoked_at: datetime | None = None,
    ) -> None:
        timestamp = self._time(revoked_at or datetime.now(UTC))
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT state FROM github_effect_authorizations "
                "WHERE authorization_id=?",
                (authorization_id,),
            ).fetchone()
            if row is None:
                connection.rollback()
                raise KeyError(authorization_id)
            state = row["state"]
            if state == "succeeded":
                next_state = "succeeded"
            elif state == "authorized":
                next_state = "revoked"
            else:
                next_state = "needs_reconciliation"
            connection.execute(
                "UPDATE github_effect_authorizations "
                "SET state=?, revoked_at=? WHERE authorization_id=?",
                (next_state, timestamp, authorization_id),
            )
            connection.commit()

    def succeed(self, authorization_id: str, *, pr_number: int, pr_url: str) -> EffectReceipt:
        from tinyassets.runtime.effect_authorization import EffectReceipt

        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM github_effect_authorizations WHERE authorization_id = ?",
                (authorization_id,),
            ).fetchone()
            if row is None:
                connection.rollback()
                raise KeyError(authorization_id)
            if row["state"] == "succeeded":
                connection.commit()
                return self._receipt(self._authorization_from_row(row))
            connection.execute(
                """
                UPDATE github_effect_authorizations
                SET state='succeeded', pr_number=?, pr_url=?
                WHERE authorization_id=? AND state='remote_started'
                """,
                (pr_number, pr_url, authorization_id),
            )
            row = connection.execute(
                "SELECT * FROM github_effect_authorizations WHERE authorization_id = ?",
                (authorization_id,),
            ).fetchone()
            connection.commit()
        authorization = self._authorization_from_row(row)
        if authorization.state != "succeeded":
            raise ValueError("effect success lost its state transition")
        return EffectReceipt(
            authorization_id=authorization.authorization_id,
            effect_id=authorization.effect_id,
            status="succeeded",
            head_ref=authorization.head_ref,
            pr_number=authorization.pr_number,
            pr_url=authorization.pr_url,
        )

    def _set_state(self, authorization_id: str, state: str) -> None:
        with self._connect() as connection:
            cursor = connection.execute(
                "UPDATE github_effect_authorizations SET state=? WHERE authorization_id=?",
                (state, authorization_id),
            )
        if cursor.rowcount != 1:
            raise KeyError(authorization_id)

    @staticmethod
    def _receipt(authorization: GitHubEffectAuthorization) -> EffectReceipt:
        from tinyassets.runtime.effect_authorization import EffectReceipt

        status = "succeeded" if authorization.state == "succeeded" else "in_flight"
        return EffectReceipt(
            authorization_id=authorization.authorization_id,
            effect_id=authorization.effect_id,
            status=status,
            head_ref=authorization.head_ref,
            pr_number=authorization.pr_number,
            pr_url=authorization.pr_url,
        )

    @staticmethod
    def _grant_from_row(row: sqlite3.Row) -> GitHubOwnerGrant:
        from tinyassets.runtime.effect_authorization import GitHubOwnerGrant

        values: dict[str, Any] = dict(row)
        for key in ("granted_at", "expires_at", "revoked_at"):
            if values[key] is not None:
                values[key] = datetime.fromisoformat(values[key])
        return GitHubOwnerGrant(**values)

    @staticmethod
    def _authorization_from_row(row: sqlite3.Row) -> GitHubEffectAuthorization:
        from tinyassets.runtime.effect_authorization import GitHubEffectAuthorization

        values: dict[str, Any] = dict(row)
        for key in (
            "authorized_at",
            "expires_at",
            "revoked_at",
            "remote_started_at",
        ):
            if values[key] is not None:
                values[key] = datetime.fromisoformat(values[key])
        return GitHubEffectAuthorization(**values)

    def _authorization_values(self, value: GitHubEffectAuthorization) -> tuple[Any, ...]:
        return (
            value.authorization_id,
            value.effect_id,
            value.grant_id,
            value.grant_generation,
            value.job_id,
            value.lease_fence,
            value.accepted_result_sha256,
            value.patch_blob_sha256,
            value.review_record_id,
            value.base_commit,
            value.base_tree,
            value.resulting_tree,
            value.expected_repository_head_sha,
            value.authorized_by,
            self._time(value.authorized_at),
            self._time(value.expires_at),
            self._time(value.revoked_at),
            value.state,
            value.pr_number,
            value.pr_url,
            value.head_ref,
            self._time(value.remote_started_at),
        )


__all__ = ["EffectAuthorizationStore", "StartDisposition"]
