"""Training-market settlement — checkpoint-based, pure logic (Track F).

Training runs (fine-tunes and pretraining windows) settle per verified
**checkpoint**, not per token: a multi-day run cannot carry all-at-the-
end default risk in either direction. This module generalizes the
capacity-forward settlement (``forwards.py``) to checkpoint units while
preserving the exact same hardened properties:

  * conservation of buyer funds and of collateral, exact to the micro
  * pro-rata payment always; a delivery threshold gates slashing only
    (finding A-1: thresholds must never round payment up)
  * demand-relative obligation (finding B-1): the seller is judged
    against checkpoints the run actually *scheduled*, so a buyer who
    cancels early or whose job crashes for buyer-side reasons cannot
    grief the seller into a slash
  * slash proceeds compensate the buyer, never the treasury (B-3)

A checkpoint is 'delivered' only when VERIFIED (weights artifact hash
recorded + attestation checks passed). Verification policy lives in
the transport/attestation layer; this module trusts its counts
(trust boundary per review finding B-5).
"""

from __future__ import annotations

from dataclasses import dataclass

from tinyassets.paid_market.forwards import (
    FEE_PPM,
    MAX_COLLATERAL_PCT,
    MIN_COLLATERAL_PCT,
    PPM,
    ForwardError,
)

__all__ = [
    "TrainingError",
    "TrainingSettlement",
    "settle_training_window",
    "TRAINING_DELIVERY_THRESHOLD_PPM",
]

# Training defaults differ from inference forwards: checkpoints are
# coarse (a 72h run might have 12-24), so one missed checkpoint should
# already register. 100% = any verified-checkpoint miss below schedule
# is a default; tune per instrument class in the transport layer.
TRAINING_DELIVERY_THRESHOLD_PPM = PPM


class TrainingError(ForwardError):
    """Raised on invalid training-settlement parameters."""


@dataclass(frozen=True)
class TrainingSettlement:
    buyer_paid_total: int
    checkpoints_scheduled: int  # demand: checkpoints the run reached/asked
    checkpoints_verified: int  # served: delivered AND attestation-passed
    seller_gross: int
    treasury_fee: int
    seller_net: int
    buyer_refund: int
    collateral_locked: int
    collateral_released: int
    slash_to_buyer: int
    defaulted: bool

    def check_invariants(self) -> None:
        if self.seller_net + self.treasury_fee + self.buyer_refund != (
            self.buyer_paid_total
        ):
            raise TrainingError("conservation violated: buyer funds")
        if self.collateral_released + self.slash_to_buyer != self.collateral_locked:
            raise TrainingError("conservation violated: collateral")
        for f in (
            "buyer_paid_total",
            "checkpoints_scheduled",
            "checkpoints_verified",
            "seller_gross",
            "treasury_fee",
            "seller_net",
            "buyer_refund",
            "collateral_locked",
            "collateral_released",
            "slash_to_buyer",
        ):
            if getattr(self, f) < 0:
                raise TrainingError(f"negative settlement field: {f}")


def settle_training_window(
    *,
    price_total_micros: int,
    checkpoints_contracted: int,
    checkpoints_scheduled: int,
    checkpoints_verified: int,
    collateral_pct: int,
    fee_ppm: int = FEE_PPM,
    threshold_ppm: int = TRAINING_DELIVERY_THRESHOLD_PPM,
) -> TrainingSettlement:
    """Settle one training window.

    ``checkpoints_contracted``  — the instrument's total (denominator
        for pricing; e.g. 24 checkpoints over a 72h window).
    ``checkpoints_scheduled``   — how many the run legitimately reached
        (buyer cancel / buyer-side crash caps this below contracted;
        cannot exceed contracted).
    ``checkpoints_verified``    — of the scheduled, how many the seller
        delivered with passing attestation (capped at scheduled).

    Payment mirrors the capacity-reservation model:
      unserved = scheduled − verified
      seller_gross = total * (contracted − unserved) / contracted
    → buyer early-cancel with all reached checkpoints verified pays in
      full (the window was reserved); seller misses within schedule →
      pro-rata refund; slash pro-rata to unserved/contracted, only when
      verified/scheduled falls below threshold.
    """
    if (
        not isinstance(price_total_micros, int)
        or isinstance(price_total_micros, bool)
        or price_total_micros <= 0
    ):
        raise TrainingError("price_total_micros must be a positive int")
    for name, v in (
        ("checkpoints_contracted", checkpoints_contracted),
        ("checkpoints_scheduled", checkpoints_scheduled),
        ("checkpoints_verified", checkpoints_verified),
    ):
        if not isinstance(v, int) or isinstance(v, bool) or v < 0:
            raise TrainingError(f"{name} must be a non-negative int")
    if checkpoints_contracted < 1:
        raise TrainingError("checkpoints_contracted must be >= 1")
    if not (0 < fee_ppm < PPM):
        raise TrainingError("fee_ppm must be in (0, PPM)")
    if not (0 < threshold_ppm <= PPM):
        raise TrainingError("threshold_ppm must be in (0, PPM]")
    if not (
        MIN_COLLATERAL_PCT <= collateral_pct <= MAX_COLLATERAL_PCT
        and isinstance(collateral_pct, int)
        and not isinstance(collateral_pct, bool)
    ):
        raise TrainingError(
            f"collateral_pct must be int in "
            f"[{MIN_COLLATERAL_PCT}, {MAX_COLLATERAL_PCT}]"
        )

    scheduled = min(checkpoints_scheduled, checkpoints_contracted)
    verified = min(checkpoints_verified, scheduled)
    unserved = scheduled - verified

    total = price_total_micros
    seller_gross = (total * (checkpoints_contracted - unserved)) // (
        checkpoints_contracted
    )
    treasury_fee = (seller_gross * fee_ppm) // PPM
    seller_net = seller_gross - treasury_fee
    buyer_refund = total - seller_gross

    collateral = (total * collateral_pct) // 100
    met = scheduled == 0 or verified * PPM >= threshold_ppm * scheduled
    slash = 0 if met else (collateral * unserved) // checkpoints_contracted
    released = collateral - slash

    s = TrainingSettlement(
        buyer_paid_total=total,
        checkpoints_scheduled=scheduled,
        checkpoints_verified=verified,
        seller_gross=seller_gross,
        treasury_fee=treasury_fee,
        seller_net=seller_net,
        buyer_refund=buyer_refund,
        collateral_locked=collateral,
        collateral_released=released,
        slash_to_buyer=slash,
        defaulted=not met,
    )
    s.check_invariants()
    return s
