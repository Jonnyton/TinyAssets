from __future__ import annotations

import inspect
import sqlite3
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

import tinyassets.storage.accounts as accounts_store
from tinyassets.daemon_server import (
    ensure_universe_registered,
    grant_universe_access,
    initialize_author_server,
)
from tinyassets.storage import CAP_GRANT_CAPABILITIES, db_path
from tinyassets.storage.accounts import (
    PRIORITY_REQUEST_CAPABILITY,
    CapabilityGrantAuthorizationError,
    active_priority_grant_from_connection,
    create_or_update_account,
    get_account,
    get_active_priority_grant,
    grant_capabilities,
    issue_priority_grant,
    list_capabilities,
    list_capability_grant_history,
    revoke_priority_grant,
)
from tinyassets.storage.request_admissions import RequestAdmissionStore


@pytest.fixture
def server_clock(
    monkeypatch: pytest.MonkeyPatch,
) -> Callable[[float], None]:
    current = [time.time()]
    monkeypatch.setattr(accounts_store, "_now", lambda: current[0])

    def set_time(timestamp: float) -> None:
        current[0] = timestamp

    return set_time


def _connect(base_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path(base_path))
    conn.row_factory = sqlite3.Row
    return conn


def _create_universe(base_path: Path, universe_id: str) -> None:
    universe_path = base_path / universe_id
    universe_path.mkdir(parents=True, exist_ok=True)
    ensure_universe_registered(
        base_path,
        universe_id=universe_id,
        universe_path=universe_path,
    )


def _create_actor(base_path: Path, username: str) -> str:
    return str(
        create_or_update_account(
            base_path,
            username=username,
        )["user_id"]
    )


def _authorized_fixture(
    base_path: Path,
    *,
    universe_id: str = "universe-a",
) -> tuple[str, str]:
    initialize_author_server(base_path)
    _create_universe(base_path, universe_id)
    issuer_id = _create_actor(base_path, "issuer")
    subject_id = _create_actor(base_path, "subject")
    grant_universe_access(
        base_path,
        universe_id=universe_id,
        actor_id=issuer_id,
        permission="admin",
        granted_by=issuer_id,
    )
    grant_capabilities(
        base_path,
        user_id=issuer_id,
        capabilities=[CAP_GRANT_CAPABILITIES],
        granted_by=issuer_id,
        universe_id=universe_id,
    )
    return issuer_id, subject_id


def test_pretraffic_migration_preserves_legacy_capability_row(
    tmp_path: Path,
) -> None:
    with _connect(tmp_path) as conn:
        conn.executescript(
            """
            CREATE TABLE user_accounts (
                user_id TEXT PRIMARY KEY,
                username TEXT NOT NULL UNIQUE COLLATE NOCASE,
                display_name TEXT NOT NULL,
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL,
                metadata_json TEXT NOT NULL DEFAULT '{}'
            );
            CREATE TABLE capability_grants (
                user_id TEXT NOT NULL,
                capability TEXT NOT NULL,
                scope TEXT NOT NULL DEFAULT '*',
                granted_by TEXT NOT NULL,
                created_at REAL NOT NULL,
                PRIMARY KEY(user_id, capability, scope),
                FOREIGN KEY(user_id) REFERENCES user_accounts(user_id)
                    ON DELETE CASCADE
            );
            INSERT INTO user_accounts (
                user_id, username, display_name, created_at, updated_at
            ) VALUES ('user::legacy', 'legacy', 'Legacy', 100, 100);
            INSERT INTO capability_grants (
                user_id, capability, scope, granted_by, created_at
            ) VALUES (
                'user::legacy', 'submit_request', '*', 'system', 100
            );
            """
        )

    initialize_author_server(tmp_path)

    with _connect(tmp_path) as conn:
        columns = {
            row["name"]: row
            for row in conn.execute(
                "PRAGMA table_info(capability_grants)"
            ).fetchall()
        }
        row = conn.execute(
            "SELECT * FROM capability_grants"
        ).fetchone()
        assert {"generation", "expires_at", "revoked_at"} <= set(columns)
        assert [
            columns[name]["pk"]
            for name in ("user_id", "capability", "scope", "generation")
        ] == [1, 2, 3, 4]
        assert row["generation"] == 1
        assert row["expires_at"] is None
        assert row["revoked_at"] is None
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []

    assert list_capabilities(
        tmp_path,
        user_id="user::legacy",
    ) == ["submit_request"]


