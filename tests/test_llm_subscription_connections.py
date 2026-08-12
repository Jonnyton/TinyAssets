from __future__ import annotations

import base64
import json
import sqlite3

import pytest


def _auth_b64(material: str) -> str:
    return base64.b64encode(material.encode()).decode()


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
        ("codex", "codex", '{"tokens":{"access_token":"codex-secret"}}'),
        ("claude", "claude-code", "claude-oauth-secret"),
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
                {"service": "codex", "auth_json_b64": _auth_b64("{}")}
            ),
        )
    )

    assert denied == {"error": "not_found", "resource": "connection"}
    assert not credential_vault_path(universe_dir).exists()


def test_connect_llm_rejects_different_owner_without_overwriting(tmp_path, monkeypatch):
    import tinyassets.universe_server as server
    from tinyassets.credential_vault import load_credential_vault

    universe_dir = tmp_path / "u-owner"
    universe_dir.mkdir()
    _as_actor(monkeypatch, tmp_path, actor="owner-1")
    original = _auth_b64('{"token":"original-secret"}')
    replacement = _auth_b64('{"token":"replacement-secret"}')
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
                {"service": "codex", "auth_json_b64": _auth_b64("{}")}
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
                    "auth_json_b64": _auth_b64("claude-owner-2"),
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
        json.dumps({"service": "claude", "auth_json_b64": _auth_b64("{}")}),
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
                {"service": "codex", "auth_json_b64": _auth_b64("{}")}
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
    (codex_home / "auth.json").write_text('{"token":"path-secret"}', encoding="utf-8")
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
    (outside / "auth.json").write_text('{"token":"outside-secret"}', encoding="utf-8")
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
