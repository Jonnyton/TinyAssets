"""The agent's platform actions: what the token proves, and what it does not.

The token proves WHO is asking. It must never prove that the answer is yes —
the ordinary API ownership check has to keep running, or this route becomes a
way to launder an unauthorised action through the daemon.
"""

from __future__ import annotations

import pytest

from tinyassets import universe_agent_actions as actions
from tinyassets.universe_agent_actions import (
    AgentActionError,
    execute_action,
    mint_turn_token,
    verify_turn_token,
)

KEY = "a" * 44


@pytest.fixture(autouse=True)
def _key(monkeypatch):
    monkeypatch.setenv("TINYASSETS_APP_INGRESS_HMAC_KEY", KEY)


# --------------------------------------------------------------------------
# The token
# --------------------------------------------------------------------------


def test_a_minted_token_round_trips():
    token = mint_turn_token(universe_id="u-a", subject_id="user_1")
    assert verify_turn_token(token) == ("u-a", "user_1")


def test_a_token_without_a_subject_is_refused_at_mint():
    """A subject-less token would authorise as nobody, which is `anonymous`."""
    with pytest.raises(AgentActionError):
        mint_turn_token(universe_id="u-a", subject_id="")
    with pytest.raises(AgentActionError):
        mint_turn_token(universe_id="", subject_id="user_1")


def test_an_expired_token_is_refused():
    token = mint_turn_token(universe_id="u-a", subject_id="user_1", ttl_seconds=10,
                            now=1_000_000)
    with pytest.raises(AgentActionError):
        verify_turn_token(token, now=1_000_011)
    # And is still good before it expires — otherwise this passes with the
    # whole feature broken.
    assert verify_turn_token(token, now=1_000_009) == ("u-a", "user_1")


def test_a_tampered_payload_is_refused():
    token = mint_turn_token(universe_id="u-a", subject_id="user_1")
    body, _, signature = token.partition(".")
    forged = mint_turn_token(universe_id="u-victim", subject_id="user_1")
    forged_body = forged.partition(".")[0]
    with pytest.raises(AgentActionError):
        verify_turn_token(f"{forged_body}.{signature}")
    assert body != forged_body


def test_a_token_signed_for_the_chat_ingress_does_not_verify_here():
    """Domain separation. The same key signs both; the purposes must not cross."""
    from tinyassets.app_ingress_http import sign

    payload = mint_turn_token(universe_id="u-a", subject_id="user_1").partition(".")[0]
    crossed = sign(payload.encode("utf-8"), "0", KEY.encode("utf-8"))
    with pytest.raises(AgentActionError):
        verify_turn_token(f"{payload}.{crossed}")


@pytest.mark.parametrize("bad", ["", "   ", "nodot", "a.b", "....", "x." + "0" * 64])
def test_malformed_tokens_are_refused(bad):
    with pytest.raises(AgentActionError):
        verify_turn_token(bad)


def test_every_refusal_reads_the_same():
    """A caller that can tell expired from forged can probe the format."""
    expired = mint_turn_token(universe_id="u-a", subject_id="s", ttl_seconds=1,
                              now=1_000_000)
    messages = set()
    for token, now in ((expired, 1_000_099), ("garbage.beef", None)):
        try:
            verify_turn_token(token, now=now)
        except AgentActionError as exc:
            messages.add(str(exc))
    assert len(messages) == 1, messages


# --------------------------------------------------------------------------
# The action
# --------------------------------------------------------------------------


def test_the_universe_comes_from_the_token_not_the_payload(monkeypatch):
    """A caller that can name the universe can aim at someone else's."""
    seen: dict = {}

    def _fake(**kwargs):
        seen.update(kwargs)
        return {"ok": True}

    monkeypatch.setattr("tinyassets.api.cloud_automations.cloud_automations", _fake)
    token = mint_turn_token(universe_id="u-mine", subject_id="user_1")
    execute_action(
        token=token, surface="automation", action="list",
        payload={"universe_id": "u-victim"},
    )
    assert seen["universe_id"] == "u-mine"


def test_an_action_outside_the_allowlist_is_refused(monkeypatch):
    called = []
    monkeypatch.setattr(
        "tinyassets.api.cloud_automations.cloud_automations",
        lambda **k: called.append(k) or {},
    )
    token = mint_turn_token(universe_id="u-a", subject_id="user_1")
    with pytest.raises(AgentActionError, match="unsupported automation action"):
        execute_action(token=token, surface="automation", action="delete_everything")
    assert called == []


def test_an_unknown_surface_is_refused():
    token = mint_turn_token(universe_id="u-a", subject_id="user_1")
    with pytest.raises(AgentActionError, match="unsupported surface"):
        execute_action(token=token, surface="billing", action="list")


def test_the_allowed_actions_actually_reach_the_api(monkeypatch):
    """The ACCEPT direction. An allowlist that refuses everything passes the
    refusal tests above while making the feature useless."""
    seen = []
    monkeypatch.setattr(
        "tinyassets.api.cloud_automations.cloud_automations",
        lambda **k: seen.append(k["action"]) or {"ok": True},
    )
    token = mint_turn_token(universe_id="u-a", subject_id="user_1")
    for action in sorted(actions.AUTOMATION_ACTIONS):
        execute_action(token=token, surface="automation", action=action)
    assert seen == sorted(actions.AUTOMATION_ACTIONS)


