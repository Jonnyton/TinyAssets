"""A cron schedule runs in the owner's clock, and says which one.

LIVE EVIDENCE (2026-09-30, prod ``6235666b``, free account): the universe
created ``cron_expr "0 7 * * *"`` and told the user "7am server time". The
daemon runs in UTC, so a Pacific user was promised a morning note and would
have received a midnight one. The message was accurate; the defect was that a
cron expression had no timezone to be written in.

The DST policy asserted here is a founder decision (2026-09-30), not a
discovered behaviour:

* a local time that does NOT EXIST (spring-forward gap) fires once, at the
  first valid instant after the gap;
* an AMBIGUOUS local time (fall-back) fires once, at the FIRST occurrence;
* de-duplication is by local date + slot, never by UTC instant.

Both 2027 transitions for ``America/Los_Angeles`` are covered for ``0 1``
(ambiguous), ``0 2`` (gap) and ``0 7`` (unaffected), because those three are
exactly the cases that behave differently.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

import pytest

from tinyassets.automations import (
    Automation,
    _due_instant,
    cron_zone_name,
    next_due_at,
    slot_key_for_due,
)
from tinyassets.schedule_timezone import (
    DEFAULT_TIMEZONE,
    UnknownTimezone,
    describe_slot,
    normalize_timezone,
    resolve_zone,
    slot_exists,
    slot_instant,
    slot_key,
)

LA = "America/Los_Angeles"
#: 2027's US transitions: forward 14 March, back 7 November.
SPRING = date(2027, 3, 14)
FALL = date(2027, 11, 7)
ORDINARY = date(2027, 6, 15)


def _cron(expr: str, *, zone: str = LA, last_local: str = "", last_utc: str = "") -> Automation:
    return Automation(
        automation_id="a1",
        universe_id="u-1",
        owner_principal_id="owner-1",
        name="Morning focus note",
        branch_def_id="b1",
        trigger_kind="cron",
        interval_seconds=0,
        cron_expr=expr,
        inputs={},
        desired_state="active",
        pause_reason="",
        revision=1,
        created_at="2027-01-01T00:00:00+00:00",
        updated_at="2027-01-01T00:00:00+00:00",
        retired_at="",
        last_due_at=last_utc,
        last_run_id="",
        last_reason="",
        last_finished_at="",
        timezone=zone,
        last_due_local=last_local,
    )


def _utc(text: str) -> datetime:
    return datetime.fromisoformat(text)


# ---------------------------------------------------------------------------
# The resolution rule itself
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("day,hour,expected_utc,kind", [
    # 01:00 is ordinary in spring, AMBIGUOUS in fall.
    (SPRING, 1, "2027-03-14T09:00:00+00:00", "normal"),
    (FALL, 1, "2027-11-07T08:00:00+00:00", "ambiguous-first"),
    # 02:00 is the GAP in spring, ordinary in fall.
    (SPRING, 2, "2027-03-14T10:00:00+00:00", "gap-end"),
    (FALL, 2, "2027-11-07T10:00:00+00:00", "normal"),
    # 07:00 is unaffected by either.
    (SPRING, 7, "2027-03-14T14:00:00+00:00", "normal"),
    (FALL, 7, "2027-11-07T15:00:00+00:00", "normal"),
    (ORDINARY, 7, "2027-06-15T14:00:00+00:00", "normal"),
])
def test_a_local_slot_resolves_to_the_decided_instant(day, hour, expected_utc, kind):
    got = slot_instant(day, time(hour, 0), resolve_zone(LA))
    assert got == _utc(expected_utc), (day, hour, kind, got.isoformat())


def test_the_gap_slot_does_not_exist_and_the_others_do():
    zone = resolve_zone(LA)
    assert not slot_exists(SPRING, time(2, 0), zone), "02:00 exists on 2027-03-14?"
    assert slot_exists(SPRING, time(1, 0), zone)
    assert slot_exists(SPRING, time(7, 0), zone)
    assert slot_exists(FALL, time(1, 0), zone)


def test_the_gap_slot_fires_at_the_first_valid_instant_after_it():
    """Not skipped, and not at the pre-gap time: at the gap's END."""
    zone = resolve_zone(LA)
    got = slot_instant(SPRING, time(2, 0), zone)
    local = got.astimezone(zone)
    assert (local.hour, local.minute) == (3, 0), local.isoformat()
    # And it is the FIRST valid instant: one minute earlier is still in the gap.
    assert (got - timedelta(minutes=1)).astimezone(zone).hour == 1


def test_the_ambiguous_slot_resolves_to_the_earlier_of_its_two_occurrences():
    zone = resolve_zone(LA)
    got = slot_instant(FALL, time(1, 0), zone)
    # Both 08:00Z and 09:00Z are 01:00 local that day; the policy takes the first.
    both = [
        inst for inst in (
            _utc("2027-11-07T08:00:00+00:00"), _utc("2027-11-07T09:00:00+00:00"),
        )
        if inst.astimezone(zone).hour == 1
    ]
    assert len(both) == 2, "2027-11-07 01:00 should be ambiguous in LA"
    assert got == both[0]


