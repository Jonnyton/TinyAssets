"""Self-service account deletion (tinyassets.account_deletion + the app route).

The floor is cross-user: deleting A must remove everything that is A's and
touch nothing that is B's. Every data test here builds two users and asserts
both halves.

The deleted row set is derived from the live schema rather than a hand-written
list, so the tests that matter most are the ones that would catch a *rule* being
wrong: a person-keyed table reaching into another universe, a new table with a
person's id in it, a cascade removing rows nobody counted.
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
import urllib.error
from pathlib import Path

import pytest

from tinyassets import account_deletion
from tinyassets.account_deletion import (
    AccountDeletionBlocked,
    AccountDeletionError,
    delete_account,
)
from tinyassets.daemon_server import (
    ensure_universe_registered,
    get_founder_home,
    grant_universe_access,
    set_founder_home,
)
from tinyassets.storage import webhook_hooks
from tinyassets.storage.outbound_connections import ConnectionLedger

A, B = "user_01AAAAAAAAAAAAAAAAAAAAAAAA", "user_01BBBBBBBBBBBBBBBBBBBBBBBB"
HOME_A, HOME_B = "u-0000000000000001", "u-0000000000000002"


def _seed_user(base: Path, sub: str, home: str) -> Path:
    universe_dir = base / home
    universe_dir.mkdir()
    (universe_dir / "soul.md").write_text("# soul\n", encoding="utf-8")
    (universe_dir / ".credential-vault.json").write_text("[]", encoding="utf-8")
    (universe_dir / "memory").mkdir()
    (universe_dir / "memory" / "notes.md").write_text("private", encoding="utf-8")
    set_founder_home(base, founder_sub=sub, universe_id=home, platform_generated=True)
    ensure_universe_registered(base, universe_id=home, universe_path=universe_dir)
    grant_universe_access(
        base, universe_id=home, actor_id=sub, permission="admin", granted_by=sub
    )
    webhook_hooks.mint(base, universe_id=home, branch_def_id=f"bd-{home}")
    return universe_dir


def _seed_outbound(base: Path) -> Path:
    path = base / "outbound.db"
    ConnectionLedger(path)  # creates the schema exactly as production does
    conn = sqlite3.connect(str(path))
    with conn:
        for sub, home, tag in ((A, HOME_A, "a"), (B, HOME_B, "b")):
            conn.execute(
                "INSERT INTO outbound_connections (connection_id, owner_user_id, "
                "connection_class, scopes_json, provider, destination, credential_ref) "
                "VALUES (?, ?, 'compute', '[]', 'openrouter', 'https://x', ?)",
                (f"conn-{tag}", sub, f"cred-{tag}"),
            )
            conn.execute(
                "INSERT INTO outbound_connection_grants (grant_id, connection_id, "
                "owner_user_id, universe_id, granted_at) VALUES (?, ?, ?, ?, 1.0)",
                (f"grant-{tag}", f"conn-{tag}", sub, home),
            )
            conn.execute(
                "INSERT INTO outbound_connector_artifacts (artifact_id, owner_user_id, "
                "connector_definition_json, mcp_client_config_json, created_at) "
                "VALUES (?, ?, '{}', '{}', 1.0)",
                (f"art-{tag}", sub),
            )
        # B remixed A's artifact: the edge references A's row and must go with it.
        conn.execute(
            "INSERT INTO outbound_connector_artifact_edges (parent_artifact_id, "
            "child_artifact_id, remixed_by_user_id, created_at) "
            "VALUES ('art-a', 'art-b', ?, 1.0)",
            (B,),
        )
    conn.close()
    return path


def _seed_auth(base: Path) -> Path:
    path = base / ".auth.db"
    conn = sqlite3.connect(str(path))
    with conn:
        conn.execute(
            "CREATE TABLE access_tokens (token TEXT PRIMARY KEY, user_id TEXT NOT NULL)"
        )
        conn.execute(
            "CREATE TABLE refresh_tokens (token TEXT PRIMARY KEY, user_id TEXT NOT NULL)"
        )
        conn.execute("CREATE TABLE oauth_clients (client_id TEXT PRIMARY KEY)")
        for sub, tag in ((A, "a"), (B, "b")):
            conn.execute("INSERT INTO access_tokens VALUES (?, ?)", (f"at-{tag}", sub))
            conn.execute("INSERT INTO refresh_tokens VALUES (?, ?)", (f"rt-{tag}", sub))
        conn.execute("INSERT INTO oauth_clients VALUES ('client-shared')")
    conn.close()
    return path


def _rows(db: Path, sql: str, params: tuple = ()) -> list[tuple]:
    conn = sqlite3.connect(str(db))
    try:
        return [tuple(r) for r in conn.execute(sql, params).fetchall()]
    finally:
        conn.close()


def _exec(db: Path, sql: str, params: tuple = ()) -> None:
    conn = sqlite3.connect(str(db))
    try:
        with conn:
            conn.execute(sql, params)
    finally:
        conn.close()


@pytest.fixture
def two_users(tmp_path: Path) -> Path:
    base = tmp_path / "data"
    base.mkdir()
    _seed_user(base, A, HOME_A)
    _seed_user(base, B, HOME_B)
    _seed_outbound(base)
    _seed_auth(base)
    return base


# --------------------------------------------------------------------------- #
# the cross-user floor
# --------------------------------------------------------------------------- #


def test_deleting_a_removes_all_of_a_and_none_of_b(two_users: Path):
    base = two_users
    root_db = base / ".tinyassets.db"
    billed: list[str] = []
    identities: list[str] = []

    receipt = delete_account(
        base,
        founder_sub=A,
        cancel_billing=lambda home: billed.append(home) or "cancelled",
        delete_identity=lambda sub: identities.append(sub) or "deleted",
    )

    # A: gone everywhere.
    assert not (base / HOME_A).exists()
    assert get_founder_home(base, A) == ""
    for table in ("universes", "branches", "universe_rules"):
        assert _rows(
            root_db, f"SELECT 1 FROM {table} WHERE universe_id = ?", (HOME_A,)
        ) == []
    assert _rows(root_db, "SELECT 1 FROM universe_acl WHERE actor_id = ?", (A,)) == []
    assert webhook_hooks.list_for_universe(base, universe_id=HOME_A) == []
    outbound = base / "outbound.db"
    for table in (
        "outbound_connections", "outbound_connection_grants", "outbound_connector_artifacts"
    ):
        assert _rows(
            outbound, f"SELECT 1 FROM {table} WHERE owner_user_id = ?", (A,)
        ) == []
    assert _rows(outbound, "SELECT 1 FROM outbound_connector_artifact_edges") == []
    auth = base / ".auth.db"
    for table in ("access_tokens", "refresh_tokens"):
        assert _rows(auth, f"SELECT 1 FROM {table} WHERE user_id = ?", (A,)) == []
    assert billed == [HOME_A]
    assert identities == [A]

    # B: untouched.
    assert (base / HOME_B / "soul.md").is_file()
    assert (base / HOME_B / "memory" / "notes.md").read_text(encoding="utf-8") == "private"
    assert get_founder_home(base, B) == HOME_B
    assert _rows(root_db, "SELECT 1 FROM universes WHERE universe_id = ?", (HOME_B,)) == [(1,)]
    assert len(_rows(root_db, "SELECT 1 FROM branches WHERE universe_id = ?", (HOME_B,))) >= 1
    b_sql = "SELECT permission FROM universe_acl WHERE universe_id = ?"
    assert _rows(root_db, b_sql, (HOME_B,)) == [("admin",)]
    assert len(webhook_hooks.list_for_universe(base, universe_id=HOME_B)) == 1
    assert _rows(outbound, "SELECT connection_id FROM outbound_connections") == [("conn-b",)]
    assert _rows(outbound, "SELECT grant_id FROM outbound_connection_grants") == [("grant-b",)]
    assert _rows(outbound, "SELECT artifact_id FROM outbound_connector_artifacts") == [("art-b",)]
    assert _rows(auth, "SELECT token FROM access_tokens") == [("at-b",)]
    assert _rows(auth, "SELECT 1 FROM oauth_clients") == [(1,)]

    # The receipt is content-free and says what happened.
    assert receipt["home_id"] == HOME_A
    assert receipt["home_removed"] is True
    assert receipt["home_staged_path"] == ""
    assert receipt["billing"] == "cancelled"
    assert receipt["identity"] == "deleted"
    assert receipt["unfinished_phases"] == []
    assert receipt["rows_deleted"]["founder_home"] == 1
    assert receipt["rows_deleted"]["universes"] == 1
    assert receipt["rows_deleted"]["webhook_hooks"] == 1
    assert receipt["rows_deleted"]["outbound:outbound_connections"] == 1
    assert A not in json.dumps(receipt) and HOME_B not in json.dumps(receipt)
    # The staging dir exists only mid-operation, so no root-level dot-dir lingers
    # for the data-root scanners to trip over.
    assert not (base / ".deleting").exists()
    assert account_deletion.pending_deletions(base) == []


def test_a_persons_rows_inside_someone_elses_universe_are_left_alone(two_users: Path):
    """The rule that decides this is ``deletion_plan``: a universe-scoped table is
    touched by home only. Sweeping it by person would delete A's authored rows
    out of B's universe — the one thing the platform must never do."""
    base = two_users
    root_db = base / ".tinyassets.db"
    _exec(
        root_db,
        "INSERT INTO branches (branch_id, universe_id, name, status, created_by, "
        "created_at, updated_at) "
        "VALUES ('br-a-in-b', ?, 'a-branch', 'active', ?, 1.0, 1.0)",
        (HOME_B, A),
    )
    before = _rows(root_db, "SELECT COUNT(*) FROM branches WHERE universe_id = ?", (HOME_B,))

    delete_account(base, founder_sub=A, delete_identity=lambda s: "deleted")

    assert _rows(root_db, "SELECT 1 FROM branches WHERE branch_id = 'br-a-in-b'") == [(1,)]
    assert _rows(
        root_db, "SELECT COUNT(*) FROM branches WHERE universe_id = ?", (HOME_B,)
    ) == before


