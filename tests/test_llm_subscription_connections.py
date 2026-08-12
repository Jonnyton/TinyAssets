from __future__ import annotations

import base64
import json
import sqlite3
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

import pytest


def _auth_b64(material: str) -> str:
    return base64.b64encode(material.encode()).decode()


def _codex_auth(token: str = "codex-access-token") -> str:
    return json.dumps({"tokens": {"access_token": token}})


def _claude_oauth(token: str = "fixture") -> str:
    return f"sk-ant-oat01-{token}-subscription-token"


def _as_actor(monkeypatch, tmp_path, *, actor: str, permission: str = "admin") -> None:
    from tinyassets.api import permissions
    from tinyassets.daemon_server import grant_universe_access

    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(permissions, "is_authenticated_request", lambda: True)
    monkeypatch.setattr(permissions, "current_actor_id", lambda: actor)
    grant_universe_access(
        tmp_path,
        universe_id="u-owner",
        actor_id=actor,
        permission=permission,
        granted_by="test-founder",
    )


def _agent_binding(tmp_path, *, actor: str) -> dict[str, object]:
    from tinyassets.custom_agents import create_binding, publish_definition

    definition = publish_definition(
        tmp_path,
        author_id=actor,
        payload={
            "schema_version": 1,
            "name": "Connected agent",
            "description": "Exercises the MCP subscription deposit boundary",
            "tags": ["test"],
            "components": {
                "identity": {"kind": "soul", "config": {"voice": "direct"}},
            },
        },
    )
    return create_binding(
        tmp_path,
        universe_id="u-owner",
        definition_id=definition["agent_definition_id"],
        created_by=actor,
        payload={"schema_version": 1, "name": "Connected agent", "role": "writer"},
    )


@pytest.mark.parametrize(
    ("service", "provider", "material"),
    [
        ("codex", "codex", _codex_auth("codex-secret")),
        ("claude", "claude-code", _claude_oauth("claude-secret")),
    ],
)
def test_connect_llm_records_depositor_surfaces_redacted_connection_and_binds(
    tmp_path,
    monkeypatch,
    caplog,
    service,
    provider,
    material,
):
    import tinyassets.universe_server as server
    from tinyassets.credential_vault import write_credential_vault
    from tinyassets.provider_serving_binding import bind_serving_provider
    from tinyassets.storage import db_path

    universe_dir = tmp_path / "u-owner"
    universe_dir.mkdir()
    _as_actor(monkeypatch, tmp_path, actor="owner-1")
    agent = _agent_binding(tmp_path, actor="owner-1")
    encoded = _auth_b64(material)
    ownerless_record = {
        "credential_type": "llm_subscription",
        "service": service,
        ("auth_json_b64" if service == "codex" else "token_b64"): encoded,
    }
    write_credential_vault(universe_dir, [ownerless_record])

    with pytest.raises(PermissionError, match="server-recorded credential owner"):
        bind_serving_provider(
            base_path=tmp_path,
            universe_dir=universe_dir,
            owner_user_id="owner-1",
            universe_id="u-owner",
            agent_binding_id=str(agent["agent_binding_id"]),
            expected_revision=1,
            provider=provider,
        )

    connected = json.loads(
        server.write_graph(
            target="connection",
            operation="connect_llm",
            graph_id="u-owner",
            payload_json=json.dumps({"service": service, "auth_json_b64": encoded}),
        )
    )

    assert connected["status"] == "connected"
    assert connected["connection"] == {
        "service": service,
        "owner_user_id": "owner-1",
        "connected_at": connected["connection"]["connected_at"],
    }
    assert connected["connection"]["connected_at"].endswith("Z")
    assert material not in json.dumps(connected)
    assert encoded not in json.dumps(connected)
    assert material not in caplog.text
    assert encoded not in caplog.text

    with sqlite3.connect(db_path(tmp_path)) as conn:
        row = conn.execute(
            "SELECT owner_user_id, connected_at "
            "FROM llm_credential_deposit_owners "
            "WHERE universe_id = ? AND service = ?",
            ("u-owner", service),
        ).fetchone()
    assert row == ("owner-1", connected["connection"]["connected_at"])

    listed = json.loads(server.read_graph(target="connections", graph_id="u-owner"))
    llm_connection = next(
        item for item in listed["connections"] if item.get("service") == service
    )
    assert llm_connection == connected["connection"]

    bound = bind_serving_provider(
        base_path=tmp_path,
        universe_dir=universe_dir,
        owner_user_id="owner-1",
        universe_id="u-owner",
        agent_binding_id=str(agent["agent_binding_id"]),
        expected_revision=1,
        provider=provider,
    )
    assert bound["status"] == "ready"

    from tinyassets.credential_vault import (
        cleanup_llm_credential_snapshot,
        current_llm_subscription_custody,
        snapshot_llm_subscription_credential,
    )
    from tinyassets.providers.base import subprocess_env_for_provider

    with sqlite3.connect(db_path(tmp_path)) as conn:
        custody = current_llm_subscription_custody(
            conn,
            universe_dir=universe_dir,
            owner_user_id="owner-1",
            universe_id="u-owner",
            service=service,
        )
    assert custody is not None
    snapshot = snapshot_llm_subscription_credential(
        universe_dir=universe_dir,
        custody=custody,
    )
    try:
        env = subprocess_env_for_provider(
            provider,
            universe_dir=universe_dir,
            credential_snapshot_dir=snapshot.directory,
        )
        if service == "codex":
            snapshotted = json.loads(
                (snapshot.directory / "auth.json").read_text(encoding="utf-8")
            )
            assert snapshotted["tokens"]["access_token"] == "codex-secret"
            assert env["CODEX_HOME"] == str(snapshot.directory)
        else:
            assert env["CLAUDE_CODE_OAUTH_TOKEN"] == material
            assert env["CLAUDE_CONFIG_DIR"] == str(snapshot.directory)
            child = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    (
                        "import os,sys; "
                        "sys.exit(0 if os.environ.get('CLAUDE_CODE_OAUTH_TOKEN', '')"
                        ".startswith('sk-ant-oat') else 9)"
                    ),
                ],
                check=False,
                env=env,
                capture_output=True,
                text=True,
            )
            assert child.returncode == 0
            assert child.stdout == ""
            assert material not in child.stderr
    finally:
        cleanup_llm_credential_snapshot(snapshot)