# ---------------------------------------------------------------------------
# Due selection across the transitions
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("expr,day,owed_utc", [
    ("0 1 * * *", SPRING, "2027-03-14T09:00:00+00:00"),
    ("0 2 * * *", SPRING, "2027-03-14T10:00:00+00:00"),
    ("0 7 * * *", SPRING, "2027-03-14T14:00:00+00:00"),
    ("0 1 * * *", FALL, "2027-11-07T08:00:00+00:00"),
    ("0 2 * * *", FALL, "2027-11-07T10:00:00+00:00"),
    ("0 7 * * *", FALL, "2027-11-07T15:00:00+00:00"),
])
def test_each_slot_becomes_due_once_on_a_transition_day(expr, day, owed_utc):
    """Polling every minute through THIS local day owes exactly ONE run.

    The window is local midnight to local midnight, which is 23 hours on the
    spring day and 25 on the autumn one -- the point being that a transition
    changes the day's length and must not change the number of firings.
    """
    automation = _cron(expr)
    zone = resolve_zone(LA)
    start = datetime(day.year, day.month, day.day, tzinfo=zone).astimezone(timezone.utc)
    nxt = day + timedelta(days=1)
    end = datetime(nxt.year, nxt.month, nxt.day, tzinfo=zone).astimezone(timezone.utc)
    fired: list[str] = []
    moment = start
    while moment < end:
        owed = _due_instant(automation, moment)
        if owed:
            # EVERY fire is counted, repeats included. Discarding duplicates
            # before counting made this pass with de-duplication disabled
            # entirely (Codex refute, PR #4128): the assertion measured the
            # helper, not the code.
            fired.append(owed)
            # Record it the way the runner does, so the next poll sees it fired.
            automation = _cron(
                expr,
                last_local=slot_key_for_due(expr, LA, owed),
                last_utc=owed,
            )
        moment += timedelta(minutes=1)
    assert fired == [owed_utc], (expr, day, fired)
    # And the day really did change length, so the window meant something.
    hours = (end - start).total_seconds() / 3600
    assert hours == (23 if day == SPRING else 25), hours


def test_the_ambiguous_slot_is_not_owed_twice_for_two_utc_buckets():
    """The bug a UTC-keyed fence would have: 01:00 local is 08:00Z AND 09:00Z."""
    expr = "0 1 * * *"
    first = "2027-11-07T08:00:00+00:00"
    automation = _cron(expr, last_local=slot_key_for_due(expr, LA, first), last_utc=first)
    # The second occurrence of the same local slot, one hour later.
    assert _due_instant(automation, _utc("2027-11-07T09:00:00+00:00")) == ""
    assert _due_instant(automation, _utc("2027-11-07T09:30:00+00:00")) == ""


def test_the_next_local_day_is_owed_again():
    """Deduping by slot must not wedge the schedule after one fire."""
    expr = "0 7 * * *"
    first = "2027-11-07T15:00:00+00:00"
    automation = _cron(expr, last_local=slot_key_for_due(expr, LA, first), last_utc=first)
    owed = _due_instant(automation, _utc("2027-11-08T15:00:00+00:00"))
    assert owed == "2027-11-08T15:00:00+00:00", owed


def test_a_slot_is_not_owed_before_its_instant():
    automation = _cron("0 7 * * *")
    # 13:59Z on an ordinary summer day is 06:59 local -- one minute early.
    assert _due_instant(automation, _utc("2027-06-15T13:59:00+00:00")) == ""
    assert _due_instant(automation, _utc("2027-06-15T14:00:00+00:00")) != ""


def test_the_zone_moves_the_run_off_the_server_clock():
    """The live failure, as one assertion: 7am Pacific is NOT 07:00Z."""
    pacific = _cron("0 7 * * *", zone=LA)
    utc_row = _cron("0 7 * * *", zone="UTC")
    assert _due_instant(pacific, _utc("2027-06-15T07:00:00+00:00")) == ""
    assert _due_instant(utc_row, _utc("2027-06-15T07:00:00+00:00")) == (
        "2027-06-15T07:00:00+00:00"
    )
    assert _due_instant(pacific, _utc("2027-06-15T14:00:00+00:00")) == (
        "2027-06-15T14:00:00+00:00"
    )


