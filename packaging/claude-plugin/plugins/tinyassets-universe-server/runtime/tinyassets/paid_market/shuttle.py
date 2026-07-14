"""MPW shuttle economics — pure math (Track I).

A shuttle run sells a fixed die area to many designs and splits the
mask/fab cost. Two exactness-critical computations:

**Cost apportionment** — each design pays area-proportional cost with
exact conservation (reuses ``apportion_exact``; the shuttle operator's
fee is a ppm skim taken first, mirroring ``distribute_revenue``).

**Gate-forfeit accounting** — designs that fail their own sign-off
gates (DRC/LVS/timing) before mask freeze forfeit nothing and pay
nothing: they simply drop out and the shuttle re-apportions across
survivors (or refunds everyone if it falls below viability). Risk
split is explicit: *your design failing its gates is your problem and
costs you only your time; the shuttle failing in fab is everyone's
problem and refunds everyone* — that split is what makes pooled
silicon safe for first-time designers.

Same discipline as the rest of the package: ints only, fail-loud,
conservation asserted.
"""

from __future__ import annotations

from dataclasses import dataclass

from tinyassets.paid_market.pool import PoolError, apportion_exact

__all__ = [
    "ShuttleError",
    "ShuttleAllocation",
    "allocate_shuttle",
]

PPM = 1_000_000


class ShuttleError(PoolError):
    """Raised on invalid shuttle parameters."""


@dataclass(frozen=True)
class ShuttleAllocation:
    """Cost split for one shuttle at mask freeze."""

    die_area_um2: int
    total_cost_micros: int
    operator_fee_micros: int
    design_costs: dict[str, int]  # design_id -> micros owed
    area_used_um2: int

    def check_invariants(self) -> None:
        if (
            sum(self.design_costs.values()) + 0
            != self.total_cost_micros
        ):
            raise ShuttleError("conservation violated: shuttle cost")
        if self.operator_fee_micros < 0:
            raise ShuttleError("negative operator fee")
        if self.area_used_um2 > self.die_area_um2:
            raise ShuttleError("area overcommit")


def allocate_shuttle(
    *,
    die_area_um2: int,
    total_cost_micros: int,
    operator_fee_ppm: int,
    design_areas_um2: dict[str, int],
    min_fill_ppm: int = 500_000,
) -> ShuttleAllocation:
    """Allocate a shuttle at mask freeze.

    ``design_areas_um2`` contains ONLY designs that passed their
    sign-off gates — gate failures were dropped upstream and owe
    nothing. Feasibility: total area must fit the die, and the shuttle
    must be at least ``min_fill_ppm`` full (default 50%) or it is not
    viable and should be rescheduled rather than soaking the survivors
    with the empty area's cost. Cost basis is the FULL die: each
    design pays ``total_cost × its_area / die_area`` — unfilled area
    is the operator's inventory risk, not the participants' (this is
    how commercial shuttles price, and it keeps a design's cost
    knowable at signup regardless of who else shows up).

    The operator fee (``operator_fee_ppm`` of the design payments) is
    accounted inside each design's payment, not on top — reported for
    the ledger, conservation unaffected.
    """
    for name, v in (
        ("die_area_um2", die_area_um2),
        ("total_cost_micros", total_cost_micros),
    ):
        if not isinstance(v, int) or isinstance(v, bool) or v <= 0:
            raise ShuttleError(f"{name} must be a positive int")
    if not (0 <= operator_fee_ppm < PPM):
        raise ShuttleError("operator_fee_ppm must be in [0, PPM)")
    if not (0 < min_fill_ppm <= PPM):
        raise ShuttleError("min_fill_ppm must be in (0, PPM]")
    if not design_areas_um2:
        raise ShuttleError("no gate-passing designs: shuttle not viable")
    for d, a in design_areas_um2.items():
        if not d:
            raise ShuttleError("design id must be non-empty")
        if not isinstance(a, int) or isinstance(a, bool) or a <= 0:
            raise ShuttleError(f"area for design {d!r} must be a positive int")

    area_used = sum(design_areas_um2.values())
    if area_used > die_area_um2:
        raise ShuttleError(
            f"designs need {area_used} um2 but die is {die_area_um2} um2"
        )
    if area_used * PPM < min_fill_ppm * die_area_um2:
        raise ShuttleError(
            "shuttle below minimum fill: reschedule rather than run hollow"
        )

    # Each design's cost: exact area-proportional share of the cost
    # attributable to used area, apportioned with exact conservation.
    used_cost = (total_cost_micros * area_used) // die_area_um2
    design_costs = apportion_exact(used_cost, design_areas_um2)
    operator_fee = (used_cost * operator_fee_ppm) // PPM

    alloc = ShuttleAllocation(
        die_area_um2=die_area_um2,
        total_cost_micros=used_cost,
        operator_fee_micros=operator_fee,
        design_costs=design_costs,
        area_used_um2=area_used,
    )
    alloc.check_invariants()
    return alloc


def break_even_units(
    *,
    nre_micros: int,
    commodity_unit_micros: int,
    custom_unit_micros: int,
) -> int | None:
    """Units at which custom silicon beats the off-the-shelf module:
    smallest n with nre + n*custom <= n*commodity. None if custom never
    wins (unit cost >= commodity). This is the number the universe
    quotes in design conversations ('break-even ~800 units') — pinned
    here so every surface computes it identically, ceiling-rounded
    (partial units don't exist)."""
    for name, v in (
        ("nre_micros", nre_micros),
        ("commodity_unit_micros", commodity_unit_micros),
        ("custom_unit_micros", custom_unit_micros),
    ):
        if not isinstance(v, int) or isinstance(v, bool) or v <= 0:
            raise ShuttleError(f"{name} must be a positive int")
    margin = commodity_unit_micros - custom_unit_micros
    if margin <= 0:
        return None
    return -(-nre_micros // margin)  # ceil division