def test_access_a_held_on_another_universe_is_revoked(two_users: Path):
    """The deliberate exception: an access grant is the deleted person's access,
    so it goes wherever it points — without taking anything from the granting
    universe."""
    base = two_users
    root_db = base / ".tinyassets.db"
    grant_universe_access(base, universe_id=HOME_B, actor_id=A, permission="read")

    delete_account(base, founder_sub=A, delete_identity=lambda s: "deleted")

    assert _rows(root_db, "SELECT 1 FROM universe_acl WHERE actor_id = ?", (A,)) == []
    b_sql = "SELECT permission FROM universe_acl WHERE universe_id = ? AND actor_id = ?"
    assert _rows(root_db, b_sql, (HOME_B, B)) == [("admin",)]
    assert (base / HOME_B / "soul.md").is_file()


def test_a_second_founder_on_the_same_home_blocks_the_deletion(two_users: Path):
    """founder_home is keyed by principal, so two people CAN reference one
    universe. Destroying it would delete the other person's whole universe."""
    base = two_users
    shared = "user_01SSSSSSSSSSSSSSSSSSSSSSSS"
    set_founder_home(base, founder_sub=shared, universe_id=HOME_A, platform_generated=True)

    with pytest.raises(AccountDeletionBlocked) as exc:
        delete_account(base, founder_sub=A, delete_identity=lambda s: "deleted")

    assert "another founder" in str(exc.value)
    assert (base / HOME_A / "soul.md").is_file(), "a blocked deletion changes nothing"
    assert get_founder_home(base, A) == HOME_A


