"""X posting from conversation: consent-gated grants + engagement feedback.

The `twitter_post` effector existed with three locks (soul authority,
effector consent, credentials) and NO user-facing way to arm any of them —
and nothing anywhere read a published post back. These tests pin the two
new primitives: a founder-consented `effector.grant` that the effector's
existing consent gate actually reads, and `posts.engagement`, the feedback
signal, honest in every no-data shape.
"""

from __future__ import annotations

import pytest

from tinyassets.universe_agent_actions import (
    AgentActionError,
    execute_action,
    mint_turn_token,
)

KEY = "a" * 44


@pytest.fixture(autouse=True)
def _key(monkeypatch):
    monkeypatch.setenv("TINYASSETS_APP_INGRESS_HMAC_KEY", KEY)


@pytest.fixture
def base(tmp_path, monkeypatch):
    from tinyassets.daemon_server import initialize_author_server

    initialize_author_server(str(tmp_path))
    (tmp_path / "u-a").mkdir(exist_ok=True)
    monkeypatch.setattr("tinyassets.api.helpers._base_path", lambda: tmp_path)
    return tmp_path


def _token():
    return mint_turn_token(universe_id="u-a", subject_id="user_1")


GRANT = {"sink": "twitter_post", "destination": "@myhandle"}


# -- consent grant: gated, exact, revocable ---------------------------------

def test_granting_posting_consent_requires_the_founders_yes(base):
    """Publishing in the founder's name must not be self-authorizable."""
    with pytest.raises(AgentActionError, match="go-ahead"):
        execute_action(token=_token(), surface="effector", action="grant",
                       payload=dict(GRANT))
    listed = execute_action(token=_token(), surface="approval", action="list",
                            payload={})
    assert [p["action_key"] for p in listed["pending"]] == [
        "effector.grant:twitter_post:myhandle"
    ]


def test_granted_consent_is_what_the_post_effector_reads(base):
    """The decisive test: the conversational grant lands in the SAME store
    the twitter_post effector's consent gate checks at publish time."""
    from tinyassets.storage.action_approvals import ActionApprovalStore
    from tinyassets.storage.effector_consents import is_consent_active

    ActionApprovalStore(base).decide(
        universe_id="u-a",
        action_key="effector.grant:twitter_post:myhandle",
        granted=True, decided_by="user_1",
    )
    result = execute_action(token=_token(), surface="effector", action="grant",
                            payload=dict(GRANT))
    assert result["destination"] == "@myhandle"
    assert is_consent_active(
        base / "u-a", sink="twitter_post", destination="@myhandle"
    )


def test_destination_is_normalized_to_the_at_handle_form(base):
    from tinyassets.storage.action_approvals import ActionApprovalStore
    from tinyassets.storage.effector_consents import is_consent_active

    # The URL form normalizes to the SAME approval key as the @handle form,
    # so an ask armed with the bare handle still matches a URL-form retry.
    payload = {"sink": "twitter_post", "destination": "https://x.com/myhandle"}
    ActionApprovalStore(base).decide(
        universe_id="u-a",
        action_key="effector.grant:twitter_post:myhandle",
        granted=True, decided_by="user_1",
    )
    result = execute_action(token=_token(), surface="effector", action="grant",
                            payload=payload)
    assert result["destination"] == "@myhandle"
    assert is_consent_active(
        base / "u-a", sink="twitter_post", destination="@myhandle"
    )


def test_revoke_needs_no_approval_and_stops_the_gate(base):
    """When the founder says stop, it stops — narrowing is never gated."""
    from tinyassets.storage.effector_consents import (
        grant_consent,
        is_consent_active,
    )

    grant_consent(base / "u-a", sink="twitter_post", destination="@myhandle",
                  granted_by="user_1")
    result = execute_action(token=_token(), surface="effector", action="revoke",
                            payload=dict(GRANT))
    assert result["revoked"] is True
    assert not is_consent_active(
        base / "u-a", sink="twitter_post", destination="@myhandle"
    )


def test_unknown_sinks_are_refused(base):
    with pytest.raises(AgentActionError, match="unknown posting sink"):
        execute_action(token=_token(), surface="effector", action="grant",
                       payload={"sink": "carrier_pigeon", "destination": "@x"})


