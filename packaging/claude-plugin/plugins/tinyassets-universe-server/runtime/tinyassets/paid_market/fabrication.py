"""Physical fabrication market — pure logic (Track I §I4).

3D-print / maker jobs reuse the paid-request machinery with three
genuinely new computations no digital instrument needed:

**1. Job quoting** — material mass + machine time + setup, exact
integer micros. Units chosen so integers suffice end-to-end:
mass in **milligrams**, time in **seconds**, material priced per kg,
machine time per hour. Each conversion divides ONCE with floor.

**2. Geography** — the first instrument where location enters
matching. Distance (haversine, float — it is geometry, not money)
maps through the seller's declared shipping bands to an integer
shipping cost; ranking is by effective total with deterministic
tie-breaks. A job outside every band is UNSERVICEABLE by that seller
(fail-closed), never "assume the last band."

**3. Per-unit settlement** — physical goods settle on ACCEPTED units:
payment pro-rata to accepted/ordered; shipping is paid to the seller
if any unit is accepted (the box shipped either way) and refunded to
the buyer only on total rejection. No collateral for spot print jobs
(cooperative-trust posture for spot per the trust memory); the
``defaulted`` flag feeds reputation, not slashing. Conservation exact,
as everywhere in this package.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from tinyassets.paid_market.forwards import FEE_PPM, PPM, ForwardError

__all__ = [
    "FabricationError",
    "quote_print_job",
    "haversine_km",
    "shipping_cost_micros",
    "rank_sellers",
    "SellerOffer",
    "PhysicalSettlement",
    "settle_physical_job",
    "ACCEPTANCE_THRESHOLD_PPM",
]

MG_PER_KG = 1_000_000
SECONDS_PER_HOUR = 3600
ACCEPTANCE_THRESHOLD_PPM = 900_000  # <90% accepted → defaulted (reputation)


class FabricationError(ForwardError):
    """Raised on invalid fabrication parameters."""


def _pos_int(v: int, name: str) -> None:
    if not isinstance(v, int) or isinstance(v, bool) or v <= 0:
        raise FabricationError(f"{name} must be a positive int")


def _nonneg_int(v: int, name: str) -> None:
    if not isinstance(v, int) or isinstance(v, bool) or v < 0:
        raise FabricationError(f"{name} must be a non-negative int")


# --------------------------------------------------------------- quote


def quote_print_job(
    *,
    mass_mg_per_unit: int,
    machine_seconds_per_unit: int,
    quantity: int,
    material_micros_per_kg: int,
    machine_micros_per_hour: int,
    setup_micros: int = 0,
) -> int:
    """Exact integer quote for a print job.

    Per-unit costs are computed on the TOTAL job quantities (mass and
    seconds multiplied by quantity BEFORE the flooring division), so
    quoting 10 units never differs from 10× the true per-unit cost by
    more than a single flooring — buyers cannot game quantity splits
    for rounding advantage, and neither can sellers.
    """
    _pos_int(mass_mg_per_unit, "mass_mg_per_unit")
    _pos_int(machine_seconds_per_unit, "machine_seconds_per_unit")
    _pos_int(quantity, "quantity")
    _pos_int(material_micros_per_kg, "material_micros_per_kg")
    _pos_int(machine_micros_per_hour, "machine_micros_per_hour")
    _nonneg_int(setup_micros, "setup_micros")

    total_mass_mg = mass_mg_per_unit * quantity
    total_seconds = machine_seconds_per_unit * quantity
    material = (material_micros_per_kg * total_mass_mg) // MG_PER_KG
    machine = (machine_micros_per_hour * total_seconds) // SECONDS_PER_HOUR
    return material + machine + setup_micros


# ----------------------------------------------------------- geography


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in km. Floats are fine: geometry, not money."""
    for name, v, lim in (
        ("lat1", lat1, 90.0),
        ("lat2", lat2, 90.0),
        ("lon1", lon1, 180.0),
        ("lon2", lon2, 180.0),
    ):
        if not isinstance(v, (int, float)) or isinstance(v, bool):
            raise FabricationError(f"{name} must be a number")
        if not (-lim <= v <= lim) or math.isnan(v):
            raise FabricationError(f"{name} out of range")
    r = 6371.0088
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(a)))


def shipping_cost_micros(
    distance_km: float,
    bands: list[tuple[int, int]],  # (max_km, cost_micros), ascending max_km
) -> int | None:
    """Map a distance to the seller's declared shipping bands.
    Returns None (UNSERVICEABLE) beyond the last band — never
    extrapolates. Bands must be ascending, positive, non-empty."""
    if not bands:
        raise FabricationError("bands must be non-empty")
    prev = 0
    for max_km, cost in bands:
        _pos_int(max_km, "band max_km")
        _nonneg_int(cost, "band cost")
        if max_km <= prev:
            raise FabricationError("bands must be strictly ascending")
        prev = max_km
    if not isinstance(distance_km, (int, float)) or distance_km < 0:
        raise FabricationError("distance_km must be >= 0")
    for max_km, cost in bands:
        if distance_km <= max_km:
            return cost
    return None


