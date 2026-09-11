"""Frozen-before/data-after differential proof for installed compatibility."""

import json
from copy import deepcopy
from dataclasses import replace
from datetime import timedelta
from itertools import permutations

import pytest

from tests import _legacy_discovery_protocol_oracle as before
from tests.test_catalog_decoders import CONNECTION, NOW, row
from tests.test_discovery_contract import descriptor
from tinyassets.providers.discovery_contract import SourceContract
from tinyassets.providers.discovery_presets import (
    bundled_discovery_documents,
    compatibility_document,
)
from tinyassets.providers.discovery_protocols import DiscoveryProtocol, discovery_protocol
from tinyassets.providers.model_policy import Catalog, Charge, ModelPolicy, order_models

KEY = "openrouter_user_models_v1"
OLD = before._PROTOCOLS[KEY]
NEW = discovery_protocol(KEY)
CAPS = tuple((name, 123456789) for name in sorted(NEW.price_components))


def outcome(call):
    try:
        return True, call()
    except (ValueError, TypeError, KeyError, AttributeError):
        return False, None


@pytest.mark.parametrize("model", ["opaque/model", "", " ", "新しい/model", "x" * 201,
                                  "@preset/name", "p/@preset/name", "a:online", "online"])
@pytest.mark.parametrize("tokens", [None, 0, 1000, True, "1000"])
def test_legacy_request_bytes_and_exclusions_are_preserved(model, tokens):
    body = {"model": model, "messages": [{"role": "user", "content": "exact 🪐"}],
            "temperature": None}
    if tokens is not None:
        body["max_tokens"] = tokens
    original = deepcopy(body)
    old = outcome(lambda: OLD.constrain_inference(body, CAPS))
    new = outcome(lambda: NEW.constrain_inference(body, CAPS))
    assert old == new
    if old[0]:
        assert json.dumps(old[1]) == json.dumps(new[1])
    assert body == original


@pytest.mark.parametrize("caps", [CAPS, list(CAPS), CAPS[:-1], CAPS + (CAPS[0],),
                                tuple((key, 10**18) for key, _ in CAPS),
                                tuple((key, True) for key, _ in CAPS),
                                tuple((key, -1) for key, _ in CAPS),
                                tuple((key, 10**18 + 1) for key, _ in CAPS)])
def test_legacy_ceiling_components_and_decimal_strings_are_preserved(caps):
    body = {"model": "new-model", "messages": []}
    assert outcome(lambda: OLD.constrain_inference(body, caps)) == outcome(
        lambda: NEW.constrain_inference(body, caps),
    )


def test_legacy_python_containers_do_not_silently_acquire_new_semantics():
    class Text(str):
        pass

    class Message(dict):
        pass

    body = Message(model=Text("future/model"), messages=[Message(role="user", content=Text("hi"))])
    assert OLD.constrain_inference(body, CAPS) == NEW.constrain_inference(body, CAPS)
    assert outcome(lambda: OLD.constrain_inference(body, iter(CAPS))) == outcome(
        lambda: NEW.constrain_inference(body, iter(CAPS)),
    )


@pytest.mark.parametrize("caps", list(permutations(CAPS)))
def test_every_legacy_cap_order_preserves_literal_request_serialization(caps):
    body = {"messages": [{"role": "user", "content": "exact 🪐"}],
            "model": "future", "max_tokens": 1000}
    old = OLD.constrain_inference(body, caps)
    new = NEW.constrain_inference(body, caps)
    assert json.dumps(old, ensure_ascii=False) == json.dumps(new, ensure_ascii=False)


@pytest.mark.parametrize("field", list(before._PRICE_FIELDS))
@pytest.mark.parametrize("value", ["0", "1", "0.000000000001", "0.0000000000001",
                                  None, True, 1.25, "NaN", "-1", "unknown"])
def test_every_advertised_price_and_eligibility_matches_prior_contract(field, value):
    item = row()
    item["pricing"][field] = value
    payload = {"data": [item]}
    old = OLD.model_decoder(payload, connection=CONNECTION)
    new = NEW.model_decoder(payload, connection=CONNECTION)
    assert old == new
    policy = ModelPolicy(0, "automatic", (), cost_caps=tuple(Charge(k, v, True) for k, v in CAPS))
    for tools in (False, True):
        results = [order_models(Catalog("owner", "u", (catalogue,)), policy,
                                replace(contract.text_interaction, needs_tools=tools),
                                owner_id="owner", universe_id="u")
                   for catalogue, contract in ((old, OLD), (new, NEW))]
        assert results[0] == results[1]


@pytest.mark.parametrize("status", [None, True, 200, 400, 402, 418, 429, 500, 503])
@pytest.mark.parametrize("headers", [None, {}, {"retry-after": "60"}, {"Retry-After": "bad"}])
def test_capacity_and_retry_scope_match(status, headers):
    assert OLD.capacity_decoder(status, headers) == NEW.capacity_decoder(status, headers)


@pytest.mark.parametrize("cost", ["0", "1e-99", "1e-9999999", "0.0000010000000000000001",
                                 "1.234567", "9223372036854.775807", "9223372036854.775808",
                                 "-1", "null", "true", '"0"', "NaN", "Infinity",
                                 "0." + "0" * 90 + "1"])
@pytest.mark.parametrize("extra", ["", ',"other":NaN'])
def test_original_usage_number_behavior_is_preserved(cost, extra):
    raw = '{"usage":{"cost":' + cost + '}' + extra + '}'
    assert OLD.usage_decoder(raw) == NEW.usage_decoder(raw)


def test_full_interaction_transport_and_benchmarks_remain_identical():
    assert OLD.text_interaction == NEW.text_interaction
    assert OLD.price_components == NEW.price_components
    for name in ("catalogue_path", "catalogue_query", "benchmark_path", "auth_scheme",
                 "account_filtered", "inference_protocol", "ranking_source"):
        assert getattr(OLD, name) == getattr(NEW, name)
    payload = {"data": [{"model_permaslug": "future/model", "source": "artificial-analysis",
                         "agentic_index": 1.25, "intelligence_index": 2.5}],
               "meta": {"as_of": NOW.isoformat()}}
    kwargs = {"now": NOW, "max_age": timedelta(days=1)}
    assert OLD.benchmark_decoder(payload, **kwargs) == NEW.benchmark_decoder(payload, **kwargs)


def test_bundled_data_detaches_and_alternate_layout_uses_shared_interpreters():
    document = compatibility_document()
    document["transport"]["catalogue_path"] = "/different/catalogue"
    document["inference"]["caps"]["image_usd"]["path"] = "/ceilings/image"
    document["capacity"]["cases"] = [{"status": 418, "scope": "model",
                                       "reason": "provider_overloaded"}]
    other = DiscoveryProtocol.from_bundled_document(document)
    encoded = other.constrain_inference({"model": "future", "messages": []}, CAPS)
    assert encoded["ceilings"]["image"] == "123.456789"
    assert other.capacity_decoder(418, None).scope == "model"
    assert NEW.capacity_decoder(418, None) is None
    original = bundled_discovery_documents()[KEY]["transport"]["catalogue_path"]
    assert original != "/different/catalogue"


@pytest.mark.parametrize("key", ["legacy", "compatibility_default", "account_filtered"])
def test_user_document_cannot_enable_bundled_trust_or_compatibility(key):
    document = descriptor()
    document[key] = True
    with pytest.raises(ValueError):
        SourceContract.compile(document)
