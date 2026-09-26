"""All user accounts are the same. No rule here may read a price or a plan.

Founder, 2026-09-25: *"all user accounts should be the same"*.

`free_sibling_retry` decides two live behaviours -- whether a transient capacity
refusal buys a SIBLING model attempt (#3981), and whether the source keeps its
cooldown (#3986) -- and both were gated on `confirmed_free_only(cost_caps)`. That
put a plan branch in the hot path: a FREE source's unknown-scope 429 continued to
a sibling and stayed hot, while a PAID source's identical 429 was cooled with no
retry. Same source contract, same HTTP status, same evidence, two different
answers depending on what the owner pays.

The price is no longer an input. What decides now is only what the SOURCE
reported: capacity scope, failure class, and its own `Retry-After`.

Money does not become unbounded, and the two mechanisms that bound it are the
ones that always did:

* **Per-attempt ceilings.** The encoder constrains every request body against the
  owner's accepted ceilings, so a sibling attempt is priced exactly like the
  first one. A retry policy cannot raise a ceiling, admit a model or widen a
  grant -- the sibling comes from the SAME order under the SAME ceilings.
* **The money case is source-reported and still stops.**
  `provider_credit_exhausted` is deliberately absent from `TRANSIENT_CAPACITY`
  ("it is about money, not about waiting"), and a reported `account` scope is
  proven breadth. Both still refuse, on a paid source and a free one alike --
  which is what the paid rows below pin.
"""

from __future__ import annotations

import inspect

import pytest

from tests import test_interactive_http_agent as integration
from tinyassets.exceptions import AllProvidersExhaustedError
from tinyassets.providers import model_capacity
from tinyassets.providers.model_capacity import TRANSIENT_CAPACITY, free_sibling_retry

rig = integration.rig
reader = integration.reader
served = integration.served
agent = integration.agent


# --------------------------------------------------------------------------
# The price is not an input at all. Parametrizing ceilings would only prove the
# ANSWER does not vary; these prove the QUESTION cannot be asked, which is what
# stops the branch being reintroduced somewhere else in the module.
# --------------------------------------------------------------------------


_PRICE_WORDS = ("cost", "caps", "price", "ceiling", "free", "paid", "plan", "tier")


def test_the_policy_cannot_be_handed_a_price():
    taken = set(inspect.signature(free_sibling_retry).parameters)
    assert taken == {"scope", "failure_class", "retry_after_s", "turn_budget_s"}
    assert not [p for p in taken if any(w in p.lower() for w in _PRICE_WORDS)]


def test_the_policy_module_reads_no_price_anywhere():
    source = inspect.getsource(model_capacity)
    for dead in ("confirmed_free_only", "cost_caps"):
        assert dead not in source, (
            f"the capacity policy reads {dead} again; all accounts must be the same"
        )


def test_no_dead_price_reader_is_left_for_someone_to_wire_back():
    """The two helpers that existed only to feed this gate are gone."""
    from tinyassets.providers import agent_model_plan, model_policy

    assert not hasattr(model_policy, "confirmed_free_only")
    assert not hasattr(agent_model_plan.AgentModelPlan, "source_cost_caps")


# --------------------------------------------------------------------------
# What the source reported is the whole input, and every answer it produces is
# the same answer for everyone.
# --------------------------------------------------------------------------


@pytest.mark.parametrize("failure", sorted(TRANSIENT_CAPACITY))
def test_a_transient_unknown_window_buys_a_sibling(failure):
    assert free_sibling_retry(scope="unknown", failure_class=failure) is True


def test_exhausted_credit_stops_because_the_source_said_so():
    """The money guard. It is the SOURCE's report, never our view of the wallet."""
    assert free_sibling_retry(
        scope="unknown", failure_class="provider_credit_exhausted",
    ) is False


@pytest.mark.parametrize("scope", ["account", "model"])
def test_a_reported_scope_is_evidence_and_stops(scope):
    assert free_sibling_retry(scope=scope, failure_class="provider_rate_limited") is False


@pytest.mark.parametrize("failure", [None, "", "provider_protocol_error", "auth_invalid"])
def test_an_unrecognized_failure_class_refuses(failure):
    """Removing the price gate must not leave a default-yes behind."""
    assert free_sibling_retry(scope="unknown", failure_class=failure) is False


# --------------------------------------------------------------------------
# End to end on a PAID source, through the real router, adapter and journal:
# the case the reviewer flagged as a live founder-rule violation.
# --------------------------------------------------------------------------


