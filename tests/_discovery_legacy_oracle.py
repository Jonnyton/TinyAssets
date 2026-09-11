# Frozen from 8b9ba65ce0551b3f59afa5a7d79d1dfef849dd34 before shared-contract rewrite.
# Keep this executable baseline independent of production decoder helpers.
"""Protocol-boundary catalogue decoding; no network, credential or authority IO.

Remote optional metadata is evidence, never execution configuration. Connection
identity, account filtering, executor capability and catalogue freshness come
from the caller's separately verified transport context, not response fields.
The output remains advisory and needs fresh admission before every attempt.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation, localcontext
from typing import Any

from tinyassets.providers.model_policy import (
    Charge,
    ConnectionModels,
    Freshness,
    Model,
    Pricing,
    Scores,
)


class CatalogDecodeError(ValueError):
    """A fixed, credential-free explanation of an unusable catalogue response."""


_PRICE_COMPONENTS = {
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


def _identifier(value: object) -> bool:
    return (
        isinstance(value, str)
        and 0 < len(value) <= 200
        and value.isprintable()
        and value == value.strip()
    )


def _exact_scaled(value: object, scale: int, *, string_only: bool) -> int | None:
    if string_only and not isinstance(value, str):
        return None
    if type(value) not in (str, int, float) or len(str(value)) > 80:
        return None
    try:
        with localcontext() as context:
            context.prec = 100
            amount = Decimal(str(value))
            if (
                not amount.is_finite()
                or amount < 0
                or amount.adjusted() > 18
                or (amount != 0 and amount.adjusted() < -80)
            ):
                return None
            # Avoid rounding a tiny nonzero price to free or inventing precision.
            scaled = amount * scale
            if scaled != scaled.to_integral_value() or scaled > 10**18:
                return None
            return int(scaled)
    except (InvalidOperation, ValueError, OverflowError):
        return None


def _pricing(raw: object, freshness: Freshness) -> Pricing:
    if not isinstance(raw, dict):
        return Pricing()
    amounts: dict[str, int] = {}
    unknown: set[str] = set()
    conditions = {"min_prompt_tokens", "utc_days", "utc_start", "utc_end"}

    def collect(prices, *, override=False):
        for name, value in prices.items():
            if name in _PRICE_COMPONENTS:
                component, scale = _PRICE_COMPONENTS[name]
                amount = _exact_scaled(value, scale, string_only=True)
                if amount is None:
                    unknown.add(component)
                else:
                    amounts[component] = max(amount, amounts.get(component, 0))
            elif (override and name in conditions) or (
                not override and name in {"discount", "overrides"}
            ):
                continue
            else:
                unknown.add(str(name))

    collect(raw)
    for required in ("prompt", "completion"):
        if required not in raw:
            unknown.add(_PRICE_COMPONENTS[required][0])
    overrides = raw.get("overrides", [])
    if not isinstance(overrides, list) or any(not isinstance(item, dict) for item in overrides):
        unknown.add("overrides")
    else:
        for override in overrides:
            collect(override, override=True)
    # A malformed base/override never inherits a deceptively usable lower value.
    charges = tuple(
        Charge(name, amount, True) for name, amount in amounts.items() if name not in unknown
    )
    return Pricing(freshness, charges, unknown_components=frozenset(unknown))


def _rows(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
        raise CatalogDecodeError("catalogue response must contain a data list")
    rows = payload["data"]
    if any(not isinstance(row, dict) for row in rows):
        raise CatalogDecodeError("catalogue entries must be objects")
    count = payload.get("total_count")
    links = payload.get("links")
    if count is not None and (type(count) is not int or count != len(rows)):
        raise CatalogDecodeError("catalogue response is incomplete or has an invalid count")
    if isinstance(links, dict) and links.get("next"):
        raise CatalogDecodeError("catalogue response is incomplete")
    return rows


def _strings(value: object) -> frozenset[str]:
    if not isinstance(value, list) or any(not _identifier(item) for item in value):
        return frozenset()
    return frozenset(value)


def decode_openrouter_models(
    payload: Any,
    *,
    connection: ConnectionModels,
    benchmarks: dict[str, Scores] | None = None,
) -> ConnectionModels:
    """Normalize a models/user response using separately established provenance.

    This function cannot establish that the endpoint was account-filtered or that
    tools execute. It retains those flags from connection, even if remote fields
    claim otherwise. No URLs, descriptions or remote executable hints are used.
    """
    models = []
    seen = set()
    for row in _rows(payload):
        model_id = row.get("id")
        if not _identifier(model_id) or model_id in seen:
            raise CatalogDecodeError("catalogue has an invalid or duplicate model identifier")
        seen.add(model_id)
        architecture = row.get("architecture")
        architecture = architecture if isinstance(architecture, dict) else {}
        parameters = row.get("supported_parameters")
        tools = None
        if isinstance(parameters, list) and all(_identifier(value) for value in parameters):
            tools = "tools" in parameters
        limits = [row.get("context_length")]
        if isinstance(row.get("top_provider"), dict):
            limits.append(row["top_provider"].get("context_length"))
        known_limits = [limit for limit in limits if type(limit) is int and limit > 0]
        canonical = row.get("canonical_slug")
        # Use exact identifiers only. No display-name, prefix or :free stripping.
        score_key = canonical if _identifier(canonical) else model_id
        models.append(
            Model(
                model_id=model_id,
                tools=tools,
                modalities=_strings(architecture.get("input_modalities")),
                output_modalities=_strings(architecture.get("output_modalities")),
                context_tokens=min(known_limits) if known_limits else None,
                pricing=_pricing(row.get("pricing"), connection.freshness),
                scores=(benchmarks or {}).get(score_key),
            )
        )
    return replace(connection, models=tuple(models))


def decode_openrouter_benchmarks(
    payload: Any,
    *,
    now: datetime,
    max_age: timedelta,
    source: str = "artificial-analysis",
) -> dict[str, Scores]:
    """Normalize one comparable source; absent/old evidence stays unranked/stale.

    Indices use exact millionths, consistently within this source. The catalogue
    must explicitly map its canonical slug to model_permaslug for a variant join.
    Returned source URLs and arbitrary benchmark pricing are never used.
    """
    if source != "artificial-analysis":
        raise CatalogDecodeError("unsupported comparable benchmark source")
    if now.utcoffset() is None or max_age < timedelta(0):
        raise ValueError("benchmark freshness needs aware time and nonnegative maximum age")
    rows = _rows(payload)
    freshness: Freshness = "missing"
    meta = payload.get("meta")
    if isinstance(meta, dict) and isinstance(meta.get("as_of"), str):
        try:
            as_of = datetime.fromisoformat(meta["as_of"].replace("Z", "+00:00"))
            if as_of.utcoffset() is not None and as_of <= now:
                freshness = "fresh" if now - as_of <= max_age else "stale"
        except ValueError:
            pass
    scores = {}
    duplicates = set()
    for row in rows:
        key = row.get("model_permaslug")
        if row.get("source") != source or not _identifier(key):
            continue
        if key in scores:
            duplicates.add(key)
        scores[key] = Scores(
            source,
            freshness,
            _exact_scaled(row.get("agentic_index"), 10**6, string_only=False),
            _exact_scaled(row.get("intelligence_index"), 10**6, string_only=False),
        )
    return {key: value for key, value in scores.items() if key not in duplicates}
