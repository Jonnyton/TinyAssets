"""Which clock a schedule runs on, and how a wall-clock slot becomes an instant.

Live 2026-09-30 (prod ``6235666b``): a universe created ``cron_expr "0 7 * * *"``
and told its user "7am server time". The daemon runs in UTC, so a Pacific user
was promised a morning note and would have received a midnight one. The message
was accurate; the defect was that a cron expression had no timezone to be
written in.

This module owns three things so no caller has to decide them twice:

* what a valid timezone name is (an IANA name ``zoneinfo`` can resolve),
* how a local wall-clock slot becomes a UTC instant across a DST transition,
* how a slot is named for de-duplication.

The DST policy is a founder decision (2026-09-30), not an implementation
detail::

    a local time that does not exist (spring-forward gap)
        -> fires ONCE, at the first valid instant after the gap
    an ambiguous local time (fall-back, two occurrences)
        -> fires ONCE, at the FIRST occurrence

Both fall out of ``naive.replace(tzinfo=zone).astimezone(utc)`` with no
special-casing, which was measured before it was relied on
(``America/Los_Angeles``, both 2027 transitions):

* ``2027-03-14 02:00`` does not exist; the expression yields ``10:00Z``, which
  is ``03:00 PDT`` -- the instant the gap ends.
* ``2027-11-07 01:00`` occurs twice; ``fold=0`` yields ``08:00Z``, the earlier.

So the policy is the default behaviour of the stdlib, and the value of stating
it here is that a future reader can tell it was CHOSEN.
"""

from __future__ import annotations

from datetime import date, datetime, time, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

#: What a schedule runs on when nothing better is known. Never a guess at the
#: owner's clock: a wrong zone silently moves every run, where UTC is at least
#: stated and visible.
DEFAULT_TIMEZONE = "UTC"

#: Longest accepted IANA name. The longest real one is well under this; the
#: bound is here so an unbounded string never reaches `ZoneInfo` or a column.
MAX_TIMEZONE_CHARS = 100


class UnknownTimezone(ValueError):
    """A timezone name ``zoneinfo`` cannot resolve. Never silently defaulted."""


def resolve_zone(name: str) -> ZoneInfo:
    """``ZoneInfo`` for an IANA name, or ``UnknownTimezone``.

    Refuses rather than falling back, because a silent fallback is exactly how
    an owner is told 7am and given midnight.
    """
    text = (name or "").strip()
    if not text:
        raise UnknownTimezone("a timezone name is required")
    if len(text) > MAX_TIMEZONE_CHARS or not text.isprintable():
        raise UnknownTimezone("timezone must be a short printable IANA name")
    try:
        return ZoneInfo(text)
    except (ZoneInfoNotFoundError, ValueError, OSError) as exc:
        # `ZoneInfo` raises OSError-family errors for a name shaped like a path.
        raise UnknownTimezone(
            f"'{text}' is not a known timezone; pass an IANA name such as "
            "'America/Los_Angeles' or 'UTC'"
        ) from exc


def is_known_timezone(name: str) -> bool:
    try:
        resolve_zone(name)
    except UnknownTimezone:
        return False
    return True


def normalize_timezone(name: str) -> str:
    """The stored form of a validated name. Raises for anything unknown."""
    resolve_zone(name)
    return (name or "").strip()


def slot_instant(local_day: date, slot: time, zone: ZoneInfo) -> datetime:
    """The UTC instant a local wall-clock slot means on ``local_day``.

    Implements the decided DST policy; see the module docstring for the
    measurements. ``fold=0`` (the default) is the earlier of an ambiguous pair,
    and a non-existent wall time normalizes forward to the end of the gap --
    which is "the first valid instant after it".
    """
    naive = datetime.combine(local_day, slot)
    return naive.replace(tzinfo=zone).astimezone(timezone.utc)


def slot_exists(local_day: date, slot: time, zone: ZoneInfo) -> bool:
    """Whether this wall time occurs at all on this day in this zone.

    Not used to skip the slot -- the policy is to fire at the end of the gap --
    but a caller that wants to SAY what happened needs to be able to tell.
    """
    naive = datetime.combine(local_day, slot)
    back = slot_instant(local_day, slot, zone).astimezone(zone).replace(tzinfo=None)
    return back == naive


def slot_key(local_day: date, slot: time) -> str:
    """The de-duplication key: local date + slot, never a UTC instant.

    A UTC key fires an ambiguous slot TWICE, because its two occurrences are
    different UTC minutes -- 2027-11-07 01:00 in Los Angeles is both 08:00Z and
    09:00Z. The owner asked for one 1am note, so the identity of a firing is its
    local slot.

    Lexicographically ordered, so "already fired" is a string comparison and
    two pollers cannot disagree about it.
    """
    return f"{local_day.isoformat()}T{slot.hour:02d}:{slot.minute:02d}"


def local_now(moment: datetime, zone: ZoneInfo) -> datetime:
    """``moment`` as a wall clock in ``zone``."""
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(zone)


def describe_slot(slot: time, zone_name: str) -> str:
    """``7:00 AM America/Los_Angeles`` -- a time is never shown without its clock.

    The live failure was a universe saying "7am server time" because that was
    the only true thing it could say. Every surface that shows a schedule uses
    this, so none of them can reintroduce a bare time.
    """
    hour = slot.hour % 12 or 12
    meridiem = "AM" if slot.hour < 12 else "PM"
    return f"{hour}:{slot.minute:02d} {meridiem} {zone_name}"