def test_exact_admin_and_capability_issue_generation(
    tmp_path: Path,
    server_clock: Callable[[float], None],
) -> None:
    issuer_id, subject_id = _authorized_fixture(tmp_path)
    issued_at = time.time() + 1
    server_clock(issued_at)

    grant = issue_priority_grant(
        tmp_path,
        subject_id=subject_id,
        universe_id="universe-a",
        issuer_id=issuer_id,
        expires_at=issued_at + 60,
    )

    assert grant == {
        "user_id": subject_id,
        "capability": PRIORITY_REQUEST_CAPABILITY,
        "scope": "universe-a",
        "granted_by": issuer_id,
        "created_at": issued_at,
        "expires_at": issued_at + 60,
        "revoked_at": None,
        "generation": 1,
    }
    assert get_active_priority_grant(
        tmp_path,
        subject_id=subject_id,
        universe_id="universe-a",
        evaluated_at=issued_at,
    ) == grant


@pytest.mark.parametrize(
    ("admin", "capability_scope"),
    [
        (False, "universe-a"),
        (True, ""),
        (True, "*"),
        (True, "universe-b"),
    ],
)
def test_issue_requires_exact_admin_and_exact_grant_capability(
    tmp_path: Path,
    admin: bool,
    capability_scope: str,
    server_clock: Callable[[float], None],
) -> None:
    initialize_author_server(tmp_path)
    _create_universe(tmp_path, "universe-a")
    _create_universe(tmp_path, "universe-b")
    issuer_id = _create_actor(tmp_path, "issuer")
    subject_id = _create_actor(tmp_path, "subject")
    if admin:
        grant_universe_access(
            tmp_path,
            universe_id="universe-a",
            actor_id=issuer_id,
            permission="admin",
            granted_by=issuer_id,
        )
    if capability_scope:
        grant_capabilities(
            tmp_path,
            user_id=issuer_id,
            capabilities=[CAP_GRANT_CAPABILITIES],
            granted_by=issuer_id,
            universe_id=(
                None if capability_scope == "*" else capability_scope
            ),
        )
    server_clock(time.time() + 1)

    with pytest.raises(CapabilityGrantAuthorizationError):
        issue_priority_grant(
            tmp_path,
            subject_id=subject_id,
            universe_id="universe-a",
            issuer_id=issuer_id,
        )

    assert list_capability_grant_history(
        tmp_path,
        subject_id=subject_id,
        universe_id="universe-a",
        capability=PRIORITY_REQUEST_CAPABILITY,
    ) == []


def test_revoked_issuer_cannot_backdate_issue_or_revoke(
    tmp_path: Path,
    server_clock: Callable[[float], None],
) -> None:
    issuer_id, subject_id = _authorized_fixture(tmp_path)
    other_subject_id = _create_actor(tmp_path, "other-subject")
    issued_at = time.time() + 1
    server_clock(issued_at)
    subject_grant = issue_priority_grant(
        tmp_path,
        subject_id=subject_id,
        universe_id="universe-a",
        issuer_id=issuer_id,
    )
    issuer_revoked_at = issued_at + 1
    with _connect(tmp_path) as conn:
        conn.execute(
            """
            UPDATE capability_grants
            SET revoked_at = ?
            WHERE user_id = ? AND capability = ? AND scope = ?
            """,
            (
                issuer_revoked_at,
                issuer_id,
                CAP_GRANT_CAPABILITIES,
                "universe-a",
            ),
        )

    server_clock(issuer_revoked_at + 1)
    with pytest.raises(CapabilityGrantAuthorizationError):
        issue_priority_grant(
            tmp_path,
            subject_id=other_subject_id,
            universe_id="universe-a",
            issuer_id=issuer_id,
        )
    with pytest.raises(CapabilityGrantAuthorizationError):
        revoke_priority_grant(
            tmp_path,
            subject_id=subject_id,
            universe_id="universe-a",
            issuer_id=issuer_id,
        )

    assert list_capability_grant_history(
        tmp_path,
        subject_id=other_subject_id,
        universe_id="universe-a",
        capability=PRIORITY_REQUEST_CAPABILITY,
    ) == []
    assert list_capability_grant_history(
        tmp_path,
        subject_id=subject_id,
        universe_id="universe-a",
        capability=PRIORITY_REQUEST_CAPABILITY,
    ) == [subject_grant]
    assert "issued_at" not in inspect.signature(
        issue_priority_grant
    ).parameters
    assert "revoked_at" not in inspect.signature(
        revoke_priority_grant
    ).parameters


