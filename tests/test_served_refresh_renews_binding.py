"""A served turn that rotates the owner's sign-in still answers.

Live 2026-09-28 18:45Z, the founder's universe: the codex document was 13h old, so
the served turn's pre-launch refresh rotated it -- correctly -- and then tried to
carry the accepted binding onto the new bytes with ``owner_user_id=None``.
``ensure_founder_serving`` returns ``held/authentication_required`` for no owner
and never raises, so the binding and custody row still pinned the OLD record
digest, custody resolved to None, and the turn was refused with "Connect your
provider". It stayed refused: the next turns found a fresh document, rotated
nothing, and so renewed nothing.

Drives the real served turn (``universe_intelligence.converse`` through the real
``authorize_served_provider_call_async``, the real refresh seam, the real renewal
and the real custody check). Only the network spend and the issuer metadata are
replaced.
"""

from __future__ import annotations

import base64
import json

import pytest

from tests import test_served_model_preferences as prefs
from tests.test_subscription_credential_refresh import (
    ID_TOKEN,
    _endpoint_from_the_credential,
)

_converse = prefs._converse
rig = prefs.rig
reader = prefs.reader
configured = prefs.configured
served = prefs.served
agent = prefs.agent


def _stale_document(refresh: str) -> str:
    return base64.b64encode(json.dumps({
        "tokens": {"id_token": ID_TOKEN, "access_token": "a-1", "refresh_token": refresh},
        "last_refresh": "2020-01-01T00:00:00Z",
    }).encode("utf-8")).decode("ascii")


def _redeposit_stale(agent) -> None:
    """The owner's last sign-in, now older than the refresh window.

    Deposited and accepted through the real reconnect path, so the binding and the
    custody row pin THIS document's digest -- the live state before the turn.
    """
    from tinyassets import daemon_server
    from tinyassets.credential_vault import write_credential_vault
    from tinyassets.custom_agents import get_binding
    from tinyassets.onboarding.serving import ensure_founder_serving

    base = agent.served.rig.base
    universe = agent.served.context.universe_dir
    daemon_server.grant_universe_access(
        base, universe_id="u-models", actor_id="owner", permission="admin",
        granted_by="owner",
    )
    write_credential_vault(
        universe, [{
            "credential_type": "llm_subscription", "service": "codex",
            "auth_json_b64": _stale_document("r-1"),
        }], owner_user_id="owner", universe_id="u-models",
    )
    result = ensure_founder_serving(
        base_path=base, universe_dir=universe, owner_user_id="owner",
        universe_id="u-models", service="codex",
    )
    assert result["status"] == "serving", result
    agent.served.agent = get_binding(
        base, universe_id="u-models", binding_id=agent.served.agent["agent_binding_id"],
    )


def _custody_matches_the_vault(agent) -> bool:
    from tinyassets.credential_vault import current_llm_subscription_custody
    from tinyassets.storage.provider_work_authority import SQLiteProviderWorkAuthorityStore

    store = SQLiteProviderWorkAuthorityStore(agent.served.rig.base)
    with store.connection() as conn:
        return current_llm_subscription_custody(
            conn, universe_dir=agent.served.context.universe_dir,
            owner_user_id="owner", universe_id="u-models", service="codex",
        ) is not None


@pytest.mark.parametrize("configured", ["mixed"], indirect=True)
def test_a_turn_that_rotates_the_signin_still_answers_and_the_next_one_too(
    agent, monkeypatch,
):
    from tinyassets import subscription_refresh
    from tinyassets.providers.model_policy import ModelRef
    from tinyassets.providers.model_preferences import ModelPreferences

    _redeposit_stale(agent)
    assert _custody_matches_the_vault(agent)

    _endpoint_from_the_credential(monkeypatch)
    spent: list[str] = []

    def spend(document, **_):
        spent.append(document.refresh_token)
        return subscription_refresh._rebuild(
            document, access_token="a-2", refresh_token="r-2", id_token="",
        )

    monkeypatch.setattr(subscription_refresh, "_spend", spend)
    explicit = ModelPreferences("explicit", ModelRef("codex", ""), ()).document()

    assert _converse(agent, monkeypatch, explicit) == "codex:hello"
    assert spent == ["r-1"], "the stale sign-in was not rotated by the served turn"
    # The artefact the live failure lacked: the accepted binding followed the bytes.
    assert _custody_matches_the_vault(agent), (
        "the rotation left custody pinned to the old document digest"
    )

    # The sticky half: the next turn rotates nothing and must still answer.
    assert _converse(agent, monkeypatch, explicit) == "codex:hello"
    assert spent == ["r-1"]
    assert agent.served.native.calls == 2


