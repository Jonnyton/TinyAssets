"""Legacy discovery names backed by the shared bounded data interpreter.

These preset declarations preserve the existing endpoint contract. New source
publication must still validate the complete source contract and authority.
"""

from tinyassets.providers.discovery_catalogue import (
    BenchmarkShape,
    CatalogDecodeError,
    CatalogueShape,
)

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
