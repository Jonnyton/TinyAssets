---
severity: P2
title: Account and automation timezones accept whatever the host's tz database resolves
filed: '2026-09-30'
summary: '`schedule_timezone.resolve_zone` accepts any name ZoneInfo resolves, so host-specific aliases like `localtime` are stored on Linux and rejected on Windows; the crash half (a stored zone that stops resolving raising out of due selection) is fixed, the portability contract is still undecided'
---

# Zone validation accepts host-specific names as IANA account zones

Review: PR #4128, requested head b955e79d, base 7261fcb1. P2 portability
correctness, not a demonstrated cross-account write or arbitrary file read.

`tinyassets/schedule_timezone.py:66` accepts everything ZoneInfo resolves.
The exact head module accepts `localtime` and `posixrules` in the installed
Linux oracle image (230e3656cb05), but rejects both on this Windows host.
`localtime` refers to host clock configuration, not a portable owner's zone.
The account setter stores these accepted strings unchanged. On a host where
they no longer resolve, account_timezone.py:112 returns empty and later creates
fall back to UTC; an existing cron with such a zone raises in due selection.

Restrict account/automation zones to portable timezone identifiers, or define
and enforce a normalization contract for system-specific aliases.

Negative checks passed: absolute/traversal paths, NUL, blank, whitespace,
10000-character names and non-string JSON were refused; previous account value
survived. Handler returned 401 without identity and 403 for another origin.
Supplying owner_user_id='b' while signed in as 'a' changed only a's timezone.

## The crash half is FIXED (2026-09-30, PR #4128)

This finding had two parts. "An existing cron with such a zone raises in due
selection" is closed: `_latest_cron_slot` and `next_due_at` now catch
`UnknownTimezone` beside the existing `CronParseError`, so a row whose stored
zone no longer resolves disqualifies ITSELF and logs, instead of raising out of
a poll that is scanning every automation in the universe. Reproduced first
(`Mars/Olympus_Mons` raised out of `_due_instant`), then pinned by
`test_an_unresolvable_stored_zone_makes_one_row_unrunnable_not_the_pump` and
`test_a_healthy_row_beside_a_broken_one_still_fires`.

## What is still OPEN

The portability question itself: `resolve_zone` accepts whatever the host's tz
database resolves, so `localtime` / `posixrules` are accepted on Linux and
refused on Windows. That needs a decision rather than a patch — restricting to
a curated list would refuse legitimate zones on hosts whose database is newer
or older than the list, and the value is owner-supplied and only selects a
clock.

**How to resolve this file:** decide the contract (accept any name the host
resolves, or a stated portable set), implement it in
`schedule_timezone.resolve_zone`, and delete this file. Until then the
behaviour is: accepted if the host resolves it, and a row that later becomes
unresolvable stops scheduling and says so in the log rather than failing either
silently or loudly.