def test_generic_grant_path_cannot_issue_operator_priority(
    tmp_path: Path,
) -> None:
    initialize_author_server(tmp_path)
    subject_id = _create_actor(tmp_path, "subject")

    with pytest.raises(
        ValueError,
        match="trusted priority-grant service",
    ):
        grant_capabilities(
            tmp_path,
            user_id=subject_id,
            capabilities=[
                "submit_request",
                PRIORITY_REQUEST_CAPABILITY,
            ],
            granted_by="system",
            universe_id="universe-a",
        )

    assert list_capabilities(
        tmp_path,
        user_id=subject_id,
        universe_id="universe-a",
    ) == []

    with pytest.raises(
        ValueError,
        match="trusted priority-grant service",
    ):
        create_or_update_account(
            tmp_path,
            username="partial-account",
            capabilities=[
                "submit_request",
                PRIORITY_REQUEST_CAPABILITY,
            ],
        )
    assert get_account(tmp_path, username="partial-account") is None


def test_wildcard_priority_target_is_rejected_without_mutation(
    tmp_path: Path,
) -> None:
    initialize_author_server(tmp_path)
    issuer_id = _create_actor(tmp_path, "issuer")
    subject_id = _create_actor(tmp_path, "subject")

    with pytest.raises(ValueError, match="exact universe"):
        issue_priority_grant(
            tmp_path,
            subject_id=subject_id,
            universe_id="*",
            issuer_id=issuer_id,
        )

    assert list_capability_grant_history(
        tmp_path,
        subject_id=subject_id,
        capability=PRIORITY_REQUEST_CAPABILITY,
    ) == []


def test_expiry_boundary_and_regrant_preserve_history(
    tmp_path: Path,
    server_clock: Callable[[float], None],
) -> None:
    issuer_id, subject_id = _authorized_fixture(tmp_path)
    issued_at = time.time() + 1
    expires_at = issued_at + 10
    server_clock(issued_at)
    first = issue_priority_grant(
        tmp_path,
        subject_id=subject_id,
        universe_id="universe-a",
        issuer_id=issuer_id,
        expires_at=expires_at,
    )

    assert get_active_priority_grant(
        tmp_path,
        subject_id=subject_id,
        universe_id="universe-a",
        evaluated_at=expires_at - 0.001,
    ) == first
    assert get_active_priority_grant(
        tmp_path,
        subject_id=subject_id,
        universe_id="universe-a",
        evaluated_at=expires_at,
    ) is None
    assert get_active_priority_grant(
        tmp_path,
        subject_id=subject_id,
        universe_id="universe-a",
        evaluated_at=expires_at + 1,
    ) is None

    server_clock(expires_at + 1)
    second = issue_priority_grant(
        tmp_path,
        subject_id=subject_id,
        universe_id="universe-a",
        issuer_id=issuer_id,
    )
    assert second["generation"] == 2
    assert [
        row["generation"]
        for row in list_capability_grant_history(
            tmp_path,
            subject_id=subject_id,
            universe_id="universe-a",
            capability=PRIORITY_REQUEST_CAPABILITY,
        )
    ] == [1, 2]


def test_repeat_issue_cannot_silently_change_active_expiry(
    tmp_path: Path,
    server_clock: Callable[[float], None],
) -> None:
    issuer_id, subject_id = _authorized_fixture(tmp_path)
    issued_at = time.time() + 1
    server_clock(issued_at)
    first = issue_priority_grant(
        tmp_path,
        subject_id=subject_id,
        universe_id="universe-a",
        issuer_id=issuer_id,
        expires_at=issued_at + 60,
    )

    server_clock(issued_at + 1)
    with pytest.raises(ValueError, match="different expiry"):
        issue_priority_grant(
            tmp_path,
            subject_id=subject_id,
            universe_id="universe-a",
            issuer_id=issuer_id,
            expires_at=issued_at + 120,
        )

    assert list_capability_grant_history(
        tmp_path,
        subject_id=subject_id,
        universe_id="universe-a",
        capability=PRIORITY_REQUEST_CAPABILITY,
    ) == [first]