def test_consent_is_keyed_per_destination():
    """Yes to one handle must not be yes to another."""
    from tinyassets.universe_agent_actions import _approval_key

    mine = _approval_key("effector", "grant", dict(GRANT))
    other = _approval_key(
        "effector", "grant",
        {"sink": "twitter_post", "destination": "@someoneelse"},
    )
    assert mine != other
    assert "twitter_post:myhandle" in mine


# -- engagement: the feedback signal ----------------------------------------

def _finalize_post_receipt(universe_dir, *, post_id, run_id="r1"):
    from tinyassets.storage.external_write_receipts import (
        finalize_receipt,
        try_reserve_receipt,
    )

    hint = f"hint_{post_id}"
    try_reserve_receipt(universe_dir, idempotency_hint=hint,
                        sink="twitter_post", run_id=run_id)
    finalize_receipt(
        universe_dir, idempotency_hint=hint, sink="twitter_post",
        evidence={
            "post_id": post_id,
            "post_url": f"https://x.com/myhandle/status/{post_id}",
            "destination": "@myhandle",
            "recorded_at": 1000.0,
        },
        run_id=run_id,
    )


def test_no_posts_yet_is_an_honest_empty(base):
    result = execute_action(token=_token(), surface="posts",
                            action="engagement", payload={})
    assert result["posts"] == []
    assert "no real posts" in result["note"]


def test_missing_credentials_is_a_structured_refusal_not_a_guess(base):
    _finalize_post_receipt(base / "u-a", post_id="111")
    result = execute_action(token=_token(), surface="posts",
                            action="engagement", payload={})
    assert result["error_kind"] == "missing_credentials"
    # The receipts we DO have still come back, so the agent can say what
    # exists even when metrics are unreachable.
    assert [p["post_id"] for p in result["posts_awaiting_metrics"]] == ["111"]


def test_metrics_are_joined_onto_receipts(base, monkeypatch):
    from tinyassets import x_engagement

    _finalize_post_receipt(base / "u-a", post_id="111", run_id="rA")
    _finalize_post_receipt(base / "u-a", post_id="222", run_id="rB")
    monkeypatch.setattr(
        x_engagement, "_fetch_metrics",
        lambda ids, *, handle, destination, universe_dir=None: {
            "data": [
                {"id": "111", "text": "hello", "created_at": "2026-08-08",
                 "public_metrics": {"like_count": 4, "reply_count": 1}},
            ]
        },
    )
    result = x_engagement.read_engagement(base / "u-a")
    by_id = {p["post_id"]: p for p in result["posts"]}
    assert by_id["111"]["metrics"] == {"like_count": 4, "reply_count": 1}
    assert by_id["111"]["text"] == "hello"
    # A post X no longer returns keeps its receipt with metrics=None —
    # a vanished post is itself signal, not an omission.
    assert by_id["222"]["metrics"] is None


def test_dry_run_receipts_are_not_posts(base):
    """Reservations and dry-run evidence carry no post_id — nothing was
    published, so nothing must be measured."""
    from tinyassets.storage.external_write_receipts import try_reserve_receipt

    try_reserve_receipt(base / "u-a", idempotency_hint="h1",
                        sink="twitter_post", run_id="r1")
    result = execute_action(token=_token(), surface="posts",
                            action="engagement", payload={})
    assert result["posts"] == []


# -- the node-level alias ----------------------------------------------------

def test_branch_nodes_can_name_the_engagement_read():
    from tinyassets.graph_compiler import _NODE_MCP_ACTION_ALIASES

    assert _NODE_MCP_ACTION_ALIASES["posts.engagement"] == ("posts", "engagement")
    assert _NODE_MCP_ACTION_ALIASES["post_engagement"] == ("posts", "engagement")


# -- vault-first credentials --------------------------------------------------

def _vault_record(**over):
    record = {
        "credential_type": "social", "service": "twitter",
        "destination": "@myhandle",
        "api_key": "k", "api_secret": "s",
        "access_token": "t", "access_token_secret": "ts",
    }
    record.update(over)
    return record


def test_deposited_twitter_credentials_resolve_for_their_exact_destination(tmp_path):
    from tinyassets.credential_vault import (
        resolve_twitter_credentials,
        write_credential_vault,
    )

    write_credential_vault(tmp_path, [_vault_record()])
    assert resolve_twitter_credentials(tmp_path, "@myhandle") == {
        "api_key": "k", "api_secret": "s",
        "access_token": "t", "access_token_secret": "ts",
    }
    # Exact destination discipline — a deposit for one account never serves
    # a post aimed at another.
    assert resolve_twitter_credentials(tmp_path, "@other") is None