# ---------------------------------------------------------------------------
# next_due_at agrees with the due path
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("expr,after,expected", [
    ("0 7 * * *", "2027-06-15T13:00:00+00:00", "2027-06-15T14:00:00+00:00"),
    ("0 2 * * *", "2027-03-14T06:00:00+00:00", "2027-03-14T10:00:00+00:00"),
    ("0 1 * * *", "2027-11-07T06:00:00+00:00", "2027-11-07T08:00:00+00:00"),
])
def test_next_due_at_reports_the_same_instant_the_due_path_would_owe(
    expr, after, expected,
):
    """With nothing currently owed, the reported instant is the coming slot.

    `next_due_at` returns an OWED instant when one exists (its docstring: "an
    instant at or before now means the run is owed"), so each case pins the
    previous slot as fired -- otherwise the answer is legitimately "now", and
    the test would be asserting the wrong question.
    """
    zone = resolve_zone(LA)
    previous_local = (_utc(after).astimezone(zone) - timedelta(days=1)).date()
    hour = int(expr.split()[1])
    fired = slot_key(previous_local, time(hour, 0))
    automation = _cron(expr, last_local=fired)
    assert next_due_at(automation, _utc(after)) == expected


def test_next_due_at_and_due_instant_never_disagree_across_a_transition():
    """Differential: whatever next_due_at promises is what becomes owed."""
    for expr in ("0 1 * * *", "0 2 * * *", "0 7 * * *"):
        automation = _cron(expr)
        moment = _utc("2027-03-13T12:00:00+00:00")
        promised = next_due_at(automation, moment)
        assert promised, expr
        # At the promised instant the schedule is owed, and owed exactly it.
        assert _due_instant(automation, _utc(promised)) == promised, expr


# ---------------------------------------------------------------------------
# Zone resolution and refusal
# ---------------------------------------------------------------------------


def test_an_empty_zone_reads_as_utc_so_an_old_row_keeps_its_behaviour():
    assert cron_zone_name(_cron("0 7 * * *", zone="")) == DEFAULT_TIMEZONE


def test_a_known_zone_normalizes_and_an_unknown_one_refuses():
    assert normalize_timezone(" America/Los_Angeles ") == "America/Los_Angeles"
    assert normalize_timezone("UTC") == "UTC"
    for bad in ("Mars/Olympus_Mons", "", "   ", "PST8PDT/../../etc/passwd", "x" * 200):
        with pytest.raises(UnknownTimezone):
            normalize_timezone(bad)


def test_the_refusal_names_the_field_and_an_example():
    try:
        normalize_timezone("Mars/Olympus_Mons")
    except UnknownTimezone as exc:
        assert "timezone" in str(exc)
        assert "America/Los_Angeles" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected UnknownTimezone")


# ---------------------------------------------------------------------------
# Saying which clock
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("slot,expected", [
    (time(7, 0), "7:00 AM America/Los_Angeles"),
    (time(0, 0), "12:00 AM America/Los_Angeles"),
    (time(12, 0), "12:00 PM America/Los_Angeles"),
    (time(13, 30), "1:30 PM America/Los_Angeles"),
    (time(23, 5), "11:05 PM America/Los_Angeles"),
])
def test_a_slot_is_described_with_its_zone(slot, expected):
    assert describe_slot(slot, LA) == expected


# ---------------------------------------------------------------------------
# The slot key
# ---------------------------------------------------------------------------


def test_the_slot_key_is_local_and_ordered():
    assert slot_key(FALL, time(1, 0)) == "2027-11-07T01:00"
    assert slot_key(FALL, time(1, 0)) < slot_key(FALL, time(2, 0))
    assert slot_key(SPRING, time(7, 0)) < slot_key(FALL, time(1, 0))


@pytest.mark.parametrize("expr,due,expected", [
    ("0 7 * * *", "2027-06-15T14:00:00+00:00", "2027-06-15T07:00"),
    # The gap slot's recorded instant inverts back to the slot the owner wrote.
    ("0 2 * * *", "2027-03-14T10:00:00+00:00", "2027-03-14T02:00"),
    # The ambiguous slot's FIRST occurrence.
    ("0 1 * * *", "2027-11-07T08:00:00+00:00", "2027-11-07T01:00"),
])
def test_a_recorded_instant_inverts_to_its_local_slot(expr, due, expected):
    assert slot_key_for_due(expr, LA, due) == expected


def test_an_uninvertible_instant_reports_no_slot_rather_than_guessing():
    # An instant this expression never produces.
    assert slot_key_for_due("0 7 * * *", LA, "2027-06-15T03:17:00+00:00") == ""
    assert slot_key_for_due("", LA, "2027-06-15T14:00:00+00:00") == ""
    assert slot_key_for_due("nonsense", LA, "2027-06-15T14:00:00+00:00") == ""


def test_an_old_row_with_no_local_key_still_dedupes_on_the_instant():
    """Bridge: a row written before the column must not re-fire its last slot."""
    automation = _cron("0 7 * * *", last_local="", last_utc="2027-06-15T14:00:00+00:00")
    assert _due_instant(automation, _utc("2027-06-15T14:30:00+00:00")) == ""
    # And the next day is still owed.
    assert _due_instant(automation, _utc("2027-06-16T14:00:00+00:00")) == (
        "2027-06-16T14:00:00+00:00"
    )


