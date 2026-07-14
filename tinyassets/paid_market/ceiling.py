"""Hosted-API ceiling feed — pure parsing, no transport (spec §2).

The ceiling is the cheapest hosted-API price for the same open-weight
model: no rational buyer pays the market more than the cloud fallback,
and the ceiling clamp is the index's absolute bound on upward
manipulation (review finding B-2). This module converts an
OpenRouter-style ``/models`` payload into ceiling prices in integer
micros-per-Mtok.

Money discipline matches the rest of the package: prices arrive as
decimal strings (USD per token); conversion uses ``decimal.Decimal``
exactly and floors once to int micros. No floats in the money path.

Conversion: USD/token → micros/Mtok multiplies by 10**12
(10**6 tokens per Mtok × 10**6 micros per USD).

The fetch itself (urllib, 1h cadence per spec) belongs to the transport
layer; this module takes the already-decoded JSON dict.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

__all__ = [
    "CeilingError",
    "ModelPrice",
    "parse_models_payload",
    "ceiling_for_capability",
    "usd_per_token_to_micros_per_mtok",
]

_USD_TOKEN_TO_MICROS_MTOK = Decimal(10) ** 12


class CeilingError(ValueError):
    """Raised on malformed ceiling-feed payloads or parameters."""


@dataclass(frozen=True)
class ModelPrice:
    """One hosted offer for one model."""

    model_id: str  # provider's model identifier, verbatim
    prompt_micros_per_mtok: int
    completion_micros_per_mtok: int


def _is_negative_sentinel(raw: object) -> bool:
    """Live catalogs (validated against OpenRouter 2026-07-08) use "-1"
    as a sentinel meaning 'dynamic / no fixed price'. That is a
    legitimate non-offer, not corruption — skip, don't raise."""
    if not isinstance(raw, str):
        return False
    try:
        return Decimal(raw) < 0
    except InvalidOperation:
        return False


def usd_per_token_to_micros_per_mtok(usd_per_token: str) -> int:
    """Exact Decimal conversion, floored. Rejects non-finite, negative,
    and non-decimal input loudly. Returns 0 only for exactly-zero input
    (free-tier listings), which callers must filter before min()."""
    if not isinstance(usd_per_token, str):
        raise CeilingError("price must be a decimal string")
    try:
        d = Decimal(usd_per_token)
    except InvalidOperation as exc:
        raise CeilingError(f"unparseable price {usd_per_token!r}") from exc
    if not d.is_finite():
        raise CeilingError(f"non-finite price {usd_per_token!r}")
    if d < 0:
        raise CeilingError(f"negative price {usd_per_token!r}")
    return int(d * _USD_TOKEN_TO_MICROS_MTOK)


def parse_models_payload(payload: dict) -> list[ModelPrice]:
    """Parse an OpenRouter-style ``{"data": [{"id", "pricing": {"prompt",
    "completion"}}]}`` payload.

    Entries are SKIPPED (not fatal) when they are structurally absent —
    missing pricing block, missing prompt/completion keys — because the
    upstream catalog legitimately contains non-inference entries.
    Negative prices are provider sentinels for dynamic/unpriced entries
    (observed as "-1" in the live OpenRouter catalog) and are skipped.
    Entries that are *present but unparseable* raise: silently dropping those could erase the true
    minimum and quietly raise the published ceiling, which is a price
    integrity failure, not a data-hygiene nit.

    Zero-priced entries (free tiers / promos) are skipped: a ceiling of
    0 would clamp every VWAP to 0 and zero out the composite quote.
    """
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
        raise CeilingError("payload must be a dict with a 'data' list")
    out: list[ModelPrice] = []
    for entry in payload["data"]:
        if not isinstance(entry, dict):
            raise CeilingError("model entry must be a dict")
        model_id = entry.get("id")
        pricing = entry.get("pricing")
        if not model_id or not isinstance(pricing, dict):
            continue  # structurally absent → not an inference offer
        prompt_raw = pricing.get("prompt")
        completion_raw = pricing.get("completion")
        if prompt_raw is None or completion_raw is None:
            continue
        if _is_negative_sentinel(prompt_raw) or _is_negative_sentinel(completion_raw):
            continue  # "-1" = provider sentinel for dynamic/no fixed price
        prompt = usd_per_token_to_micros_per_mtok(prompt_raw)
        completion = usd_per_token_to_micros_per_mtok(completion_raw)
        if prompt <= 0 or completion <= 0:
            continue  # free tier — not a meaningful ceiling
        out.append(
            ModelPrice(
                model_id=str(model_id),
                prompt_micros_per_mtok=prompt,
                completion_micros_per_mtok=completion,
            )
        )
    return out


def ceiling_for_capability(
    prices: list[ModelPrice],
    model_ids: list[str],
) -> int | None:
    """Cheapest hosted *completion* price across the hosted model ids
    mapped to one capability. Completion (output) tokens are the spot
    quote's unit (spec §1), so the ceiling compares like with like.

    The capability → hosted-id mapping is caller-supplied and curated
    (e.g. ``llama-405b:batch`` → every provider id serving that model
    at an acceptable quant). An empty or unmatched mapping returns
    None: an *absent* ceiling is honest; a guessed one corrupts the
    clamp. Matching is exact — fuzzy model-name matching across
    providers is a curation task, not a parser guess.
    """
    if not isinstance(model_ids, list) or not all(
        isinstance(m, str) and m for m in model_ids
    ):
        raise CeilingError("model_ids must be a list of non-empty strings")
    wanted = set(model_ids)
    candidates = [
        p.completion_micros_per_mtok for p in prices if p.model_id in wanted
    ]
    return min(candidates) if candidates else None