def test_another_persons_request_in_my_universe_blocks_the_deletion(two_users: Path):
    """Their request cascades into their admissions and tasks. The operator path
    refuses in this situation; so does this one."""
    base = two_users
    root_db = base / ".tinyassets.db"
    _exec(
        root_db,
        "INSERT INTO user_requests (request_id, universe_id, user_id, request_type, text, "
        "status, created_at, updated_at) "
        "VALUES ('req-b', ?, ?, 'ask', 'theirs', 'done', 1.0, 1.0)",
        (HOME_A, B),
    )

    with pytest.raises(AccountDeletionBlocked) as exc:
        delete_account(base, founder_sub=A, delete_identity=lambda s: "deleted")

    assert "another person's requests" in str(exc.value)
    assert _rows(root_db, "SELECT 1 FROM user_requests WHERE request_id = 'req-b'") == [(1,)]


def test_my_own_dependent_rows_are_deleted_and_counted_not_silently_cascaded(
    two_users: Path,
):
    """``request_admissions`` and ``branch_tasks_v2`` carry ON DELETE CASCADE
    onto ``user_requests``, so deleting the parent alone would take them
    invisibly and the receipt would understate what was destroyed."""
    base = two_users
    root_db = base / ".tinyassets.db"
    _exec(
        root_db,
        "INSERT INTO user_requests (request_id, universe_id, user_id, request_type, text, "
        "status, created_at, updated_at) "
        "VALUES ('req-a', ?, ?, 'ask', 'mine', 'done', 1.0, 1.0)",
        (HOME_A, A),
    )
    _exec(
        root_db,
        "INSERT INTO branch_tasks_v2 (branch_task_id, admission_id, request_id, universe_id, "
        "branch_def_id, trigger_source, priority_weight, status, queued_at) "
        "VALUES ('task-a', 'adm-a', 'req-a', ?, 'bd-x', 'user_request', 1.0, 'succeeded', "
        "'2026-01-01')",
        (HOME_A,),
    )
    _exec(
        root_db,
        "INSERT INTO request_admissions (admission_id, request_id, branch_task_id, tenant_id, "
        "actor_id, universe_id, idempotency_key_hash, body_digest, body_digest_version, "
        "trigger_source, accepted_priority_weight, priority_policy_version, state, "
        "result_json, created_at, updated_at) "
        "VALUES ('adm-a', 'req-a', 'task-a', 'tenant', ?, ?, 'hash', 'digest', 'v1', "
        "'user_request', 1.0, 'v1', 'committed', '{}', '2026-01-01', '2026-01-01')",
        (A, HOME_A),
    )

    receipt = delete_account(base, founder_sub=A, delete_identity=lambda s: "deleted")

    assert _rows(root_db, "SELECT 1 FROM request_admissions WHERE admission_id = 'adm-a'") == []
    assert _rows(root_db, "SELECT 1 FROM branch_tasks_v2 WHERE branch_task_id = 'task-a'") == []
    assert _rows(root_db, "SELECT 1 FROM user_requests WHERE request_id = 'req-a'") == []
    rows = receipt["rows_deleted"]
    assert rows.get("request_admissions") == 1, rows
    assert rows.get("branch_tasks_v2") == 1, rows
    assert rows.get("user_requests") == 1, rows


