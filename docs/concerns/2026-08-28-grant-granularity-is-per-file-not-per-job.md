# A grant is approved per file, so a job already approved keeps stopping for permission

**Filed:** 2026-08-28
**Severity:** P2 — friction, not a hole. But it is friction on the exact axis the
founder has already ruled on twice.

## Source (verbatim)

Founder, 2026-08-28, on being shown an `extend_http` tab asking to add one file
path to a GitHub grant they had already funded:

> as for the other thing it seems an intermeteat step for something it already
> has approval to drive to the end

And earlier the same day, on credential prompts generally:

> adding something like a github api or any other credential should be done one
> or as they expire as needed, not for each action with that credential

## What happened

The universe was approved to open a pull request: its `github` connection was
deposited with the endpoints that job needs — read `main`'s ref, create a branch,
read/write `app.html`, open a pull. It then needed to write **one more file in
the same repo** (`request_theme.json`), and that required a fresh owner approval,
because endpoint matching is exact on host, method and path
(`storage/outbound_connections.py`).

So a job the founder had already approved end-to-end stopped and asked again for
a strictly smaller thing than what was already granted: another file, same repo,
same key, same purpose.

## The structural point

The grant's unit is **the endpoint**. The user's unit is **the job**. Those are
not the same shape, and the gap between them is paid by the user, once per file
the agent turns out to need.

Exact-path matching is the right *enforcement* primitive — it is what makes a
grant auditable and what stops a key reaching somewhere nobody agreed to. The
problem is that it is also the *approval* primitive, so the user is asked to
authorize implementation detail. An agent cannot enumerate every file it will
touch before it starts, and if it over-asks up front to avoid coming back, the
grant sentence becomes long enough that nobody reads it — which is worse.

Note this is not solved by `extend_http` (which correctly removed the *re-paste*,
so the ask is now a plain yes/no). It removed the typing, not the interruption.

## Directions worth weighing

1. **Approve a scope, enforce a path.** Let the user approve something the size
   of a job — "this key, this repo, read and write" — and keep exact-path
   matching underneath as the audit record of what was actually called.
2. **Ask once, widen silently within the approved scope.** An extension that
   stays inside what was already approved (same host, same repo prefix, same
   methods) applies without a prompt and is *recorded* for review, rather than
   gated.
3. **Ask for the job, not the call.** Have the agent declare the outcome it wants
   ("open a PR changing files under `tinyassets/onboarding/`") and derive the
   endpoint set from it.

Any of these has to preserve the property the current design gets right: nothing
the user did not agree to should ever be reachable, and what *was* reachable must
be reconstructible after the fact.

## How to resolve this file

Delete it when a universe approved to do a job can finish that job without
returning for a second approval on a narrower thing — and the endpoint-level
enforcement record still shows exactly which calls were made.
