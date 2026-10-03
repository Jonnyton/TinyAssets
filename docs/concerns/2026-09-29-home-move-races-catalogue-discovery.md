---
severity: P2
title: A home move between the home check and catalogue discovery still allows one read
filed: '2026-09-29'
summary: prepare_owned_model_plan checks current home inside a SQL fence, then performs
  catalogue discovery outside it. A home move landing in that window still permits one
  discovery request against the universe the owner just left; the recheck refuses only
  afterward. Pre-existing and shared with the conversation path.
---

# A home move between the home check and catalogue discovery still allows one read

**Filed:** 2026-09-29
**Verified:** 2026-09-29, Codex refutation of `run-provider-parity` (branch head `0215a4d5`),
reproduced with a real run and a synthetic HTTP transport.
**Severity:** P2

## Source (verbatim)

> C2 DISAGREE_EVIDENCE — `served_model_plan.py:394` checks current home before releasing
> SQL/fence; discovery at `:487` has no home check in `discovery_snapshot/_context` or
> `discovery_http` broker path; moving home just before real refresh yielded one
> old-universe discovery read then recheck rejected current home. HTTP transport
> synthetic, metadata/authority/graph paths real; source broker code verifies grant
> owner/universe but not founder_home. No evidence IO is under assignment
> fence/write lock.

## What this is and is not

`prepare_owned_model_plan` deliberately performs its discovery IO outside both the
assignment fence and every SQL transaction (no network under a write lock). Between the
in-transaction `check_current_home` and that IO, a home move can land. The consequence is
**one catalogue read on the owner's own grant for the universe they just left**, after
which `PreparedPlan.recheck` refuses.

Not a cross-user issue: the grant, the connection and the credential all belong to that
owner and that universe, and leaving home does not revoke the grant. Codex found no
foreign-owner credential use (C1 `AGREE`, C3 `AGREE`, C4 `AGREE`).

**Pre-existing, and shared.** This is the same function and the same window the
conversation path uses; `run-provider-parity` only made runs reach it too. Fixing it means
changing how a shared resolver fences its IO, which is a different lane from that change.

## What would settle it

Either (a) re-read current home immediately before the discovery call and refuse there, or
(b) pass the observed home generation into the discovery broker so the outbound request
itself carries it. (a) narrows the window; only (b) closes it. Whichever lands must hold
for the conversation path too, since one resolver serves both.
