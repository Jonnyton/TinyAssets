"""Frozen pre-migration executable specification from fe81526e (September11).

Kept in tests only for differential compatibility, never used by production.
"""

import json
from dataclasses import dataclass
from decimal import ROUND_CEILING, Decimal, InvalidOperation, localcontext
from typing import Callable
from urllib.parse import urlsplit

from tinyassets.providers import agent_chat_codec as codec
from tinyassets.providers.discovery_catalogue import (
    BenchmarkShape,
    CatalogDecodeError,
    CatalogueShape,
)
from tinyassets.providers.model_policy import ConnectionModels, Interaction, Scores

_PRICE_FIELDS = {
    "prompt": ("input_million_tokens_usd", 10**12),
    "completion": ("output_million_tokens_usd", 10**12),
    "request": ("request_usd", 10**6),
    "image": ("image_usd", 10**6),
    "audio": ("audio_million_tokens_usd", 10**12),
    "audio_output": ("audio_output_million_tokens_usd", 10**12),
    "image_output": ("image_output_usd", 10**6),
    "image_token": ("image_million_tokens_usd", 10**12),
    "input_audio_cache": ("input_audio_cache_million_tokens_usd", 10**12),
    "input_cache_read": ("input_cache_read_million_tokens_usd", 10**12),
    "input_cache_write": ("input_cache_write_million_tokens_usd", 10**12),
    "input_cache_write_1h": ("input_cache_write_1h_million_tokens_usd", 10**12),
    "internal_reasoning": ("reasoning_million_tokens_usd", 10**12),
    "web_search": ("web_search_usd", 10**6),
}

_CATALOGUE = CatalogueShape.compile(
    {
        "rows": "/data", "count": "/total_count", "next_page": "/links/next",
        "model_id": "/id", "join_key": "/canonical_slug",
        "inputs": "/architecture/input_modalities",
        "outputs": "/architecture/output_modalities",
        "tools": "/supported_parameters", "tools_member": "tools",
        "contexts": ["/context_length", "/top_provider/context_length"],
        "prices": "/pricing",
    },
    {
        "fields": {name: {"component": component, "scale": scale}
                   for name, (component, scale) in _PRICE_FIELDS.items()},
        "required": ["prompt", "completion"],
        "overrides": "/overrides",
        "metadata": ["discount", "overrides"],
        "conditions": ["min_prompt_tokens", "utc_days", "utc_start", "utc_end"],
    },
    legacy=True,
)
_BENCHMARK = BenchmarkShape.compile({
    "rows": "/data", "count": "/total_count", "next_page": "/links/next",
    "source": "artificial-analysis", "source_field": "/source",
    "model_id": "/model_permaslug", "timestamp": "/meta/as_of",
    "agentic": "/agentic_index", "general": "/intelligence_index", "scale": 10**6,
}, legacy=True)


def decode_openrouter_models(payload, *, connection, benchmarks=None):
    """Decode with the unchanged preset, preserving caller-supplied provenance."""
    return _CATALOGUE.decode(payload, connection=connection, benchmarks=benchmarks)


def decode_openrouter_benchmarks(payload, *, now, max_age, source="artificial-analysis"):
    """Preserve the legacy source restriction and exact score/freshness rules."""
    if source != _BENCHMARK.source:
        raise CatalogDecodeError("unsupported comparable benchmark source")
    return _BENCHMARK.decode(payload, now=now, max_age=max_age)


def openrouter_usage_cost(raw_json: str) -> int | None:
    """Documented account charge in USD -> ceiling micros, never a zero guess.

    Parse the original numeric token as Decimal so float conversion cannot erase
    a sub-micro charge. This is observation, not permission to spend.
    """
    try:
        value = json.loads(raw_json, parse_float=Decimal, object_pairs_hook=codec._pairs)
        usage = value.get("usage")
        cost = usage.get("cost") if isinstance(usage, dict) else None
        if type(cost) not in (int, Decimal):
            return None
        cost = Decimal(cost)
        if not cost.is_finite() or cost < 0 or cost > Decimal("9223372036854.775807"):
            return None
        if 0 < cost < Decimal("0.000001"):
            return 1
        with localcontext() as context:
            context.prec = max(32, len(cost.as_tuple().digits) + 7)
            return int((cost * 10**6).to_integral_value(rounding=ROUND_CEILING))
    except (ValueError, TypeError, AttributeError, InvalidOperation, OverflowError):
        return None






