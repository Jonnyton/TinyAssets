"""Unfamiliar wire layouts through the shared interpreter; not live authority."""

from copy import deepcopy
from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta, timezone

import pytest

from tinyassets.providers.discovery_catalogue import (
    BenchmarkShape,
    CatalogDecodeError,
    CatalogueShape,
    Pointer,
)
from tinyassets.providers.model_policy import ConnectionModels

CATALOGUE = {
    "rows": "/inventory/items", "count": "/inventory/count", "next_page": "/page/next",
    "model_id": "/identity/key", "join_key": "/identity/evaluation",
    "inputs": "/features/in", "outputs": "/features/out", "tools": "/features/functions",
    "contexts": ["/limits/0", "/limits/1"], "prices": "/tariff",
    "default_model": "/preferred",
}
PRICES = {
    "fields": {
        "input": {"component": "input_million_tokens_usd", "scale": 10**6},
        "output": {"component": "output_million_tokens_usd", "scale": 10**6},
        "call": {"component": "request_usd", "scale": 10**6},
    },
    "required": ["input", "output", "call"], "overrides": "/tiers",
    "metadata": ["tiers"], "conditions": ["when"],
}
BENCHMARK = {
    "rows": "/evaluations", "source": "independent-lab/schema-v3",
    "source_field": "/measurement/source", "model_id": "/subject",
    "timestamp": "/measured_at", "agentic": "/measurement/agent_score",
    "general": "/measurement/reason_score", "scale": 1000,
}
CONNECTION = ConnectionModels("owned-source", "custom-http", "http", "fresh", False, False, ())
NOW = datetime(2026, 9, 11, tzinfo=timezone.utc)


def payload():
    return {
        "inventory": {"count": 1, "items": [{
            "identity": {"key": "unseen:model-v7", "evaluation": "evaluation/7"},
            "features": {"in": ["text"], "out": ["text"], "functions": True},
            "limits": [12345, 8000],
            "tariff": {"input": "1.234567", "output": "2", "call": "0",
                       "tiers": [{"input": "1.5", "when": "peak"}]},
        }]},
        "page": {"next": None}, "preferred": "unseen:model-v7",
        "owner_filtered": True, "executor_tools": True,
        "authenticated_account_id": "invented", "source_kind": "subscription",
    }


def test_unfamiliar_layout_and_models_need_no_preset_or_brand_registration():
    catalogue = CatalogueShape.compile(CATALOGUE, PRICES)
    benchmark = BenchmarkShape.compile(BENCHMARK)
    scores = benchmark.decode({"measured_at": NOW.isoformat(), "evaluations": [{
        "subject": "evaluation/7", "measurement": {
            "source": "independent-lab/schema-v3", "agent_score": 14.25, "reason_score": "22.5",
        },
    }]}, now=NOW, max_age=timedelta(days=1))
    wire = payload()
    before = deepcopy(wire)
    decoded = catalogue.decode(wire, connection=CONNECTION, benchmarks=scores)
    model = decoded.models[0]
    assert model.model_id == "unseen:model-v7"
    assert model.context_tokens == 8000 and model.tools is True
    assert model.modalities == model.output_modalities == frozenset({"text"})
    assert model.scores.agentic == 14250 and model.scores.general == 22500
    assert model.scores.source == "independent-lab/schema-v3"
    assert model.scores.freshness == "fresh"
    assert {charge.component: charge.amount_micros for charge in model.pricing.charges} == {
        "input_million_tokens_usd": 1500000, "output_million_tokens_usd": 2000000,
        "request_usd": 0,
    }
    assert decoded.default_model_id == model.model_id
    assert replace(decoded, models=(), default_model_id=None) == CONNECTION
    assert wire == before


def test_shape_is_immutable_and_detached_from_input_documents():
    spec, prices = deepcopy(CATALOGUE), deepcopy(PRICES)
    shape = CatalogueShape.compile(spec, prices)
    spec["model_id"] = "/malicious"
    prices["fields"]["input"]["scale"] = 1
    assert shape.decode(payload(), connection=CONNECTION).models[0].model_id == "unseen:model-v7"
    with pytest.raises(FrozenInstanceError):
        shape.tools_member = "changed"