# ---------------------------------------------------------------------------
# A slot is missed, never backfilled
# ---------------------------------------------------------------------------


def test_a_slot_the_daemon_slept_through_is_missed_not_replayed():
    """The pre-timezone code matched only the current minute, so a slept-through
    slot was skipped. That behaviour is KEPT deliberately: a "morning note"
    arriving at lunchtime is worse than one that did not arrive, and without
    this bound a schedule created at noon would immediately owe the 7am slot
    that passed before it existed.
    """
    automation = _cron("0 7 * * *")
    # 07:00 local is 14:00Z; a poll four hours late owes nothing.
    assert _due_instant(automation, _utc("2027-06-15T18:00:00+00:00")) == ""


def test_a_slot_missed_by_minutes_is_still_claimed():
    """The other half: a restart or a deploy must not lose the run."""
    automation = _cron("0 7 * * *")
    owed = _due_instant(automation, _utc("2027-06-15T14:20:00+00:00"))
    assert owed == "2027-06-15T14:00:00+00:00", owed


def test_a_fresh_schedule_created_after_its_slot_does_not_fire_immediately():
    """A new automation is not a backlog."""
    automation = _cron("0 7 * * *")
    # Created at local noon, hours after that morning's slot.
    assert _due_instant(automation, _utc("2027-06-15T19:00:00+00:00")) == ""
    # And tomorrow's slot is owed normally.
    assert _due_instant(automation, _utc("2027-06-16T14:00:00+00:00")) == (
        "2027-06-16T14:00:00+00:00"
    )


# ---------------------------------------------------------------------------
# Zones that are not whole hours, and a DST shift that is not an hour
# ---------------------------------------------------------------------------


def _fires(expr: str, zone_name: str, day: date, *, hours: int) -> list[str]:
    """Distinct instants owed while polling every minute, recording each fire."""
    zone = resolve_zone(zone_name)
    start = datetime(day.year, day.month, day.day, tzinfo=zone).astimezone(timezone.utc)
    automation = _cron(expr, zone=zone_name)
    fired: list[str] = []
    for minute in range(hours * 60):
        owed = _due_instant(automation, start + timedelta(minutes=minute))
        if owed:
            # Repeats counted, for the reason in `test_each_slot_...` above.
            fired.append(owed)
            automation = _cron(
                expr, zone=zone_name,
                last_local=slot_key_for_due(expr, zone_name, owed), last_utc=owed,
            )
    return fired


def _local_day_hours(zone_name: str, day: date) -> float:
    """How long this local day really is -- 23, 23.5, 24, 24.5 or 25 hours.

    Both ends are converted to UTC before subtracting. Subtracting two aware
    datetimes that share a `tzinfo` gives the WALL-clock difference (a flat 24
    hours across any transition), which is the trap that made this helper
    report 24 for a 25-hour day on the first attempt.
    """
    zone = resolve_zone(zone_name)
    nxt = day + timedelta(days=1)
    start = datetime(day.year, day.month, day.day, tzinfo=zone).astimezone(timezone.utc)
    end = datetime(nxt.year, nxt.month, nxt.day, tzinfo=zone).astimezone(timezone.utc)
    return (end - start).total_seconds() / 3600


@pytest.mark.parametrize("expr,expected_slot", [
    ("0 7 * * *", "2027-06-15T07:00"),
    ("30 7 * * *", "2027-06-15T07:30"),
])
def test_a_half_hour_offset_zone_resolves_and_inverts(expr, expected_slot):
    """Asia/Kolkata is +05:30, so an hour-granular assumption would drift."""
    fired = _fires(expr, "Asia/Kolkata", date(2027, 6, 15), hours=24)
    assert len(fired) == 1, fired
    assert slot_key_for_due(expr, "Asia/Kolkata", fired[0]) == expected_slot
    # And it really is 07:00 local, not 07:00Z.
    local = _utc(fired[0]).astimezone(resolve_zone("Asia/Kolkata"))
    assert (local.hour, local.minute) == (7, int(expr.split()[0]))


#: Australia/Lord_Howe shifts by THIRTY minutes, so its spring gap is
#: 02:00-02:30 and only half of 01:30-02:00 repeats in autumn. An
#: implementation that assumed a one-hour DST step passes Los Angeles and fails
#: here, which is why this zone is in the suite.
LORD_HOWE = "Australia/Lord_Howe"