def test_audit_rows_survive_without_the_person_or_the_content(two_users: Path):
    """/legal promises 'audit records with the actor replaced by an opaque id and
    their content emptied'. This is the test that makes that sentence true."""
    base = two_users
    root_db = base / ".tinyassets.db"
    _exec(
        root_db,
        "INSERT INTO action_records (action_id, universe_id, visibility, actor_type, "
        "actor_id, action_type, target_type, target_id, summary, created_at, payload_json) "
        "VALUES ('act-a', ?, 'public', 'user', ?, 'write', 'page', 'my-secret-page', "
        "'A wrote something private', 1.0, '{\"secret\": 1}')",
        (HOME_A, A),
    )

    receipt = delete_account(base, founder_sub=A, delete_identity=lambda s: "deleted")

    row = _rows(
        root_db,
        "SELECT actor_id, summary, target_id, payload_json FROM action_records "
        "WHERE action_id = 'act-a'",
    )
    assert len(row) == 1, "the audit row itself survives"
    actor, summary, target, payload = row[0]
    assert actor.startswith("deleted:") and A not in actor
    assert summary == "" and target == "" and payload == "{}"
    assert receipt["rows_deleted"]["action_records (redacted)"] == 1


def test_a_principal_with_no_home_still_loses_grants_tokens_and_identity(two_users: Path):
    base = two_users
    stranger = "user_01CCCCCCCCCCCCCCCCCCCCCCCC"
    grant_universe_access(base, universe_id=HOME_B, actor_id=stranger, permission="read")
    _exec(base / ".auth.db", "INSERT INTO access_tokens VALUES ('at-c', ?)", (stranger,))
    seen: list[str] = []

    receipt = delete_account(
        base,
        founder_sub=stranger,
        delete_identity=lambda sub: seen.append(sub) or "deleted",
    )

    assert receipt["home_id"] == ""
    assert receipt["home_removed"] is True
    assert receipt["billing"] == "not_configured"
    assert seen == [stranger]
    root_db = base / ".tinyassets.db"
    assert _rows(root_db, "SELECT 1 FROM universe_acl WHERE actor_id = ?", (stranger,)) == []
    auth = base / ".auth.db"
    assert _rows(auth, "SELECT 1 FROM access_tokens WHERE user_id = ?", (stranger,)) == []
    b_sql = "SELECT permission FROM universe_acl WHERE universe_id = ? AND actor_id = ?"
    assert _rows(root_db, b_sql, (HOME_B, B)) == [("admin",)]
    assert (base / HOME_B / "soul.md").is_file()


