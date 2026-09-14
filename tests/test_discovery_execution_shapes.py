"""Pure execution contract prerequisites, not live source admission evidence."""

import json
from copy import deepcopy
from dataclasses import FrozenInstanceError
from decimal import Decimal

import pytest

from tinyassets.providers.discovery_execution import CapacityShape, RequestCeilings, UsageShape
from tinyassets.providers.model_selection import SelectedModel

UNITS = ("input_million_tokens_usd", "output_million_tokens_usd", "request_usd")
REQUEST = {
    "required": ["model", "messages"], "allowed": ["model", "messages", "max_tokens"],
    "caps": {component: {"path": f"/billing/ceilings/{index}", "divisor": 1000000}
             for index, component in enumerate(UNITS)},
    "constants": [{"path": "/billing/enforce", "value": {"strict": True},
                   "charge_components": ["request_usd"]}],
    "model_exclusions": {"prefixes": ["alias:"], "suffixes": [":network"],
                         "substrings": ["@preset/"]},
}


def caps(input=2, output=3, request=4):
    return tuple(zip(UNITS, (input, output, request)))


def validate(body):
    assert body["messages"] == [{"role": "user", "content": "hello"}]


def body(model="unseen-source/model-2030"):
    return {"model": model, "messages": [{"role": "user", "content": "hello"}]}


@pytest.mark.parametrize("value,expected", [
    ("0", 0), ("0.000000000000000001", 1), ("1e-9999999", 1),
    ("0.00000100000000000001", 2), ("1.234567", 1234567),
    ("9223372036854.775807", 2**63 - 1), ("9223372036854.775808", None),
    ("-1", None), ("true", None), ("null", None), ("NaN", None),
    ("Infinity", None), ('"0__0"', None), ('" 0"', None), ('"0.25"', 250000),
])
def test_usage_keeps_original_number_and_rounds_up_only(value, expected):
    shape = UsageShape.compile({"cost": "/meter/charge", "scale": 10**6, "encoding": "either"})
    assert shape.decode('{"meter":{"charge":' + value + '}}') == expected


@pytest.mark.parametrize("encoding,value,expected", [
    ("string", "0", None), ("number", '"0"', None),
    ("string", '"0"', 0), ("number", "0", 0),
])
def test_usage_respects_declared_encoding(encoding, value, expected):
    shape = UsageShape.compile({"cost": "/cost", "scale": 1, "encoding": encoding})
    assert shape.decode('{"cost":' + value + '}') == expected


@pytest.mark.parametrize("raw", ["null", "[]", "{}", '{"cost":0,"cost":1}',
                                '{"cost":0,"other":NaN}', '{"cost":',
                                '{"cost":1e9999999999999999999999999}',
                                "[" * 2000 + "]" * 2000])
def test_unusable_usage_never_becomes_zero(raw):
    assert UsageShape.compile({"cost": "/cost", "scale": 10**6,
                               "encoding": "number"}).decode(raw) is None


@pytest.mark.parametrize("scale", [0, -1, True, 2, 10**19, [], "1000"])
def test_invalid_scales_refuse_at_compile(scale):
    with pytest.raises(ValueError):
        UsageShape.compile({"cost": "/cost", "scale": scale, "encoding": "number"})


def test_capacity_is_declared_data_not_a_source_or_account_identity():
    document = {"cases": [{"status": 418, "scope": "model", "reason": "provider_overloaded"},
                          {"status": 420, "scope": "unknown", "reason": "provider_rate_limited"}],
                "retry_after": True}
    shape = CapacityShape.compile(document)
    document["cases"][0]["scope"] = "account"
    assert shape.decode(418, {"Retry-After": "7"}).scope == "model"
    assert shape.decode(418, {"Retry-After": "7"}).retry_after_s == 7
    assert shape.decode(420, {}).scope == "unknown"
    assert shape.decode(429, {}) is None and shape.decode(True, {}) is None
    assert CapacityShape.compile({**document, "retry_after": False}).decode(
        418, {"Retry-After": "7"},
    ).retry_after_s is None


