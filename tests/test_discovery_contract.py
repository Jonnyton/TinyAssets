"""One unfamiliar source composes all interpreters without registry mutation.

No connection publication, network authority or live provider claims.
"""

from copy import deepcopy
from dataclasses import FrozenInstanceError, replace
from datetime import timedelta
from decimal import Decimal

import pytest

from tests.test_discovery_catalogue_shapes import (
    BENCHMARK,
    CATALOGUE,
    CONNECTION,
    NOW,
    PRICES,
    payload,
)
from tests.test_discovery_execution_shapes import REQUEST, UNITS, body, caps
from tests.test_discovery_quantities import STANDARD
from tinyassets.providers.discovery_contract import SourceContract
from tinyassets.providers.protocol_encoders import PROTOCOLS


def descriptor():
    document = {
        "version": 1,
        "transport": {"protocol": "openai_chat", "auth_scheme": "bearer",
                      "catalogue_path": "/my/catalogue", "catalogue_query": "owned=1",
                      "benchmark_path": "/my/evaluations"},
        "catalogue": deepcopy(CATALOGUE), "prices": deepcopy(PRICES),
        "benchmark": {**BENCHMARK, "score_schema": "index-v3"},
        "inference": deepcopy(REQUEST), "quantity_model": deepcopy(STANDARD),
        "extension_quantities": {"/billing/enforce": "quantity_neutral"},
        "charge_bindings": dict(zip(UNITS, ("input_tokens", "output_tokens", "requests"))),
        "capacity": {"cases": [{"status": 418, "scope": "unknown",
                                 "reason": "provider_rate_limited"}], "retry_after": True},
        "usage": {"cost": "/meter/usd", "encoding": "number", "scale": 10**6},
        "price_bound_basis": "source_request_caps",
    }
    document["inference"]["constants"].append({
        "path": "/samples", "value": 8, "charge_components": [UNITS[1]],
    })
    document["extension_quantities"]["/samples"] = ["output_tokens"]
    document["quantity_model"]["quantities"]["output_tokens"]["output"] = 8
    return document


def test_unfamiliar_source_composes_catalogue_ranking_request_cost_usage_capacity():
    original_registry = dict(PROTOCOLS)
    contract = SourceContract.compile(descriptor())
    contract.validate_urls("https://owned.example/my/catalogue?owned=1",
                           "https://owned.example/my/evaluations")
    scores = contract.decode_benchmarks({"measured_at": NOW.isoformat(), "evaluations": [{
        "subject": "evaluation/7", "measurement": {
            "source": BENCHMARK["source"], "agent_score": Decimal("14.25"),
            "reason_score": "22.5",
        },
    }]}, now=NOW, max_age=timedelta(days=1))
    models = contract.decode_models(payload(), connection=CONNECTION, benchmarks=scores)
    model = models.models[0]
    assert model.model_id == "unseen:model-v7"
    assert model.scores.agentic == 14250 and model.scores.source == contract.ranking_source
    assert models.owner_filtered is False and models.executor_tools is False
    assert models.authenticated_account_id is None and models.source_kind == "http"
    _, request = contract.wire.encode(prompt="hello", system="", model=model.model_id,
                                     max_tokens=1000)
    limits = caps(0, 10_000_000, 0)
    envelope = contract.constrain_inference(request, limits)
    contract.validate_envelope(request, envelope, limits)
    assert envelope["samples"] == 8 and "samples" not in request
    assert contract.cost_upper_bound(limits, model.context_tokens, 1000) == 80_000
    assert contract.affordable_output(limits, model.context_tokens, 1000, 10_000) == 125
    assert contract.usage.decode('{"meter":{"usd":0.00000000000001}}') == 1
    assert contract.usage.decode('{}') is None
    assert contract.capacity.decode(418, {"Retry-After": "9"}).retry_after_s == 9
    assert PROTOCOLS == original_registry  # No dynamically installed service adapter.


def test_installed_agent_wire_retains_tool_validation():
    document = descriptor()
    document["inference"]["allowed"] += ["tools", "tool_choice"]
    contract = SourceContract.compile(document)
    codec = contract.wire.agent_factory()
    _, request = codec.encode(prompt="hello", system="", source_ref="owned",
                              model="unseen:model-v7", max_tokens=1000, tools=[{
                                  "type": "function", "function": {"name": "read",
                                    "description": "Read", "parameters": {"type": "object"}},
                              }])
    envelope = contract.constrain_inference(request, caps())
    contract.validate_envelope(request, envelope, caps())
    assert envelope["tools"] == request["tools"]
    request["tools"][0]["function"]["parameters"] = "not an object"
    with pytest.raises(ValueError):
        contract.constrain_inference(request, caps())


@pytest.mark.parametrize("change", ["new_field", "protected", "bool_integer", "price",
                                   "nested", "missing"])
def test_final_envelope_is_exact_not_merely_compatible(change):
    contract = SourceContract.compile(descriptor())
    request = body()
    envelope = contract.constrain_inference(request, caps())
    if change == "new_field":
        envelope["unbounded"] = True
    elif change == "protected":
        envelope["model"] = "different"
    elif change == "bool_integer":
        envelope["billing"]["enforce"]["strict"] = 1
    elif change == "price":
        envelope["billing"]["ceilings"]["0"] = "99"
    elif change == "nested":
        envelope["messages"][0]["content"] = "different"
    else:
        del envelope["samples"]
    with pytest.raises(ValueError, match="final envelope"):
        contract.validate_envelope(request, envelope, caps())