def test_partial_vault_record_resolves_to_none_not_a_partial(tmp_path):
    """Three-quarters of a credential signs nothing — refuse, don't guess."""
    from tinyassets.credential_vault import (
        resolve_twitter_credentials,
        write_credential_vault,
    )

    write_credential_vault(tmp_path, [_vault_record(access_token_secret="")])
    assert resolve_twitter_credentials(tmp_path, "@myhandle") is None


def test_effector_prefers_the_vault_over_env(tmp_path, monkeypatch):
    from tinyassets.credential_vault import write_credential_vault
    from tinyassets.effectors.twitter_post import _resolve_credentials

    monkeypatch.setenv("TWITTER_API_KEY", "envk")
    monkeypatch.setenv("TWITTER_API_SECRET", "envs")
    monkeypatch.setenv("TWITTER_ACCESS_TOKEN", "envt")
    monkeypatch.setenv("TWITTER_ACCESS_TOKEN_SECRET", "envts")
    write_credential_vault(tmp_path, [_vault_record()])
    resolved = _resolve_credentials(
        handle="@myhandle", destination="@myhandle", universe_dir=tmp_path
    )
    assert resolved is not None
    assert resolved.source == "vault"
    assert resolved.api_key == "k"
    # No vault record for this destination -> the env fallback still works.
    env_resolved = _resolve_credentials(
        handle="@other", destination="@other", universe_dir=tmp_path
    )
    assert env_resolved is not None
    assert env_resolved.source == "default"


# -- platform-assembled packets ----------------------------------------------

class _Node:
    def __init__(self, handoffs):
        self.node_id = "publish"
        self.output_keys = ["post_text"]
        self.effects = ["twitter_post"]
        self.handoffs = handoffs


_DECLARATION = {
    "output_field": "post_text", "adapter": "twitter_post",
    "adapter_action": "post", "destination": "myhandle",
    "effect_class": "irreversible", "outcome_kind": "published_post",
}


def test_branch_build_carries_handoffs_through_the_funnel(base):
    """Found live: the create funnel dropped `handoffs` silently, so the
    dispatcher had no declaration to assemble from. The build must store it
    and reject a malformed one with an actionable message."""
    import json as _json

    good = execute_action(token=_token(), surface="branch", action="build",
                          payload={"spec_json": _json.dumps({
                              "name": "handoff_carry_check",
                              "description": "d",
                              "entry_point": "publish",
                              "nodes": [{
                                  "node_id": "publish",
                                  "display_name": "P",
                                  "output_keys": ["post_text"],
                                  "effects": ["twitter_post"],
                                  "handoffs": [dict(_DECLARATION)],
                                  "prompt_template": "Write a line.",
                              }],
                              "edges": [{"from": "publish", "to": "END"}],
                          })})
    branch_id = good.get("branch_def_id") or good.get("id")
    assert branch_id, good
    read = execute_action(token=_token(), surface="branch", action="read",
                          payload={"branch_def_id": branch_id})
    nodes = read.get("nodes") or read.get("node_defs") or []
    stored = next(n for n in nodes if n.get("node_id") == "publish")
    assert stored.get("handoffs"), "the funnel dropped the declaration again"

    bad = execute_action(token=_token(), surface="branch", action="build",
                         payload={"spec_json": _json.dumps({
                             "name": "handoff_bad_check",
                             "description": "d",
                             "entry_point": "publish",
                             "nodes": [{
                                 "node_id": "publish",
                                 "display_name": "P",
                                 "output_keys": ["post_text"],
                                 "handoffs": [{"output_field": "post_text"}],
                                 "prompt_template": "Write a line.",
                             }],
                             "edges": [{"from": "publish", "to": "END"}],
                         })})
    assert "handoffs invalid" in str(bad)


def test_packet_is_assembled_from_the_declaration_not_the_llm():
    """The LLM writes prose; the immutable declaration names the destination.
    Live 2026-08-08: prompting a node to emit packet JSON was refused twice —
    the model reads byte-exact write payloads as injection."""
    from tinyassets.effectors.twitter_post import packet_from_handoffs

    packet = packet_from_handoffs(
        _Node([_DECLARATION]), {"post_text": "shipped the slack agent"}
    )
    assert packet == {
        "sink": "twitter_post",
        "destination": "@myhandle",
        "payload": {"text": "shipped the slack agent"},
    }