@pytest.mark.parametrize("day", [date(2027, 10, 3), date(2027, 4, 4)])
@pytest.mark.parametrize("expr", ["0 2 * * *", "30 2 * * *", "0 7 * * *"])
def test_a_thirty_minute_dst_shift_still_fires_each_slot_once(expr, day):
    """One fire per LOCAL DAY, on a day that is 23.5 or 24.5 hours long."""
    hours = _local_day_hours(LORD_HOWE, day)
    assert hours in (23.5, 24.5), (day, hours)
    # Poll only this local day, so a fire on the next date cannot be counted.
    fired = _fires(expr, LORD_HOWE, day, hours=int(hours))
    assert len(fired) == 1, (expr, day, fired)
    # It inverts to a slot on THIS local date.
    assert slot_key_for_due(expr, LORD_HOWE, fired[0]).startswith(day.isoformat())


def test_an_hourly_cron_fires_the_repeated_hour_once():
    """`0 * * * *` on a 25-hour day: 24 local slots, the ambiguous one once.

    The sharpest test of "dedupe by local slot": a UTC-keyed fence would fire 25
    times here, because the fall-back hour supplies two UTC buckets whose local
    label is the same.
    """
    day = date(2027, 11, 7)
    assert _local_day_hours(LA, day) == 25
    fired = _fires("0 * * * *", LA, day, hours=25)
    inversions = [slot_key_for_due("0 * * * *", LA, inst) for inst in fired]
    assert len(fired) == 24, fired
    assert len(set(inversions)) == 24, inversions
    # 09:00Z is 01:00 PST -- the SECOND occurrence of 01:00 -- and is skipped.
    assert "2027-11-07T09:00:00+00:00" not in fired
    assert "2027-11-07T08:00:00+00:00" in fired


# ---------------------------------------------------------------------------
# Codex refute round, PR #4128: the gap's END, not the gap's middle
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("zone_name,day,slot,expected_local", [
    # Los Angeles skips 02:00-03:00; EVERY absent label fires at 03:00.
    (LA, SPRING, time(2, 0), (3, 0)),
    (LA, SPRING, time(2, 15), (3, 0)),
    (LA, SPRING, time(2, 30), (3, 0)),
    (LA, SPRING, time(2, 59), (3, 0)),
    # Lord Howe skips only 02:00-02:30, so its absent labels fire at 02:30.
    (LORD_HOWE, date(2027, 10, 3), time(2, 0), (2, 30)),
    (LORD_HOWE, date(2027, 10, 3), time(2, 15), (2, 30)),
])
def test_every_slot_inside_a_gap_fires_at_the_gaps_end(
    zone_name, day, slot, expected_local,
):
    """The policy is "the first valid instant AFTER it" -- not "shifted by the
    offset", which is what attaching a zone to an absent wall time does.

    Codex refute: only a slot at the gap's exact START happened to land on the
    gap's end, so testing 02:00 alone read as "the policy is free". 02:15 became
    03:15 in Los Angeles and 02:45 in Lord Howe -- both inside or past the gap
    rather than at its close.
    """
    zone = resolve_zone(zone_name)
    assert not slot_exists(day, slot, zone), (zone_name, day, slot)
    local = slot_instant(day, slot, zone).astimezone(zone)
    assert (local.hour, local.minute) == expected_local, local.isoformat()
    assert local.date() == day


def test_the_gap_end_is_the_first_valid_minute_not_merely_a_valid_one():
    zone = resolve_zone(LA)
    landed = slot_instant(SPRING, time(2, 30), zone)
    # One minute earlier is still inside the gap, so this really is the edge.
    before = (landed - timedelta(minutes=1)).astimezone(zone)
    assert (before.hour, before.minute) == (1, 59), before.isoformat()


def test_several_gap_slots_collapse_to_one_firing(served_free=None):
    """`0,15,30 2 * * *` in Los Angeles on the gap day is ONE run, not three.

    All three labels are absent and all three clamp to the same instant, so the
    owner asked for three runs at times that do not exist and gets the single
    run the gap's end can carry.
    """
    expr = "0,15,30 2 * * *"
    fired = _fires(expr, LA, SPRING, hours=23)
    assert fired.count("2027-03-14T10:00:00+00:00") == 1, fired
    assert len(set(fired)) == 1, fired


def test_selection_and_persistence_agree_on_the_gap_days_slot():
    """The identity a fire is recorded under must be the one selection compares.

    Codex refute, claim 2: selection chose local 03:00 for 10:00Z and the old
    inversion stored 02:00, so the key never matched and the slot stayed owed
    all day. Both now come from one function.
    """
    expr = "0 * * * *"
    owed = _due_instant(_cron(expr), _utc("2027-03-14T10:00:00+00:00"))
    assert owed == "2027-03-14T10:00:00+00:00"
    recorded = slot_key_for_due(expr, LA, owed)
    assert recorded, "a selected instant must map to a slot"
    # Recording it settles the slot: the same moment is no longer owed.
    after = _cron(expr, last_local=recorded, last_utc=owed)
    assert _due_instant(after, _utc("2027-03-14T10:00:00+00:00")) == ""
    assert _due_instant(after, _utc("2027-03-14T10:30:00+00:00")) == ""


