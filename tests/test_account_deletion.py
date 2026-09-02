"""Self-service account deletion (tinyassets.account_deletion + the app route).

The floor is cross-user: deleting A must remove everything that is A's and
touch nothing that is B's. Every test here builds two users and asserts both
halves.
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
import urllib.error
from pathlib import Path

import pytest

from tinyassets import account_deletion
from tinyassets.account_deletion import AccountDeletionError, delete_account
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
            "child_artifact_id, remixed_by_user_id, created_at) VALUES ('art-a', 'art-b', ?, 1.0)",
            (B,),
        )
    conn.close()
    return path


def _seed_auth(base: Path) -> Path:
    path = base / ".auth.db"
    conn = sqlite3.connect(str(path))
    with conn:
        conn.execute("CREATE TABLE access_tokens (token TEXT PRIMARY KEY, user_id TEXT NOT NULL)")
        conn.execute("CREATE TABLE refresh_tokens (token TEXT PRIMARY KEY, user_id TEXT NOT NULL)")
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


@pytest.fixture
def two_users(tmp_path: Path) -> Path:
    base = tmp_path / "data"
    base.mkdir()
    _seed_user(base, A, HOME_A)
    _seed_user(base, B, HOME_B)
    _seed_outbound(base)
    _seed_auth(base)
    return base


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
    assert _rows(root_db, "SELECT 1 FROM universes WHERE universe_id = ?", (HOME_A,)) == []
    assert _rows(root_db, "SELECT 1 FROM branches WHERE universe_id = ?", (HOME_A,)) == []
    assert _rows(root_db, "SELECT 1 FROM universe_rules WHERE universe_id = ?", (HOME_A,)) == []
    assert _rows(root_db, "SELECT 1 FROM universe_acl WHERE actor_id = ?", (A,)) == []
    assert webhook_hooks.list_for_universe(base, universe_id=HOME_A) == []
    outbound = base / "outbound.db"
    assert _rows(outbound, "SELECT 1 FROM outbound_connections WHERE owner_user_id = ?", (A,)) == []
    for table in ("outbound_connection_grants", "outbound_connector_artifacts"):
        assert _rows(outbound, f"SELECT 1 FROM {table} WHERE owner_user_id = ?", (A,)) == []
    assert _rows(outbound, "SELECT 1 FROM outbound_connector_artifact_edges") == []
    auth = base / ".auth.db"
    assert _rows(auth, "SELECT 1 FROM access_tokens WHERE user_id = ?", (A,)) == []
    assert _rows(auth, "SELECT 1 FROM refresh_tokens WHERE user_id = ?", (A,)) == []
    assert billed == [HOME_A]
    assert identities == [A]

    # B: untouched.
    assert (base / HOME_B / "soul.md").is_file()
    assert (base / HOME_B / "memory" / "notes.md").read_text(encoding="utf-8") == "private"
    assert get_founder_home(base, B) == HOME_B
    assert _rows(root_db, "SELECT 1 FROM universes WHERE universe_id = ?", (HOME_B,)) == [(1,)]
    assert len(_rows(root_db, "SELECT 1 FROM branches WHERE universe_id = ?", (HOME_B,))) >= 1
    b_grants = _rows(root_db, "SELECT permission FROM universe_acl WHERE actor_id = ?", (B,))
    assert b_grants == [("admin",)]
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
    assert receipt["rows_deleted"]["founder_home"] == 1
    assert receipt["rows_deleted"]["universes"] == 1
    assert receipt["rows_deleted"]["webhook_hooks"] == 1
    assert receipt["rows_deleted"]["outbound_connections"] == 1
    assert A not in json.dumps(receipt) and HOME_B not in json.dumps(receipt)
    # The staging dir exists only mid-operation: no root-level dot-dir lingers for
    # the data-root scanners (universe list, _resolve_udir fallback) to trip over.
    assert not (base / ".deleting").exists()


def test_a_principal_with_no_home_still_loses_grants_tokens_and_identity(two_users: Path):
    base = two_users
    # A holds a read grant on B's universe and tokens, but never founded a home.
    stranger = "user_01CCCCCCCCCCCCCCCCCCCCCCCC"
    grant_universe_access(base, universe_id=HOME_B, actor_id=stranger, permission="read")
    conn = sqlite3.connect(str(base / ".auth.db"))
    with conn:
        conn.execute("INSERT INTO access_tokens VALUES ('at-c', ?)", (stranger,))
    conn.close()
    seen: list[str] = []

    receipt = delete_account(
        base, founder_sub=stranger, delete_identity=lambda sub: seen.append(sub) or "deleted"
    )

    assert receipt["home_id"] == ""
    assert receipt["home_removed"] is True
    assert receipt["billing"] == "not_configured"
    assert seen == [stranger]
    root_db = base / ".tinyassets.db"
    assert _rows(root_db, "SELECT 1 FROM universe_acl WHERE actor_id = ?", (stranger,)) == []
    auth = base / ".auth.db"
    rows = _rows(auth, "SELECT 1 FROM access_tokens WHERE user_id = ?", (stranger,))
    assert rows == []
    # B's own grant and home are exactly as they were.
    b_sql = "SELECT permission FROM universe_acl WHERE universe_id = ?"
    assert _rows(root_db, b_sql, (HOME_B,)) == [("admin",)]
    assert (base / HOME_B / "soul.md").is_file()


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
        receipt = delete_account(base, founder_sub=A, cancel_billing=_boom, delete_identity=_boom)

    assert receipt["billing"] == "error"
    assert receipt["identity"] == "error"
    assert receipt["home_removed"] is True, "the data still goes; the failure is reported"
    assert not (base / HOME_A).exists()
    errors = [r.getMessage() for r in caplog.records if r.levelname == "ERROR"]
    assert len(errors) == 2
    assert "sk_live_SHOULD_NOT_APPEAR" not in " ".join(errors), "exception text stays out of logs"


def test_a_second_deletion_of_the_same_principal_is_a_clean_noop(two_users: Path):
    delete_account(two_users, founder_sub=A, delete_identity=lambda s: "deleted")
    receipt = delete_account(two_users, founder_sub=A, delete_identity=lambda s: "deleted")
    assert receipt["home_id"] == ""
    assert receipt["rows_deleted"] == {}
    assert (two_users / HOME_B / "soul.md").is_file()


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
        "host:jonathan", request=lambda req, timeout: calls.append(req.full_url) or _Resp(200)
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
    calls: dict[str, object] = {"deleted": [], "dropped": []}
    monkeypatch.setattr(
        "tinyassets.account_deletion.delete_account",
        lambda base, *, founder_sub: calls["deleted"].append((Path(base), founder_sub)) or {
            "home_removed": True, "billing": "none", "identity": "deleted",
        },
    )
    monkeypatch.setattr(onboarding, "_drop_refresh_session", lambda h: calls["dropped"].append(h))
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
    assert body == {"deleted": True, "home_removed": True, "billing": "none", "identity": "deleted"}
    assert calls["deleted"] == [(tmp_path, A)]
    assert calls["dropped"] == [handle]
    set_cookie = resp.headers.get("set-cookie", "")
    assert "ta_rt=" in set_cookie
    assert "Max-Age=0" in set_cookie or "expires=" in set_cookie.lower()
    assert resp.headers.get("cache-control") == "no-store"


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


def test_the_app_page_carries_the_deletion_path():
    page = Path(__file__).resolve().parents[1] / "tinyassets" / "onboarding" / "app.html"
    html = page.read_text(encoding="utf-8")
    assert 'id="btn-account"' in html and 'id="btn-connect-account"' in html
    assert 'id="btn-delete-account"' in html
    assert '"/mcp/app/account/delete"' in html
    assert 'confirm:"DELETE"' in html
    assert "cannot be undone" in html