def test_no_declaration_or_no_text_assembles_nothing():
    from tinyassets.effectors.twitter_post import packet_from_handoffs

    assert packet_from_handoffs(_Node([]), {"post_text": "x"}) is None
    assert packet_from_handoffs(_Node([_DECLARATION]), {"post_text": ""}) is None
    other = dict(_DECLARATION, adapter="github_pr")
    assert packet_from_handoffs(_Node([other]), {"post_text": "x"}) is None


def test_dispatcher_falls_back_to_handoff_assembly(base):
    """End to end through run_effects_for_branch: a node whose output is
    plain prose still reaches the effector via the declaration — and stops
    at the credential gate as dry-run, not at no_matching_packet."""
    from tinyassets.effectors.github_pr import run_effects_for_branch
    from tinyassets.storage.effector_consents import grant_consent

    grant_consent(base / "u-a", sink="twitter_post", destination="@myhandle",
                  granted_by="user_1")

    class _Branch:
        node_defs = [_Node([_DECLARATION])]

    results = run_effects_for_branch(
        branch=_Branch(),
        run_state={"post_text": "shipped the slack agent"},
        base_path=base / "u-a",
        run_id="r_assembly",
    )
    evidence = results["publish"]["twitter_post"]
    assert evidence.get("error_kind") != "no_matching_packet"
    assert evidence.get("reason") == "missing_credentials"
    assert evidence.get("packet_assembled_from_handoff") is True
    assert evidence["would_post"]["text"] == "shipped the slack agent"


def test_package_wrapper_preserves_handoffs_to_the_dispatch(base):
    """The package-level run_effects_for_branch rebuilds each node as a
    SimpleNamespace before dispatch; it MUST carry handoffs or every real
    post assembles nothing (found live 2026-08-08, run f8009a189b38 — the
    wrapper is the path production actually takes, not github_pr's directly)."""
    from tinyassets.effectors import run_effects_for_branch
    from tinyassets.storage.effector_consents import grant_consent

    grant_consent(base / "u-a", sink="twitter_post", destination="@myhandle",
                  granted_by="user_1")

    class _Branch:
        node_defs = [_Node([_DECLARATION])]

    results = run_effects_for_branch(
        branch=_Branch(),
        run_state={"post_text": "shipped the slack agent"},
        base_path=base / "u-a",
        run_id="r_wrapper",
    )
    evidence = results["publish"]["twitter_post"]
    assert evidence.get("packet_assembled_from_handoff") is True
    assert evidence.get("reason") == "missing_credentials"


# -- label-free classification ------------------------------------------------

_KEY = "K" * 25
_SECRET = "S" * 50
_TOKEN = "1234567890123456789-" + ("T" * 30)
_TOKEN_SECRET = "X" * 45


def test_values_are_sorted_by_shape_in_any_order():
    """X renamed these fields and shows OAuth 2.0 values beside them, so the
    founder must never have to match labels."""
    from tinyassets.effectors.twitter_post import classify_credential_values

    expected = {
        "api_key": _KEY, "api_secret": _SECRET,
        "access_token": _TOKEN, "access_token_secret": _TOKEN_SECRET,
    }
    for order in (
        [_KEY, _SECRET, _TOKEN, _TOKEN_SECRET],
        [_TOKEN_SECRET, _TOKEN, _SECRET, _KEY],
        [_SECRET, _TOKEN_SECRET, _KEY, _TOKEN],
    ):
        assert classify_credential_values(order) == expected


def test_a_bearer_token_is_named_as_the_mistake_it_is():
    from tinyassets.effectors.twitter_post import classify_credential_values

    with pytest.raises(ValueError, match="Bearer Token"):
        classify_credential_values(["A" * 110, _KEY, _SECRET, _TOKEN_SECRET])


def test_missing_access_token_says_what_to_look_for():
    """The OAuth 2.0 Client ID/Secret pair lands here — no id-prefixed token."""
    from tinyassets.effectors.twitter_post import classify_credential_values

    with pytest.raises(ValueError, match="Access Token"):
        classify_credential_values([_KEY, _SECRET, _TOKEN_SECRET, "Z" * 40])


