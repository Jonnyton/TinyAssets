# Two gaps a credential removal leaves behind

**Found 2026-08-31** by a Codex refute review of PR #2755 (Q2 and Q3), which
returned REJECT. Five of its seven findings were fixed in that PR. These two are
real, are **not** regressions introduced by it, and are recorded rather than
folded in — both are pre-existing, and both are narrower than the five that
blocked the merge.

## 1. Removal does not clear the deposit-ownership row

`forget_credential` rewrites the vault file. It does **not** delete the matching
row in `llm_credential_deposit_owners`
(`credential_vault.py:586`, `:598`, `:650`).

So after Alice removes `github`, the stale `http:github` ownership row survives.
A later deposit of that destination **by a different user** is then treated as
an ownership transfer and refused (`api/http_connection.py:714`), which
contradicts the promise `remove_http` returns:

> the destination `'github'` is free -- deposit it again whenever you like

**Bounded:** it is true for the ORIGINAL owner, which is the case that motivated
removal and the one the founder's re-deposit exercises. It bites when a
different principal re-deposits the same destination in the same universe.

**Fix:** delete the ownership row inside `forget_credential`, in the same
exclusive lock, next to the vault rewrite — one authority fact, one place.
Needs a test with two principals, which is why it is not a one-liner.

## 2. An orphaned secret can be removed by any admin of the universe

`remove_http` checks ownership as `resource is not None and
resource.owner_user_id != actor`. When the connection row is **absent** there is
no owner to compare, so the check is skipped.

That state is reachable: `connect_http` deposits the vault record before it
creates the connection row, and the module documents the window
(`api/http_connection.py:550`, `:578`) as leaving "INERT partial state" a retry
heals. During it, any *other* admin of the same universe can call `remove_http`
and delete the orphaned secret — and learn it existed from `secrets_removed: 1`.

**Bounded:** admin of that universe already, a narrow crash window, and the
secret is unusable (no connection references it). It is an information leak and
an unauthorised deletion, not credential disclosure.

**Fix:** when there is no connection row, fall back to the deposit-ownership row
for the owner check rather than skipping it. That row is the same one gap 1 says
to delete on removal, so the two want fixing together.

## Why these were not fixed with the other five

The five that were fixed were introduced by that PR or would have broken the
first live credential ask: a plain-text field persisting a credential, a
completeness check keyed off the wrong count, multi-value assembly for a scheme
that cannot encode it, an unenforced URL length bound, and a Control Station
prompt still teaching the removed no-fields shape.

These two are pre-existing, need a two-principal test each, and touch the
ownership table rather than the deposit path. Doing them properly is a change of
its own; folding them in would have meant a larger diff on an authority path at
the moment it most needs to be reviewable.
