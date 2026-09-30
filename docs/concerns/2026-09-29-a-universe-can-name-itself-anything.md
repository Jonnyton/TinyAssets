---
severity: P3
title: A universe's display name can be agent-set, and notifications put it in an identity line
filed: '2026-09-29'
summary: A soul-learned display name is chosen by the universe's own agent, not typed by its owner, and notifications render it as "<name> asks". So an agent can name its universe "TinyAssets Security". No cross-user reach and the owner's own device only, but the fix belongs where a name is accepted, with its provenance in hand, not in each surface that renders one.
---

# A universe's display name can be agent-set, and it is an identity line

Found by `gpt-6-astra` reviewing PR #4122 round 2. Partly fixed there; the rest
is a naming-lane question, not a notifications one.

## The observation

`tinyassets/api/universe.py` accepts a **learned** display name — one the
universe's own agent derived from its soul, not one the person typed — and
`set_universe_display_name` stores it. Notifications put that name in the
title (`owner_notifications._universe_title`). Astra drove the real handler
and got:

- `TinyAssets Security` → `TinyAssets Security asks`
- `x asks` → `x asks asks`
- `U+200B` → an invisible identity line

So the claim "no agent-controlled text reaches the title" was too strong. What
is true is narrower and is now what the code and its tests say.

## What is enforced now

`_universe_title` sanitises the name for the identity position: invisible and
bidi-control characters are removed, a name that already ends in the fixed
suffix cannot double it, and the name is bounded in bytes as well as
characters. The **structure** of the title is server-owned and unreachable from
any ask. `tests/test_owner_notifications.py::test_a_universe_name_cannot_fake_the_title_structure`
pins all of that, and the over-claiming test name was corrected.

## What is not, and why it is not a notifications fix

A universe called `TinyAssets Security` still renders as
`TinyAssets Security asks`. That is the owner's own universe, named in the
owner's own account, appearing on the owner's own device — no cross-user reach
and no other user's content. Astra agreed with that framing in round 1.

But it is worth deciding deliberately, because two things differ:

- a **person** naming their universe `TinyAssets Security` is their choice to
  make and the platform should probably allow it;
- their **agent** naming it that from a soul it wrote, with no person in the
  loop, is the agent choosing how the platform's own surfaces describe it.

Only the second is a problem, and the only place to fix it is where the name is
accepted — not in every surface that renders one. Notifications are the first
surface to put a display name in an identity position; the app header and the
commons listing already do something similar.

## The fix when the naming lane takes it

Decide whether a **learned** name (as opposed to an owner-typed one) may
contain a platform-reserved word, and enforce it once at
`set_universe_display_name` with the provenance of the name in hand. Every
renderer then inherits it. Acceptance: a person can still name their universe
what they like; an agent-learned name cannot claim to be the platform.

## Severity

Not a floor breach: no cross-user reach, no other user's data, and the surface
is dark until slice 2 ships device registration. It is a truth-in-labelling
question about one field, on the owner's own screen.