def test_deposit_accepts_a_pasted_blob(base, monkeypatch):
    from tinyassets.credential_vault import resolve_twitter_credentials

    monkeypatch.setattr(
        "tinyassets.effectors.twitter_post.whoami", lambda c: "myhandle"
    )
    result = execute_action(token=_token(), surface="effector",
                            action="deposit", payload={
                                "sink": "twitter_post",
                                "destination": "@myhandle",
                                "values": f"{_SECRET}\n{_TOKEN}\n{_KEY}\n{_TOKEN_SECRET}",
                            })
    assert result["deposited_for"] == "@myhandle"
    stored = resolve_twitter_credentials(base / "u-a", "@myhandle")
    assert stored == {
        "api_key": _KEY, "api_secret": _SECRET,
        "access_token": _TOKEN, "access_token_secret": _TOKEN_SECRET,
    }


# -- conversational deposit ---------------------------------------------------

_DEPOSIT = {
    "sink": "twitter_post", "destination": "@myhandle",
    "api_key": "k", "api_secret": "s",
    "access_token": "t", "access_token_secret": "ts",
}


def test_deposit_verifies_identity_and_stores_in_the_vault(base, monkeypatch):
    from tinyassets.credential_vault import resolve_twitter_credentials

    monkeypatch.setattr(
        "tinyassets.effectors.twitter_post.whoami", lambda c: "MyHandle"
    )
    result = execute_action(token=_token(), surface="effector",
                            action="deposit", payload=dict(_DEPOSIT))
    assert result["deposited_for"] == "@myhandle"
    assert result["authenticates_as"] == "@MyHandle"
    # No secret value may appear anywhere in the reply the agent sees.
    blob = str(result)
    for value in ("'k'", "'s'", "'t'", "'ts'"):
        assert value not in blob
    assert resolve_twitter_credentials(base / "u-a", "@myhandle") is not None


def test_deposit_refuses_a_credential_for_a_different_account(base, monkeypatch):
    """Consent and authority name ONE account; a credential that signs as
    another must never be stored under that destination."""
    from tinyassets.credential_vault import resolve_twitter_credentials

    monkeypatch.setattr(
        "tinyassets.effectors.twitter_post.whoami", lambda c: "someoneelse"
    )
    with pytest.raises(AgentActionError, match="authenticate as @someoneelse"):
        execute_action(token=_token(), surface="effector",
                       action="deposit", payload=dict(_DEPOSIT))
    assert resolve_twitter_credentials(base / "u-a", "@myhandle") is None


def test_deposit_requires_all_four_values(base):
    partial = dict(_DEPOSIT)
    partial["access_token_secret"] = ""
    with pytest.raises(AgentActionError, match="missing"):
        execute_action(token=_token(), surface="effector",
                       action="deposit", payload=partial)


def test_deposit_rejection_never_echoes_the_values(base, monkeypatch):
    def _reject(_creds):
        raise ValueError("X rejected the credentials (HTTP 401): unauthorized")

    monkeypatch.setattr("tinyassets.effectors.twitter_post.whoami", _reject)
    with pytest.raises(AgentActionError) as excinfo:
        execute_action(token=_token(), surface="effector",
                       action="deposit", payload=dict(_DEPOSIT))
    message = str(excinfo.value)
    for value in ("'k'", "'s'", "'t'", "'ts'"):
        assert value not in message


# -- outward chat bindings need consent --------------------------------------

def test_making_an_agent_live_in_chat_requires_the_founders_yes(base):
    """Live 2026-08-08: an agent was connected WORKSPACE-WIDE off a misread
    terse message, with no ask. Outward visibility is consent-gated now."""
    with pytest.raises(AgentActionError, match="go-ahead"):
        execute_action(
            token=_token(), surface="chat_surface", action="bind_channel",
            payload={"agent_binding_id": "b1", "workspace_id": "T0TEST"},
        )
    listed = execute_action(token=_token(), surface="approval", action="list",
                            payload={})
    assert [p["action_key"] for p in listed["pending"]] == [
        "chat_surface.bind_channel:t0test:workspace_wide"
    ]


def test_binding_consent_is_keyed_to_the_scope():
    """Yes to one channel must not be yes to the whole workspace."""
    from tinyassets.universe_agent_actions import _approval_key

    one_channel = _approval_key(
        "chat_surface", "bind_channel",
        {"workspace_id": "T0TEST", "channel_id": "C42"},
    )
    whole_workspace = _approval_key(
        "chat_surface", "bind_channel", {"workspace_id": "T0TEST"},
    )
    assert one_channel != whole_workspace
    assert "workspace_wide" in whole_workspace
