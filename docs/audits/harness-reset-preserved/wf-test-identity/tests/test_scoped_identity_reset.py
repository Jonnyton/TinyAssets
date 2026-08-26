"""Principal-scoped reset: isolation, repeatability, and real auth boundary."""

from __future__ import annotations

import json
import sqlite3
from inspect import signature
from pathlib import Path

import tinyassets.reset as reset_module

_A1 = "u-01aaaaaaaaaaaaaaaaaaaaaaaa"
_A2 = "u-01aaaaaaaaaaaaaaaaaaaaaaab"
_B1 = "u-01bbbbbbbbbbbbbbbbbbbbbbbb"


def _rows(base: Path, table: str) -> list[tuple]:
    with sqlite3.connect(str(base / ".tinyassets.db")) as conn:
        return conn.execute(f"SELECT * FROM {table} ORDER BY 1").fetchall()


def _query(base: Path, sql: str) -> list[tuple]:
    with sqlite3.connect(str(base / ".tinyassets.db")) as conn:
        return conn.execute(sql).fetchall()


def _seed(base: Path) -> None:
    from tinyassets.daemon_server import (
        ensure_universe_registered,
        grant_universe_access,
        initialize_author_server,
        save_branch_definition,
        save_goal,
        set_founder_home,
    )

    initialize_author_server(base)
    for uid in (_A1, _A2, _B1):
        udir = base / uid
        udir.mkdir()
        (udir / "soul.md").write_text(f"# {uid}\n", encoding="utf-8")
        ensure_universe_registered(base, universe_id=uid, universe_path=udir)

    for uid in (_A1, _A2):
        grant_universe_access(
            base,
            universe_id=uid,
            actor_id="founder-a",
            permission="admin",
            granted_by="founder-a",
        )
    grant_universe_access(
        base,
        universe_id=_B1,
        actor_id="founder-b",
        permission="admin",
        granted_by="founder-b",
    )
    # Even a delegated admin grant does not transfer ownership: A's grant on B
    # is removed without deleting B's universe.
    grant_universe_access(
        base,
        universe_id=_B1,
        actor_id="founder-a",
        permission="admin",
        granted_by="founder-b",
    )
    set_founder_home(base, founder_sub="founder-a", universe_id=_A1)
    set_founder_home(base, founder_sub="founder-b", universe_id=_B1)

    save_branch_definition(
        base,
        branch_def={"branch_def_id": "b-commons", "name": "commons"},
    )
    save_goal(base, goal={"goal_id": "g-commons", "name": "commons goal"})
    with sqlite3.connect(str(base / ".tinyassets.db")) as conn:
        conn.execute(
            "INSERT INTO gate_claims "
            "(claim_id, branch_def_id, goal_id, rung_key, evidence_url, "
            " evidence_note, claimed_by, claimed_at) "
            "VALUES ('c-commons', 'b-commons', 'g-commons', 'r1', '', '', "
            "        'founder-b', '2026-07-21T00:00:00Z')"
        )
        conn.execute(
            "INSERT INTO canonical_bindings "
            "(goal_id, scope_token, branch_version_id, bound_by_actor_id, "
            " bound_at, visibility) "
            "VALUES ('g-commons', '', 'bv-commons', 'founder-b', 1.0, 'public')"
        )
        for branch_id, uid in (("bi-a", _A1), ("bi-b", _B1)):
            conn.execute(
                "INSERT INTO branches "
                "(branch_id, universe_id, name, created_by, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, 1.0, 1.0)",
                (branch_id, uid, branch_id, "founder-a" if uid == _A1 else "founder-b"),
            )
            conn.execute(
                "INSERT INTO branch_heads (branch_id, updated_at) VALUES (?, 1.0)",
                (branch_id,),
            )

    (base / ".runs.db").write_bytes(b"runs-sentinel")
    wiki = base / "wiki"
    wiki.mkdir()
    (wiki / "commons.md").write_text("wiki sentinel\n", encoding="utf-8")


def test_reset_principal_removes_only_that_principals_state(tmp_path: Path) -> None:
    reset_principal = getattr(reset_module, "reset_principal", None)
    assert callable(reset_principal), "principal-scoped reset is missing"

    base = tmp_path / "data"
    base.mkdir()
    _seed(base)
    commons_before = {
        table: _rows(base, table)
        for table in (
            "branch_definitions",
            "goals",
            "gate_claims",
            "canonical_bindings",
        )
    }
    runs_before = (base / ".runs.db").read_bytes()
    wiki_before = (base / "wiki" / "commons.md").read_bytes()

    result = reset_principal(base, principal="founder-a")

    assert result["principal"] == "founder-a"
    assert result["universes_removed"] == [_A1, _A2]
    assert not (base / _A1).exists()
    assert not (base / _A2).exists()
    assert (base / _B1 / "soul.md").read_text(encoding="utf-8") == f"# {_B1}\n"
    assert [row[0] for row in _rows(base, "universes")] == [_B1]
    assert [(row[0], row[1]) for row in _rows(base, "founder_home")] == [
        ("founder-b", _B1)
    ]
    assert [(row[0], row[1], row[2]) for row in _rows(base, "universe_acl")] == [
        (_B1, "founder-b", "admin")
    ]
    surviving_branches = _query(
        base,
        "SELECT branch_id, universe_id FROM branches ORDER BY branch_id",
    )
    assert surviving_branches
    assert {row[1] for row in surviving_branches} == {_B1}
    assert {row[0] for row in _rows(base, "branch_heads")} == {
        row[0] for row in surviving_branches
    }
    assert {
        table: _rows(base, table)
        for table in commons_before
    } == commons_before
    assert (base / ".runs.db").read_bytes() == runs_before
    assert (base / "wiki" / "commons.md").read_bytes() == wiki_before