@pytest.mark.parametrize("change", ["no_effect", "extra_effect", "wrong_effect", "zero_effect",
                                   "unknown_charge", "wrong_unit", "no_base", "wire_field",
                                   "wire_allow", "missing_price", "unknown_wire", "tariff",
                                   "trust", "version", "benchmark", "benchmark_path",
                                   "benchmark_schema", "benchmark_type"])
def test_cross_component_gaps_refuse(change):
    document = descriptor()
    if change == "no_effect":
        del document["extension_quantities"]["/samples"]
    elif change == "extra_effect":
        document["extension_quantities"]["/nothing"] = "quantity_neutral"
    elif change == "wrong_effect":
        document["extension_quantities"]["/samples"] = ["requests"]
    elif change == "zero_effect":
        document["extension_quantities"]["/samples"] = []
    elif change == "unknown_charge":
        document["prices"]["fields"]["image"] = {"component": "image_usd", "scale": 10**6}
    elif change == "wrong_unit":
        document["charge_bindings"][UNITS[1]] = "requests"
    elif change == "no_base":
        document["quantity_model"]["quantities"]["requests"]["per_attempt"] = 0
    elif change == "wire_field":
        document["inference"]["constants"][1]["path"] = "/tool_choice"
    elif change == "wire_allow":
        document["inference"]["allowed"].append("invented")
    elif change == "missing_price":
        document["prices"]["required"] = ["input"]
    elif change == "unknown_wire":
        document["transport"]["protocol"] = "uninstalled-wire"
    elif change == "tariff":
        document["price_bound_basis"] = "owner_tariff"
    elif change == "trust":
        document["trusted"] = True
    elif change == "version":
        document["version"] = True
    elif change == "benchmark":
        del document["benchmark"]
    elif change == "benchmark_path":
        document["transport"]["benchmark_path"] = ""
    elif change == "benchmark_schema":
        del document["benchmark"]["score_schema"]
    else:
        document["benchmark"] = []
    with pytest.raises(ValueError):
        SourceContract.compile(document)


def test_missing_installed_validator_cannot_be_supplied_by_remote_fields(monkeypatch):
    document = descriptor()
    name = document["transport"]["protocol"]
    monkeypatch.setitem(PROTOCOLS, name, replace(PROTOCOLS[name], request_validator=None))
    with pytest.raises(ValueError, match="installed constrained"):
        SourceContract.compile(document)


def test_contract_identity_captures_all_semantics_and_detaches_caller_data():
    document = descriptor()
    compiled = SourceContract.compile(document)
    assert SourceContract.compile(dict(reversed(list(document.items())))).digest == compiled.digest
    document["quantity_model"]["quantities"]["output_tokens"]["output"] = 9
    assert SourceContract.compile(document).digest != compiled.digest
    assert compiled.quantities.bounds(1, 1) == (1, 8, 1)
    with pytest.raises(FrozenInstanceError):
        compiled.auth_scheme = "none"


@pytest.mark.parametrize("change", ["source", "score_schema", "scale"])
def test_ranking_identity_separates_incomparable_score_semantics(change):
    document = descriptor()
    original = SourceContract.compile(document)
    document["benchmark"][change] = 100 if change == "scale" else "different"
    assert SourceContract.compile(document).ranking_source != original.ranking_source


def test_benchmark_and_usage_are_optional_but_no_success_is_fabricated():
    document = descriptor()
    del document["benchmark"], document["usage"]
    document["transport"]["benchmark_path"] = ""
    compiled = SourceContract.compile(document)
    assert compiled.usage is None and compiled.ranking_source is None
    with pytest.raises(ValueError):
        compiled.decode_benchmarks({}, now=NOW, max_age=timedelta(days=1))


@pytest.mark.parametrize("body_patch", [{"max_tokens": True}, {"max_tokens": 0},
                                       {"temperature": float("nan")},
                                       {"temperature": 10**1000},
                                       {"messages": [{"role": "user", "content": []}]}])
def test_installed_structure_refuses_malformed_text_request(body_patch):
    with pytest.raises(ValueError):
        SourceContract.compile(descriptor()).constrain_inference({**body(), **body_patch}, caps())


@pytest.mark.parametrize("catalogue,benchmark", [
    ("https://x/my/catalogue?other=1", "https://x/my/evaluations"),
    ("https://x/other?owned=1", "https://x/my/evaluations"),
    ("https://x/my/catalogue?owned=1", ""),
    ("https://x/my/catalogue?owned=1", "https://x/my/evaluations?q=1"),
])
def test_url_shapes_cannot_change_with_the_response(catalogue, benchmark):
    with pytest.raises(ValueError):
        SourceContract.compile(descriptor()).validate_urls(catalogue, benchmark)


@pytest.mark.parametrize("bad", [float("nan"), {1: "not a JSON key"}, ("tuple",)])
def test_literal_extensions_are_json_data_only(bad):
    document = descriptor()
    document["inference"]["constants"][0]["value"] = bad
    with pytest.raises(ValueError):
        SourceContract.compile(document)


def test_literal_extension_nesting_is_explicitly_bounded():
    document = descriptor()
    nested = {}
    document["inference"]["constants"][0]["value"] = nested
    for _ in range(17):
        nested["nested"] = {}
        nested = nested["nested"]
    with pytest.raises(ValueError, match="nesting"):
        SourceContract.compile(document)