def test_a_gap_day_hourly_cron_does_not_stay_owed():
    """The consequence of claim 2, as a loop: no instant repeats."""
    fired = _fires("0 * * * *", LA, SPRING, hours=23)
    assert len(fired) == len(set(fired)), fired


# ---------------------------------------------------------------------------
# Codex refute: the preview must promise the instant that will actually run
# ---------------------------------------------------------------------------


#: Zones chosen to break an hour-granular or DST-naive assumption:
#: a 45-minute offset (Chatham), a 30-minute DST step (Lord Howe), a skipped
#: calendar DAY (Apia, 2011-12-30) and a plain half-hour offset (Kolkata).
_AWKWARD_ZONES = (
    "America/Los_Angeles", "Australia/Lord_Howe", "Pacific/Apia",
    "Asia/Kolkata", "Europe/Berlin", "Pacific/Chatham",
)


@pytest.mark.parametrize("zone_name", _AWKWARD_ZONES)
@pytest.mark.parametrize("year", [2011, 2027, 2028])
def test_wall_label_order_is_instant_order_once_a_gap_clamps(zone_name, year):
    """The invariant that makes selection's ordering unambiguous.

    Clamping an absent label to the gap's end COLLAPSES labels onto one instant
    but never inverts them, so ascending wall labels give ascending instants.
    Asserted rather than assumed because it is why `_latest_cron_slot` may take
    the latest candidate and `next_due_at` the earliest ahead, and it is also
    the honest account of one of Codex's findings on PR #4128: the reported
    Lord Howe ordering disagreement was a SYMPTOM of the gap bug, not an
    independent defect -- with clamping correct, the two orders coincide.

    Every day of the year at 15-minute granularity, across zones picked to
    break a whole-hour assumption.
    """
    zone = resolve_zone(zone_name)
    labels = [time(hour, minute) for hour in range(24) for minute in (0, 15, 30, 45)]
    day = date(year, 1, 1)
    inversions = []
    while day.year == year:
        instants = [slot_instant(day, slot, zone) for slot in labels]
        inversions += [
            (day.isoformat(), str(labels[i]), str(labels[i + 1]))
            for i in range(len(instants) - 1)
            if instants[i] > instants[i + 1]
        ]
        day += timedelta(days=1)
    assert not inversions, inversions[:5]


@pytest.mark.parametrize("zone_name,expr,moment", [
    # The reported case, which the gap fix also settles.
    (LORD_HOWE, "15,30 2 * * *", "2027-10-02T15:29:00+00:00"),
    (LA, "15,30 2 * * *", "2027-03-14T09:59:00+00:00"),
    (LA, "0 * * * *", "2027-03-14T09:59:00+00:00"),
])
def test_next_due_at_promises_the_instant_selection_will_owe(zone_name, expr, moment):
    automation = _cron(expr, zone=zone_name)
    promised = next_due_at(automation, _utc(moment))
    assert promised, (zone_name, expr, moment)
    owed = _due_instant(automation, _utc(promised))
    assert owed == promised, (zone_name, expr, promised, owed)


# ---------------------------------------------------------------------------
# Codex refute: grace is for a late poller, not a licence to run history
# ---------------------------------------------------------------------------


def test_a_slot_before_the_automation_existed_is_never_owed():
    """Created at 07:59 local, a 7am schedule must not immediately owe 07:00.

    Codex refute, claim 3: the grace window had no `created_at` floor, so a
    fresh schedule fired for a slot that passed before there was a schedule.
    """
    automation = _cron("0 7 * * *")
    automation = replace(automation, created_at="2027-06-15T14:59:00+00:00")
    assert _due_instant(automation, _utc("2027-06-15T14:59:30+00:00")) == ""
    # The next day's slot is owed normally.
    assert _due_instant(automation, _utc("2027-06-16T14:00:00+00:00")) == (
        "2027-06-16T14:00:00+00:00"
    )


def test_a_slot_after_creation_is_still_claimed_inside_grace():
    """The floor must not cost a genuinely late poller its run."""
    automation = replace(
        _cron("0 7 * * *"), created_at="2027-06-15T13:00:00+00:00",
    )
    assert _due_instant(automation, _utc("2027-06-15T14:20:00+00:00")) == (
        "2027-06-15T14:00:00+00:00"
    )


# ---------------------------------------------------------------------------
# A row whose stored zone stopped resolving must not take the poller with it
# ---------------------------------------------------------------------------


