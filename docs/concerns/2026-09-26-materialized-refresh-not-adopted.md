# Materialized rotations can remain outside the vault

**Filed:** 2026-09-26
**Verified:** 2026-09-26, Windows/Python 3.14, PR #4032 at `776abaaf`
**Severity:** P1

## Source (verbatim)

> Materialized rotations can remain outside the vault.

Source: finding 6 of the Codex refute-review of PR #4032 (head `6a94d242`), recorded as a comment on that PR. The finding is quoted above in full; the review transcript is not kept in the repo.

Code at that commit: `credential_vault.py:2088, 2097; subscription_refresh.py:541-572`.

The PR comment carries the reviewer's verification commands and observed outputs.
Concurrent working-tree fixes were not reviewed; this finding is pinned to the
requested committed head, not a claim about those edits.

## Closure

Use the actual materialization resolver including its default path, and share one freshness comparison in both directions.


## Partially closed on `claude/credential-refresh`

**Verified:** 2026-09-26, Windows/Python 3.14, at the branch head that carries the
fix (not `776abaaf`, which this finding was pinned to). The second half of the closure is done: ONE freshness comparison is now shared in both directions -- `_strictly_newer` takes the same record-stamp fallback `credential_vault._on_disk_document_is_newer` uses, so adoption can no longer restore an older document over a fresh deposit (`test_the_two_newest_wins_comparators_agree_on_a_fresh_deposit`). The deposit path also goes through the shared record builder now, without which that fallback had nothing to read.

STILL OPEN: the first half. `_materialized_document` scans the record's own values, so a home materialized at the DEFAULT path (no path field on the record) is not seen. Closing it needs the materialization resolver itself, which is keyed by service name -- and naming a service in `subscription_refresh` is what `scripts/check_channel_agnostic.py` refuses. So the closure is a resolver that answers 'where is this record's home' without the caller naming the source.
