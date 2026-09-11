"""Declared aggregate quantities: exact arithmetic, not remote semantics proof."""

from copy import deepcopy
from dataclasses import FrozenInstanceError

import pytest

from tinyassets.providers.discovery_quantities import QuantityModel

UNITS = ("input_million_tokens_usd", "output_million_tokens_usd", "request_usd")
STANDARD = {"version": 1, "quantities": {
    "input_tokens": {"input": 1, "output": 0, "per_attempt": 0, "fixed": 0},
    "output_tokens": {"input": 0, "output": 1, "per_attempt": 0, "fixed": 0},
    "requests": {"input": 0, "output": 0, "per_attempt": 1, "fixed": 0},
}}


def caps(input=0, output=0, request=0):
    return tuple(zip(UNITS, (input, output, request)))


def test_eight_internal_samples_reserve_eight_outputs_not_one():
    document = deepcopy(STANDARD)
    document["quantities"]["output_tokens"]["output"] = 8
    model = QuantityModel.compile(document)
    assert model.bounds(100, 1000) == (100, 8000, 1)
    # $10/million = 10,000,000 micros/million. Eight samples cost $0.08.
    assert model.cost_upper_bound(caps(output=10_000_000), 100, 1000) == 80_000
    assert model.affordable_output(caps(output=10_000_000), 100, 1000, 10_000) == 125


def test_aggregate_input_replication_fixed_overhead_and_request_multiplicity():
    document = deepcopy(STANDARD)
    document["quantities"]["input_tokens"] = {
        "input": 8, "output": 2, "per_attempt": 4, "fixed": 3,
    }
    document["quantities"]["requests"]["per_attempt"] = 8
    model = QuantityModel.compile(document)
    assert model.bounds(10, 20, attempts=2) == (131, 20, 16)
    assert model.cost_upper_bound(caps(1_000_000, 2_000_000, 3), 10, 20,
                                  attempts=2) == 219


def test_round_each_charge_up_and_keep_free_output_finite():
    model = QuantityModel.compile(STANDARD)
    assert model.cost_upper_bound(caps(1, 1, 1), 1, 1) == 3
    assert model.affordable_output(caps(1, 1, 1), 1, 1, 2) == 0
    assert model.affordable_output(caps(), 100, 65536, 0) == 65536
    assert model.affordable_output(caps(request=1), 100, 65536, 0) == 0


def test_affordability_matches_exhaustive_bounded_search():
    for samples in (0, 1, 8, 100):
        document = deepcopy(STANDARD)
        document["quantities"]["output_tokens"]["output"] = samples
        document["quantities"]["input_tokens"]["output"] = 2
        model = QuantityModel.compile(document)
        for prices in (caps(), caps(1, 3, 7), caps(999_999, 1_000_001, 3)):
            for remaining in range(50):
                for limit in (0, 1, 29):
                    expected = max([0] + [n for n in range(1, limit + 1)
                                          if model.cost_upper_bound(prices, 3, n) <= remaining])
                    assert model.affordable_output(prices, 3, limit, remaining) == expected


@pytest.mark.parametrize("value", [True, False, -1, 1.0, "1", None, [], {}, 10**6 + 1])
@pytest.mark.parametrize("key", ["input", "output", "per_attempt", "fixed"])
def test_coefficients_are_bounded_nonnegative_integers(value, key):
    document = deepcopy(STANDARD)
    document["quantities"]["input_tokens"][key] = value
    with pytest.raises(ValueError):
        QuantityModel.compile(document)


@pytest.mark.parametrize("change", ["version", "extra", "missing", "dimension", "formula",
                                   "request_input", "request_output"])
def test_closed_dimensionally_typed_shape(change):
    document = deepcopy(STANDARD)
    if change == "version":
        document["version"] = True
    elif change == "extra":
        document["trusted"] = True
    elif change == "missing":
        del document["quantities"]["requests"]
    elif change == "dimension":
        document["quantities"]["images"] = document["quantities"]["requests"]
    elif change == "formula":
        document["quantities"]["output_tokens"]["expression"] = "eval(input)"
    else:
        document["quantities"]["requests"][change.removeprefix("request_")] = 1
    with pytest.raises(ValueError):
        QuantityModel.compile(document)


@pytest.mark.parametrize("value", [True, -1, 1.0, "1", None, 10**18 + 1])
@pytest.mark.parametrize("position", ["input", "output", "attempts"])
def test_invalid_facts_are_not_silently_treated_as_unaffordable(value, position):
    model = QuantityModel.compile(STANDARD)
    facts = {"input": 1, "output": 1, "attempts": 1, position: value}
    with pytest.raises(ValueError):
        model.affordable_output(caps(), facts["input"], facts["output"], 0,
                                attempts=facts["attempts"])


def test_no_attemptless_dispatch_and_no_mutable_caller_data():
    document = deepcopy(STANDARD)
    model = QuantityModel.compile(document)
    document["quantities"]["output_tokens"]["output"] = 999
    assert model.bounds(1, 1) == (1, 1, 1)
    with pytest.raises(FrozenInstanceError):
        model.coefficients = ()
    with pytest.raises(ValueError):
        model.bounds(1, 1, attempts=0)


@pytest.mark.parametrize("prices", [(), ((UNITS[0], 0),) * 3, caps(output=True),
                                    caps(input=-1), caps(request=10**18 + 1),
                                    list(caps()), (("images", 0),) + caps()])
def test_invalid_price_bounds_refuse(prices):
    with pytest.raises(ValueError):
        QuantityModel.compile(STANDARD).cost_upper_bound(prices, 1, 1)


def test_overflow_refuses_reservation_but_affordability_can_find_a_safe_quantity():
    model = QuantityModel.compile(STANDARD)
    with pytest.raises(ValueError, match="supported cost range"):
        model.cost_upper_bound(caps(output=10**18), 0, 10**18)
    assert model.affordable_output(caps(output=10**18), 0, 10**18,
                                   2**63 - 1) == (2**63 - 1) // 10**12
    safe = model.affordable_output(caps(output=10**18), 0, 10**18, 2**63 - 1)
    assert model.cost_upper_bound(caps(output=10**18), 0, safe) <= 2**63 - 1


@pytest.mark.parametrize("remaining", [True, -1, 1.0, "1", None, 2**63])
def test_remaining_authority_must_be_a_bounded_integer(remaining):
    with pytest.raises(ValueError):
        QuantityModel.compile(STANDARD).affordable_output(caps(), 0, 1, remaining)
