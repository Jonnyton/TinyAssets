"""Protocol-boundary discovery contracts, never a model-release catalogue.

Owners choose the granted host. Each adapter defines which path/query actually
has its account-filtered semantics; schema similarity cannot substitute for it.
"""

from dataclasses import dataclass
from typing import Callable
from urllib.parse import urlsplit

from tinyassets.providers.catalog_decoders import (
    decode_openrouter_benchmarks,
    decode_openrouter_models,
)
from tinyassets.providers.model_policy import ConnectionModels, Interaction, Scores


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
    )
}


def discovery_protocol(protocol: str) -> DiscoveryProtocol:
    try:
        return _PROTOCOLS[protocol]
    except (KeyError, TypeError):
        raise ValueError("model discovery protocol is not supported") from None
