"""Capacity forwards — state machine + settlement math (spec §3).

Pure logic, no transport, no storage. The invariants this module
guarantees are the ones a persistence layer must not be able to break:

  1. **Conservation of buyer funds.** For every settlement:
         seller_net + treasury_fee + buyer_refund == buyer_paid_total
     to the micro, always, including full default and over-delivery.
  2. **Conservation of collateral.**
         collateral_released + collateral_slashed == collateral_locked
  3. **Pro-rata payment, always.** The seller is paid for tokens
     actually delivered (capped at contract size). The delivery
     threshold gates *collateral slashing only* — it never rounds a
     partial delivery up to full payment. (A >=95% "counts as
     delivered" payment rule would let sellers systematically skim the
     last 5% of every contract; review pass A, finding A-1.)
  4. **Monotone state machine.** Transitions only along declared edges.

All money is integer micros. All division is explicit floor division
with the remainder assigned deliberately (fees floor in the seller's
favor; refunds absorb rounding dust so conservation is exact).
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = [
    "ForwardError",
    "ForwardState",
    "VALID_TRANSITIONS",
    "assert_transition",
    "SIZES_MTOK",
    "TOKENS_PER_MTOK",
    "FEE_PPM",
    "DELIVERY_THRESHOLD_PPM",
    "MIN_COLLATERAL_PCT",
    "MAX_COLLATERAL_PCT",
    "contract_total_micros",
    "collateral_micros",
    "Settlement",
    "settle_forward",
]

SIZES_MTOK = (1, 10, 100)
TOKENS_PER_MTOK = 1_000_000
PPM = 1_000_000

FEE_PPM = 10_000  # 1% treasury fee (99/1 split per settlement spec)
DELIVERY_THRESHOLD_PPM = 950_000  # >=95% delivered → no collateral slash
MIN_COLLATERAL_PCT = 5
MAX_COLLATERAL_PCT = 100


class ForwardError(ValueError):
    """Raised on invalid forward parameters or transitions."""


class ForwardState:
    OPEN = "open"
    SOLD = "sold"
    DELIVERING = "delivering"
    SETTLED = "settled"  # terminal, includes pro-rata default settlements
    EXPIRED = "expired"  # terminal, unsold at bucket start
    ALL = (OPEN, SOLD, DELIVERING, SETTLED, EXPIRED)


VALID_TRANSITIONS: dict[str, tuple[str, ...]] = {
    ForwardState.OPEN: (ForwardState.SOLD, ForwardState.EXPIRED),
    ForwardState.SOLD: (ForwardState.DELIVERING,),
    ForwardState.DELIVERING: (ForwardState.SETTLED,),
    ForwardState.SETTLED: (),
    ForwardState.EXPIRED: (),
}


def assert_transition(current: str, new: str) -> None:
    if current not in VALID_TRANSITIONS:
        raise ForwardError(f"unknown state {current!r}")
    if new not in VALID_TRANSITIONS:
        raise ForwardError(f"unknown state {new!r}")
    if new not in VALID_TRANSITIONS[current]:
        raise ForwardError(f"illegal transition {current!r} -> {new!r}")


def _require_positive_int(value: int, name: str) -> None:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ForwardError(f"{name} must be int")
    if value <= 0:
        raise ForwardError(f"{name} must be > 0")


def _require_nonneg_int(value: int, name: str) -> None:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ForwardError(f"{name} must be int")
    if value < 0:
        raise ForwardError(f"{name} must be >= 0")


def contract_total_micros(size_mtok: int, price_micros_per_mtok: int) -> int:
    """Buyer pays size * unit price. Exact int product, no division."""
    if size_mtok not in SIZES_MTOK:
        raise ForwardError(f"size_mtok must be one of {SIZES_MTOK}")
    _require_positive_int(price_micros_per_mtok, "price_micros_per_mtok")
    return size_mtok * price_micros_per_mtok


def collateral_micros(total_micros: int, collateral_pct: int) -> int:
    """Seller collateral, floored. Bounds enforced (spec §3 default 20%)."""
    _require_positive_int(total_micros, "total_micros")
    if (
        not isinstance(collateral_pct, int)
        or isinstance(collateral_pct, bool)
        or not (MIN_COLLATERAL_PCT <= collateral_pct <= MAX_COLLATERAL_PCT)
    ):
        raise ForwardError(
            f"collateral_pct must be int in "
            f"[{MIN_COLLATERAL_PCT}, {MAX_COLLATERAL_PCT}]"
        )
    return (total_micros * collateral_pct) // 100


@dataclass(frozen=True)
class Settlement:
    """Exact money movements for one forward at bucket end.

    ``slash_to_buyer`` is buyer compensation for the shortfall — it
    goes to the buyer, not the treasury, so the platform never profits
    from seller defaults (perverse-incentive guard; review B, B-3).
    """

    buyer_paid_total: int
    tokens_served: int  # min(delivered, demand) — obligation actually met
    tokens_demand: int  # min(requested, size) — buyer's exercised claim
    seller_gross: int
    treasury_fee: int
    seller_net: int
    buyer_refund: int
    collateral_locked: int
    collateral_released: int
    slash_to_buyer: int
    defaulted: bool  # True → delivery below threshold, slash applied

    def check_invariants(self) -> None:
        if self.seller_net + self.treasury_fee + self.buyer_refund != (
            self.buyer_paid_total
        ):
            raise ForwardError("conservation violated: buyer funds")
        if self.collateral_released + self.slash_to_buyer != self.collateral_locked:
            raise ForwardError("conservation violated: collateral")
        for name in (
            "buyer_paid_total",
            "tokens_served",
            "tokens_demand",
            "seller_gross",
            "treasury_fee",
            "seller_net",
            "buyer_refund",
            "collateral_locked",
            "collateral_released",
            "slash_to_buyer",
        ):
            if getattr(self, name) < 0:
                raise ForwardError(f"negative settlement field: {name}")


def settle_forward(
    *,
    size_mtok: int,
    price_micros_per_mtok: int,
    tokens_requested: int,
    tokens_delivered: int,
    collateral_pct: int,
    fee_ppm: int = FEE_PPM,
    threshold_ppm: int = DELIVERY_THRESHOLD_PPM,
) -> Settlement:
    """Compute the settlement for a forward at bucket end.

    **Capacity-reservation model** (review pass B, finding B-1): the
    seller's obligation is to serve the buyer's *requests* during the
    window, up to contract size — not to unilaterally emit tokens. The
    original delivered/size formula let an attacker buy a competitor's
    forward, submit zero requests, and collect a full refund PLUS the
    slashed collateral: profitable griefing at zero cost. Under this
    model:

      demand   = min(tokens_requested, size)      (buyer's exercised claim)
      served   = min(tokens_delivered, demand)    (obligation actually met)
      unserved = demand - served                  (the only buyer harm)

      seller_gross = total * (size - unserved) / size   (floored)
        → buyer no-show (demand=0): seller paid in full — the capacity
          was reserved either way (use-it-or-lose-it, like any
          reservation). Griefing now costs the griefer the full price.
        → seller misses demand: refund pro-rata to unserved demand only.

      slash: only if demand > 0 and served/demand < threshold, pro-rata
      to unserved/size. Threshold gates the slash ONLY — payment is
      always pro-rata (finding A-1: a ">=95% counts as full delivery"
      payment rule would let sellers skim the last 5% of every
      contract).

    Rounding policy (deliberate, tested):
      * seller_gross floors → dust stays with the buyer via refund
      * treasury_fee floors → dust stays with the seller
      * slash floors        → dust stays with the seller via release
    Conservation is exact by construction (subtraction, never a second
    division).
    """
    total = contract_total_micros(size_mtok, price_micros_per_mtok)
    _require_nonneg_int(tokens_requested, "tokens_requested")
    _require_nonneg_int(tokens_delivered, "tokens_delivered")
    if not (0 < fee_ppm < PPM):
        raise ForwardError("fee_ppm must be in (0, PPM)")
    if not (0 < threshold_ppm <= PPM):
        raise ForwardError("threshold_ppm must be in (0, PPM]")

    size_tokens = size_mtok * TOKENS_PER_MTOK
    demand = min(tokens_requested, size_tokens)
    served = min(tokens_delivered, demand)  # over-serving earns nothing extra
    unserved = demand - served

    seller_gross = (total * (size_tokens - unserved)) // size_tokens
    treasury_fee = (seller_gross * fee_ppm) // PPM
    seller_net = seller_gross - treasury_fee
    buyer_refund = total - seller_gross  # exact, absorbs rounding dust

    collateral = collateral_micros(total, collateral_pct)
    # Threshold in integers: served/demand >= threshold/PPM
    #   <=>  served * PPM >= threshold * demand   (demand > 0)
    met_threshold = demand == 0 or served * PPM >= threshold_ppm * demand
    if met_threshold:
        slash = 0
    else:
        slash = (collateral * unserved) // size_tokens
    released = collateral - slash

    settlement = Settlement(
        buyer_paid_total=total,
        tokens_served=served,
        tokens_demand=demand,
        seller_gross=seller_gross,
        treasury_fee=treasury_fee,
        seller_net=seller_net,
        buyer_refund=buyer_refund,
        collateral_locked=collateral,
        collateral_released=released,
        slash_to_buyer=slash,
        defaulted=not met_threshold,
    )
    settlement.check_invariants()
    return settlement