# --------------------------------------------------------------------------- #
# the schema-derived rule itself
# --------------------------------------------------------------------------- #


def test_every_person_keyed_table_is_covered_or_deliberately_kept(two_users: Path):
    """The guard against a migration adding a table full of someone's data that
    deletion never touches: every live root table carrying a person or universe
    column must be in the plan, preserved on purpose, redacted, or blocking."""
    from tinyassets.account_deletion import (
        BLOCKING_TABLES,
        INDIRECTLY_SCOPED_TABLES,
        PRESERVED_TABLES,
        PRINCIPAL_KEYS,
        REDACTED_TABLES,
        deletion_plan,
    )

    conn = sqlite3.connect(str(two_users / ".tinyassets.db"))
    try:
        plan = deletion_plan(conn, principal=A, home=HOME_A)
        tables = [
            str(r[0])
            for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
            if not str(r[0]).startswith("sqlite_")
        ]
        uncovered = []
        for table in tables:
            cols = {str(r[1]) for r in conn.execute(f'PRAGMA table_info("{table}")')}
            carries_identity = bool(cols & set(PRINCIPAL_KEYS)) or "universe_id" in cols
            handled = (
                table in plan
                or table in PRESERVED_TABLES
                or table in REDACTED_TABLES
                or table in BLOCKING_TABLES
                or table in INDIRECTLY_SCOPED_TABLES
            )
            if carries_identity and not handled:
                uncovered.append(table)
    finally:
        conn.close()
    assert uncovered == [], (
        "these tables hold a person's or a universe's rows and account deletion "
        f"has no policy for them: {uncovered}"
    )


def test_created_by_is_not_a_deletion_key():
    """Authorship is not ownership. Sweeping ``created_by`` would delete the rows
    this person authored inside other people's universes."""
    assert "created_by" not in account_deletion.PRINCIPAL_KEYS


# --------------------------------------------------------------------------- #
# refusals and failures
# --------------------------------------------------------------------------- #


def test_anonymous_and_empty_principals_are_refused(two_users: Path):
    for bad in ("", "  ", "anonymous"):
        with pytest.raises(AccountDeletionError):
            delete_account(two_users, founder_sub=bad, delete_identity=lambda s: "deleted")
    assert (two_users / HOME_A).is_dir() and (two_users / HOME_B).is_dir()


def test_an_escaping_home_binding_is_refused_before_anything_changes(two_users: Path):
    base = two_users
    evil = "user_01EEEEEEEEEEEEEEEEEEEEEEEE"
    set_founder_home(base, founder_sub=evil, universe_id="../outside", platform_generated=True)
    (base.parent / "outside").mkdir()
    (base.parent / "outside" / "keep.txt").write_text("x", encoding="utf-8")

    with pytest.raises(AccountDeletionError):
        delete_account(base, founder_sub=evil, delete_identity=lambda s: "deleted")

    assert (base.parent / "outside" / "keep.txt").is_file()
    assert get_founder_home(base, evil) == "../outside", "refusal must change nothing"


