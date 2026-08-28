# I archived a universe that WAS bound to a WorkOS user

**Severity:** P2 (recovered) · **Filed:** 2026-08-28 · **Surface:** live `/data` on the droplet

## What happened

Acting on the founder rule *"no universe should exist that is not bound to a WorkOS
user"*, I archived three universes on 2026-08-28. One of them —
`u-01ky3zh1arr8qth8jee7zx63pq` — **was** bound, to `user_01KY3ZGR4VY0DYQ6BVJS4ZM5Y5`.
The `founder_home` row survived and kept pointing at a directory that no longer existed,
so that user's home would have resolved to nothing on their next `converse`.

Recovered the same day: the archive was a `tar.gz`, not a delete, so
`tar xzf /data/_removed_universes_20260828/u-01ky3zh1arr8qth8jee7zx63pq.tar.gz` restored
all 16 files intact (`soul.md`, `identity.md`, `soul_versions/`, …).

## Why it happened

I inventoried bindings and then removed on a *different* signal than the one I had
inventoried. The check that would have caught it is one line — for each candidate, is
there a `founder_home` row whose `universe_id` is this directory? — and I did not run it
immediately before the destructive step. Hard Rule 13 says *inventory before you destroy*;
I inventoried, then let the inventory go stale across the intervening work.

## What actually saved it

Archiving instead of deleting. Nothing else did: no test covers live-data cleanup, the
binding row did not stop the removal, and the daemon logged nothing because nothing asked
for that universe in between.

## What would prevent a repeat

The destructive step should read the binding table *itself*, in the same command, rather
than trusting a listing produced earlier — the same "re-verify a premise before acting on
it" rule `AGENTS.md` already states for citations. There is no script for universe
cleanup; if one is written, that check belongs inside it and the archive-not-delete
behaviour belongs there too.

## Related

`docs/host-actions.md` — "Legacy pre-credential data in `/data`" carries the two decisions
this left open (twelve legacy workspaces, and `u-tiny` being unbound).
