"""Treasury distribution math — pure functions, no I/O.

Spec: project_monetization_crypto_1pct (1% platform take, basis-points model).
      project_designer_royalties_and_bounties (50% of take → bounty pool).

All amounts are MicroTokens (integers). Basis points: 10_000 bp = 100%.

Key invariant: compute_take(amount, rate_bp) + net_after_take(amount, rate_bp) == amount.
"""

from __future__ import annotations

# ── Take-rate constants ───────────────────────────────────────────────────────

PLATFORM_TAKE_BP: int = 100        # 1% in basis points
BOUNTY_POOL_SHARE_BP: int = 5_000  # 50% of the 1% take, in basis points of the take
TREASURY_SHARE_BP: int = 5_000     # remaining 50% of the take

# ── Pure functions ────────────────────────────────────────────────────────────

def compute_take(amount: int, rate_bp: int = PLATFORM_TAKE_BP) -> int:
    """Compute platform take for a settlement amount.

    Args:
        amount:  Settlement amount in MicroTokens (must be >= 0).
        rate_bp: Take rate in basis points (100 bp = 1%). Defaults to 1%.

    Returns:
        Integer MicroTokens taken as platform fee (floor division).
    """
    if amount < 0:
        raise ValueError(f"amount must be >= 0, got {amount!r}")
    if rate_bp < 0:
        raise ValueError(f"rate_bp must be >= 0, got {rate_bp!r}")
    return amount * rate_bp // 10_000


def net_after_take(amount: int, rate_bp: int = PLATFORM_TAKE_BP) -> int:
    """Settlement amount minus platform take."""
    return amount - compute_take(amount, rate_bp)


def compute_bounty_allocation(
    take_amount: int,
    pool_share_bp: int = BOUNTY_POOL_SHARE_BP,
) -> int:
    """Compute bounty pool slice from the platform take.

    Args:
        take_amount:   Total platform fee collected (MicroTokens).
        pool_share_bp: Fraction of take going to bounty pool in basis points.
                       Default = 5000 bp = 50%.

    Returns:
        Integer MicroTokens allocated to the bounty pool (floor division).
    """
    if take_amount < 0:
        raise ValueError(f"take_amount must be >= 0, got {take_amount!r}")
    if pool_share_bp < 0 or pool_share_bp > 10_000:
        raise ValueError(f"pool_share_bp must be in [0, 10000], got {pool_share_bp!r}")
    return take_amount * pool_share_bp // 10_000


def compute_treasury_retained(
    take_amount: int,
    pool_share_bp: int = BOUNTY_POOL_SHARE_BP,
) -> int:
    """Compute the portion of take kept in treasury (not bounty pool)."""
    return take_amount - compute_bounty_allocation(take_amount, pool_share_bp)


def compute_royalty_share(gross_amount: int, designer_share: float) -> int:
    """Compute designer royalty from a settlement gross amount.

    Args:
        gross_amount:   Settlement amount before treasury take (MicroTokens).
        designer_share: Fraction going to the designer, in [0.0, 1.0].

    Returns:
        Integer MicroTokens to pay the designer (floor).
    """
    if gross_amount < 0:
        raise ValueError(f"gross_amount must be >= 0, got {gross_amount!r}")
    if not 0.0 <= designer_share <= 1.0:
        raise ValueError(f"designer_share must be in [0.0, 1.0], got {designer_share!r}")
    return int(gross_amount * designer_share)


def split_take(
    amount: int,
    rate_bp: int = PLATFORM_TAKE_BP,
    pool_share_bp: int = BOUNTY_POOL_SHARE_BP,
) -> tuple[int, int, int]:
    """Compute full split of a settlement in one call.

    Returns:
        (net_to_claimer, bounty_pool, treasury_retained)
        Invariant: sum of all three == amount.
    """
    take = compute_take(amount, rate_bp)
    net = amount - take
    bounty = compute_bounty_allocation(take, pool_share_bp)
    treasury = take - bounty
    return net, bounty, treasury