def test_billing_and_identity_failures_are_reported_not_hidden(two_users: Path, caplog):
    base = two_users

    def _boom(_: str) -> str:
        raise RuntimeError("stripe down sk_live_SHOULD_NOT_APPEAR")

    with caplog.at_level("ERROR"):
        receipt = delete_account(
            base, founder_sub=A, cancel_billing=_boom, delete_identity=_boom
        )

    assert receipt["billing"] == "error"
    assert receipt["identity"] == "error"
    assert receipt["unfinished_phases"] == ["billing", "identity"]
    assert receipt["home_removed"] is True, "the data still goes; the failure is reported"
    assert not (base / HOME_A).exists()
    errors = [r.getMessage() for r in caplog.records if r.levelname == "ERROR"]
    assert len(errors) == 2
    assert "sk_live_SHOULD_NOT_APPEAR" not in " ".join(errors)
    # A durable, content-free receipt tells the host exactly what to finish.
    pending = account_deletion.pending_deletions(base)
    assert len(pending) == 1
    assert pending[0]["unfinished_phases"] == ["billing", "identity"]
    assert A not in json.dumps(pending[0])


def test_a_failed_row_phase_still_cancels_the_billing(two_users: Path, monkeypatch, caplog):
    """The phase that must never be skipped is the one that stops the money.
    A broken satellite store must not leave a live subscription behind."""
    base = two_users
    billed: list[str] = []

    def _broken(*_args, **_kwargs):
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(account_deletion, "_delete_satellite_rows", _broken)
    with caplog.at_level("ERROR"):
        receipt = delete_account(
            base,
            founder_sub=A,
            cancel_billing=lambda home: billed.append(home) or "cancelled",
            delete_identity=lambda s: "deleted",
        )

    assert billed == [HOME_A], "billing ran even though an earlier phase failed"
    assert receipt["identity"] == "deleted"
    assert receipt["unfinished_phases"] == ["auth", "outbound"]
    assert receipt["host_receipt_path"]


def test_a_second_deletion_of_the_same_principal_is_a_clean_noop(two_users: Path):
    delete_account(two_users, founder_sub=A, delete_identity=lambda s: "deleted")
    receipt = delete_account(two_users, founder_sub=A, delete_identity=lambda s: "deleted")
    assert receipt["home_id"] == ""
    assert receipt["rows_deleted"] == {}
    assert (two_users / HOME_B / "soul.md").is_file()


def test_a_deleted_principal_cannot_be_handed_a_fresh_universe(two_users: Path):
    """A second device's token stays valid here until it expires. Without the
    tombstone, first-contact would re-found the account seconds after deletion."""
    from tinyassets.api.first_contact import ensure_founder_home, principal_is_deleted

    base = two_users
    assert principal_is_deleted(base, A) is False
    delete_account(base, founder_sub=A, delete_identity=lambda s: "deleted")

    assert principal_is_deleted(base, A) is True
    assert ensure_founder_home(base, A) == "", "a deleted account must not be re-founded"
    assert get_founder_home(base, A) == ""
    assert principal_is_deleted(base, B) is False


def test_the_operator_reset_still_clears_the_tombstone():
    """A scoped identity reset KEEPS the login, so it must clear the tombstone or
    the reset test identity could never birth a home again."""
    from tinyassets.scoped_reset import MAIN_DB_TABLE_CLASSIFICATIONS

    assert MAIN_DB_TABLE_CLASSIFICATIONS["deleted_principals"] == "reset_binding"


# --------------------------------------------------------------------------- #
# WorkOS identity deletion
# --------------------------------------------------------------------------- #


class _Resp:
    def __init__(self, status: int) -> None:
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_workos_deletion_is_not_configured_without_a_key(monkeypatch):
    monkeypatch.delenv("WORKOS_API_KEY", raising=False)
    assert account_deletion.delete_workos_user(A) == "not_configured"


