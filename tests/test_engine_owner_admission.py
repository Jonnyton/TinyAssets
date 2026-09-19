"""Real SQLite authority boundaries, independent of legacy membership fixtures."""

import sqlite3

import pytest

from tinyassets import engine_mcp_http as routes
from tinyassets.storage import DB_FILENAME


@pytest.fixture
def scope(tmp_path, monkeypatch):
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("TINYASSETS_ENGINE_MCP_TOOLS", "1")
    monkeypatch.delenv("TINYASSETS_ENGINE_RUN_GRAPH_UNIVERSES", raising=False)
    with sqlite3.connect(tmp_path / DB_FILENAME) as conn:
        conn.executescript("""
            CREATE TABLE agent_bindings (universe_id TEXT, created_by TEXT, status TEXT);
            CREATE TABLE universe_acl (universe_id TEXT, actor_id TEXT, permission TEXT);
            CREATE TABLE deleted_principals (founder_sub TEXT);
            INSERT INTO agent_bindings VALUES ('u-a', 'owner-a', 'serving');
            INSERT INTO universe_acl VALUES ('u-a', 'owner-a', 'admin');
            INSERT INTO agent_bindings VALUES ('u-b', 'owner-b', 'serving');
            INSERT INTO universe_acl VALUES ('u-b', 'owner-b', 'admin');
        """)
    routes._write_routes(tmp_path, [
        routes._EngineServer("u-a", "owner-a", 8790, str(tmp_path)),
        routes._EngineServer("u-b", "owner-b", 8791, str(tmp_path)),
    ])
    from tinyassets import engine_mcp_server as server

    monkeypatch.setattr(server, "_ACTOR_ID", "owner-a")
    monkeypatch.setattr(server, "_GRAPH_ID", "u-a")
    return tmp_path


def _route(actor="owner-a", graph="u-a"):
    return routes.read_engine_mcp_route(actor_id=actor, graph_id=graph)


def test_ordinary_serving_owners_get_tools_without_env_membership(scope):
    from tinyassets import engine_mcp_server as server

    assert routes._desired_owners(scope) == {"u-a": "owner-a", "u-b": "owner-b"}
    assert _route() is not None
    assert _route("owner-b", "u-b") is not None
    assert server._binding_error() is None


@pytest.mark.parametrize("mutation", [
    "DELETE FROM universe_acl WHERE universe_id = 'u-a'",
    "UPDATE universe_acl SET permission = 'read' WHERE universe_id = 'u-a'",
    "UPDATE agent_bindings SET status = 'inactive' WHERE universe_id = 'u-a'",
    "UPDATE agent_bindings SET created_by = 'owner-b' WHERE universe_id = 'u-a'",
    "INSERT INTO agent_bindings VALUES ('u-a', 'owner-b', 'serving')",
    "INSERT INTO agent_bindings VALUES ('u-a', NULL, 'serving')",
    "DROP TABLE universe_acl",
    "DROP TABLE agent_bindings",
])
def test_stale_route_and_pinned_handler_refuse_changed_authority(scope, monkeypatch, mutation):
    from tinyassets import engine_mcp_server as server

    # Even an old deployment's vetted membership cannot override current scope.
    monkeypatch.setenv("TINYASSETS_ENGINE_RUN_GRAPH_UNIVERSES", "u-a")
    assert _route() is not None
    with sqlite3.connect(scope / DB_FILENAME) as conn:
        conn.execute(mutation)
    assert "u-a" not in routes._desired_owners(scope)
    assert _route() is None
    assert server._binding_error() is not None


def test_deleted_owner_refused_before_supervisor_reconciles(scope, monkeypatch):
    from tinyassets import engine_mcp_server as server
    from tinyassets.account_deletion import principal_digest

    monkeypatch.setenv("TINYASSETS_ENGINE_RUN_GRAPH_UNIVERSES", "u-a")
    with sqlite3.connect(scope / DB_FILENAME) as conn:
        conn.execute("INSERT INTO deleted_principals VALUES (?)", (principal_digest("owner-a"),))
    assert routes._desired_owners(scope) == {"u-b": "owner-b"}
    assert _route() is None
    assert server._binding_error() is not None


def test_multiple_bindings_for_same_owner_are_not_ambiguous(scope):
    with sqlite3.connect(scope / DB_FILENAME) as conn:
        conn.execute("INSERT INTO agent_bindings VALUES ('u-a', 'owner-a', 'serving')")
    assert routes._desired_owners(scope)["u-a"] == "owner-a"
    assert _route() is not None


def test_foreign_owner_and_bearer_cannot_cross_universes(scope):
    from tinyassets.engine_mcp_server import _bearer_ok

    assert _route("owner-b", "u-a") is None
    assert _route("owner-a", "u-b") is None
    first, second = _route(), _route("owner-b", "u-b")
    assert first is not None and second is not None
    assert not _bearer_ok("Bearer " + first.secret, second.secret)


def test_disabled_flag_darkens_routes_supervisor_and_handlers(scope, monkeypatch):
    from tinyassets import engine_mcp_server as server

    monkeypatch.setenv("TINYASSETS_ENGINE_RUN_GRAPH_UNIVERSES", "u-a")
    monkeypatch.setenv("TINYASSETS_ENGINE_MCP_TOOLS", "0")
    assert routes._desired_owners(scope) == {}
    assert _route() is None
    assert server._binding_error() is not None


def test_missing_database_refuses_without_creating_it(tmp_path, monkeypatch):
    monkeypatch.setenv("TINYASSETS_ENGINE_MCP_TOOLS", "1")
    assert routes._desired_owners(tmp_path) == {}
    assert not (tmp_path / DB_FILENAME).exists()


@pytest.mark.parametrize("name,arguments,expected", [
    ("run_graph", {"operation": "unknown"}, "operation must be"),
    ("write_graph", {"target": "unknown"}, "not available"),
    ("remix_shape", {}, "fork_from"),
    ("write_brain", {}, "nothing"),
    ("connect_compute", {}, "access_method"),
    ("source_channel", {"action": "unknown"}, "supports action"),
])
def test_every_formerly_vetted_write_reaches_its_own_validation(scope, name, arguments, expected):
    from tinyassets import engine_mcp_server as server

    tool = getattr(server, name)
    result = getattr(tool, "fn", tool)(**arguments)
    assert expected in result.lower()
    assert "vetted" not in result.lower()


@pytest.mark.parametrize("owner", [None, "", " owner-a", "anonymous"])
def test_invalid_creator_is_not_inferred_from_acl(scope, owner):
    with sqlite3.connect(scope / DB_FILENAME) as conn:
        conn.execute("UPDATE agent_bindings SET created_by = ? WHERE universe_id = 'u-a'", (owner,))
    assert "u-a" not in routes._desired_owners(scope)
    assert _route() is None


def test_malformed_deletion_schema_fails_closed(scope):
    with sqlite3.connect(scope / DB_FILENAME) as conn:
        conn.execute("DROP TABLE deleted_principals")
        conn.execute("CREATE TABLE deleted_principals (wrong_column TEXT)")
    assert routes._desired_owners(scope) == {}
    assert _route() is None