def test_an_unresolvable_stored_zone_makes_one_row_unrunnable_not_the_pump():
    """`docs/concerns/automation-timezone-host-aliases.md`, the crash half.

    The tz database drops and renames zones, and a host-specific name may not
    exist on the next host at all. Due selection scans EVERY automation for a
    universe, so a row it cannot evaluate has to disqualify itself rather than
    raise -- otherwise one bad row stops every other schedule in that universe.
    """
    broken = _cron("0 7 * * *", zone="Mars/Olympus_Mons")
    assert _due_instant(broken, _utc("2027-06-15T14:00:00+00:00")) == ""
    assert next_due_at(broken, _utc("2027-06-15T13:00:00+00:00")) == ""
    assert slot_key_for_due("0 7 * * *", "Mars/Olympus_Mons", "2027-06-15T14:00:00+00:00") == ""


def test_a_healthy_row_beside_a_broken_one_still_fires():
    """The point of failing soft: the other schedules keep running."""
    broken = _cron("0 7 * * *", zone="Mars/Olympus_Mons")
    healthy = _cron("0 7 * * *", zone=LA)
    moment = _utc("2027-06-15T14:00:00+00:00")
    assert _due_instant(broken, moment) == ""
    assert _due_instant(healthy, moment) == "2027-06-15T14:00:00+00:00"


# ---------------------------------------------------------------------------
# 2b: the owner's zone, captured and then used as the default
# ---------------------------------------------------------------------------


@pytest.fixture
def account_store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    base = tmp_path / "output"
    base.mkdir()
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(base))
    return base


def test_an_unknown_account_has_no_zone_rather_than_a_wrong_one(account_store):
    from tinyassets.storage.account_timezone import get_account_timezone

    assert get_account_timezone(account_store, owner_user_id="nobody") == ""


def test_a_reported_zone_round_trips(account_store):
    from tinyassets.storage.account_timezone import (
        get_account_timezone,
        set_account_timezone,
    )

    assert set_account_timezone(
        account_store, owner_user_id="owner-1", timezone_name=" America/Los_Angeles ",
    ) == LA
    assert get_account_timezone(account_store, owner_user_id="owner-1") == LA


def test_reporting_again_replaces_it(account_store):
    from tinyassets.storage.account_timezone import (
        get_account_timezone,
        set_account_timezone,
    )

    set_account_timezone(account_store, owner_user_id="o", timezone_name=LA)
    set_account_timezone(account_store, owner_user_id="o", timezone_name="Europe/Berlin")
    assert get_account_timezone(account_store, owner_user_id="o") == "Europe/Berlin"


def test_an_unresolvable_report_is_refused_and_leaves_the_stored_zone_alone(
    account_store,
):
    """A client that cannot name its zone must not be able to CLEAR one."""
    from tinyassets.storage.account_timezone import (
        get_account_timezone,
        set_account_timezone,
    )

    set_account_timezone(account_store, owner_user_id="o", timezone_name=LA)
    for bad in ("Mars/Olympus_Mons", "", "  ", "../../etc/localtime"):
        with pytest.raises(UnknownTimezone):
            set_account_timezone(account_store, owner_user_id="o", timezone_name=bad)
    assert get_account_timezone(account_store, owner_user_id="o") == LA


def test_two_accounts_do_not_share_a_zone(account_store):
    from tinyassets.storage.account_timezone import (
        get_account_timezone,
        set_account_timezone,
    )

    set_account_timezone(account_store, owner_user_id="a", timezone_name=LA)
    set_account_timezone(account_store, owner_user_id="b", timezone_name="Europe/Berlin")
    assert get_account_timezone(account_store, owner_user_id="a") == LA
    assert get_account_timezone(account_store, owner_user_id="b") == "Europe/Berlin"


# ---------------------------------------------------------------------------
# Saying which clock, on the returned automation
# ---------------------------------------------------------------------------


def test_a_returned_cron_automation_carries_its_zone_and_prose():
    from tinyassets.api.automations import _cron_timezone, _schedule_local

    automation = _cron("0 7 * * *")
    assert _cron_timezone(automation) == LA
    assert _schedule_local(automation) == "7:00 AM America/Los_Angeles"


def test_a_cron_row_with_no_stored_zone_reads_as_utc_not_as_blank():
    from tinyassets.api.automations import _cron_timezone, _schedule_local

    automation = _cron("0 7 * * *", zone="")
    assert _cron_timezone(automation) == "UTC"
    assert _schedule_local(automation) == "7:00 AM UTC"


def test_a_multi_slot_expression_names_no_single_time():
    """Better '' than picking one of several slots to display as THE time."""
    from tinyassets.api.automations import _schedule_local

    assert _schedule_local(_cron("0,30 7 * * *")) == ""
    assert _schedule_local(_cron("0 * * * *")) == ""


def test_a_non_cron_trigger_claims_no_zone():
    from dataclasses import replace

    from tinyassets.api.automations import _cron_timezone, _schedule_local

    interval = replace(_cron("0 7 * * *"), trigger_kind="interval")
    assert _cron_timezone(interval) == ""
    assert _schedule_local(interval) == ""


