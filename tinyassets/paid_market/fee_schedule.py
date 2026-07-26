"""Versioned canonical settlement fee schedules.

**Positivity is not canonicality.**  A settlement that carries *some* positive
fee proves nothing: a 1-micro fee on a 1,000,000-micro gross conserves exactly
and is still not the fee the platform charges.  A settlement is canonical only
when its ``fee_micros`` equals the amount its *bound schedule version* derives
from the settled gross.

This module owns the version binding only.  The amount comes from the landed
canonical primitive :func:`tinyassets.paid_market.forwards.canonical_fee_micros`,
so the paid market has exactly one fee formula and a schedule can only choose
its rate — never a second arithmetic.  All money is integer micros; no float
appears anywhere in this path.

An unknown, empty, or non-text version fails closed: an unversioned fee is not
a canonical fee.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping

from tinyassets.paid_market.forwards import FEE_PPM, canonical_fee_micros

__all__ = [
    "CANONICAL_FEE_SCHEDULE_VERSION",
    "FEE_SCHEDULES",
    "FeeSchedule",
    "FeeScheduleError",
    "fee_schedule",
    "scheduled_fee_micros",
]


class FeeScheduleError(ValueError):
    """The bound fee schedule version is unknown or the fee is not its amount."""


@dataclass(frozen=True)
class FeeSchedule:
    """One immutable, content-pinned fee version."""

    version: str
    fee_ppm: int


CANONICAL_FEE_SCHEDULE_VERSION = "tinyassets.paid-market.fee.v1"

# Immutable registry: a version is added, never edited in place, so a settlement
# recorded under an existing version can never be re-derived to a new amount.
FEE_SCHEDULES: Mapping[str, FeeSchedule] = MappingProxyType(
    {
        CANONICAL_FEE_SCHEDULE_VERSION: FeeSchedule(
            version=CANONICAL_FEE_SCHEDULE_VERSION, fee_ppm=FEE_PPM
        ),
    }
)


def fee_schedule(version: object) -> FeeSchedule:
    """Resolve one enrolled schedule version, or fail closed."""
    if not isinstance(version, str) or not version:
        raise FeeScheduleError("fee_schedule_version must be non-empty text")
    schedule = FEE_SCHEDULES.get(version)
    if schedule is None:
        raise FeeScheduleError("unknown_fee_schedule_version")
    return schedule


def scheduled_fee_micros(gross_micros: int, *, fee_schedule_version: object) -> int:
    """Return the exact integer fee the bound schedule derives for this gross."""
    return canonical_fee_micros(gross_micros, fee_schedule(fee_schedule_version).fee_ppm)
