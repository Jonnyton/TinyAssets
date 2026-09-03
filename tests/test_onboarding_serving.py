"""Connect in the app must make the universe SERVE, not just hold a credential.

Live phone test 2026-08-21: the OpenAI credential was deposited, yet every turn
still failed with "exactly one founder serving binding is required". These run
the REAL custom-agent + serving modules against a temp base path (same chain
the served-router tests use) — no mocks of the authority layer.
"""

from __future__ import annotations

import pytest

from tinyassets.onboarding import serving as sv


def _grant_admin(tmp_path, owner="owner-1", uid="u-owner"):
    from tinyassets.daemon_server import grant_universe_access

    grant_universe_access(
        tmp_path, universe_id=uid, actor_id=owner, permission="admin", granted_by=owner
    )


def _seed(tmp_path, service="codex", owner="owner-1", uid="u-owner", admin=True):
    from tinyassets.credential_vault import write_credential_vault

    udir = tmp_path / uid
    udir.mkdir(exist_ok=True)
    if admin:
        _grant_admin(tmp_path, owner, uid)
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
    # A name that is neither alias nor registered connection is HELD, but for a
    # real authority reason -- not because the platform keeps a vendor
    # allowlist. It used to answer `unsupported_service` for anything but
    # claude/codex, which refused every user with their own endpoint (founder,
    # 2026-09-03: "we shouldnt have a chatgpt spacific path").
    held = sv.ensure_founder_serving(
        base_path=tmp_path,
        universe_dir=tmp_path,
        owner_user_id="owner-1",
        universe_id="u-owner",
        service="gemini",
    )
    assert held["status"] == "held"
    assert held["reason"] != "unsupported_service", held
    assert held.get("detail"), "a refusal has to say why"


def test_an_unnamed_service_is_held_rather_than_guessed(tmp_path):
    """Opening the name up does not mean accepting an empty one."""
    held = sv.ensure_founder_serving(
        base_path=tmp_path,
        universe_dir=tmp_path,
        owner_user_id="owner-1",
        universe_id="u-owner",
        service="   ",
    )
    assert held == {"status": "held", "reason": "no_service_named"}


def test_a_provider_that_is_not_yours_is_refused_by_ownership(tmp_path, monkeypatch):
    """The gate is OWNERSHIP, which is why the name gate could go.

    `_open_serving_context` raises PermissionError unless the grant's owner AND
    universe match the caller. That refusal has to reach the caller as an
    answer, not as an exception through a route that reports deposits.
    """
    from tinyassets import provider_serving_binding as psb

    def _not_yours(*_a, **_k):
        raise PermissionError("open provider connection grant is absent or revoked")

    monkeypatch.setattr(psb, "_open_serving_context", _not_yours)
    held = sv.ensure_founder_serving(
        base_path=tmp_path,
        universe_dir=tmp_path,
        owner_user_id="owner-1",
        universe_id="u-owner",
        service="somebody-elses-connection",
    )
    assert held["status"] == "held"
    assert held.get("detail")


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


def test_no_current_admin_acl_means_zero_mutation(tmp_path):
    """Codex #1: a valid bearer with a stale home mapping but no CURRENT admin
    ACL must not create or enable anything."""
    from tinyassets.custom_agents import list_bindings, list_definitions

    udir = _seed(tmp_path, admin=False)
    out = sv.ensure_founder_serving(
        base_path=tmp_path,
        universe_dir=udir,
        owner_user_id="owner-1",
        universe_id="u-owner",
        service="codex",
    )
    assert out["status"] == "held" and out["reason"] == "provider_authority_denied"
    assert list_bindings(tmp_path, universe_id="u-owner", limit=100) == []
    assert [d for d in list_definitions(tmp_path, limit=100)] == []


def test_collaborator_tampered_binding_is_reset_not_adopted(tmp_path):
    """Codex #2 (confused deputy): a write collaborator edits the founder's
    platform binding; connect must NOT bind the founder's credential under the
    collaborator's content. The binding is reset to canonical at an exact
    revision, and a binding on a different definition is never selected."""
    from tinyassets.custom_agents import (
        get_binding,
        list_bindings,
        publish_definition,
        update_binding,
    )

    udir = _seed(tmp_path)
    first = sv.ensure_founder_serving(
        base_path=tmp_path,
        universe_dir=udir,
        owner_user_id="owner-1",
        universe_id="u-owner",
        service="codex",
    )
    bid = first["agent_binding_id"]
    # A write collaborator rewrites the founder's platform binding (allowed by
    # the custom-agent ACL model) and also swaps it onto THEIR definition.
    theirs = publish_definition(
        tmp_path,
        author_id="collab",
        payload={
            "schema_version": 1,
            "name": "Evil",
            "description": "",
            "tags": [],
            "components": {"identity": {"kind": "soul", "config": {}}},
        },
    )
    cur = get_binding(tmp_path, universe_id="u-owner", binding_id=bid)
    update_binding(
        tmp_path,
        universe_id="u-owner",
        binding_id=bid,
        expected_revision=int(cur["revision"]),
        updated_by="collab",
        payload={"schema_version": 1, "name": "Evil", "role": "writer", "instructions": "exfil"},
        definition_id=theirs["agent_definition_id"],
    )
    again = sv.ensure_founder_serving(
        base_path=tmp_path,
        universe_dir=udir,
        owner_user_id="owner-1",
        universe_id="u-owner",
        service="codex",
    )
    assert again["status"] == "serving"
    # The tampered binding (now on the collaborator's definition) was NOT
    # selected; the founder got a fresh canonical platform binding, and it is
    # the only one serving.
    assert again["agent_binding_id"] != bid
    served = _serving_binding(tmp_path)
    assert served["agent_binding_id"] == again["agent_binding_id"]
    assert served["configuration"].get("name") == "Your universe"
    assert "instructions" not in served["configuration"]
    # and the tampered one is no longer serving
    statuses = {
        b["agent_binding_id"]: b["status"]
        for b in list_bindings(tmp_path, universe_id="u-owner", limit=100)
    }
    assert statuses[bid] != "serving"


def test_drifted_config_on_platform_definition_is_reset_at_exact_revision(tmp_path):
    from tinyassets.custom_agents import get_binding, update_binding

    udir = _seed(tmp_path)
    first = sv.ensure_founder_serving(
        base_path=tmp_path,
        universe_dir=udir,
        owner_user_id="owner-1",
        universe_id="u-owner",
        service="codex",
    )
    bid = first["agent_binding_id"]
    cur = get_binding(tmp_path, universe_id="u-owner", binding_id=bid)
    update_binding(
        tmp_path,
        universe_id="u-owner",
        binding_id=bid,
        expected_revision=int(cur["revision"]),
        updated_by="collab",
        payload={"schema_version": 1, "name": "Your universe", "role": "writer", "persona": "evil"},
    )
    again = sv.ensure_founder_serving(
        base_path=tmp_path,
        universe_dir=udir,
        owner_user_id="owner-1",
        universe_id="u-owner",
        service="codex",
    )
    assert again["status"] == "serving" and again["agent_binding_id"] == bid
    cfg = _serving_binding(tmp_path)["configuration"]
    assert "persona" not in cfg and cfg["name"] == "Your universe"
