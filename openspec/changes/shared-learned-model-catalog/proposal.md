## Why

A user cannot select a model the platform has never heard of, and today the
platform only hears about a model in two ways: the source enumerates its own
catalogue, or the owner declared the id by hand. A source that cannot enumerate —
a subscription CLI is the common case — therefore shows a stale hand-declared
set, labelled "owner-selected; availability not verified". Founder, 2026-09-26:
*"i cant seem to select fable as a user for the llm"*, against a `claude-code`
source listing only a provider default plus two older ids.

Shipping a patch whenever a vendor releases a model is the wrong fix and the
founder said so: *"we also should not have to put out new patches for providers
so make sure it is made provider agnostic always updates for users once one user
adds the newly available model"*.

So the platform learns. When a model id **succeeds in a real call** through a
source, that fact is worth keeping, and it is worth keeping for everyone with
that kind of source — one user's successful call is evidence the id exists and
works, and that evidence carries nothing private.

## What Changes

- A platform-wide **learned model catalog**: exactly three fields per row —
  source kind, model id, first-verified time. No user id, no universe id, no
  prompt, no reply, no credential. A failed or merely-declared id never enters.
- Recording happens only where a call has already **succeeded** through the
  source, so the catalog is a record of verified facts, not of attempts.
- A universe whose source kind appears in the catalog sees, from the catalog,
  **only the newest model of each class** for that source kind. A user's own
  previously verified ids stay on their own list and are **unioned on top, never
  removed** — a model someone is happily using does not disappear because a newer
  one was verified elsewhere.
- **Class and newest are derived, with no vendor or model names in platform
  code.** Class is the model id with version tokens removed (numeric runs and
  date stamps); a named suffix such as `-sol` is part of the class, not the
  version, so it reads as a distinct line rather than a newer version of another.
  Newest is the highest version tuple, tie-broken by first-verified time. One
  function, table-driven tests. An id whose shape cannot be parsed is its own
  class — never a guess.
- New model availability reaches every user with no release: the first verified
  call publishes the id for that source kind.

## Capabilities

### New Capabilities

- `learned-model-catalog`: platform-wide verified model facts, contributed by
  successful calls and surfaced newest-per-class per source kind.

### Modified Capabilities

- `provider-capability-negotiation`: a source that cannot enumerate its catalogue
  gains catalog-contributed candidates instead of only owner-declared ids.

## Impact

Storage: one new platform-scoped table. Surface: additional rows in the existing
advisory model options document — no new MCP handle, no change to what the
selection API accepts. Authority: unchanged; a catalog row is evidence that an id
exists, never permission to use it, and serving still requires accepted model
access for that universe.

**The cross-user floor.** This is the first store that is deliberately shared
across users, so the invariant is explicit and tested: the catalog carries no
user data of any kind. Reading it tells you which model ids work for a kind of
source; it cannot tell you who used one, when they used it, from which universe,
or what they asked. The only time recorded is when the id was FIRST verified
platform-wide, which is a property of the id, not of a person.

Owner: Claude Code; branch `claude/model-catalog`. Split from the model-dropdown
UI change (#4027) on the lead's instruction: that one is UI-only, this one is
storage shape plus a cross-user surface and carries its own Codex round.