@pytest.mark.parametrize("path,value,expected", [
    ("", [1], [1]), ("/a~1b/~0/0", {"a/b": {"~": [4]}}, 4),
    ("/01", [1, 2], None), ("/01", {"01": 3}, 3),
    ("/-", [1], None), ("/99999999999", [1], None),
    ("/x/y", {"x": None}, None), ("/", {"": 5}, 5),
])
def test_pointer_is_bounded_data_lookup(path, value, expected):
    assert Pointer.compile(path).read(value) == expected


@pytest.mark.parametrize("path", [None, 1, "x", "/~", "/~3", "/" + "x" * 512, "/x" * 17])
def test_invalid_pointer_refuses_without_interpreting_expressions(path):
    with pytest.raises(ValueError):
        Pointer.compile(path)


@pytest.mark.parametrize("change", [
    {"unknown": True}, {"tools_member": None}, {"contexts": []},
    {"contexts": ["/a"] * 17}, {"owner_filtered": True},
    {"executor_tools": True}, {"source_kind": "local"},
])
def test_catalogue_shape_cannot_publish_flags_or_unknown_instructions(change):
    with pytest.raises(ValueError):
        CatalogueShape.compile({**CATALOGUE, **change}, PRICES)


@pytest.mark.parametrize("change", [
    {"fields": {}}, {"required": ["missing"]}, {"metadata": ["input"]},
    {"conditions": ["output"]}, {"required": ["input", "input"]},
    {"fields": {"input": {"component": "input_million_tokens_usd", "scale": True}}},
    {"fields": {"input": {"component": "input_million_tokens_usd", "scale": 3}}},
    {"fields": {"input": {"component": "input_million_tokens_usd", "scale": 10**20}}},
    {"fields": {"input": {"component": "unit", "scale": 1},
                "alias": {"component": "unit", "scale": 1}}},
])
def test_invalid_price_mapping_is_not_compiled(change):
    with pytest.raises(ValueError):
        CatalogueShape.compile(CATALOGUE, {**PRICES, **change})


@pytest.mark.parametrize("tariff", [
    {"input": "0", "output": "0", "call": "0", "new_fee": "0"},
    {"input": "0", "output": "0", "call": "0", "tiers": None},
    {"input": "0", "output": "0", "call": "0", "tiers": [{"input": "bad"}]},
    {"input": "0.0000001", "output": "0", "call": "0"},
    {"input": "0", "output": "0"},
])
def test_unknown_or_unrepresentable_prices_remain_ineligible_data(tariff):
    wire = payload()
    wire["inventory"]["items"][0]["tariff"] = tariff
    pricing = CatalogueShape.compile(CATALOGUE, PRICES).decode(
        wire, connection=CONNECTION,
    ).models[0].pricing
    assert pricing.unknown_components and not pricing.unmetered


@pytest.mark.parametrize("default", [None, [], {}, 0, "not-in-catalogue", " padded "])
def test_unknown_default_does_not_invent_a_choice(default):
    wire = payload()
    wire["preferred"] = default
    assert CatalogueShape.compile(CATALOGUE, PRICES).decode(
        wire, connection=CONNECTION,
    ).default_model_id is None


def test_missing_and_explicit_null_override_are_distinct_even_at_array_path():
    shape = CatalogueShape.compile(CATALOGUE, {**PRICES, "overrides": "/tiers/0"})
    wire = payload()
    tariff = wire["inventory"]["items"][0]["tariff"]
    tariff["tiers"] = [[]]
    assert not shape.decode(wire, connection=CONNECTION).models[0].pricing.unknown_components
    tariff["tiers"] = [None]
    assert shape.decode(wire, connection=CONNECTION).models[0].pricing.unknown_components
    tariff["tiers"] = None
    assert shape.decode(wire, connection=CONNECTION).models[0].pricing.unknown_components
    tariff["tiers"] = []
    assert not shape.decode(wire, connection=CONNECTION).models[0].pricing.unknown_components


def test_incomplete_and_oversized_results_do_not_publish_a_prefix():
    shape = CatalogueShape.compile(CATALOGUE, PRICES)
    for mutation in ("count", "next", "rows", "overrides"):
        wire = payload()
        if mutation == "count":
            wire["inventory"]["count"] = 2
        elif mutation == "next":
            wire["page"]["next"] = "https://untrusted.invalid/next"
        elif mutation == "rows":
            wire["inventory"]["items"] *= 10001
        else:
            wire["inventory"]["items"][0]["tariff"]["tiers"] *= 129
        with pytest.raises(CatalogDecodeError):
            shape.decode(wire, connection=CONNECTION)
