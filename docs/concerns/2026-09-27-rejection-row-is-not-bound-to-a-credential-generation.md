---
severity: P2
title: A sign-in rejection row is not bound to the credential generation it describes
filed: '2026-09-27'
summary: >-
  A failed refresh releases its credential locks before recording the rejection, so a
  successful replacement in between leaves the old rejection marking the NEW credential
  as dead.
---

**Filed:** 2026-09-27
**Verified:** 2026-09-27, gpt-6-astra refute-review round 2 of the spent-sign-in lane,
against `81ed2db3`.
**Severity:** P2 -- a narrow interleaving, and the wrong outcome is a card over a
working connection rather than a dead connection with no card.

## Source (verbatim)

> There is also an ordering concern: a failed refresh releases its credential locks
> before recording rejection (`subscription_refresh.py:721`). A successful replacement
> and clear can occur between those operations, after which the old rejection marks the
> new credential dead. Bind rejection state to credential generation and conditionally
> record/clear it under the credential lock.

## Why it matters

`record_refresh_rejected` is keyed by `(universe_id, service)` and carries a timestamp,
not an identity. It therefore describes "this service" rather than "the credential that
was refused". The refresh releases the per-credential lock and the vault admission
before it writes the row, so between those two moments the owner can deposit a working
credential (which clears the row) and the late write can then re-assert a rejection
against it.

The lane already removes the other half of this class -- a row whose credential no
longer exists raises no card -- but a row whose credential was *replaced* still can.

## Closure

Carry the credential's generation or record digest on the row, and record or clear it
under the same lock the refresh holds, so a write cannot describe a credential that is
no longer there. Both stores are already reachable from inside that hold.
