"""TINY fund mechanics — NAV, creation, redemption. Pure math (Token doc).

TINY functions as an open-ended fund over the platform's productive
assets: stable reserves (treasury fee inflows) plus positions valued
by realized cash flow. This module owns the arithmetic that keeps the
fund conservative under adversarial use:

  * **NAV discipline** — tokens are only minted against contributed
    value at NAV, and only redeemed by burning at NAV. There is no
    code path for minting without inflow: a fund that can print is
    not a fund.
  * **Fund-favoring rounding** — mint FLOORS tokens issued; redemption
    FLOORS value paid out. Dust from every operation accretes to
    remaining holders, never leaks out. The alternative (rounding
    against the fund) is exploitable by high-frequency tiny
    mint/redeem cycles that each skim a micro.
  * **No mixing** — everything here is stablecoin micros and TINY
    token base-units. TINY never appears in market settlement paths
    (settlement modules do not import this one, by design).

Valuation of non-reserve positions (realized trailing cash flow only)
is a ledger/reporting concern; this module takes AUM as an input and
never guesses it.

LEGAL GATE (stated in code because it must survive refactors): a token
whose value derives from a managed asset pool has substantial
securities/fund regulatory surface. Nothing in this module ships to a
public mint without counsel sign-off. See the token-architecture doc.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = [
    "FundError",
    "FundState",
    "nav_micros_per_token",
    "mint_at_nav",
    "redeem_at_nav",
    "record_fee_inflow",
    "mint_at_nav_with_fee",
    "redeem_at_nav_with_fee",
]

TOKEN_UNIT = 1_000_000  # TINY base-units per whole token (6 decimals)


class FundError(ValueError):
    """Raised on invalid fund operations."""


@dataclass(frozen=True)
class FundState:
    """Fund snapshot. ``aum_micros`` = stable reserves at face plus
    productive positions at realized-cash-flow valuation (computed
    upstream, auditable from the ledger)."""

    aum_micros: int
    supply_base_units: int  # total TINY outstanding, in base units

    def validate(self) -> None:
        for name in ("aum_micros", "supply_base_units"):
            v = getattr(self, name)
            if not isinstance(v, int) or isinstance(v, bool) or v < 0:
                raise FundError(f"{name} must be a non-negative int")
        if (self.supply_base_units == 0) != (self.aum_micros == 0):
            # Empty fund must be empty on both sides; a supply with no
            # assets (or assets with no supply) is an accounting fault,
            # except genesis handled by mint_at_nav's bootstrap path.
            if self.supply_base_units == 0 and self.aum_micros > 0:
                # Assets with zero supply: allowed only as a transient
                # pre-genesis treasury; minting bootstraps 1:1.
                return
            raise FundError("non-zero supply with zero AUM")


def nav_micros_per_token(state: FundState) -> int | None:
    """NAV per WHOLE token, floored to int micros. None when supply is
    zero (NAV undefined pre-genesis; mint bootstraps instead)."""
    state.validate()
    if state.supply_base_units == 0:
        return None
    return (state.aum_micros * TOKEN_UNIT) // state.supply_base_units


def mint_at_nav(
    state: FundState,
    contribution_micros: int,
) -> tuple[FundState, int]:
    """Mint TINY against a stable contribution at current NAV.

    Returns ``(new_state, base_units_minted)``. Minted units are
    FLOORED: the contributor receives at most exact-NAV value, dust
    accretes to the fund. Genesis (zero supply): bootstrap at 1 micro
    per base unit against total AUM including any pre-existing
    treasury, so early treasury value is captured in the first mint's
    price rather than gifted.
    """
    state.validate()
    if (
        not isinstance(contribution_micros, int)
        or isinstance(contribution_micros, bool)
        or contribution_micros <= 0
    ):
        raise FundError("contribution_micros must be a positive int")

    if state.supply_base_units == 0:
        # Genesis: price the first mint against ALL assets (pre-seeded
        # treasury included) at 1 micro/base-unit reference.
        minted = contribution_micros  # 1:1 bootstrap
    else:
        # minted = contribution * supply / AUM, floored.
        minted = (contribution_micros * state.supply_base_units) // (
            state.aum_micros
        )
        if minted == 0:
            raise FundError(
                "contribution too small to mint one base unit at current NAV"
            )
    new_state = FundState(
        aum_micros=state.aum_micros + contribution_micros,
        supply_base_units=state.supply_base_units + minted,
    )
    new_state.validate()
    return new_state, minted


def redeem_at_nav(
    state: FundState,
    burn_base_units: int,
) -> tuple[FundState, int]:
    """Redeem by burning TINY for a pro-rata AUM payout at NAV.

    Returns ``(new_state, payout_micros)``. Payout is FLOORED; dust
    stays with remaining holders. Redeeming the entire supply pays the
    entire AUM exactly (no stranded assets). Never pays more than AUM.
    """
    state.validate()
    if (
        not isinstance(burn_base_units, int)
        or isinstance(burn_base_units, bool)
        or burn_base_units <= 0
    ):
        raise FundError("burn_base_units must be a positive int")
    if burn_base_units > state.supply_base_units:
        raise FundError("cannot burn more than outstanding supply")

    if burn_base_units == state.supply_base_units:
        payout = state.aum_micros  # full wind-down: exact, no stranding
    else:
        payout = (state.aum_micros * burn_base_units) // state.supply_base_units
    new_state = FundState(
        aum_micros=state.aum_micros - payout,
        supply_base_units=state.supply_base_units - burn_base_units,
    )
    new_state.validate()
    return new_state, payout


def record_fee_inflow(state: FundState, fee_micros: int) -> FundState:
    """Treasury fee inflow (the 1% from every settlement across all
    markets) raises AUM with NO minting — this is how NAV accretes to
    holders. The only non-mint AUM increase path."""
    state.validate()
    if not isinstance(fee_micros, int) or isinstance(fee_micros, bool):
        raise FundError("fee_micros must be int")
    if fee_micros < 0:
        raise FundError("fee_micros must be >= 0")
    return FundState(
        aum_micros=state.aum_micros + fee_micros,
        supply_base_units=state.supply_base_units,
    )


def redemption_capacity_base_units(
    state: FundState,
    stable_reserves_micros: int,
    reserve_floor_micros: int = 0,
) -> int:
    """Max base units redeemable RIGHT NOW, paid from stable reserves.

    Fund positions (model shares, revenue legs) are non-transferable
    and cannot be liquidated to meet redemptions — only the stable
    portion of AUM can pay out. Redemptions beyond this capacity must
    QUEUE (transport concern), never fail silently or pay from thin
    air. ``reserve_floor_micros`` optionally protects an operating
    buffer. Returns 0 pre-genesis.
    """
    state.validate()
    for name, v in (
        ("stable_reserves_micros", stable_reserves_micros),
        ("reserve_floor_micros", reserve_floor_micros),
    ):
        if not isinstance(v, int) or isinstance(v, bool) or v < 0:
            raise FundError(f"{name} must be a non-negative int")
    if stable_reserves_micros > state.aum_micros:
        raise FundError("stable reserves cannot exceed AUM")
    if state.supply_base_units == 0:
        return 0
    payable = max(0, stable_reserves_micros - reserve_floor_micros)
    # Largest burn whose NAV payout fits in payable:
    # payout = aum * burn // supply <= payable  →  burn <= payable*supply/aum
    return min(
        (payable * state.supply_base_units) // state.aum_micros,
        state.supply_base_units,
    )


def mint_at_nav_with_fee(
    state: FundState,
    contribution_micros: int,
    entry_fee_ppm: int,
) -> tuple[FundState, int]:
    """Mint with an entry fee that ACCRUES TO AUM (oracle-latency
    protection for volatile-asset NAV). The fee portion raises AUM
    without minting — existing holders capture it. Net contribution
    mints at NAV as usual. fee_ppm in [0, 100_000] (0-10%)."""
    if not isinstance(entry_fee_ppm, int) or isinstance(entry_fee_ppm, bool):
        raise FundError("entry_fee_ppm must be int")
    if not (0 <= entry_fee_ppm <= 100_000):
        raise FundError("entry_fee_ppm must be in [0, 100000]")
    if (
        not isinstance(contribution_micros, int)
        or isinstance(contribution_micros, bool)
        or contribution_micros <= 0
    ):
        raise FundError("contribution_micros must be a positive int")
    fee = (contribution_micros * entry_fee_ppm) // 1_000_000
    net = contribution_micros - fee
    if net <= 0:
        raise FundError("contribution consumed entirely by fee")
    mid, minted = mint_at_nav(state, net)
    final = record_fee_inflow(mid, fee)
    return final, minted


def redeem_at_nav_with_fee(
    state: FundState,
    burn_base_units: int,
    exit_fee_ppm: int,
) -> tuple[FundState, int]:
    """Redeem with an exit fee retained in AUM (accrues to remaining
    holders). Payout = NAV payout minus fee; the fee never leaves the
    fund. Full wind-down (burning the entire supply) charges NO fee —
    there is no one left to accrue to."""
    if not isinstance(exit_fee_ppm, int) or isinstance(exit_fee_ppm, bool):
        raise FundError("exit_fee_ppm must be int")
    if not (0 <= exit_fee_ppm <= 100_000):
        raise FundError("exit_fee_ppm must be in [0, 100000]")
    full_winddown = burn_base_units == state.supply_base_units
    mid, gross_payout = redeem_at_nav(state, burn_base_units)
    if full_winddown:
        return mid, gross_payout
    fee = (gross_payout * exit_fee_ppm) // 1_000_000
    net_payout = gross_payout - fee
    final = record_fee_inflow(mid, fee)
    return final, net_payout
