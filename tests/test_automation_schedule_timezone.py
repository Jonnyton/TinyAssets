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
        if owed and owed not in fired:
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