@pytest.mark.parametrize("configured", ["mixed"], indirect=True)
def test_an_unproven_request_spends_no_refresh_token(agent, monkeypatch):
    """The owner comes from the request carrier the admission proves. A carrier
    that proves nothing must not spend the owner's single-use refresh token."""
    import asyncio

    from tinyassets import provider_assignment, subscription_refresh
    from tinyassets.exceptions import ProviderAuthorityHeldError
    from tinyassets.providers.model_policy import ModelRef

    _redeposit_stale(agent)
    _endpoint_from_the_credential(monkeypatch)
    monkeypatch.setattr(
        subscription_refresh, "refresh_deposited_subscriptions",
        lambda **_k: pytest.fail("an unproven request reached the refresh"),
    )
    # Not a request carrier the auth middleware issued.
    stranger = object()

    async def drive():
        async with provider_assignment.authorize_served_provider_call_async(
            agent.served.rig.base, universe_dir=agent.served.context.universe_dir,
            request_carrier=stranger, role="writer", operation="converse",
            model_selection=ModelRef("codex", ""), agent_turn=True,
        ):
            pass

    with pytest.raises(ProviderAuthorityHeldError):
        asyncio.run(drive())


@pytest.mark.parametrize("configured", ["mixed"], indirect=True)
def test_a_rotation_at_launch_carries_custody_and_the_same_request_launches(
    agent, monkeypatch,
):
    """The launch-time refresh is the backstop for callers that mint their own
    carrier. A same-account rotation carries custody forward, so the request
    that already pinned the binding revision still launches, and so does the
    next one (carry-custody-across-rotation). Before the carry, the rotating
    request was refused and only the renewal saved the next one."""
    import asyncio

    from tinyassets import provider_assignment, subscription_refresh
    from tinyassets.auth import middleware as auth
    from tinyassets.custom_agents import get_binding
    from tinyassets.providers.model_policy import ModelRef

    _redeposit_stale(agent)
    _endpoint_from_the_credential(monkeypatch)
    spent: list[str] = []

    def spend(document, **_):
        spent.append(document.refresh_token)
        return subscription_refresh._rebuild(
            document, access_token="a-2", refresh_token="r-2", id_token="",
        )

    monkeypatch.setattr(subscription_refresh, "_spend", spend)
    base = agent.served.rig.base
    binding_id = agent.served.agent["agent_binding_id"]

    def authorize(request_id):
        current = get_binding(base, universe_id="u-models", binding_id=binding_id)
        reserve = auth.reserve_provider_request(
            principal_id="owner", session_id="launch", request_id=request_id,
            tool_name="converse",
        )
        capability = auth.claim_provider_request(reserve, tool_name="converse")
        carrier = auth.mint_provider_request_carrier(
            universe_id="u-models", agent_binding_id=binding_id,
            binding_revision=current["revision"], operation="converse",
        )

        async def drive():
            async with provider_assignment.authorize_served_provider_call_async(
                base, universe_dir=agent.served.context.universe_dir,
                request_carrier=carrier, role="writer", operation="converse",
                model_selection=ModelRef("codex", ""),
            ) as authority:
                return authority.provider

        try:
            return asyncio.run(drive())
        finally:
            auth.revoke_provider_request(capability)

    before = get_binding(base, universe_id="u-models", binding_id=binding_id)["revision"]
    assert authorize("rotating") == "codex"
    assert spent == ["r-1"]
    assert _custody_matches_the_vault(agent)
    # Nothing republished: the binding revision every carrier pins did not move.
    assert get_binding(base, universe_id="u-models", binding_id=binding_id)["revision"] == before
    assert authorize("next") == "codex"
    assert spent == ["r-1"]