#: The real create rig: serving assignment, owner home, admin ACL, a private
#: branch this owner authored, and the consumer flag -- every precondition
#: `register_automation` checks before it looks at a trigger. Borrowed from the
#: suite that already stands it up, so these tests exercise the production path
#: rather than a second fixture that could drift from it.
@pytest.fixture
def real_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    from tests.test_automation_events import FOLLOWED, _seed_branch, _seed_owner
    from tests.test_background_budget_finalization_e2e import _seed_serving_assignment

    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("TINYASSETS_ASSIGNED_QUEUE_CONSUMER", "1")
    _seed_serving_assignment(tmp_path)
    _seed_owner(tmp_path)
    _seed_branch(tmp_path, branch_def_id=FOLLOWED, visibility="private")
    monkeypatch.setattr(
        "tinyassets.provider_serving_binding.list_serving_universes",
        lambda _base: ["universe_alice"],
    )
    return tmp_path


def _register(base: Path, **kw):
    from tests.test_automation_events import FOLLOWED
    from tinyassets.auth.middleware import identity_context
    from tinyassets.auth.provider import Identity
    from tinyassets.automations import register_automation

    owner = "acct_alice"
    with identity_context(Identity(user_id=owner, username=owner)):
        return register_automation(
            base,
            universe_id="universe_alice",
            owner_principal_id=owner,
            name="Morning focus note",
            branch_def_id=FOLLOWED,
            **kw,
        )


def test_the_create_path_defaults_to_the_owners_stored_zone(real_home):
    """END TO END through `register_automation`, not through a helper.

    This is the assertion the whole change exists for: an owner whose app has
    reported `America/Los_Angeles` gets a 7am schedule in THEIR clock without
    having to know a timezone field exists.
    """
    from tinyassets.storage.account_timezone import set_account_timezone

    set_account_timezone(real_home, owner_user_id="acct_alice", timezone_name=LA)
    stored = _register(real_home, cron_expr="0 7 * * *")
    assert stored.timezone == LA
    # And it is the OWNER's 7am: 14:00Z in June, not 07:00Z.
    assert _due_instant(stored, _utc("2027-06-15T07:00:00+00:00")) == ""
    assert _due_instant(stored, _utc("2027-06-15T14:00:00+00:00")) != ""


def test_the_create_path_falls_back_to_utc_when_no_zone_is_known(real_home):
    stored = _register(real_home, cron_expr="0 7 * * *")
    assert stored.timezone == DEFAULT_TIMEZONE


def test_the_create_path_honours_an_explicit_override(real_home):
    from tinyassets.storage.account_timezone import set_account_timezone

    set_account_timezone(real_home, owner_user_id="acct_alice", timezone_name=LA)
    stored = _register(
        real_home, cron_expr="0 7 * * *", timezone_name="Europe/Berlin",
    )
    assert stored.timezone == "Europe/Berlin"


def test_the_create_path_refuses_an_unknown_zone(real_home):
    from tinyassets.automations import AutomationUnavailable

    with pytest.raises(AutomationUnavailable) as caught:
        _register(
            real_home, cron_expr="0 7 * * *", timezone_name="Mars/Olympus_Mons",
        )
    assert caught.value.reason == "timezone_invalid"


def test_an_interval_automation_stores_no_zone(real_home):
    """Only a wall-clock trigger has a clock; an interval must not claim one."""
    stored = _register(real_home, interval_seconds=900)
    assert stored.timezone == ""


def test_the_stored_zone_survives_a_read_back(real_home):
    """The column is really persisted, not just set on the returned object."""
    from tinyassets.automations import AutomationStore
    from tinyassets.storage.account_timezone import set_account_timezone

    set_account_timezone(real_home, owner_user_id="acct_alice", timezone_name=LA)
    created = _register(real_home, cron_expr="0 7 * * *")
    reread = AutomationStore(real_home).get(created.automation_id)
    assert reread is not None
    assert reread.timezone == LA


def test_the_owner_facing_refusal_names_the_field_and_an_example():
    from tinyassets.api.automations import _UNAVAILABLE_DETAIL

    detail = _UNAVAILABLE_DETAIL["timezone_invalid"]
    assert "America/Los_Angeles" in detail
    assert "IANA" in detail


def test_the_projection_never_shows_a_time_without_a_zone():
    """The rule, structurally: `schedule_local` always carries its zone name."""
    from tinyassets.api.automations import _schedule_local

    for expr in ("0 7 * * *", "0 0 * * *", "30 13 * * 1"):
        prose = _schedule_local(_cron(expr))
        assert prose, expr
        assert LA in prose, prose
        assert any(part in prose for part in ("AM", "PM")), prose