def test_connect_llm_requires_current_admin_acl(tmp_path, monkeypatch):
    import tinyassets.universe_server as server
    from tinyassets.credential_vault import credential_vault_path

    universe_dir = tmp_path / "u-owner"
    universe_dir.mkdir()
    _as_actor(monkeypatch, tmp_path, actor="writer-1", permission="write")

    denied = json.loads(
        server.write_graph(
            target="connection",
            operation="connect_llm",
            graph_id="u-owner",
            payload_json=json.dumps(
                {
                    "service": "codex",
                    "auth_json_b64": _auth_b64(_codex_auth()),
                }
            ),
        )
    )

    assert denied == {"error": "not_found", "resource": "connection"}
    assert not credential_vault_path(universe_dir).exists()


def test_connect_llm_rechecks_admin_at_the_admitted_write(tmp_path, monkeypatch):
    import tinyassets.universe_server as server
    from tinyassets.api import cloud_connections as connections_api
    from tinyassets.credential_vault import credential_vault_path
    from tinyassets.daemon_server import revoke_universe_access

    universe_dir = tmp_path / "u-owner"
    universe_dir.mkdir()
    _as_actor(monkeypatch, tmp_path, actor="owner-1")
    real_write = connections_api.write_credential_vault

    def revoke_then_write(*args, **kwargs):
        revoke_universe_access(
            tmp_path,
            universe_id="u-owner",
            actor_id="owner-1",
        )
        return real_write(*args, **kwargs)

    monkeypatch.setattr(connections_api, "write_credential_vault", revoke_then_write)
    refused = json.loads(
        server.write_graph(
            target="connection",
            operation="connect_llm",
            graph_id="u-owner",
            payload_json=json.dumps(
                {
                    "service": "codex",
                    "auth_json_b64": _auth_b64(_codex_auth()),
                }
            ),
        )
    )

    assert refused == {"error": "not_found", "resource": "connection"}
    assert not credential_vault_path(universe_dir).exists()