def test_the_identity_is_bound_for_the_call(monkeypatch):
    from tinyassets.api import permissions

    observed = {}

    def _fake(**kwargs):
        observed["actor"] = permissions.current_actor_id()
        observed["authenticated"] = permissions.is_authenticated_request()
        return {}

    monkeypatch.setattr("tinyassets.api.cloud_automations.cloud_automations", _fake)
    token = mint_turn_token(universe_id="u-a", subject_id="user_founder")
    execute_action(token=token, surface="automation", action="list")
    assert observed["actor"] == "user_founder"
    assert observed["authenticated"] is True


def test_the_identity_does_not_leak_past_the_call(monkeypatch):
    """A leaked identity would make the NEXT request run as this founder."""
    from tinyassets.api import permissions

    def _boom(**kwargs):
        raise RuntimeError("api exploded")

    monkeypatch.setattr("tinyassets.api.cloud_automations.cloud_automations", _boom)
    token = mint_turn_token(universe_id="u-a", subject_id="user_founder")
    before = permissions.current_actor_id()
    with pytest.raises(RuntimeError):
        execute_action(token=token, surface="automation", action="list")
    assert permissions.current_actor_id() == before == "anonymous"


def test_the_api_ownership_check_still_runs(tmp_path, monkeypatch):
    """The token says WHO, never that the answer is yes.

    Binding an identity the universe does not belong to must be refused by the
    ordinary API check — otherwise this route launders unauthorised actions.
    """
    from tinyassets.daemon_server import initialize_author_server

    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
    initialize_author_server(str(tmp_path))

    token = mint_turn_token(universe_id="u-not-mine", subject_id="user_stranger")
    result = execute_action(token=token, surface="automation", action="list")
    # `_not_found()` — the API refuses a non-owner rather than listing.
    assert "error" in result or not result.get("automations")


def test_the_connection_surface_reaches_the_api(monkeypatch):
    """Enrolling compute and authorizing GitHub are the automation prerequisites.

    Without these the agent can SEE it is blocked and do nothing about it, which
    is exactly the complaint `owner-operable-automation` records: "I can request
    state changes but I can't spin one up myself."
    """
    seen = []
    monkeypatch.setattr(
        "tinyassets.api.cloud_connections.cloud_connections",
        lambda **k: seen.append(k["action"]) or {"ok": True},
    )
    token = mint_turn_token(universe_id="u-a", subject_id="user_1")
    for action in sorted(actions.CONNECTION_ACTIONS):
        execute_action(token=token, surface="connection", action=action)
    assert seen == sorted(actions.CONNECTION_ACTIONS)


def test_an_unknown_connection_action_is_refused(monkeypatch):
    called = []
    monkeypatch.setattr(
        "tinyassets.api.cloud_connections.cloud_connections",
        lambda **k: called.append(k) or {},
    )
    token = mint_turn_token(universe_id="u-a", subject_id="user_1")
    with pytest.raises(AgentActionError, match="unsupported connection action"):
        execute_action(token=token, surface="connection", action="revoke_everything")
    assert called == []


def test_bind_provider_is_reachable(monkeypatch):
    """The prerequisite the agent must be able to satisfy itself."""
    seen = []
    monkeypatch.setattr(
        "tinyassets.api.cloud_automations.cloud_automations",
        lambda **k: seen.append(k["action"]) or {"ok": True},
    )
    token = mint_turn_token(universe_id="u-a", subject_id="user_1")
    execute_action(token=token, surface="automation", action="bind_provider",
                   payload={"payload": {"provider": "claude-code"}})
    assert seen == ["bind_provider"]


def test_the_connection_surface_uses_the_token_universe(monkeypatch):
    seen: dict = {}
    monkeypatch.setattr(
        "tinyassets.api.cloud_connections.cloud_connections",
        lambda **k: seen.update(k) or {},
    )
    token = mint_turn_token(universe_id="u-mine", subject_id="user_1")
    execute_action(token=token, surface="connection", action="list",
                   payload={"universe_id": "u-victim"})
    assert seen["universe_id"] == "u-mine"