def test_workos_deletion_skips_non_workos_principals(monkeypatch):
    monkeypatch.setenv("WORKOS_API_KEY", "sk_test_x")
    calls: list[str] = []
    assert account_deletion.delete_workos_user(
        "host:jonathan",
        request=lambda req, timeout: calls.append(req.full_url) or _Resp(200),
    ) == "not_applicable"
    assert calls == []


def test_workos_deletion_sends_a_delete_and_treats_gone_as_done(monkeypatch):
    monkeypatch.setenv("WORKOS_API_KEY", "sk_test_x")
    seen: list[tuple[str, str]] = []

    def _ok(req, timeout):
        seen.append((req.get_method(), req.full_url))
        assert req.get_header("Authorization") == "Bearer sk_test_x"
        return _Resp(200)

    assert account_deletion.delete_workos_user(A, request=_ok) == "deleted"
    assert seen == [("DELETE", f"https://api.workos.com/user_management/users/{A}")]

    def _gone(req, timeout):
        raise urllib.error.HTTPError(req.full_url, 404, "gone", {}, None)

    assert account_deletion.delete_workos_user(A, request=_gone) == "deleted"


def test_workos_deletion_failures_raise_without_the_key(monkeypatch):
    monkeypatch.setenv("WORKOS_API_KEY", "sk_test_SECRET")

    def _fail(req, timeout):
        raise urllib.error.HTTPError(req.full_url, 500, "boom sk_test_SECRET", {}, None)

    with pytest.raises(AccountDeletionError) as exc:
        account_deletion.delete_workos_user(A, request=_fail)
    assert "500" in str(exc.value) and "SECRET" not in str(exc.value)

    def _timeout(req, timeout):
        raise TimeoutError()

    with pytest.raises(AccountDeletionError):
        account_deletion.delete_workos_user(A, request=_timeout)


# --------------------------------------------------------------------------- #
# the app route
# --------------------------------------------------------------------------- #


class _Request:
    def __init__(self, body: dict | None, *, origin: str = "https://tinyassets.io",
                 ctype: str = "application/json") -> None:
        self._raw = json.dumps(body).encode("utf-8") if body is not None else b"{"
        self.headers = {
            "content-type": ctype,
            "origin": origin,
            "host": "tinyassets.io",
            "content-length": str(len(self._raw)),
        }

    async def stream(self):
        yield self._raw


@pytest.fixture
def app_route(monkeypatch, tmp_path):
    from tinyassets import onboarding

    monkeypatch.setattr(onboarding, "onboarding_enabled", lambda: True)
    monkeypatch.setattr(
        onboarding, "app_config",
        lambda: {"configured": True, "resource": "https://tinyassets.io/mcp"},
    )
    monkeypatch.setattr("tinyassets.api.helpers._base_path", lambda: tmp_path)
    calls: dict[str, list] = {"deleted": [], "dropped": []}
    monkeypatch.setattr(
        "tinyassets.account_deletion.delete_account",
        lambda base, *, founder_sub: calls["deleted"].append((Path(base), founder_sub)) or {
            "home_removed": True, "billing": "none", "identity": "deleted",
            "unfinished_phases": [],
        },
    )
    monkeypatch.setattr(
        onboarding, "_drop_refresh_session", lambda h: calls["dropped"].append(h)
    )
    return onboarding, calls


def _as(identity_user: str | None):
    from tinyassets.auth.middleware import identity_context
    from tinyassets.auth.provider import ANONYMOUS, Identity

    ident = ANONYMOUS if identity_user is None else Identity(user_id=identity_user, username="a@x")
    return identity_context(ident)


def test_route_requires_a_signed_in_user(app_route):
    onboarding, calls = app_route
    with _as(None):
        resp = asyncio.run(onboarding._handle_account_delete(_Request({"confirm": "DELETE"})))
    assert resp.status_code == 401
    assert calls["deleted"] == []