def test_connect_llm_rolls_back_vault_when_owner_commit_fails(tmp_path, monkeypatch):
    import tinyassets.universe_server as server
    from tinyassets import credential_vault
    from tinyassets.credential_vault import credential_vault_path
    from tinyassets.storage import db_path

    universe_dir = tmp_path / "u-owner"
    universe_dir.mkdir()
    _as_actor(monkeypatch, tmp_path, actor="owner-1")
    vault_path = credential_vault_path(universe_dir)
    original = '{"schema_version":1,"credentials":[]}\n'
    vault_path.write_text(original, encoding="utf-8")

    def fail_owner_write(*args, **kwargs):
        raise sqlite3.OperationalError("injected owner metadata failure")

    monkeypatch.setattr(credential_vault, "_upsert_llm_deposit_owner", fail_owner_write)
    refused = json.loads(
        server.write_graph(
            target="connection",
            operation="connect_llm",
            graph_id="u-owner",
            payload_json=json.dumps(
                {
                    "service": "codex",
                    "auth_json_b64": _auth_b64(_codex_auth("must-roll-back")),
                }
            ),
        )
    )

    assert refused == {"error": "llm_connection_invalid"}
    assert vault_path.read_text(encoding="utf-8") == original
    assert not (universe_dir / ".credential-vault.deposit-journal.json").exists()
    with sqlite3.connect(db_path(tmp_path)) as conn:
        owner = conn.execute(
            "SELECT owner_user_id FROM llm_credential_deposit_owners "
            "WHERE universe_id = ? AND service = ?",
            ("u-owner", "codex"),
        ).fetchone()
    assert owner is None


