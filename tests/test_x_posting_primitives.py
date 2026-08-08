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
