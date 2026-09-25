"""A zero-cost source's transient refusal must not dead-end the turn.

Live 2026-09-25, free-only account ``u-01ky3zh1arr8qth8jee7zx63pq``: the first
message after a successful connect failed with ``provider_rate_limited`` and
``attempts=1``. The source's contract maps HTTP 429 to capacity scope
``unknown``; ``capacity_boundary`` collapses anything that is not unanimously
``model`` to an ACCOUNT exhaustion, and an account exhaustion removes every
sibling model on that connection from the order -- so there was no second
candidate and nothing was retried. The router had also cooled the whole source,
which would have skipped a sibling even if one had survived.

The conservatism is right when being wrong costs money. On a source whose
accepted ceilings are all zero it costs nothing, and it is what makes a freshly
connected universe mute on its very first message.
"""

import json
from dataclasses import replace

import pytest

from tests import test_interactive_http_agent as integration
from tinyassets.exceptions import AllProvidersExhaustedError
from tinyassets.providers.model_capacity import (
    TRANSIENT_CAPACITY,
    CapacitySignal,
    free_sibling_retry,
)
from tinyassets.providers.model_policy import Charge, confirmed_free_only

rig = integration.rig
reader = integration.reader
served = integration.served
agent = integration.agent


# --------------------------------------------------------------------------
# The policy predicate: one definition, two readers (router + coordinator).
# --------------------------------------------------------------------------


@pytest.mark.parametrize("caps", [
    None,
    (Charge("input_million_tokens_usd", 0, True),),
    (("input_million_tokens_usd", 0), ("request_usd", 0)),
])
def test_zero_ceilings_are_free_only(caps):
    assert confirmed_free_only(caps) is True


@pytest.mark.parametrize("caps", [
    (),
    (Charge("input_million_tokens_usd", 1, True),),
    (Charge("input_million_tokens_usd", 0, False),),
    (("input_million_tokens_usd", 5),),
    (("input_million_tokens_usd", True),),
    "free",
    [Charge("request_usd", 0, True)],
])
def test_anything_but_confirmed_zero_is_not_free_only(caps):
    assert confirmed_free_only(caps) is False


@pytest.mark.parametrize("failure", sorted(TRANSIENT_CAPACITY))
def test_free_only_unknown_scope_may_try_a_sibling(failure):
    assert free_sibling_retry(scope="unknown", failure_class=failure, cost_caps=None) is True


@pytest.mark.parametrize("scope,failure,caps", [
    # A source that reported the ACCOUNT is evidence; never retry past it.
    ("account", "provider_rate_limited", None),
    # Exhausted credit is about money, not a transient window.
    ("unknown", "provider_credit_exhausted", None),
    # Model-local needs no policy: the existing order already keeps siblings.
    ("model", "provider_rate_limited", None),
    # A source that can spend must keep the conservative treatment.
    ("unknown", "provider_rate_limited", (Charge("request_usd", 1, True),)),
    ("unknown", None, None),
])
def test_paid_proven_or_nontransient_capacity_keeps_the_conservative_policy(scope, failure, caps):
    assert free_sibling_retry(scope=scope, failure_class=failure, cost_caps=caps) is False


def test_capacity_signal_scope_stays_observed_evidence():
    """The policy reads the scope; it never rewrites the source's own signal."""
    signal = CapacitySignal("unknown", "provider_rate_limited", 60)
    assert signal.scope == "unknown"


# --------------------------------------------------------------------------
# End to end through the real router, adapter, journal and provider.
# --------------------------------------------------------------------------


def test_free_only_rate_limit_continues_to_a_sibling_model(agent, monkeypatch):
    """The founder's turn: 429 on the first model, answered by the next one."""
    alternate = integration._with_fallback(agent, monkeypatch)
    agent.capacity_failures[2] = 429
    assert integration.run(agent) == "finished exact answer"
    assert len(agent.wires) == 3 and len(agent.tools) == 1
    turn = agent.latest()
    assert turn.state == "completed"
    assert [round.state for round in turn.rounds] == ["received", "failed", "received"]
    assert agent.wires[-1][1]["body"]["model"] == alternate
    # The retry stays inside the same owner grant at the same zero ceilings.
    assert all(
        set(wire[1]["body"]["provider"]["max_price"].values()) == {"0"}
        for wire in agent.wires
    )


