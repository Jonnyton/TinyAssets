"""Finite advisory orders never enlarge accepted invocation authority."""

import pytest

from tinyassets.providers.model_policy import ModelRef


def refs(n):
    return tuple(ModelRef("owned", str(i)) for i in range(n))


def test_automatic_prefixes_fit_weighted_ceiling_without_increasing_it():
    from tinyassets.providers.work_candidate_data import fit_orders

    groups = {"a": (refs(100), 2, True), "b": (refs(100), 1, True)}
    fitted, minimum = fit_orders(groups, ceiling=7)
    assert fitted == {"a": refs(2), "b": refs(3)}
    assert minimum == 7


def test_explicit_order_does_not_silently_truncate():
    from tinyassets.providers.work_candidate_data import fit_orders

    with pytest.raises(PermissionError, match="invocation allowance"):
        fit_orders({"explicit": (refs(3), 2, False)}, ceiling=5)
    assert fit_orders({"empty_tail": (refs(1), 2, False)}, ceiling=100) == (
        {"empty_tail": refs(1)}, 2,
    )


@pytest.mark.parametrize("ceiling", [0, True, -1])
def test_invalid_ceiling_refuses(ceiling):
    from tinyassets.providers.work_candidate_data import fit_orders

    with pytest.raises((ValueError, PermissionError)):
        fit_orders({"a": (refs(1), 1, True)}, ceiling=ceiling)


def data(*, automatic=False, reconnect=()):
    from tests.test_model_policy import NEEDS, connection, model
    from tinyassets.providers.agent_model_plan import AgentModelPlan
    from tinyassets.providers.model_policy import Catalog, ModelPolicy
    from tinyassets.providers.work_candidate_data import WorkCandidateData

    catalog = Catalog("owner", "universe", (
        connection("a", models=[model("A")]), connection("b", models=[model("B")]),
    ))
    policy = (ModelPolicy(0, "automatic", ()) if automatic else
              ModelPolicy(0, "explicit", (ModelRef("b", "B"),),
                          saved_default=ModelRef("a", "A")))
    plan = AgentModelPlan(catalog, policy, NEEDS, reconnect_sources=reconnect)
    return WorkCandidateData(plan)


def test_exhaustion_is_retained_across_reentry_without_fresh_catalogue_lookup():
    from tinyassets.providers.model_policy import Exhaustion

    choices = data()
    assert choices.fit({"node_defs": [{"prompt_template": "hello"}]},
                       ceiling=10, retry_multiplier=3) == 2
    assert choices.next_candidate(None) == ModelRef("a", "A")
    assert choices.next_candidate(None, (Exhaustion("model", ModelRef("a", "A")),)) == (
        ModelRef("b", "B")
    )
    # A newly refreshed catalogue could lack A. No refreshed object is consulted;
    # the session retains original capacity facts instead of restarting its plan.
    assert choices.next_candidate(None) == ModelRef("b", "B")
    assert choices.next_candidate(None, (Exhaustion("account", ModelRef("b", "B")),)) is None
    assert choices.next_candidate(None) is None


def test_automatic_health_demotion_is_preserved_but_explicit_primary_is_not_replaced():
    for automatic, expected in ((True, ModelRef("b", "B")), (False, ModelRef("a", "A"))):
        choices = data(automatic=automatic, reconnect=("a",))
        choices.fit({"node_defs": [{"prompt_template": "hello"}]},
                    ceiling=10, retry_multiplier=3)
        assert choices.next_candidate(None) == expected


def test_graph_pin_cannot_replace_explicit_user_primary_or_discard_tail():
    for policy in ({"preferred": {"provider": "b"}}, {"fallback_chain": []}):
        choices = data()
        with pytest.raises(PermissionError, match="conflicts"):
            choices.fit({"node_defs": [{"prompt_template": "hello", "llm_policy": policy}]},
                        ceiling=10, retry_multiplier=3)