def test_a_launch_refresh_without_an_owner_refuses_before_spending(tmp_path, monkeypatch):
    """No owner means the rotation could not be renewed: refuse up front."""
    from tinyassets import subscription_refresh

    universe = tmp_path / "u-models"
    universe.mkdir()
    monkeypatch.setattr(
        subscription_refresh, "_spend",
        lambda *_a, **_k: pytest.fail("spent a refresh token it could not renew"),
    )
    for owner in (None, "", "  "):
        with pytest.raises(ValueError):
            subscription_refresh.refresh_deposited_subscriptions(
                base_path=tmp_path, universe_dir=universe, owner_user_id=owner,
                universe_id="u-models", launching="codex",
            )


@pytest.mark.parametrize("configured", ["mixed"], indirect=True)
def test_a_rotation_whose_renewal_never_landed_heals_on_the_next_turn(agent, monkeypatch):
    """The live state after the failure: fresh bytes in the vault, a binding still
    pinning the old ones, and nothing stale enough to rotate again. The next turn
    must renew the accepted source rather than refuse forever."""
    from tinyassets import subscription_refresh
    from tinyassets.providers.model_policy import ModelRef
    from tinyassets.providers.model_preferences import ModelPreferences

    _redeposit_stale(agent)
    _endpoint_from_the_credential(monkeypatch)
    monkeypatch.setattr(
        subscription_refresh, "_spend",
        lambda document, **_: subscription_refresh._rebuild(
            document, access_token="a-2", refresh_token="r-2", id_token=""),
    )
    # Rotated with no renewal, exactly as the pre-fix served turn left it.
    assert subscription_refresh.refresh_before_launch(
        universe_dir=agent.served.context.universe_dir, service="codex",
        owner_user_id=None, universe_id="u-models",
    )
    assert not _custody_matches_the_vault(agent)
    monkeypatch.setattr(
        subscription_refresh, "_spend",
        lambda *_a, **_k: pytest.fail("a fresh document was spent again"),
    )

    explicit = ModelPreferences("explicit", ModelRef("codex", ""), ()).document()
    assert _converse(agent, monkeypatch, explicit) == "codex:hello"
    assert _custody_matches_the_vault(agent)


def test_a_deposit_the_owner_never_accepted_is_not_renewed_by_a_turn(agent, monkeypatch):
    """Renewal carries an ACCEPTED source forward; it never binds a new one."""
    from datetime import datetime, timezone

    from tinyassets import subscription_refresh
    from tinyassets.credential_vault import write_credential_vault

    fresh = base64.b64encode(json.dumps({
        "tokens": {"id_token": ID_TOKEN, "access_token": "a-1", "refresh_token": "r-1"},
        "last_refresh": datetime.now(timezone.utc).isoformat(),
    }).encode("utf-8")).decode("ascii")
    write_credential_vault(
        agent.served.context.universe_dir, [{
            "credential_type": "llm_subscription", "service": "codex",
            "auth_json_b64": fresh,
        }], owner_user_id="owner", universe_id="u-models",
    )
    renewed: list[str] = []
    monkeypatch.setattr(
        subscription_refresh, "renew_accepted_source",
        lambda **kwargs: renewed.append(kwargs["service"]) or {"status": "serving"},
    )

    assert _converse(agent, monkeypatch) == "finished exact answer"
    assert renewed == []


def test_another_principals_deposit_is_never_spent_on_this_owners_turn(agent, monkeypatch):
    """Proving the serving binding is not proving every credential in the vault."""
    from tinyassets import subscription_refresh
    from tinyassets.credential_vault import write_credential_vault

    write_credential_vault(
        agent.served.context.universe_dir, [{
            "credential_type": "llm_subscription", "service": "codex",
            "auth_json_b64": _stale_document("r-other"),
        }], owner_user_id="other-owner", universe_id="u-models",
    )
    _endpoint_from_the_credential(monkeypatch)
    monkeypatch.setattr(
        subscription_refresh, "_spend",
        lambda *_a, **_k: pytest.fail("spent another principal's refresh token"),
    )
    renewed: list[str] = []
    monkeypatch.setattr(
        subscription_refresh, "renew_accepted_source",
        lambda **kwargs: renewed.append(kwargs["service"]) or {"status": "serving"},
    )

    assert _converse(agent, monkeypatch) == "finished exact answer"
    assert renewed == []