def test_free_only_rate_limit_does_not_cool_the_whole_source(agent):
    """A cooled source skips its own siblings, which is the same dead end."""
    agent.capacity_failures[1] = 429
    with pytest.raises(AllProvidersExhaustedError):
        integration.run(agent)
    provider = agent.served.context.model_selection.connection_id
    assert agent.served.router._quota.cooldown_remaining(provider) == 0


def test_exhausted_credit_still_stops_at_the_first_model(agent, monkeypatch):
    """402 is the account and it is about money: never widen, never retry."""
    integration._with_fallback(agent, monkeypatch)
    agent.capacity_failures[2] = 402
    with pytest.raises(AllProvidersExhaustedError):
        integration.run(agent)
    assert len(agent.wires) == 2 and len(agent.tools) == 1
    provider = agent.served.context.model_selection.connection_id
    assert agent.served.router._quota.cooldown_remaining(provider) > 0


def test_sibling_retries_are_bounded_and_every_attempt_is_recorded(agent, monkeypatch):
    """Three tries, then report -- with all of them in the failure evidence."""
    from tinyassets.providers import discovery_snapshot
    from tinyassets.providers.agent_model_plan import AgentModelPlan
    from tinyassets.providers.discovery_protocols import discovery_protocol
    from tinyassets.providers.model_policy import Catalog, ModelPolicy, ModelRef

    siblings = [f"future-vendor/model-{index}" for index in range(5)]
    original = discovery_snapshot.read_http_discovery_document

    def added(**kwargs):
        value = original(**kwargs)
        if "models/user" in kwargs["url"]:
            value["data"].extend(
                integration.authority_tests.snapshot_tests._model(name) for name in siblings
            )
        return value

    monkeypatch.setattr(discovery_snapshot, "read_http_discovery_document", added)
    snapshot = integration.authority_tests.snapshot_tests._refresh(agent.served.rig)
    selected = agent.served.context.model_selection
    agent.served.context = replace(agent.served.context, agent_model_plan=AgentModelPlan(
        Catalog("owner", agent.served.context.universe_dir.name, (snapshot.models,)),
        ModelPolicy(
            generation=7, mode="explicit", saved_default=selected,
            fallbacks=tuple(ModelRef(selected.connection_id, name) for name in siblings),
        ),
        replace(
            discovery_protocol(snapshot.models.provider_scope).text_interaction, needs_tools=True,
        ),
        policy_source="saved",
    ))
    agent.capacity_failures.update({index: 429 for index in range(1, 9)})
    with pytest.raises(AllProvidersExhaustedError) as error:
        integration.run(agent)
    # One first attempt plus at most three narrowed retries.
    assert len(agent.wires) == 4
    assert len(error.value.attempts) == 4
    assert {attempt.failure_class for attempt in error.value.attempts} == {"provider_rate_limited"}
    assert len({wire[1]["body"]["model"] for wire in agent.wires}) == 4


# --------------------------------------------------------------------------
# The owner's own failure record must carry the source's words, not our class.
# --------------------------------------------------------------------------


def test_capacity_detail_carries_the_sources_own_words(agent):
    """`Detail: "provider_rate_limited"` told the founder only our class name."""
    from tinyassets import universe_server

    agent.capacity_failures[1] = 429
    with pytest.raises(AllProvidersExhaustedError) as error:
        integration.run(agent)
    detail = error.value.attempts[-1].detail
    assert "429" in detail and "synthetic refusal" in detail
    record = universe_server._served_failure_record(error.value)
    assert record.code == "provider_rate_limited"
    assert "synthetic refusal" in record.provider_detail
    assert record.provider_detail != "provider_rate_limited"


def test_capacity_detail_is_bounded_and_scrubbed(agent):
    """Provider text is the owner's own, but it is still untrusted transport."""
    from tinyassets.conversation_failure import DETAIL_LIMIT
    from tinyassets.providers.api_key_http_provider import ApiKeyHttpProvider

    body = json.dumps({"error": {"message": "sk-live-" + "A" * 4000}})
    detail = ApiKeyHttpProvider._capacity_detail(429, {"body": body})
    assert len(detail) <= DETAIL_LIMIT
    assert "A" * 400 not in detail
