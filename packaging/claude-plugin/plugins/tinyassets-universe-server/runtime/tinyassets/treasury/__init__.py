"""tinyassets.treasury — Platform fee, bounty pool, and designer royalty primitives.

Schema (schema.py): treasury_balance / bounty_pool_balance / royalty_payout DDL.
Distribution math (distribution.py): pure functions, no I/O.
Status (status.py): read-only cost-ledger + treasury summaries.
"""

from __future__ import annotations

from tinyassets.treasury.distribution import (
    BOUNTY_POOL_SHARE_BP,
    PLATFORM_TAKE_BP,
    TREASURY_SHARE_BP,
    compute_bounty_allocation,
    compute_royalty_share,
    compute_take,
    compute_treasury_retained,
    net_after_take,
    split_take,
)
from tinyassets.treasury.schema import (
    TREASURY_SCHEMA,
    BountyAllocation,
    RoyaltyPayment,
    TreasuryEntry,
    migrate_treasury_schema,
)
from tinyassets.treasury.status import treasury_status

__all__ = [
    # distribution.py
    "BOUNTY_POOL_SHARE_BP",
    "PLATFORM_TAKE_BP",
    "TREASURY_SHARE_BP",
    "compute_bounty_allocation",
    "compute_royalty_share",
    "compute_take",
    "compute_treasury_retained",
    "net_after_take",
    "split_take",
    # schema.py
    "TREASURY_SCHEMA",
    "BountyAllocation",
    "RoyaltyPayment",
    "TreasuryEntry",
    "migrate_treasury_schema",
    # status.py
    "treasury_status",
]