@pytest.mark.parametrize("case", [
    {"status": True, "scope": "model", "reason": "provider_overloaded"},
    {"status": 200, "scope": "model", "reason": "provider_overloaded"},
    {"status": 429, "scope": "credential_rotation", "reason": "provider_overloaded"},
    {"status": 429, "scope": "model", "reason": "success"},
    {"status": 429, "scope": "model", "reason": "provider_overloaded", "account_id": "x"},
])
def test_invalid_capacity_data_cannot_publish_an_interpretation(case):
    with pytest.raises(ValueError):
        CapacityShape.compile({"cases": [case], "retry_after": True})


def test_capacity_duplicates_and_unbounded_cases_refuse():
    case = {"status": 429, "scope": "model", "reason": "provider_overloaded"}
    for cases in ([case, case], [dict(case, status=400 + i) for i in range(33)]):
        with pytest.raises(ValueError):
            CapacityShape.compile({"cases": cases, "retry_after": True})


def test_exact_ceilings_share_reservation_units_and_do_not_mutate_input():
    document, original = deepcopy(REQUEST), body()
    shape = RequestCeilings.compile(document)
    document["constants"][0]["value"]["strict"] = False
    result = shape.constrain(original, caps(1234567, 0, 1), validate_body=validate)
    assert result["billing"] == {"ceilings": {"0": "1.234567", "1": "0", "2": "0.000001"},
                                 "enforce": {"strict": True}}
    assert original == body() and result["messages"] is not original["messages"]
    with pytest.raises(FrozenInstanceError):
        shape.prefixes = ()


@pytest.mark.parametrize("model", ["alias:x", "real:network", "x@preset/y", " model", ""])
def test_model_indirections_are_literal_bounded_source_data(model):
    with pytest.raises(ValueError, match="model indirection"):
        RequestCeilings.compile(REQUEST).constrain(body(model), caps(), validate_body=validate)


@pytest.mark.parametrize("path", ["", "/model", "/messages/x", "/tools", "/headers/key",
                                 "/max_tokens", "/billing/enforce/x", "/billing/ceilings/0"])
def test_protected_and_overlapping_output_paths_are_rejected(path):
    document = deepcopy(REQUEST)
    document["caps"][UNITS[1]]["path"] = path
    with pytest.raises(ValueError):
        RequestCeilings.compile(document)


def test_body_validation_cannot_be_skipped_by_declared_data():
    def refuse(_):
        raise ValueError("installed codec refused")

    with pytest.raises(ValueError, match="installed codec"):
        RequestCeilings.compile(REQUEST).constrain(body(), caps(), validate_body=refuse)
    with pytest.raises(ValueError):
        RequestCeilings.compile({**REQUEST, "validator": "import something"})


@pytest.mark.parametrize("change", ["extra_unit", "missing_unit", "unknown_effect", "no_effect",
                                   "body_overlap", "unknown_field"])
def test_unbounded_or_conflicting_charge_shape_is_rejected(change):
    document = deepcopy(REQUEST)
    if change == "extra_unit":
        document["caps"]["image_usd"] = {"path": "/billing/image", "divisor": 1000000}
    elif change == "missing_unit":
        del document["caps"][UNITS[0]]
    elif change == "unknown_effect":
        document["constants"][0]["charge_components"] = ["unbounded_operations"]
    elif change == "no_effect":
        document["constants"][0]["charge_components"] = []
    elif change == "body_overlap":
        document["allowed"].append("billing")
    else:
        document["can_spend"] = True
    with pytest.raises(ValueError):
        RequestCeilings.compile(document)


@pytest.mark.parametrize("amounts", [caps(), caps(0, 0, 0), caps(1000001, 7654321, 123),
                                     caps(10**18, 10**18, 10**18)])
def test_reservation_and_affordability_match_unchanged_selected_model(amounts):
    shape = RequestCeilings.compile(REQUEST)
    legacy = SelectedModel("p", "m", "old", amounts, "digest", 32000)
    for output in (0, 1, 1000, 99999):
        assert shape.cost_upper_bound(amounts, 32000, output) == legacy.cost_upper_bound(output)
    for remaining in (0, 1, 100, 1000000, 10**25):
        assert (shape.affordable_output(amounts, 32000, remaining)
                == legacy.affordable_output(remaining))
    encoded = shape.constrain(body(), amounts, validate_body=validate)
    for index, (_, amount) in enumerate(amounts):
        assert Decimal(encoded["billing"]["ceilings"][str(index)]) * 10**6 == amount
    assert json.loads(json.dumps(encoded)) == encoded
