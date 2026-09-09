"""Protocol-boundary discovery contracts, never a model-release catalogue.

Owners choose the granted host. Each adapter defines which path/query actually
has its account-filtered semantics; schema similarity cannot substitute for it.
"""

import math
from dataclasses import dataclass
from fractions import Fraction
from typing import Callable
from urllib.parse import urlsplit

from tinyassets.providers.catalog_decoders import (
    decode_openrouter_benchmarks,
    decode_openrouter_models,
)
from tinyassets.providers.model_policy import ConnectionModels, Scores


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
    if set(body) - {"model", "messages", "temperature", "max_tokens"}:
        raise ValueError("unsupported fields in price-constrained inference")
    if (
        len(caps) != len(_OPENROUTER_PRICE_FIELDS)
        or {key for key, _ in caps} != _OPENROUTER_PRICE_FIELDS.keys()
    ):
        raise ValueError("incomplete inference price bounds")
    prices = {}
    for component, micros in caps:
        if type(micros) is not int or micros < 0:
            raise ValueError("invalid inference price bound")
        # Wire units are USD/million tokens or USD/request/image. Never round a
        # user ceiling upward when converting exact integer micros to JSON float.
        bound = Fraction(micros, 10**6)
        try:
            value = float(bound)
        except OverflowError:
            raise ValueError("inference price bound is too large") from None
        if not math.isfinite(value):
            raise ValueError("inference price bound is too large")
        if Fraction(value) > bound:
            value = math.nextafter(value, 0.0)
        prices[_OPENROUTER_PRICE_FIELDS[component]] = value
    return {**body, "provider": {"max_price": prices, "require_parameters": True}}


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
    )
}


def discovery_protocol(protocol: str) -> DiscoveryProtocol:
    try:
        return _PROTOCOLS[protocol]
    except (KeyError, TypeError):
        raise ValueError("model discovery protocol is not supported") from None
