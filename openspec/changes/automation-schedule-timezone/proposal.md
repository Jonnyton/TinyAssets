# A schedule runs in a timezone, and says which one

**Public surface + storage.** One cross-family review is owed before landing.

## Why

Live, 2026-09-30 (prod `6235666b`, free account, the run that followed
#4108/#4123): the universe created `cron_expr "0 7 * * *"` and told the user
"7am server time". The daemon runs in UTC, so a Pacific user was told their
morning note would arrive at 7am and it will arrive at **midnight**.

The cause is not a wrong message — the message was accurate. It is that a cron
expression had no timezone to be written in:

- `tinyassets/automations.py:_due_instant` matches with
  `_cron_matches(expr, time.localtime(moment.timestamp()))` — the *process's*
  clock, which is the container's, which is UTC.
- Nothing anywhere stores a user's timezone. The app formats every timestamp it
  displays with `Intl.DateTimeFormat` **client-side only**
  (`tinyassets/onboarding/app.html:1547-1551`), so the browser knows the zone,
  never sends it, and no column exists to receive it.

So the platform displays local times it computes in the browser while running
schedules on a clock the user never chose, and the only honest thing it could
say was the thing that reads as a bug.

Verified before proposing (`America/Los_Angeles`, both 2027 transitions):
`next_due_at`'s minute-skip arithmetic is *not* the defect — it recomputes local
fields each pass and agrees with a brute-force walk. The defect is the absent
zone, and, once a zone exists, two decisions DST forces.

## What changes

**The owner's zone is captured.** The app reports
`Intl.DateTimeFormat().resolvedOptions().timeZone` on sign-in/load and it is
stored on the account. One IANA name, validated against `zoneinfo`.

**An automation carries a `timezone`.** Resolved once, at create: the owner's
stored zone, or UTC when none is known, or whatever the owner passes to override
it. Stored on the row, so evaluation reads only the row and changing the account
zone later cannot silently move an existing schedule.

**DST is decided, not discovered** (founder direction, 2026-09-30):

| local time | policy |
|---|---|
| does not exist (spring-forward gap) | fires **once**, at the first valid instant after the gap |
| ambiguous (fall-back, occurs twice) | fires **once**, at the **first** occurrence |

Both fall out of `naive.replace(tzinfo=zone).astimezone(utc)` with no
special-casing — measured, not assumed: on 2027-03-14 `02:00` resolves to
`10:00Z` (= `03:00 PDT`, the instant the gap ends) and on 2027-11-07 `01:00`
resolves to `08:00Z` (the earlier of its two occurrences).

**Dedupe moves to the local slot.** Today a cron fire is deduped against
`last_due_at >= bucket` where the bucket is a UTC minute. Under a zone that is
wrong in exactly the ambiguous case: the two `01:00` occurrences on a fall-back
day are *different* UTC minutes, so the schedule would fire twice for one local
`01:00`. The fence key stays the UTC instant (it must — it is what the run claim
is keyed on), and a second recorded value, the local slot, is what decides
whether a slot has already fired.

**The zone is shown wherever a schedule is.** `read_graph target="automations"`
and the app both read `7:00 AM America/Los_Angeles`, so the universe can no
longer describe a schedule without saying which clock it is on.

## Non-goals

- Per-automation DST *overrides*. One policy, stated above.
- Re-resolving an existing automation's zone when the account zone changes. The
  row is authoritative once written; the owner can patch it.
- `interval_seconds` and `event_type` triggers, which have no wall-clock slot.

## Scope note

The founder is the only user and there are no stored automations that predate
this, so the two added columns need no backfill: an empty `timezone` reads as
UTC, which is exactly what those rows already do today.
