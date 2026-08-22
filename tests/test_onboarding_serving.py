"""Connect in the app must make the universe SERVE, not just hold a credential.

Live phone test 2026-08-21: the OpenAI credential was deposited, yet every turn
still failed with "exactly one founder serving binding is required". These run
the REAL custom-agent + serving modules against a temp base path (same chain
the served-router tests use) — no mocks of the authority layer.
"""

from __future__ import annotations

import pytest

from tinyassets.onboarding import serving as sv


def _seed(tmp_path, service="codex", owner="owner-1", uid="u-owner"):
    from tinyassets.credential_vault import write_credential_vault

    udir = tmp_path / uid
    udir.mkdir(exist_ok=True)
    cred = (
        {"credential_type": "llm_subscription", "service": "codex", "auth_json_b64": "e30="}
        if service == "codex"
        else {"credential_type": "llm_subscription", "service": "claude", "oauth_token": "sk-ant-x"}
    )
    write_credential_vault(udir, [cred], owner_user_id=owner, universe_id=uid)
    return udir


def _serving_binding(tmp_path, uid="u-owner", owner="owner-1"):
    from tinyassets.provider_serving_binding import resolve_serving_agent_binding

    return resolve_serving_agent_binding(tmp_path, universe_id=uid, owner_user_id=owner)


def test_fresh_universe_gets_definition_binding_and_serving(tmp_path):
    udir = _seed(tmp_path)
    out = sv.ensure_founder_serving(
        base_path=tmp_path,
        universe_dir=udir,
        owner_user_id="owner-1",
        universe_id="u-owner",
        service="codex",
    )
    assert out["status"] == "serving" and out["provider"] == "codex"
    # The exact check converse performs now passes.
    b = _serving_binding(tmp_path)
    assert b["agent_binding_id"] == out["agent_binding_id"]
    assert b["created_by"] == "owner-1" and b["status"] == "serving"


def test_idempotent_and_reuses_the_founders_binding(tmp_path):
    from tinyassets.custom_agents import list_bindings, list_definitions

    udir = _seed(tmp_path)
    first = sv.ensure_founder_serving(
        base_path=tmp_path,
        universe_dir=udir,
        owner_user_id="owner-1",
        universe_id="u-owner",
        service="codex",
    )
    second = sv.ensure_founder_serving(
        base_path=tmp_path,
        universe_dir=udir,
        owner_user_id="owner-1",
        universe_id="u-owner",
        service="codex",
    )
    assert second["status"] == "serving"
    assert second["agent_binding_id"] == first["agent_binding_id"]
    assert len(list_bindings(tmp_path, universe_id="u-owner", limit=100)) == 1
    # exactly one platform definition, however many founders connect
    defs = [
        d
        for d in list_definitions(tmp_path, limit=100)
        if d.get("author_id") == sv.PLATFORM_DEFINITION_AUTHOR
    ]
    assert len(defs) == 1
    assert _serving_binding(tmp_path)["status"] == "serving"


def test_anonymous_or_missing_universe_is_held_not_raised(tmp_path):
    assert (
        sv.ensure_founder_serving(
            base_path=tmp_path,
            universe_dir=tmp_path,
            owner_user_id="anonymous",
            universe_id="u-owner",
            service="codex",
        )["status"]
        == "held"
    )
    assert sv.ensure_founder_serving(
        base_path=tmp_path,
        universe_dir=tmp_path,
        owner_user_id="owner-1",
        universe_id="u-owner",
        service="gemini",
    ) == {"status": "held", "reason": "unsupported_service"}


def test_claude_serving_refusal_is_reported_not_raised(tmp_path, monkeypatch):
    """Claude serving is held by default (operator opt-in). The deposit must
    still be reported as a success with the serving outcome alongside."""
    monkeypatch.delenv("TINYASSETS_ALLOW_CLAUDE_SERVING", raising=False)
    udir = _seed(tmp_path, service="claude")
    out = sv.ensure_founder_serving(
        base_path=tmp_path,
        universe_dir=udir,
        owner_user_id="owner-1",
        universe_id="u-owner",
        service="claude",
    )
    assert out["status"] == "held" and out["reason"] in (
        "provider_authority_denied",
        "binding_invalid",
    )
    with pytest.raises(PermissionError):
        _serving_binding(tmp_path)


def test_other_users_binding_is_not_hijacked(tmp_path):
    """A collaborator's binding in the same universe is never re-pointed; the
    founder gets their own."""
    from tinyassets.custom_agents import create_binding, publish_definition

    udir = _seed(tmp_path)
    d = publish_definition(
        tmp_path,
        author_id="someone-else",
        payload={
            "schema_version": 1,
            "name": "Other",
            "description": "",
            "tags": [],
            "components": {"identity": {"kind": "soul", "config": {}}},
        },
    )
    other = create_binding(
        tmp_path,
        universe_id="u-owner",
        definition_id=d["agent_definition_id"],
        created_by="someone-else",
        payload={"schema_version": 1, "name": "Other", "role": "writer"},
    )
    out = sv.ensure_founder_serving(
        base_path=tmp_path,
        universe_dir=udir,
        owner_user_id="owner-1",
        universe_id="u-owner",
        service="codex",
    )
    assert out["status"] == "serving" and out["agent_binding_id"] != other["agent_binding_id"]