@dataclass(frozen=True)
class SellerOffer:
    seller_id: str
    lat: float
    lon: float
    quote_micros: int
    shipping_bands: list[tuple[int, int]]


def rank_sellers(
    *,
    job_lat: float,
    job_lon: float,
    offers: list[SellerOffer],
) -> list[tuple[str, int, int]]:
    """Rank serviceable offers by effective total cost.

    Returns ``[(seller_id, effective_micros, shipping_micros), ...]``
    sorted by (effective total asc, distance asc, seller_id asc) —
    fully deterministic so every node computes the same ranking.
    Unserviceable sellers (outside all their bands) are excluded, not
    ranked last: shipping you can't actually buy is not a big number,
    it is not an offer.
    """
    ranked: list[tuple[int, float, str, int]] = []
    for o in offers:
        if not o.seller_id:
            raise FabricationError("seller_id must be non-empty")
        _pos_int(o.quote_micros, "quote_micros")
        d = haversine_km(job_lat, job_lon, o.lat, o.lon)
        ship = shipping_cost_micros(d, o.shipping_bands)
        if ship is None:
            continue
        ranked.append((o.quote_micros + ship, d, o.seller_id, ship))
    ranked.sort(key=lambda t: (t[0], t[1], t[2]))
    return [(sid, eff, ship) for eff, _d, sid, ship in ranked]


# ----------------------------------------------------------- settlement


@dataclass(frozen=True)
class PhysicalSettlement:
    goods_paid_total: int
    shipping_paid_total: int
    units_ordered: int
    units_accepted: int
    seller_gross: int
    treasury_fee: int
    seller_net: int
    buyer_refund: int
    defaulted: bool  # reputation signal; no collateral on spot fab jobs

    def check_invariants(self) -> None:
        total_in = self.goods_paid_total + self.shipping_paid_total
        if self.seller_net + self.treasury_fee + self.buyer_refund != total_in:
            raise FabricationError("conservation violated: physical job")
        for f in (
            "goods_paid_total",
            "shipping_paid_total",
            "units_ordered",
            "units_accepted",
            "seller_gross",
            "treasury_fee",
            "seller_net",
            "buyer_refund",
        ):
            if getattr(self, f) < 0:
                raise FabricationError(f"negative settlement field: {f}")


def settle_physical_job(
    *,
    goods_micros: int,
    shipping_micros: int,
    units_ordered: int,
    units_accepted: int,
    fee_ppm: int = FEE_PPM,
    threshold_ppm: int = ACCEPTANCE_THRESHOLD_PPM,
) -> PhysicalSettlement:
    """Settle a physical job at the end of its acceptance window.

    Goods payment is pro-rata to accepted units (accepted capped at
    ordered; unreviewed units auto-accept at window expiry — transport
    concern, counts arrive here as accepted). Shipping goes to the
    seller if ANY unit was accepted (the box shipped either way) and
    back to the buyer only on total rejection. Fee applies to the
    seller's gross (goods + shipping kept). ``defaulted`` is a
    reputation flag when acceptance falls below threshold — no
    collateral, no slash, on spot fabrication.
    """
    _pos_int(goods_micros, "goods_micros")
    _nonneg_int(shipping_micros, "shipping_micros")
    _pos_int(units_ordered, "units_ordered")
    _nonneg_int(units_accepted, "units_accepted")
    if not (0 < fee_ppm < PPM):
        raise FabricationError("fee_ppm must be in (0, PPM)")
    if not (0 < threshold_ppm <= PPM):
        raise FabricationError("threshold_ppm must be in (0, PPM]")

    accepted = min(units_accepted, units_ordered)
    goods_gross = (goods_micros * accepted) // units_ordered
    ship_gross = shipping_micros if accepted > 0 else 0
    seller_gross = goods_gross + ship_gross
    treasury_fee = (seller_gross * fee_ppm) // PPM
    seller_net = seller_gross - treasury_fee
    buyer_refund = (goods_micros - goods_gross) + (shipping_micros - ship_gross)

    s = PhysicalSettlement(
        goods_paid_total=goods_micros,
        shipping_paid_total=shipping_micros,
        units_ordered=units_ordered,
        units_accepted=accepted,
        seller_gross=seller_gross,
        treasury_fee=treasury_fee,
        seller_net=seller_net,
        buyer_refund=buyer_refund,
        defaulted=accepted * PPM < threshold_ppm * units_ordered,
    )
    s.check_invariants()
    return s