def test_issue_time_cannot_predate_existing_generation(
    tmp_path: Path,
    server_clock: Callable[[float], None],
) -> None:
    issuer_id, subject_id = _authorized_fixture(tmp_path)
    issued_at = time.time() + 10
    server_clock(issued_at)
    first = issue_priority_grant(
        tmp_path,
        subject_id=subject_id,
        universe_id="universe-a",
        issuer_id=issuer_id,
    )

    server_clock(issued_at - 1)
    with pytest.raises(ValueError, match="predate"):
        issue_priority_grant(
            tmp_path,
            subject_id=subject_id,
            universe_id="universe-a",
            issuer_id=issuer_id,
        )

    assert list_capability_grant_history(
        tmp_path,
        subject_id=subject_id,
        universe_id="universe-a",
        capability=PRIORITY_REQUEST_CAPABILITY,
    ) == [first]


@pytest.mark.parametrize("invalid_time", [float("nan"), float("inf")])
def test_nonfinite_issue_times_fail_without_mutation(
    tmp_path: Path,
    invalid_time: float,
    server_clock: Callable[[float], None],
) -> None:
    issuer_id, subject_id = _authorized_fixture(tmp_path)

    server_clock(invalid_time)
    with pytest.raises(ValueError, match="finite"):
        issue_priority_grant(
            tmp_path,
            subject_id=subject_id,
            universe_id="universe-a",
            issuer_id=issuer_id,
        )
    server_clock(time.time() + 1)
    with pytest.raises(ValueError, match="finite"):
        issue_priority_grant(
            tmp_path,
            subject_id=subject_id,
            universe_id="universe-a",
            issuer_id=issuer_id,
            expires_at=invalid_time,
        )
    assert list_capability_grant_history(
        tmp_path,
        subject_id=subject_id,
        universe_id="universe-a",
        capability=PRIORITY_REQUEST_CAPABILITY,
    ) == []


def test_revoke_is_exact_prospective_idempotent_and_regrant_increments(
    tmp_path: Path,
    server_clock: Callable[[float], None],
) -> None:
    issuer_id, subject_id = _authorized_fixture(tmp_path)
    issued_at = time.time() + 1
    server_clock(issued_at)
    first = issue_priority_grant(
        tmp_path,
        subject_id=subject_id,
        universe_id="universe-a",
        issuer_id=issuer_id,
    )
    revoked_at = issued_at + 2

    server_clock(revoked_at)
    revoked = revoke_priority_grant(
        tmp_path,
        subject_id=subject_id,
        universe_id="universe-a",
        issuer_id=issuer_id,
    )
    server_clock(revoked_at + 1)
    repeated = revoke_priority_grant(
        tmp_path,
        subject_id=subject_id,
        universe_id="universe-a",
        issuer_id=issuer_id,
    )
    assert revoked == repeated
    assert revoked["generation"] == first["generation"]
    assert revoked["revoked_at"] == revoked_at
    active_before_revocation = get_active_priority_grant(
        tmp_path,
        subject_id=subject_id,
        universe_id="universe-a",
        evaluated_at=revoked_at - 0.001,
    )
    assert active_before_revocation is not None
    assert active_before_revocation["generation"] == first["generation"]
    assert active_before_revocation["revoked_at"] == revoked_at
    assert get_active_priority_grant(
        tmp_path,
        subject_id=subject_id,
        universe_id="universe-a",
        evaluated_at=revoked_at,
    ) is None

    server_clock(revoked_at + 2)
    second = issue_priority_grant(
        tmp_path,
        subject_id=subject_id,
        universe_id="universe-a",
        issuer_id=issuer_id,
    )
    assert second["generation"] == 2
    history = list_capability_grant_history(
        tmp_path,
        subject_id=subject_id,
        universe_id="universe-a",
        capability=PRIORITY_REQUEST_CAPABILITY,
    )
    assert history[0]["revoked_at"] == revoked_at
    assert history[1]["revoked_at"] is None


