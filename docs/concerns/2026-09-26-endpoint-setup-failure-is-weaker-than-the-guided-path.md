---
severity: P1
title: API-key setup failure is weaker than the guided path
filed: '2026-09-26'
summary: 'the guided answer requires `status: "answered"` and re-reads serving; the endpoint path falls back to the rail, whose handler reads any non-error result as sent (`{}` included), never re-reads, and asks for the key again instead of a one-tap finish. The spec requirement is narrowed to the guided path until this lands'
---

# API-key setup failure is weaker than the guided path

**Filed:** 2026-09-26, from the owed cross-family review of
`notification-is-the-setup`, run against what #3964 (`be32f2a2`) shipped — verdict
summary on the sync PR. **Severity:** P1. **Owner:** unassigned.

## The finding

"Only an explicit answer counts" holds on the GUIDED sign-in path: that handler
checks `status === "answered"` and re-reads serving state either way
(`tinyassets/onboarding/app.html`, the hosted answer handler).

The API-key / own-server path is weaker in three ways:

1. On failure it tells the owner to finish the ask in the ordinary rail. That
   generic handler checks only `r.error`, so `{}`, a non-JSON tool result
   normalised to `{reply: ...}`, and any other non-error object take its success
   branch, display "Sent", and relay a chat turn.
2. Its failure and thrown-result branches do not re-read `/mcp/app/me`, so the app
   does not learn whether the universe is now powered.
3. It offers no one-tap "Finish connecting" — the owner has to paste the key again.

The reviewer executed the `{}` case and confirmed both the "Sent" display and the
relay.

## Why the spec was narrowed instead

The lead's instruction for that lane was docs-only, with code changes reserved for
a P0 (one was found and fixed: a typed credential surviving sign-out). Rather than
let `openspec/specs/onboarding-connection-progress/spec.md` assert a guarantee the
endpoint path does not meet, the requirement is now titled "Only an explicit answer
counts, **on the guided path**" and states what the endpoint path does instead.
That is honest as-built truth, and it is the smaller of the two wrongs — but it is
a narrower promise than the one the change set out to make.

## The fix

Give the endpoint path the same three properties as the guided one: treat only
`status: "answered"` as success, re-read what powers the universe after any answer
attempt, and offer the one-tap finish instead of asking for the key again. The
generic rail handler's non-error-means-sent behaviour is the shared root — fixing
it there covers both paths and anything added later, but it is a wider blast
radius, so decide deliberately which layer takes the change.

Then widen the spec requirement back and delete this file.

## Related

The same review found `foldedModelAccess()` selecting on action type and count
rather than on free-only access; that is recorded in the spec text as as-built
behaviour rather than as a concern, because the approval sentence the owner reads
is rendered from the request itself and carries the access it is granting.