@pytest.mark.parametrize("configured", ["mixed"], indirect=True)
def test_a_source_no_longer_accepted_is_not_renewed_back_in(agent, monkeypatch):
    """A custody row from an earlier acceptance is history, not consent."""
    from tinyassets import subscription_refresh
    from tinyassets.api.custom_agents import custom_agents
    from tinyassets.custom_agents import get_binding
    from tinyassets.provider_assignment import load_provider_assignment
    from tinyassets.provider_assignment_manifest import ModelAccess

    _redeposit_stale(agent)
    base = agent.served.rig.base
    current = get_binding(
        base, universe_id="u-models", binding_id=agent.served.agent["agent_binding_id"],
    )
    # The owner narrows the accepted setup to the HTTP source alone.
    narrowed = custom_agents(
        action="bind_serving_provider", universe_id="u-models",
        binding_id=current["agent_binding_id"], expected_revision=current["revision"],
        payload={"provider": agent.served.rig.definition.id, "model_access": {
            agent.served.rig.definition.id: ModelAccess("discovered").document(),
        }},
    )
    assert narrowed["status"] == "ready", narrowed
    before = load_provider_assignment(base, universe_id="u-models")
    assert "codex" not in {m.provider for m in before.candidates}

    _endpoint_from_the_credential(monkeypatch)
    monkeypatch.setattr(
        subscription_refresh, "_spend",
        lambda document, **_: subscription_refresh._rebuild(
            document, access_token="a-2", refresh_token="r-2", id_token=""),
    )
    # Fresh bytes behind the old codex custody row, with no renewal.
    assert subscription_refresh.refresh_before_launch(
        universe_dir=agent.served.context.universe_dir, service="codex",
        owner_user_id=None, universe_id="u-models",
    )
    renewed: list[str] = []
    monkeypatch.setattr(
        subscription_refresh, "renew_accepted_source",
        lambda **kwargs: renewed.append(kwargs["service"]) or {"status": "serving"},
    )
    subscription_refresh.refresh_deposited_subscriptions(
        base_path=base, universe_dir=agent.served.context.universe_dir,
        owner_user_id="owner", universe_id="u-models",
    )
    assert renewed == []
    assert load_provider_assignment(base, universe_id="u-models") == before


@pytest.mark.parametrize("configured", ["mixed"], indirect=True)
def test_an_unreadable_assignment_renews_nothing_and_leaves_the_refusal_to_the_launch(
    agent, monkeypatch,
):
    """The self-heal check must not replace the launch's own refusal with its error."""
    from tinyassets import provider_assignment, subscription_refresh

    _redeposit_stale(agent)
    monkeypatch.setattr(
        subscription_refresh, "_spend",
        lambda *_a, **_k: pytest.fail("nothing is stale; nothing may be spent"),
    )
    def unreadable(*_a, **_k):
        # The loader's own words for a tampered row (provider_assignment.py).
        raise RuntimeError("provider assignment digest is invalid")

    monkeypatch.setattr(
        provider_assignment, "load_provider_assignment_in_transaction", unreadable,
    )
    renewed: list[str] = []
    monkeypatch.setattr(
        subscription_refresh, "renew_accepted_source",
        lambda **kwargs: renewed.append(kwargs["service"]) or {"status": "serving"},
    )
    # Nothing is stale, so only the self-heal check runs.
    monkeypatch.setattr(subscription_refresh, "document_is_stale", lambda *_a: False)

    subscription_refresh.refresh_deposited_subscriptions(
        base_path=agent.served.rig.base, universe_dir=agent.served.context.universe_dir,
        owner_user_id="owner", universe_id="u-models",
    )
    assert renewed == []