def test_revoke_cannot_predate_grant(
    tmp_path: Path,
    server_clock: Callable[[float], None],
) -> None:
    issuer_id, subject_id = _authorized_fixture(tmp_path)
    issued_at = time.time() + 10
    server_clock(issued_at)
    first = issue_priority_grant(
        tmp_path,
        subject_id=subject_id,
        universe_id="universe-a",
        issuer_id=issuer_id,
    )

    server_clock(issued_at - 1)
    with pytest.raises(ValueError, match="predate"):
        revoke_priority_grant(
            tmp_path,
            subject_id=subject_id,
            universe_id="universe-a",
            issuer_id=issuer_id,
        )

    assert list_capability_grant_history(
        tmp_path,
        subject_id=subject_id,
        universe_id="universe-a",
        capability=PRIORITY_REQUEST_CAPABILITY,
    ) == [first]


def test_concurrent_repeated_issue_creates_one_active_generation(
    tmp_path: Path,
    server_clock: Callable[[float], None],
) -> None:
    issuer_id, subject_id = _authorized_fixture(tmp_path)
    issued_at = time.time() + 1
    server_clock(issued_at)

    def issue(_index: int) -> dict:
        return issue_priority_grant(
            tmp_path,
            subject_id=subject_id,
            universe_id="universe-a",
            issuer_id=issuer_id,
        )

    with ThreadPoolExecutor(max_workers=12) as pool:
        results = list(pool.map(issue, range(24)))

    assert {result["generation"] for result in results} == {1}
    history = list_capability_grant_history(
        tmp_path,
        subject_id=subject_id,
        universe_id="universe-a",
        capability=PRIORITY_REQUEST_CAPABILITY,
    )
    assert len(history) == 1
    assert history[0]["generation"] == 1


def test_admission_callback_rereads_current_grant_in_write_transaction(
    tmp_path: Path,
    server_clock: Callable[[float], None],
) -> None:
    issuer_id, subject_id = _authorized_fixture(tmp_path)
    issued_at = time.time() + 1
    server_clock(issued_at)
    grant = issue_priority_grant(
        tmp_path,
        subject_id=subject_id,
        universe_id="universe-a",
        issuer_id=issuer_id,
    )
    store = RequestAdmissionStore(tmp_path)

    def require_generation(evaluated_at: float):
        def check(conn: sqlite3.Connection) -> None:
            current = active_priority_grant_from_connection(
                conn,
                subject_id=subject_id,
                universe_id="universe-a",
                evaluated_at=evaluated_at,
            )
            if current is None:
                raise CapabilityGrantAuthorizationError(
                    "priority_authorization_required"
                )
            assert current["generation"] == grant["generation"]

        return check

    first = store.commit_admission(
        tenant_id="tenant-a",
        actor_id=subject_id,
        universe_id="universe-a",
        idempotency_key_hash="hmac:key-a",
        body_digest="sha256:body-a",
        body_digest_version="rfc8785-v1",
        request_type="general",
        text="admit while grant is active",
        branch_id="",
        branch_def_id="loop-branch",
        trigger_source="operator_request",
        accepted_priority_weight=50,
        policy_version="operator-priority-v1",
        grant_generation=grant["generation"],
        receipt={},
        directed_daemon_id="",
        created_at="2026-07-24T19:00:00Z",
        authority_check=require_generation(issued_at),
    )
    revoked_at = issued_at + 2
    server_clock(revoked_at)
    revoke_priority_grant(
        tmp_path,
        subject_id=subject_id,
        universe_id="universe-a",
        issuer_id=issuer_id,
    )

    with pytest.raises(
        CapabilityGrantAuthorizationError,
        match="priority_authorization_required",
    ):
        store.commit_admission(
            tenant_id="tenant-a",
            actor_id=subject_id,
            universe_id="universe-a",
            idempotency_key_hash="hmac:key-b",
            body_digest="sha256:body-b",
            body_digest_version="rfc8785-v1",
            request_type="general",
            text="must not admit after revocation",
            branch_id="",
            branch_def_id="loop-branch",
            trigger_source="operator_request",
            accepted_priority_weight=50,
            policy_version="operator-priority-v1",
            grant_generation=grant["generation"],
            receipt={},
            directed_daemon_id="",
            created_at="2026-07-24T19:01:00Z",
            authority_check=require_generation(revoked_at),
        )

    with _connect(tmp_path) as conn:
        assert conn.execute(
            "SELECT COUNT(*) FROM request_admissions"
        ).fetchone()[0] == 1
        assert conn.execute(
            """
            SELECT admission_id
            FROM request_admissions
            WHERE request_id = ?
            """,
            (first["request_id"],),
        ).fetchone() is not None