def _charge_paid(agent, monkeypatch):
    """Make this universe's ACCEPTED ceilings carry a real price.

    The ceilings ride on the serving authority, not on the caller's config (the
    router overwrites caller selections), so this wraps the real authority
    entrypoint and prices the selection it produced. Everything else -- the
    binding, the admission, the budget reservation, the wire -- is the real path;
    only the one field an owner changes by approving paid model access differs.
    """
    from contextlib import asynccontextmanager
    from dataclasses import replace

    from tinyassets import provider_assignment
    from tinyassets.providers.discovery_protocols import discovery_protocol

    # Every component the wire prices, or the encoder refuses the body as
    # "incomplete inference price bounds". A real paid ceiling on input tokens
    # and a real per-request fee; the rest confirmed zero.
    contract = discovery_protocol("openrouter_user_models_v1")
    charged = {"input_million_tokens_usd": 3000, "request_usd": 50}
    paid = tuple(
        (name, charged.get(name, 0)) for name in sorted(contract.price_components)
    )
    assert any(amount > 0 for _, amount in paid), "this must be a PAID source"
    real = provider_assignment.authorize_served_provider_call_async
    seen = []

    @asynccontextmanager
    async def priced(*args, **kwargs):
        async with real(*args, **kwargs) as authority:
            selected = authority.selected_model
            assert selected is not None, "the rig must reach a real selection"
            seen.append(authority.provider)
            yield replace(authority, selected_model=replace(selected, cost_caps=paid))

    monkeypatch.setattr(
        provider_assignment, "authorize_served_provider_call_async", priced,
    )
    return seen


def test_a_paid_source_is_not_cooled_by_a_transient_refusal(agent, monkeypatch):
    """A paid 429 used to be cooled with no retry while a free one was not."""
    priced = _charge_paid(agent, monkeypatch)
    agent.capacity_failures[1] = 429
    with pytest.raises(AllProvidersExhaustedError):
        integration.run(agent)
    provider = agent.served.context.model_selection.connection_id
    assert agent.served.router._quota.cooldown_remaining(provider) == 0
    assert priced, "the paid ceilings never reached a real authority"


def test_a_paid_source_continues_to_a_sibling_model(agent, monkeypatch):
    """The same answer a free source already got (test_free_model_sibling_retry)."""
    alternate = integration._with_fallback(agent, monkeypatch)
    priced = _charge_paid(agent, monkeypatch)
    agent.capacity_failures[2] = 429
    assert integration.run(agent) == "finished exact answer"
    assert agent.wires[-1][1]["body"]["model"] == alternate
    assert priced, "the paid ceilings never reached a real authority"


def test_a_paid_source_still_honours_a_window_longer_than_the_turn(agent, monkeypatch):
    """The money-adjacent guard: waiting is still the answer for a paid source."""
    from dataclasses import replace

    priced = _charge_paid(agent, monkeypatch)
    agent.config = replace(agent.config, absolute_cap_s=10)
    agent.capacity_failures[1] = 429
    with pytest.raises(AllProvidersExhaustedError):
        integration.run(agent)
    provider = agent.served.context.model_selection.connection_id
    # The rig's source names 60s; a turn that may live 10s cannot outlast it.
    assert 60 <= agent.served.router._quota.cooldown_remaining(provider) <= 61
    assert priced, "the paid ceilings never reached a real authority"


# --------------------------------------------------------------------------
# A native/subscription executor is governed by what the SOURCE is, not by what
# the owner pays -- so it must behave identically after the price gate is gone.
# --------------------------------------------------------------------------


@pytest.mark.parametrize("kind,narrows", [("engine_inference", True), ("native_agent", False)])
def test_the_executor_kind_decides_narrowing_without_consulting_a_plan(kind, narrows):
    """A native executor runs on ONE subscription, so its account IS the source.

    That refusal is right and has nothing to do with price: it is about the
    source's shape. The plan handed in here has NO ceiling accessor at all, so
    this fails loudly if anything on the path asks for one again.
    """
    from types import SimpleNamespace

    from tinyassets.agent_turn_coordinator import AgentTurnCoordinator
    from tinyassets.providers.agent_capacity_boundary import CapacityBoundary
    from tinyassets.providers.base import ModelConfig
    from tinyassets.providers.model_policy import Exhaustion, ModelRef

    ref = ModelRef("some-source", "some-model")
    turn = AgentTurnCoordinator.__new__(AgentTurnCoordinator)
    turn.execution_kind = kind
    turn.free_sibling_retries = 0
    turn.context = SimpleNamespace(model_selection=ref)
    turn.plan = SimpleNamespace()  # no source_cost_caps: asking would raise
    turn.config = ModelConfig(absolute_cap_s=120)
    boundary = CapacityBoundary(
        Exhaustion("account", ref), True, "provider_rate_limited", 60.0, "unknown",
    )
    exhaustion, narrowed = turn._narrowed(boundary)
    assert narrowed is narrows
    assert exhaustion.scope == ("model" if narrows else "account")


