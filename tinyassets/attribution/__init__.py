"""tinyassets.attribution — Attribution chain and remix provenance primitives.

Schema layer (schema.py): attribution_edge / attribution_credit DDL and dataclasses.
Calculation layer (calc.py): compute_credit_shares + compute_payout_shares.
"""

from __future__ import annotations

from tinyassets.attribution.calc import compute_credit_shares, compute_payout_shares
from tinyassets.attribution.schema import (
    ATTRIBUTION_SCHEMA,
    AttributionCredit,
    AttributionEdge,
    ContributionKind,
    RemixProvenance,
    migrate_attribution_schema,
)

__all__ = [
    "ATTRIBUTION_SCHEMA",
    "AttributionCredit",
    "AttributionEdge",
    "ContributionKind",
    "RemixProvenance",
    "compute_credit_shares",
    "compute_payout_shares",
    "migrate_attribution_schema",
]