@dataclass(frozen=True, slots=True)
class DiscoveryProtocol:
    catalogue_path: str
    catalogue_query: str
    benchmark_path: str
    auth_scheme: str
    account_filtered: bool
    model_decoder: Callable[..., ConnectionModels]
    benchmark_decoder: Callable[..., dict[str, Scores]]
    inference_protocol: str
    price_components: frozenset[str]
    constrain_inference: Callable[..., dict]
    text_interaction: Interaction
    capacity_decoder: Callable | None = None
    ranking_source: str | None = None
    usage_decoder: Callable[[str], int | None] | None = None

    def validate_urls(self, catalogue_url: str, benchmark_url: str) -> None:
        catalogue = urlsplit(catalogue_url)
        if (catalogue.path, catalogue.query) != (self.catalogue_path, self.catalogue_query):
            raise ValueError("discovery catalogue URL does not match the protocol")
        if benchmark_url:
            benchmark = urlsplit(benchmark_url)
            if benchmark.path != self.benchmark_path or benchmark.query:
                raise ValueError("discovery benchmark URL does not match the protocol")


_OPENROUTER_PRICE_FIELDS = {
    "input_million_tokens_usd": "prompt",
    "output_million_tokens_usd": "completion",
    "request_usd": "request",
    "image_usd": "image",
}


def _openrouter_constrained_body(body: dict, caps: tuple[tuple[str, int], ...]) -> dict:
    # Existing text encoder has no server plugins, router-selected models array,
    # or user-controlled provider overrides. Never merge those into a bounded call.
    agent = "tools" in body or "tool_choice" in body
    if set(body) - {"model", "messages", "temperature", "max_tokens", "tools", "tool_choice"}:
        raise ValueError("unsupported fields in price-constrained inference")
    model = body.get("model")
    messages = body.get("messages")
    if not isinstance(model, str) or "@preset/" in model or model.endswith(":online"):
        raise ValueError("unsupported model indirection in price-constrained inference")
    if agent:
        from tinyassets.providers.agent_chat_codec import validate_agent_body

        validate_agent_body(body)
    elif not isinstance(messages, list) or any(
        not isinstance(message, dict)
        or set(message) != {"role", "content"}
        or message["role"] not in ("system", "user", "assistant")
        or not isinstance(message["content"], str)
        for message in messages
    ):
        raise ValueError("unsupported message shape in price-constrained inference")
    if (
        len(caps) != len(_OPENROUTER_PRICE_FIELDS)
        or {key for key, _ in caps} != _OPENROUTER_PRICE_FIELDS.keys()
    ):
        raise ValueError("incomplete inference price bounds")
    prices = {}
    for component, micros in caps:
        if type(micros) is not int or micros < 0:
            raise ValueError("invalid inference price bound")
        if micros > 10**18:
            raise ValueError("inference price bound is too large")
        # Exact decimal string, independent of Decimal context or binary floats.
        whole, fraction = divmod(micros, 10**6)
        value = f"{whole}.{fraction:06d}".rstrip("0").rstrip(".")
        prices[_OPENROUTER_PRICE_FIELDS[component]] = value
    return {**body, "provider": {"max_price": prices, "require_parameters": True}}


def _openrouter_capacity(status, headers):
    from tinyassets.providers.model_capacity import CapacitySignal, retry_after_seconds

    if type(status) is not int:
        return None
    kind = {
        402: ("account", "provider_credit_exhausted"),
        429: ("unknown", "provider_rate_limited"),
        503: ("model", "provider_overloaded"),
    }.get(status)
    return None if kind is None else CapacitySignal(*kind, retry_after_seconds(headers))


_PROTOCOLS = {
    "openrouter_user_models_v1": DiscoveryProtocol(
        "/api/v1/models/user",
        "output_modalities=all",
        "/api/v1/benchmarks",
        "bearer",
        True,
        decode_openrouter_models,
        decode_openrouter_benchmarks,
        "openai_chat",
        frozenset(_OPENROUTER_PRICE_FIELDS),
        _openrouter_constrained_body,
        Interaction(
            needs_tools=False,
            modalities=frozenset({"text"}),
            charge_components=frozenset({"input_million_tokens_usd", "output_million_tokens_usd"}),
            min_context=1,
            ceiling_components=frozenset(_OPENROUTER_PRICE_FIELDS),
            excluded_components=frozenset(
                {
                    "audio_million_tokens_usd",
                    "image_million_tokens_usd",
                    "input_audio_cache_million_tokens_usd",
                    "input_cache_write_1h_million_tokens_usd",
                }
            ),
            extra_price_bounds=(
                ("input_cache_read_million_tokens_usd", "input_million_tokens_usd"),
                ("input_cache_write_million_tokens_usd", "input_million_tokens_usd"),
                ("reasoning_million_tokens_usd", "output_million_tokens_usd"),
                ("web_search_usd", None),
                ("image_output_usd", None),
                ("audio_output_million_tokens_usd", None),
            ),
            output_price_components=(
                ("image", "image_output_usd"),
                ("audio", "audio_output_million_tokens_usd"),
            ),
        ),
        capacity_decoder=_openrouter_capacity,
        ranking_source="artificial-analysis",
        usage_decoder=openrouter_usage_cost,
    )
}


def discovery_protocol(protocol: str) -> DiscoveryProtocol:
    try:
        return _PROTOCOLS[protocol]
    except (KeyError, TypeError):
        raise ValueError("model discovery protocol is not supported") from None
