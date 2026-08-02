"""Trusted market-scope projector — the public aggregate key's third leg.

An aggregate is keyed by ``(market_class_id, market_scope_revision,
public_scope_dimensions)``.  This module owns the last one: a bounded canonical
ASCII object of allowlisted coarse public dimensions, derived from resolved
quote/domain terms *before* execution and re-derived against accepted
settlement evidence.  An ordered tuple of strings is not equivalent authority.

A scope revision may not duplicate, override, or reclassify a descriptor or
market-class facet unless it declares a single canonical projection from that
already-bound facet — so scope can never manufacture a second equivalence class
out of a facet the descriptor already decided.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Mapping

from tinyassets.paid_market.descriptors import (
    IDENTIFIER_PATTERN,
    MAX_CANONICAL_BYTES,
    MAX_MEMBERS,
    lane_field_names,
)

__all__ = [
    "SCOPE_DOMAIN",
    "ScopeError",
    "ScopeRevision",
    "derive_public_scope_dimensions",
    "validate_scope_dimensions",
]

SCOPE_DOMAIN = "tinyassets.market-scope"

# Facets the descriptor and market class already decide.  A scope dimension may
# only reuse one of these names through a declared canonical projection.
_MARKET_FACETS = frozenset(
    {
        "lane",
        "profile_schema_revision",
        "unit_semantics",
        "region",
        "region_class",
        "privacy_class",
        "reliability_class",
        "public_requirements",
        "descriptor_id",
        "market_class_id",
    }
    | lane_field_names()
)


class ScopeError(ValueError):
    """Scope derivation failed; no observation may enter a public aggregate."""


@dataclass(frozen=True)
class ScopeRevision:
    """Globally immutable content-addressed projection contract."""

    revision_id: str
    dimensions: tuple[str, ...]
    allowed_values: Mapping[str, frozenset[str]]
    # dimension name -> already-bound facet it canonically projects from
    projected_facets: Mapping[str, str] = field(default_factory=dict)
    # facet name -> {facet value: dimension value}
    facet_projections: Mapping[str, Mapping[str, str]] = field(default_factory=dict)


def derive_public_scope_dimensions(
    revision: ScopeRevision,
    terms: Mapping[str, object],
    *,
    market_facets: Mapping[str, str] | None = None,
) -> bytes:
    """Derive the canonical dimension bytes, or fail closed.

    Never echoes a caller value: an exact destination, tenant policy, or
    low-entropy term must not leak through an error message either.
    """
    _validate_revision(revision)
    if not isinstance(terms, Mapping):
        raise ScopeError("scope terms must be an object")
    facets = market_facets or {}

    supplied = set(terms)
    derived_names = set(revision.projected_facets)
    if supplied & derived_names:
        raise ScopeError("scope_facet_conflict: projected dimension is derived, not supplied")
    unknown = supplied - set(revision.dimensions)
    if unknown:
        raise ScopeError("scope_dimension_not_allowlisted")

    dimensions: dict[str, str] = {}
    for name in revision.dimensions:
        if name in derived_names:
            facet = revision.projected_facets[name]
            table = revision.facet_projections.get(facet, {})
            bound = facets.get(facet)
            value = table.get(bound) if isinstance(bound, str) else None
            if value is None:
                raise ScopeError("scope_projection_unavailable")
        else:
            if name not in terms:
                raise ScopeError("scope_dimension_missing")
            value = terms[name]  # type: ignore[assignment]
        if not isinstance(value, str) or not IDENTIFIER_PATTERN.fullmatch(value):
            raise ScopeError("scope_value_invalid")
        if value not in revision.allowed_values.get(name, frozenset()):
            raise ScopeError("scope_value_not_allowed")
        dimensions[name] = value

    raw = json.dumps(
        dimensions,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("ascii")
    if len(raw) > MAX_CANONICAL_BYTES:
        raise ScopeError("scope_limit_exceeded")
    return raw


def validate_scope_dimensions(raw: object) -> bytes:
    """Accept only canonical ASCII object bytes produced by the projector."""
    if not isinstance(raw, (bytes, bytearray)):
        raise ScopeError("public_scope_dimensions must be canonical ASCII bytes")
    raw = bytes(raw)
    if not raw or len(raw) > MAX_CANONICAL_BYTES:
        raise ScopeError("public_scope_dimensions is empty or oversized")
    try:
        text = raw.decode("ascii")
        parsed = json.loads(text)
    except (UnicodeDecodeError, ValueError) as exc:
        raise ScopeError("public_scope_dimensions is not canonical ASCII JSON") from exc
    if not isinstance(parsed, dict) or not parsed:
        raise ScopeError("public_scope_dimensions must be a non-empty object")
    if len(parsed) > MAX_MEMBERS:
        raise ScopeError("public_scope_dimensions exceeds member bound")
    for name, value in parsed.items():
        if not isinstance(value, str) or not IDENTIFIER_PATTERN.fullmatch(value):
            raise ScopeError("public_scope_dimensions holds a non-identifier value")
        if not IDENTIFIER_PATTERN.fullmatch(name):
            raise ScopeError("public_scope_dimensions holds a non-identifier key")
    canonical = json.dumps(
        parsed,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("ascii")
    if canonical != raw:
        raise ScopeError("public_scope_dimensions is not canonical")
    return raw


def _validate_revision(revision: ScopeRevision) -> None:
    if not isinstance(revision, ScopeRevision):
        raise ScopeError("a ScopeRevision is required")
    if not revision.revision_id or not IDENTIFIER_PATTERN.fullmatch(revision.revision_id):
        raise ScopeError("scope revision_id must be an identifier")
    if not revision.dimensions:
        raise ScopeError("scope revision declares no dimensions")
    if len(set(revision.dimensions)) != len(revision.dimensions):
        raise ScopeError("scope dimensions must be unique")
    for name in revision.dimensions:
        if not IDENTIFIER_PATTERN.fullmatch(name):
            raise ScopeError("scope dimension names must be identifiers")
        if name in _MARKET_FACETS and name not in revision.projected_facets:
            raise ScopeError(
                "scope_facet_conflict: a market facet needs a declared canonical projection"
            )
    for name in revision.projected_facets:
        if name not in revision.dimensions:
            raise ScopeError("projected dimension is not declared")
