"""Training pools & fractional ownership — pure math (Track H).

Many users pool funds toward one training goal; the minted model is
owned fractionally in proportion to contribution; inference revenue
distributes to owners (and up the attribution chain for derived
models). This module owns the two exactness-critical computations:

**1. Pool accounting.** Contributions accumulate toward a target;
overshoot on the closing contribution is refunded exactly; a failed
pool refunds everyone exactly (trivially conservative — refunds ARE
the contributions).

**2. Revenue apportionment.** Distributing R micros over ownership
shares by naive floor division leaks up to (n_owners − 1) micros per
distribution — dust that compounds over thousands of payouts. This
module uses **largest-remainder apportionment**: floor everyone, then
hand the leftover micros one each to the largest fractional
remainders (deterministic tie-break) so that ``sum(payouts) == R``
exactly, every time, with no owner ever more than 1 micro from their
exact pro-rata share.

Same discipline as the rest of the package: integers and Fractions
only in the money path, fail-loud validation, conservation asserted.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction

__all__ = [
    "PoolError",
    "PoolAccounting",
    "settle_pool_funding",
    "apportion_exact",
    "distribute_revenue",
]

PPM = 1_000_000


class PoolError(ValueError):
    """Raised on invalid pool or apportionment inputs."""


# ------------------------------------------------------------- funding


@dataclass(frozen=True)
class PoolAccounting:
    """Outcome of pool funding at close."""

    target_micros: int
    filled: bool
    accepted: dict[str, int]  # contributor -> micros actually accepted
    refunds: dict[str, int]  # contributor -> micros returned
    total_accepted: int

    def check_invariants(self, contributions: list[tuple[str, int]]) -> None:
        paid_in: dict[str, int] = {}
        for who, amt in contributions:
            paid_in[who] = paid_in.get(who, 0) + amt
        for who, amt in paid_in.items():
            if self.accepted.get(who, 0) + self.refunds.get(who, 0) != amt:
                raise PoolError(f"conservation violated for contributor {who!r}")
        if self.total_accepted != sum(self.accepted.values()):
            raise PoolError("total_accepted mismatch")
        if self.filled and self.total_accepted != self.target_micros:
            raise PoolError("filled pool must accept exactly the target")
        if not self.filled and any(self.accepted.values()):
            raise PoolError("failed pool must accept nothing")


def settle_pool_funding(
    *,
    target_micros: int,
    contributions: list[tuple[str, int]],  # (contributor_id, micros), ORDERED
) -> PoolAccounting:
    """Close a pool. Contributions are processed in arrival order
    (order is consensus-critical — persist it). The contribution that
    crosses the target is split: the crossing part is accepted, the
    overshoot refunded. Everything after the fill is refunded whole.
    If the total never reaches the target, the pool fails and every
    contribution is refunded in full.
    """
    if not isinstance(target_micros, int) or isinstance(target_micros, bool):
        raise PoolError("target_micros must be int")
    if target_micros <= 0:
        raise PoolError("target_micros must be > 0")
    accepted: dict[str, int] = {}
    refunds: dict[str, int] = {}
    running = 0
    for who, amt in contributions:
        if not who:
            raise PoolError("contributor id must be non-empty")
        if not isinstance(amt, int) or isinstance(amt, bool) or amt <= 0:
            raise PoolError(f"contribution from {who!r} must be a positive int")
        if running >= target_micros:
            refunds[who] = refunds.get(who, 0) + amt
            continue
        take = min(amt, target_micros - running)
        accepted[who] = accepted.get(who, 0) + take
        if amt - take:
            refunds[who] = refunds.get(who, 0) + (amt - take)
        running += take

    filled = running == target_micros
    if not filled:
        # Failed pool: everything back, nothing accepted.
        refunds = {}
        for who, amt in contributions:
            refunds[who] = refunds.get(who, 0) + amt
        accepted = {}
        running = 0

    acct = PoolAccounting(
        target_micros=target_micros,
        filled=filled,
        accepted=accepted,
        refunds=refunds,
        total_accepted=running,
    )
    acct.check_invariants(contributions)
    return acct


# -------------------------------------------------------- apportionment


def apportion_exact(
    amount_micros: int,
    shares: dict[str, int],
) -> dict[str, int]:
    """Split ``amount_micros`` across ``shares`` (arbitrary positive
    integer weights, e.g. accepted contributions) with EXACT
    conservation via largest-remainder apportionment.

    Guarantees:
      * sum(result.values()) == amount_micros, always
      * every payout within 1 micro of exact pro-rata
      * deterministic: remainder ties broken by (remainder desc, key asc)
    """
    if not isinstance(amount_micros, int) or isinstance(amount_micros, bool):
        raise PoolError("amount_micros must be int")
    if amount_micros < 0:
        raise PoolError("amount_micros must be >= 0")
    if not shares:
        raise PoolError("shares must be non-empty")
    for k, w in shares.items():
        if not k:
            raise PoolError("share key must be non-empty")
        if not isinstance(w, int) or isinstance(w, bool) or w <= 0:
            raise PoolError(f"share weight for {k!r} must be a positive int")

    total_w = sum(shares.values())
    floors: dict[str, int] = {}
    remainders: list[tuple[Fraction, str]] = []
    distributed = 0
    for k, w in shares.items():
        exact = Fraction(amount_micros * w, total_w)
        fl = int(exact)  # floor for non-negative
        floors[k] = fl
        distributed += fl
        remainders.append((exact - fl, k))

    leftover = amount_micros - distributed  # 0 <= leftover < len(shares)
    # Largest remainders first; ties broken by key for determinism.
    remainders.sort(key=lambda t: (-t[0], t[1]))
    for i in range(leftover):
        floors[remainders[i][1]] += 1

    if sum(floors.values()) != amount_micros:
        raise PoolError("apportionment conservation violated")  # unreachable
    return floors


def distribute_revenue(
    *,
    revenue_micros: int,
    owner_shares: dict[str, int],
    attribution_ppm: int = 0,
    attribution_shares: dict[str, int] | None = None,
) -> tuple[dict[str, int], dict[str, int], int]:
    """Distribute one revenue event for a model.

    ``attribution_ppm`` of revenue flows up the attribution chain
    (base/remixed-from models' owners) BEFORE owner distribution —
    derived models pay their lineage (Track H §4; rate is set at mint
    from the remix records and is immutable thereafter). Returns
    ``(owner_payouts, attribution_payouts, attribution_total)``; the
    two payout maps each conserve exactly and jointly sum to
    ``revenue_micros``.
    """
    if not isinstance(revenue_micros, int) or isinstance(revenue_micros, bool):
        raise PoolError("revenue_micros must be int")
    if revenue_micros < 0:
        raise PoolError("revenue_micros must be >= 0")
    if not (0 <= attribution_ppm < PPM):
        raise PoolError("attribution_ppm must be in [0, PPM)")
    if attribution_ppm and not attribution_shares:
        raise PoolError("attribution_ppm set but no attribution_shares")

    attribution_total = (revenue_micros * attribution_ppm) // PPM
    owner_total = revenue_micros - attribution_total  # exact remainder

    owner_payouts = (
        apportion_exact(owner_total, owner_shares) if owner_total or owner_shares
        else {}
    )
    attribution_payouts = (
        apportion_exact(attribution_total, attribution_shares)
        if attribution_total
        else {}
    )
    if (
        sum(owner_payouts.values()) + sum(attribution_payouts.values())
        != revenue_micros
    ):
        raise PoolError("revenue conservation violated")  # unreachable
    return owner_payouts, attribution_payouts, attribution_total