def test_branch_versions_are_scoped_to_the_token_subject(tmp_path, monkeypatch):
    """Discovery must not leak another publisher's branch versions.

    The subject comes from the TOKEN; a caller supplying a publisher must not
    be able to widen the result.
    """
    import sqlite3

    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
    con = sqlite3.connect(tmp_path / ".runs.db")
    con.execute(
        "CREATE TABLE branch_versions (branch_version_id TEXT, branch_def_id TEXT,"
        " content_hash TEXT, snapshot_json TEXT, notes TEXT, publisher TEXT,"
        " published_at REAL, parent_version_id TEXT, status TEXT,"
        " rolled_back_at REAL, rolled_back_by TEXT, rolled_back_reason TEXT,"
        " watch_window_seconds INTEGER)"
    )
    con.executemany(
        "INSERT INTO branch_versions (branch_version_id, branch_def_id, notes,"
        " publisher, published_at, status) VALUES (?,?,?,?,?,?)",
        [
            ("mine@aaaa", "mine", "ok", "user_me", 2.0, "published"),
            ("theirs@bbbb", "theirs", "secret", "user_other", 3.0, "published"),
        ],
    )
    con.commit()
    con.close()

    token = mint_turn_token(universe_id="u-a", subject_id="user_me")
    result = execute_action(
        token=token, surface="branch", action="list_versions",
        payload={"publisher": "user_other"},
    )
    ids = [v["branch_version_id"] for v in result["branch_versions"]]
    assert ids == ["mine@aaaa"], ids
    assert result["count"] == 1


def test_an_unknown_branch_action_is_refused():
    token = mint_turn_token(universe_id="u-a", subject_id="user_me")
    with pytest.raises(AgentActionError, match="unsupported branch action"):
        execute_action(token=token, surface="branch", action="delete_version")


def test_capabilities_are_granted_per_action_not_blanket(monkeypatch):
    """A turn gets exactly the scopes its action needs, and nothing more.

    Capabilities normally come from the founder's OAuth grant; this turn has
    none, so every scope here is one we chose to confer. A blanket list would
    silently widen as new actions are added.
    """
    from tinyassets.api import permissions
    from tinyassets.auth import middleware

    seen = {}

    def _capture(**kwargs):
        seen[kwargs.get("action")] = list(middleware.current_identity().capabilities)
        return {}

    monkeypatch.setattr("tinyassets.api.cloud_automations.cloud_automations", _capture)
    token = mint_turn_token(universe_id="u-a", subject_id="user_1")
    execute_action(token=token, surface="automation", action="list")
    assert seen["list"] == [], "a read action was handed capabilities"
    assert permissions.current_actor_id() == "anonymous"


def _run_with_declared_operations(monkeypatch, operations):
    """Run a branch with a stubbed provider binding declaring *operations*."""
    from tinyassets.auth import middleware

    class _Binding:
        allowed_operations = tuple(operations or ())

    class _Store:
        def __init__(self, *a, **k):
            pass

        def list_bindings(self, **kwargs):
            return [_Binding()] if operations is not None else []

    monkeypatch.setattr(
        "tinyassets.storage.provider_work_authority."
        "SQLiteProviderWorkAuthorityStore", _Store,
    )
    # Consent is a separate gate and fires FIRST. These tests are about the
    # capability derivation, so grant it and let them get that far.
    monkeypatch.setattr(
        "tinyassets.storage.action_approvals.ActionApprovalStore."
        "consume_if_granted", lambda self, **kwargs: True,
    )
    seen = {}
    monkeypatch.setattr(
        "tinyassets.universe_server.run_graph",
        lambda **k: seen.update(
            caps=list(middleware.current_identity().capabilities)
        ) or "{}",
    )
    token = mint_turn_token(universe_id="u-a", subject_id="user_1")
    execute_action(token=token, surface="branch", action="run",
                   payload={"branch_def_id": "abc"})
    return seen["caps"]


def test_a_declared_operation_confers_its_scope(monkeypatch):
    """The ACCEPT direction — the owner declared it, so the run may spend it."""
    caps = _run_with_declared_operations(monkeypatch, ["repository_spec_delivery"])
    assert "tinyassets.extensions.costly" in caps


def test_an_automation_cannot_borrow_another_kind_of_authority(monkeypatch):
    """Different automations do different work and carry different capabilities.

    A binding declared for some other operation must NOT confer the costly
    scope — otherwise the platform, not the owner, decides what every automation
    may spend. Host correction 2026-08-07.
    """
    caps = _run_with_declared_operations(monkeypatch, ["some_other_operation"])
    assert caps == []


def test_no_declared_binding_confers_nothing(monkeypatch):
    caps = _run_with_declared_operations(monkeypatch, None)
    assert caps == []


def test_a_costly_action_needs_consent_before_authority_matters(monkeypatch):
    """"Are you allowed" and "are you sure" are different questions.

    Running a branch spends the founder's own compute and can open a pull
    request. Nothing asked before this existed.
    """
    called = []
    monkeypatch.setattr(
        "tinyassets.universe_server.run_graph",
        lambda **k: called.append(k) or "{}",
    )
    token = mint_turn_token(universe_id="u-a", subject_id="user_1")
    with pytest.raises(AgentActionError, match="go-ahead"):
        execute_action(token=token, surface="branch", action="run",
                       payload={"branch_def_id": "abc"})
    assert called == [], "it ran without asking"


def test_consent_is_keyed_to_the_thing_being_approved(monkeypatch):
    """Yes to one branch must not be yes to a different one."""
    from tinyassets.universe_agent_actions import _approval_key

    safe = _approval_key("branch", "run", {"branch_def_id": "safe123"})
    risky = _approval_key("branch", "run", {"branch_def_id": "repo999"})
    assert safe != risky
    assert "safe123" in safe