def test_reset_principal_is_idempotent_and_unknown_is_noop(tmp_path: Path) -> None:
    reset_principal = getattr(reset_module, "reset_principal", None)
    assert callable(reset_principal), "principal-scoped reset is missing"

    base = tmp_path / "data"
    base.mkdir()
    _seed(base)
    before_unknown = (base / ".tinyassets.db").read_bytes()
    assert reset_principal(base, principal="not-a-founder")["universes_removed"] == []
    assert (base / ".tinyassets.db").read_bytes() == before_unknown

    reset_principal(base, principal="founder-a")
    after_first = (base / ".tinyassets.db").read_bytes()
    second = reset_principal(base, principal="founder-a")
    assert second["universes_removed"] == []
    assert second["rows_removed"] == {}
    assert (base / ".tinyassets.db").read_bytes() == after_first


def test_reset_identity_public_surface_uses_only_request_principal(
    tmp_path: Path,
    monkeypatch,
) -> None:
    import tinyassets.universe_server as server
    from tinyassets.auth.middleware import auth_middleware, set_provider
    from tinyassets.auth.provider import AuthProvider, DevAuthProvider, Identity

    reset_identity = getattr(server, "reset_identity", None)
    assert callable(reset_identity), "authenticated reset tool is missing"

    class Provider(AuthProvider):
        def resolve_token(self, token: str):
            if token == "bearer-a":
                return Identity(
                    user_id="founder-a",
                    username="a",
                    capabilities=["write"],
                )
            if token == "bearer-reader":
                return Identity(
                    user_id="founder-a",
                    username="a",
                    capabilities=["read"],
                )
            return None

        def is_auth_required(self) -> bool:
            return True

        def register_client(self, metadata):
            return metadata

        def create_authorization(self, *args, **kwargs):
            return "code"

        def exchange_code(self, *args, **kwargs):
            return None

    base = tmp_path / "data"
    base.mkdir()
    _seed(base)
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(base))

    # A resolved subject is not enough: destructive reset also needs write.
    set_provider(Provider())
    try:
        auth_middleware("bearer-reader")
        denied = json.loads(reset_identity(confirm=True))
    finally:
        set_provider(DevAuthProvider())
        auth_middleware(None)
    assert denied == {
        "error": "write_scope_required",
        "auth_scope_required": True,
    }
    assert (base / _A1).is_dir()

    set_provider(Provider())
    try:
        auth_middleware("bearer-a")
        result = json.loads(reset_identity(confirm=True))
    finally:
        set_provider(DevAuthProvider())
        auth_middleware(None)

    assert result["principal"] == "founder-a"
    assert result["universes_removed"] == [_A1, _A2]
    assert (base / _B1).is_dir()
    assert "principal" not in signature(reset_identity).parameters


def test_reset_identity_rejects_requests_without_a_bearer(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from tinyassets.auth.middleware import auth_middleware, set_provider
    from tinyassets.auth.provider import DevAuthProvider
    from tinyassets.universe_server import reset_identity

    base = tmp_path / "data"
    base.mkdir()
    _seed(base)
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(base))
    set_provider(DevAuthProvider())
    auth_middleware(None)

    result = json.loads(reset_identity(confirm=True))

    assert result == {"error": "authentication_required", "auth_required": True}
    assert (base / _A1).is_dir()
    assert (base / _B1).is_dir()


def test_indexed_path_traversal_cannot_delete_wiki(tmp_path: Path) -> None:
    reset_principal = reset_module.reset_principal
    base = tmp_path / "data"
    base.mkdir()
    _seed(base)
    wiki_before = (base / "wiki" / "commons.md").read_bytes()
    with sqlite3.connect(str(base / ".tinyassets.db")) as conn:
        conn.execute(
            "INSERT INTO universe_acl "
            "(universe_id, actor_id, permission, granted_at, granted_by) "
            "VALUES ('wiki', 'hostile-founder', 'admin', 1.0, 'hostile-founder')"
        )

    result = reset_principal(base, principal="hostile-founder")

    assert result["universes_removed"] == ["wiki"]
    assert (base / "wiki" / "commons.md").read_bytes() == wiki_before