def test_connection_read_recovers_interrupted_uncommitted_deposit(tmp_path):
    from tinyassets.credential_vault import (
        _write_llm_deposit_journal,
        credential_vault_path,
        list_llm_subscription_connections,
    )

    universe_dir = tmp_path / "u-owner"
    universe_dir.mkdir()
    vault_path = credential_vault_path(universe_dir)
    original = '{"schema_version":1,"credentials":[]}\n'
    vault_path.write_text(original, encoding="utf-8")
    _write_llm_deposit_journal(universe_dir, deposit_id="interrupted-deposit")
    vault_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "credentials": [
                    {
                        "credential_type": "llm_subscription",
                        "service": "codex",
                        "auth_json_b64": _auth_b64(_codex_auth("uncommitted")),
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    assert list_llm_subscription_connections(
        universe_dir,
        universe_id="u-owner",
    ) == []
    assert vault_path.read_text(encoding="utf-8") == original
    assert not (universe_dir / ".credential-vault.deposit-journal.json").exists()


def test_connection_reads_serialize_legacy_owner_schema_migration(tmp_path):
    from tinyassets.credential_vault import list_llm_subscription_connections
    from tinyassets.storage import db_path

    for universe_id in ("u-one", "u-two"):
        (tmp_path / universe_id).mkdir()
    with sqlite3.connect(db_path(tmp_path)) as conn:
        conn.execute(
            """
            CREATE TABLE llm_credential_deposit_owners (
                universe_id TEXT NOT NULL,
                service TEXT NOT NULL,
                owner_user_id TEXT NOT NULL,
                PRIMARY KEY (universe_id, service)
            )
            """
        )
        conn.executemany(
            "INSERT INTO llm_credential_deposit_owners VALUES (?, 'codex', 'owner')",
            [("u-one",), ("u-two",)],
        )

    def read(universe_id: str):
        return list_llm_subscription_connections(
            tmp_path / universe_id,
            universe_id=universe_id,
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert list(pool.map(read, ("u-one", "u-two"))) == [[], []]

    with sqlite3.connect(db_path(tmp_path)) as conn:
        columns = {
            row[1] for row in conn.execute("PRAGMA table_info(llm_credential_deposit_owners)")
        }
        connected = conn.execute(
            "SELECT connected_at FROM llm_credential_deposit_owners"
        ).fetchall()
    assert {"connected_at", "deposit_id"}.issubset(columns)
    assert all(value and value.endswith("Z") for (value,) in connected)


def test_deposit_durability_order_fences_database_commit(tmp_path, monkeypatch):
    import tinyassets.universe_server as server
    from tinyassets import credential_vault

    (tmp_path / "u-owner").mkdir()
    _as_actor(monkeypatch, tmp_path, actor="owner-1")
    events: list[str] = []
    real_sync_file = credential_vault._durable_sync_file
    real_sync_directory = credential_vault._durable_sync_directory
    real_upsert = credential_vault._upsert_llm_deposit_owner

    def sync_file(path):
        events.append(f"file:{path.name}")
        return real_sync_file(path)

    def sync_directory(path):
        events.append(f"dir:{path.name}")
        return real_sync_directory(path)

    def upsert(*args, **kwargs):
        events.append("database-owner")
        return real_upsert(*args, **kwargs)

    monkeypatch.setattr(credential_vault, "_durable_sync_file", sync_file)
    monkeypatch.setattr(credential_vault, "_durable_sync_directory", sync_directory)
    monkeypatch.setattr(credential_vault, "_upsert_llm_deposit_owner", upsert)
    connected = json.loads(
        server.write_graph(
            target="connection",
            operation="connect_llm",
            graph_id="u-owner",
            payload_json=json.dumps(
                {
                    "service": "codex",
                    "auth_json_b64": _auth_b64(_codex_auth()),
                }
            ),
        )
    )

    assert connected["status"] == "connected"
    assert events.index("file:.credential-vault.deposit-journal.json") < events.index(
        "file:.credential-vault.json"
    )
    assert events.index("file:.credential-vault.json") < events.index("database-owner")
    assert events[-1] == "dir:u-owner"


def test_vault_durable_sync_failure_recovers_before_owner_commit(tmp_path, monkeypatch):
    import tinyassets.universe_server as server
    from tinyassets import credential_vault
    from tinyassets.credential_vault import credential_vault_path
    from tinyassets.storage import db_path

    universe_dir = tmp_path / "u-owner"
    universe_dir.mkdir()
    _as_actor(monkeypatch, tmp_path, actor="owner-1")
    vault_path = credential_vault_path(universe_dir)
    original = '{"schema_version":1,"credentials":[]}\n'
    vault_path.write_text(original, encoding="utf-8")
    real_sync_file = credential_vault._durable_sync_file
    failed = False

    def fail_new_vault_sync(path):
        nonlocal failed
        if path.name == ".credential-vault.json" and not failed:
            failed = True
            raise OSError("injected vault durability failure")
        return real_sync_file(path)

    monkeypatch.setattr(
        credential_vault,
        "_durable_sync_file",
        fail_new_vault_sync,
    )
    refused = json.loads(
        server.write_graph(
            target="connection",
            operation="connect_llm",
            graph_id="u-owner",
            payload_json=json.dumps(
                {
                    "service": "codex",
                    "auth_json_b64": _auth_b64(_codex_auth("not-durable")),
                }
            ),
        )
    )

    assert refused == {"error": "llm_connection_invalid"}
    assert vault_path.read_text(encoding="utf-8") == original
    assert not (universe_dir / ".credential-vault.deposit-journal.json").exists()
    with sqlite3.connect(db_path(tmp_path)) as conn:
        owner = conn.execute(
            "SELECT owner_user_id FROM llm_credential_deposit_owners "
            "WHERE universe_id = ? AND service = ?",
            ("u-owner", "codex"),
        ).fetchone()
    assert owner is None


def test_connect_llm_rejects_different_owner_without_overwriting(tmp_path, monkeypatch):
    import tinyassets.universe_server as server
    from tinyassets.credential_vault import load_credential_vault

    universe_dir = tmp_path / "u-owner"
    universe_dir.mkdir()
    _as_actor(monkeypatch, tmp_path, actor="owner-1")
    original = _auth_b64(_codex_auth("original-secret"))
    replacement = _auth_b64(_codex_auth("replacement-secret"))
    first = json.loads(
        server.write_graph(
            target="connection",
            operation="connect_llm",
            graph_id="u-owner",
            payload_json=json.dumps(
                {"service": "codex", "auth_json_b64": original}
            ),
        )
    )
    assert first["status"] == "connected"

    _as_actor(monkeypatch, tmp_path, actor="owner-2")
    refused = json.loads(
        server.write_graph(
            target="connection",
            operation="connect_llm",
            graph_id="u-owner",
            payload_json=json.dumps(
                {"service": "codex", "auth_json_b64": replacement}
            ),
        )
    )

    assert refused == {"error": "connection_conflict", "resource": "llm_subscription"}
    assert load_credential_vault(universe_dir) == [
        {
            "credential_type": "llm_subscription",
            "service": "codex",
            "auth_json_b64": original,
        }
    ]
    assert replacement not in json.dumps(refused)


def test_connect_llm_ownership_conflict_is_scoped_to_the_deposited_service(
    tmp_path,
    monkeypatch,
):
    import tinyassets.universe_server as server
    from tinyassets.storage import db_path

    (tmp_path / "u-owner").mkdir()
    _as_actor(monkeypatch, tmp_path, actor="owner-1")
    codex = json.loads(
        server.write_graph(
            target="connection",
            operation="connect_llm",
            graph_id="u-owner",
            payload_json=json.dumps(
                {"service": "codex", "auth_json_b64": _auth_b64(_codex_auth())}
            ),
        )
    )
    assert codex["status"] == "connected"

    _as_actor(monkeypatch, tmp_path, actor="owner-2")
    claude = json.loads(
        server.write_graph(
            target="connection",
            operation="connect_llm",
            graph_id="u-owner",
            payload_json=json.dumps(
                {
                    "service": "claude",
                    "auth_json_b64": _auth_b64(_claude_oauth("owner-2")),
                }
            ),
        )
    )
    assert claude["status"] == "connected"

    with sqlite3.connect(db_path(tmp_path)) as conn:
        owners = conn.execute(
            "SELECT service, owner_user_id "
            "FROM llm_credential_deposit_owners "
            "WHERE universe_id = ? ORDER BY service",
            ("u-owner",),
        ).fetchall()
    assert owners == [("claude", "owner-2"), ("codex", "owner-1")]


@pytest.mark.parametrize(
    "payload_json",
    [
        "{}",
        json.dumps({"service": "gemini", "auth_json_b64": _auth_b64("{}")}),
        json.dumps({"service": "codex", "auth_json_b64": "not-base64"}),
        json.dumps({"service": "codex", "auth_json_b64": _auth_b64("not-json")}),
        json.dumps({"service": "codex", "auth_json_b64": _auth_b64("{}")}),
        json.dumps({"service": "codex", "auth_json_b64": _auth_b64("[]")}),
        json.dumps(
            {
                "service": "codex",
                "auth_json_b64": _auth_b64(
                    '{"tokens":{"access_token":"one","access_token":"two"}}'
                ),
            }
        ),
        json.dumps({"service": "claude", "auth_json_b64": _auth_b64("{}")}),
        json.dumps(
            {"service": "claude", "auth_json_b64": _auth_b64("not-an-oauth-token")}
        ),
        json.dumps(
            {
                "service": "codex",
                "auth_json_b64": _auth_b64("{}"),
                "owner_user_id": "attacker",
            }
        ),
        '{"service":"codex","service":"claude","auth_json_b64":"e30="}',
    ],
)
def test_connect_llm_rejects_malformed_or_wrong_service_without_partial_write(
    tmp_path,
    monkeypatch,
    payload_json,
):
    import tinyassets.universe_server as server
    from tinyassets.credential_vault import credential_vault_path

    universe_dir = tmp_path / "u-owner"
    universe_dir.mkdir()
    _as_actor(monkeypatch, tmp_path, actor="owner-1")

    refused = json.loads(
        server.write_graph(
            target="connection",
            operation="connect_llm",
            graph_id="u-owner",
            payload_json=payload_json,
        )
    )

    assert refused == {"error": "llm_connection_invalid"}
    assert not credential_vault_path(universe_dir).exists()


def test_connect_llm_rejects_duplicate_existing_slot_without_collapsing_it(
    tmp_path,
    monkeypatch,
):
    import tinyassets.universe_server as server
    from tinyassets.credential_vault import credential_vault_path

    universe_dir = tmp_path / "u-owner"
    universe_dir.mkdir()
    _as_actor(monkeypatch, tmp_path, actor="owner-1")
    duplicate_vault = json.dumps(
        {
            "schema_version": 1,
            "credentials": [
                {
                    "credential_type": "llm_subscription",
                    "service": "codex",
                    "auth_json_b64": _auth_b64('{"slot":1}'),
                },
                {
                    "credential_type": "llm_subscription",
                    "service": "codex",
                    "auth_json_b64": _auth_b64('{"slot":2}'),
                },
            ],
        },
        sort_keys=True,
    )
    vault_path = credential_vault_path(universe_dir)
    vault_path.write_text(duplicate_vault, encoding="utf-8")

    refused = json.loads(
        server.write_graph(
            target="connection",
            operation="connect_llm",
            graph_id="u-owner",
            payload_json=json.dumps(
                {"service": "codex", "auth_json_b64": _auth_b64(_codex_auth())}
            ),
        )
    )

    assert refused == {"error": "llm_connection_invalid"}
    assert vault_path.read_text(encoding="utf-8") == duplicate_vault


def test_connect_llm_accepts_contained_codex_home_and_never_echoes_path(
    tmp_path,
    monkeypatch,
    caplog,
):
    import tinyassets.universe_server as server

    universe_dir = tmp_path / "u-owner"
    codex_home = universe_dir / ".credentials" / "codex"
    codex_home.mkdir(parents=True)
    (codex_home / "auth.json").write_text(
        _codex_auth("path-secret"), encoding="utf-8"
    )
    _as_actor(monkeypatch, tmp_path, actor="owner-1")

    connected = json.loads(
        server.write_graph(
            target="connection",
            operation="connect_llm",
            graph_id="u-owner",
            payload_json=json.dumps(
                {"service": "codex", "codex_home": str(codex_home)}
            ),
        )
    )

    assert connected["status"] == "connected"
    assert str(codex_home) not in json.dumps(connected)
    assert str(codex_home) not in caplog.text


def test_path_backed_codex_rotation_to_unusable_holds_binding(tmp_path, monkeypatch):
    import tinyassets.universe_server as server
    from tinyassets.provider_serving_binding import bind_serving_provider

    universe_dir = tmp_path / "u-owner"
    codex_home = universe_dir / ".credentials" / "codex"
    codex_home.mkdir(parents=True)
    auth_file = codex_home / "auth.json"
    auth_file.write_text(_codex_auth("valid-at-deposit"), encoding="utf-8")
    _as_actor(monkeypatch, tmp_path, actor="owner-1")
    agent = _agent_binding(tmp_path, actor="owner-1")
    connected = json.loads(
        server.write_graph(
            target="connection",
            operation="connect_llm",
            graph_id="u-owner",
            payload_json=json.dumps(
                {"service": "codex", "codex_home": str(codex_home)}
            ),
        )
    )
    assert connected["status"] == "connected"

    auth_file.write_text("{}", encoding="utf-8")

    with pytest.raises((PermissionError, ValueError)):
        bind_serving_provider(
            base_path=tmp_path,
            universe_dir=universe_dir,
            owner_user_id="owner-1",
            universe_id="u-owner",
            agent_binding_id=str(agent["agent_binding_id"]),
            expected_revision=1,
            provider="codex",
        )


def test_claude_rotation_to_unusable_holds_binding(tmp_path, monkeypatch):
    import tinyassets.universe_server as server
    from tinyassets.credential_vault import credential_vault_path
    from tinyassets.provider_serving_binding import bind_serving_provider

    universe_dir = tmp_path / "u-owner"
    universe_dir.mkdir()
    _as_actor(monkeypatch, tmp_path, actor="owner-1")
    agent = _agent_binding(tmp_path, actor="owner-1")
    connected = json.loads(
        server.write_graph(
            target="connection",
            operation="connect_llm",
            graph_id="u-owner",
            payload_json=json.dumps(
                {
                    "service": "claude",
                    "auth_json_b64": _auth_b64(_claude_oauth("valid-at-deposit")),
                }
            ),
        )
    )
    assert connected["status"] == "connected"
    credential_vault_path(universe_dir).write_text(
        json.dumps(
            {
                "schema_version": 1,
                "credentials": [
                    {
                        "credential_type": "llm_subscription",
                        "service": "claude",
                        "token_b64": _auth_b64("not-oauth-anymore"),
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises((PermissionError, ValueError)):
        bind_serving_provider(
            base_path=tmp_path,
            universe_dir=universe_dir,
            owner_user_id="owner-1",
            universe_id="u-owner",
            agent_binding_id=str(agent["agent_binding_id"]),
            expected_revision=1,
            provider="claude-code",
        )


def test_ownerless_replacement_clears_depositor_and_custody(tmp_path, monkeypatch):
    import tinyassets.universe_server as server
    from tinyassets.credential_vault import (
        adopt_llm_subscription_custody,
        write_credential_vault,
    )
    from tinyassets.storage import db_path

    universe_dir = tmp_path / "u-owner"
    universe_dir.mkdir()
    _as_actor(monkeypatch, tmp_path, actor="owner-1")
    connected = json.loads(
        server.write_graph(
            target="connection",
            operation="connect_llm",
            graph_id="u-owner",
            payload_json=json.dumps(
                {
                    "service": "codex",
                    "auth_json_b64": _auth_b64(_codex_auth("owned")),
                }
            ),
        )
    )
    assert connected["status"] == "connected"
    with sqlite3.connect(db_path(tmp_path), isolation_level=None) as conn:
        conn.execute("BEGIN IMMEDIATE")
        custody = adopt_llm_subscription_custody(
            conn,
            universe_dir=universe_dir,
            owner_user_id="owner-1",
            universe_id="u-owner",
            service="codex",
        )
        conn.commit()
    assert custody.owner_user_id == "owner-1"

    write_credential_vault(
        universe_dir,
        [
            {
                "credential_type": "llm_subscription",
                "service": "codex",
                "auth_json_b64": _auth_b64(_codex_auth("ownerless-replacement")),
            }
        ],
    )

    with sqlite3.connect(db_path(tmp_path), isolation_level=None) as conn:
        owner = conn.execute(
            "SELECT owner_user_id FROM llm_credential_deposit_owners "
            "WHERE universe_id = ? AND service = ?",
            ("u-owner", "codex"),
        ).fetchone()
        conn.execute("BEGIN IMMEDIATE")
        with pytest.raises(PermissionError, match="credential owner"):
            adopt_llm_subscription_custody(
                conn,
                universe_dir=universe_dir,
                owner_user_id="owner-1",
                universe_id="u-owner",
                service="codex",
            )
        conn.rollback()
    assert owner is None


def test_connect_llm_rejects_uncontained_path_without_echoing_it(
    tmp_path,
    monkeypatch,
    caplog,
):
    import tinyassets.universe_server as server
    from tinyassets.credential_vault import credential_vault_path

    universe_dir = tmp_path / "u-owner"
    universe_dir.mkdir()
    outside = tmp_path / "outside-codex-home"
    outside.mkdir()
    (outside / "auth.json").write_text(
        _codex_auth("outside-secret"), encoding="utf-8"
    )
    _as_actor(monkeypatch, tmp_path, actor="owner-1")

    refused = json.loads(
        server.write_graph(
            target="connection",
            operation="connect_llm",
            graph_id="u-owner",
            payload_json=json.dumps({"service": "codex", "codex_home": str(outside)}),
        )
    )

    assert refused == {"error": "llm_connection_invalid"}
    assert str(outside) not in json.dumps(refused)
    assert str(outside) not in caplog.text
    assert not credential_vault_path(universe_dir).exists()
