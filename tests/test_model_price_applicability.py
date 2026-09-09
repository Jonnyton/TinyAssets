"""Realistic public pricing shapes; synthetic account/inference, no live claim."""

import pytest

from tests.test_catalog_decoders import decode, row
from tinyassets.providers.discovery_protocols import discovery_protocol
from tinyassets.providers.model_policy import Catalog, Charge, ModelPolicy, order_models

CONTRACT = discovery_protocol("openrouter_user_models_v1")


def priced(pricing, *, outputs=("text",), cap=0):
    connection = decode(
        row(
            pricing=pricing,
            architecture={
                "input_modalities": ["text"],
                "output_modalities": list(outputs),
            },
        )
    )
    policy = ModelPolicy(
        0,
        "automatic",
        (),
        cost_caps=tuple(Charge(name, cap, True) for name in sorted(CONTRACT.price_components)),
    )
    order = order_models(
        Catalog("owner", "universe", (connection,)),
        policy,
        CONTRACT.text_interaction,
        owner_id="owner",
        universe_id="universe",
    )
    return connection.models[0].pricing, order


def test_optional_omission_is_not_invented_free_evidence():
    pricing, order = priced({"prompt": "0", "completion": "0"})
    assert order.candidates and not order.ineligible
    assert {c.component for c in pricing.charges} == {
        "input_million_tokens_usd",
        "output_million_tokens_usd",
    }
    caps = tuple((name, 0) for name in CONTRACT.price_components)
    body = CONTRACT.constrain_inference({"model": "future/new", "messages": []}, caps)
    assert body["provider"]["max_price"] == {
        "prompt": "0",
        "completion": "0",
        "request": "0",
        "image": "0",
    }


@pytest.mark.parametrize(
    "extra,price,eligible",
    [
        ("request", "0.01", False),
        ("request", None, False),
        ("web_search", "0", True),
        ("web_search", "0.001", False),
        ("input_cache_read", "0", True),
        ("input_cache_read", "0.000001", False),
        ("input_cache_write", "0.000002", False),
        ("input_cache_write_1h", "0.000002", True),
        ("internal_reasoning", "0.000001", False),
        ("new_fee", "0", False),
        ("new_fee", "0.01", False),
    ],
)
def test_extras_use_encoded_request_applicability(extra, price, eligible):
    pricing, order = priced({"prompt": "0", "completion": "0", extra: price})
    assert bool(order.candidates) is eligible
    assert "input_million_tokens_usd" in {c.component for c in pricing.charges}
    if not eligible:
        assert order.ineligible[0].component


@pytest.mark.parametrize("field", ["input_cache_read", "input_cache_write", "internal_reasoning"])
def test_cached_and_reasoning_tokens_must_fit_accepted_token_cap(field):
    assert priced({"prompt": "0.000001", "completion": "0.000001", field: "0.000001"}, cap=10**6)[
        1
    ].candidates
    assert not priced(
        {"prompt": "0.000001", "completion": "0.000001", field: "0.000002"}, cap=10**6
    )[1].candidates


@pytest.mark.parametrize(
    "outputs,extra,eligible",
    [
        (("text", "image"), {}, False),
        (("text", "audio"), {}, False),
        (("text", "video"), {}, False),
        (("text", "image"), {"image_output": "0"}, True),
        (("text", "image"), {"image_output": "0.001"}, False),
        (("text", "audio"), {"audio_output": "0"}, True),
        (("text", "audio"), {"audio_output": "0.000001"}, False),
    ],
)
def test_output_media_cannot_escape_text_reservation(outputs, extra, eligible):
    assert (
        bool(priced({"prompt": "0", "completion": "0", **extra}, outputs=outputs)[1].candidates)
        is eligible
    )


def test_all_conditional_overrides_contribute_conservative_maximum():
    pricing, order = priced(
        {
            "prompt": "0.000001",
            "completion": "0.000001",
            "discount": 0.5,
            "overrides": [
                {"min_prompt_tokens": 100000, "prompt": "0.000003"},
                {"utc_start": 400, "utc_end": 600, "prompt": "0.000002"},
            ],
        },
        cap=10**6,
    )
    assert not order.candidates
    assert {c.component: c.amount_micros for c in pricing.charges}[
        "input_million_tokens_usd"
    ] == 3 * 10**6


@pytest.mark.parametrize(
    "overrides", [None, {}, [None], [{"prompt": "invalid"}], [{"new_fee": "0"}]]
)
def test_malformed_or_unknown_overrides_do_not_inherit_free(overrides):
    assert not priced({"prompt": "0", "completion": "0", "overrides": overrides})[1].candidates


def test_override_does_not_supply_missing_mandatory_base():
    assert not priced({"completion": "0", "overrides": [{"prompt": "0"}]})[1].candidates


def test_negative_variable_router_price_is_not_free():
    assert not priced({"prompt": "-1", "completion": "-1"})[1].candidates


@pytest.mark.parametrize("model", ["vendor/x:online", "@preset/custom", "vendor/@preset/custom"])
def test_server_indirections_cannot_enable_unbounded_plugins(model):
    with pytest.raises(ValueError, match="indirection"):
        CONTRACT.constrain_inference(
            {"model": model, "messages": []}, tuple((n, 0) for n in CONTRACT.price_components)
        )


@pytest.mark.parametrize(
    "message",
    [
        {"role": "user", "content": [{"type": "text", "text": "hello"}]},
        {"role": "user", "content": "hello", "cache_control": {}},
        {"role": "tool", "content": "hello"},
        {"role": "user", "content": None},
    ],
)
def test_excluded_fees_require_actual_plain_string_encoder_shape(message):
    with pytest.raises(ValueError, match="message shape"):
        CONTRACT.constrain_inference(
            {"model": "vendor/x", "messages": [message]},
            tuple((n, 0) for n in CONTRACT.price_components),
        )


def test_missing_optional_price_cannot_bypass_missing_accepted_cap():
    connection = decode(row(pricing={"prompt": "0", "completion": "0"}))
    policy = ModelPolicy(
        0,
        "automatic",
        (),
        cost_caps=tuple(
            Charge(name, 0, True) for name in CONTRACT.text_interaction.charge_components
        ),
    )
    order = order_models(
        Catalog("owner", "universe", (connection,)),
        policy,
        CONTRACT.text_interaction,
        owner_id="owner",
        universe_id="universe",
    )
    assert not order.candidates
    assert order.ineligible[0].reason == "exceeds_cost_cap"


def test_generic_advisory_caller_does_not_ignore_newly_decoded_extra_price():
    from tests.test_catalog_decoders import order

    item = row()
    item["pricing"]["web_search"] = "0.001"
    result = order(decode(item))
    assert not result.candidates
    assert result.ineligible[0].reason == "unknown_price_component"
    assert result.ineligible[0].component == "web_search_usd"