# --------------------------------------------------------------------------
# A source may not retire itself, and the router's own window rule must be live
# at its CALL SITE, not only as a unit.
# --------------------------------------------------------------------------


@pytest.mark.parametrize("asked,applied", [
    (30, 31),                       # a plausible window, honoured
    (86_399, 86_400),               # right at the ceiling
    (86_400, 86_400),               # clamped by one second
    (99_999_999, 86_400),           # the buggy header: 3.2 years, not honoured
    (float("inf"), 120),            # unusable, so the fixed default
    (-5, 120),
    (True, 120),                    # a bool is not a wait
])
def test_a_source_cannot_retire_itself_with_a_retry_after_header(asked, applied):
    """`Retry-After` is remote input: unbounded, it is a source-side denial.

    `_retry_after_cooldown_s` is the single definition used by the capacity
    handler AND `cool_source`, so bounding it here bounds both.
    """
    from tinyassets.providers.quota import MAX_COOLDOWN_S
    from tinyassets.providers.router import _retry_after_cooldown_s

    assert _retry_after_cooldown_s(asked) == applied
    assert _retry_after_cooldown_s(asked) <= MAX_COOLDOWN_S


def test_the_routers_own_window_rule_is_live(agent):
    """The window rule decided at the ROUTER, not just inside the predicate.

    #3986 put the rule in `free_sibling_retry` and passes it two arguments from
    the router's capacity handler, but only the predicate had a test: nulling
    either argument at the call site left 191 tests green. This drives the real
    handler -- the rig's source reports `retry-after: 60`, and against a turn that
    may only live 10s that window outlasts the turn, so the source must be cooled.
    """
    from dataclasses import replace

    agent.config = replace(agent.config, absolute_cap_s=10)
    agent.capacity_failures[1] = 429
    with pytest.raises(AllProvidersExhaustedError):
        integration.run(agent)
    remaining = agent.served.router._quota.cooldown_remaining(
        agent.served.context.model_selection.connection_id)
    # 60s (+1s margin), read back through a truncating remaining-seconds call.
    # Discriminates both ways: no cooling at all reads 0, and ignoring the
    # source's own number reads the fixed 120s default.
    assert 60 <= remaining <= 61, remaining


def test_a_short_window_leaves_the_source_hot(agent):
    """Its guard: 60s inside a 120s turn still buys the sibling attempt."""
    from dataclasses import replace

    agent.config = replace(agent.config, absolute_cap_s=120)
    agent.capacity_failures[1] = 429
    with pytest.raises(AllProvidersExhaustedError):
        integration.run(agent)
    assert agent.served.router._quota.cooldown_remaining(
        agent.served.context.model_selection.connection_id) == 0


def _coordinator(kind="engine_inference", *, retry_after, budget):
    """A coordinator at the point it decides whether to narrow, nothing mocked
    but the two objects it reads."""
    from types import SimpleNamespace

    from tinyassets.agent_turn_coordinator import AgentTurnCoordinator
    from tinyassets.providers.agent_capacity_boundary import CapacityBoundary
    from tinyassets.providers.base import ModelConfig
    from tinyassets.providers.model_policy import Exhaustion, ModelRef

    ref = ModelRef("some-source", "some-model")
    turn = AgentTurnCoordinator.__new__(AgentTurnCoordinator)
    turn.execution_kind = kind
    turn.free_sibling_retries = 0
    turn.context = SimpleNamespace(model_selection=ref)
    turn.plan = SimpleNamespace()
    turn.config = ModelConfig(absolute_cap_s=budget)
    boundary = CapacityBoundary(
        Exhaustion("account", ref), True, "provider_rate_limited", retry_after, "unknown",
    )
    return turn, boundary


@pytest.mark.parametrize("retry_after,budget,narrows", [
    (60.0, 120.0, True),    # a wait the turn can absorb: buy the sibling
    (600.0, 120.0, False),  # longer than the turn may live: waiting is the answer
])
def test_the_coordinators_own_window_rule_is_live(retry_after, budget, narrows):
    """The other half of #3986's window rule, at ITS call site.

    `_narrowed` passes `window=True`; nulling either argument there left the whole
    suite green, the same gap the router's call site had.
    """
    turn, boundary = _coordinator(retry_after=retry_after, budget=budget)
    exhaustion, narrowed = turn._narrowed(boundary)
    assert narrowed is narrows
    assert exhaustion.scope == ("model" if narrows else "account")