def test_route_refuses_cross_origin_and_unconfirmed_posts(app_route):
    onboarding, calls = app_route
    with _as(A):
        cross = asyncio.run(onboarding._handle_account_delete(
            _Request({"confirm": "DELETE"}, origin="https://evil.example")))
        form = asyncio.run(onboarding._handle_account_delete(
            _Request({"confirm": "DELETE"}, ctype="application/x-www-form-urlencoded")))
        unconfirmed = asyncio.run(onboarding._handle_account_delete(_Request({"confirm": "yes"})))
        malformed = asyncio.run(onboarding._handle_account_delete(_Request(None)))
    assert cross.status_code == 403 and form.status_code == 403
    assert unconfirmed.status_code == 400
    assert json.loads(unconfirmed.body) == {"error": "confirmation_required"}
    assert malformed.status_code == 400
    assert calls["deleted"] == []


def test_route_deletes_the_signed_in_principal_and_ends_the_session(app_route, tmp_path):
    onboarding, calls = app_route
    handle = "a" * 43  # a well-formed session handle
    with _as(A):
        resp = asyncio.run(onboarding._handle_account_delete(
            _Request({"confirm": "DELETE", "session_ref": handle})))
    assert resp.status_code == 200
    body = json.loads(resp.body)
    assert body["deleted"] is True and body["identity"] == "deleted"
    assert body["unfinished"] == []
    assert calls["deleted"] == [(tmp_path, A)]
    assert calls["dropped"] == [handle]
    set_cookie = resp.headers.get("set-cookie", "")
    assert "ta_rt=" in set_cookie
    assert "Max-Age=0" in set_cookie or "expires=" in set_cookie.lower()
    assert resp.headers.get("cache-control") == "no-store"


def test_route_reports_a_block_with_its_reasons(app_route, monkeypatch):
    onboarding, calls = app_route

    def _blocked(base, *, founder_sub):
        raise AccountDeletionBlocked(
            "another founder is bound to this universe; a vote is still open"
        )

    monkeypatch.setattr("tinyassets.account_deletion.delete_account", _blocked)
    with _as(A):
        resp = asyncio.run(onboarding._handle_account_delete(_Request({"confirm": "DELETE"})))
    assert resp.status_code == 409
    body = json.loads(resp.body)
    assert body["error"] == "deletion_blocked"
    assert body["reasons"] == [
        "another founder is bound to this universe", "a vote is still open",
    ]
    assert calls["dropped"] == [], "a blocked deletion must not sign the user out"


def test_route_reports_a_refusal_without_pretending(app_route, monkeypatch):
    onboarding, calls = app_route

    def _refuse(base, *, founder_sub):
        raise AccountDeletionError("home path escapes the data root")

    monkeypatch.setattr("tinyassets.account_deletion.delete_account", _refuse)
    with _as(A):
        resp = asyncio.run(onboarding._handle_account_delete(_Request({"confirm": "DELETE"})))
    assert resp.status_code == 409
    assert json.loads(resp.body)["error"] == "deletion_refused"
    assert calls["dropped"] == []


# --------------------------------------------------------------------------- #
# the shipped page
# --------------------------------------------------------------------------- #


def _app_html() -> str:
    from tinyassets import onboarding

    return (Path(onboarding.__file__).parent / "app.html").read_text(encoding="utf-8")


def test_the_app_page_carries_the_deletion_path():
    html = _app_html()
    assert 'id="btn-account"' in html and 'id="btn-connect-account"' in html
    assert 'id="btn-delete-account"' in html
    assert '"/mcp/app/account/delete"' in html
    assert 'confirm:"DELETE"' in html
    assert "cannot be undone" in html


def test_the_android_shell_cannot_reach_checkout():
    """Play's payments policy is about capability, not layout: hiding the button
    is not enough while the code path still POSTs to the checkout endpoint."""
    html = _app_html()
    start = html.index("async function startSubscribe()")
    guard = html.index("if(NATIVE){", start)
    checkout = html.index('billingFetch("/mcp/app/billing/checkout"', start)
    assert guard < checkout, "the native guard must precede any checkout call"
    assert "if(!b || !PLAN || NATIVE) return;" in html, "and the button stays hidden"
