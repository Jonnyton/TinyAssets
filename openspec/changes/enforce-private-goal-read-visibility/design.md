# Design: viewer-aware private Goal reads

## Decision

Enforce the existing `private` state on reads. Do not reject private writes and
do not introduce a migration.

Private Goals are already an intentional stored state, are exercised by the
Goal surface tests, and align with PLAN.md's instance-private direction. A
write-side rejection would remove a real concept and still require a risky
disposition for existing confidential rows.

## Identity boundary

The three user-facing Goal read actions resolve their viewer internally with
`permissions.current_actor_id()`. That helper reads only request-scoped signed
identity and returns `anonymous` otherwise. The Goal API does not accept a
viewer argument from MCP callers and does not use `_current_actor()`, whose
legacy environment fallback is attribution-only and is not authorization.

## Storage boundary

`list_goals` and `search_goals` apply viewer filtering by default. `get_goal`
accepts an optional `viewer` only because it is also the daemon's trusted
internal record loader; when a viewer is supplied it returns `KeyError` for a
private Goal owned by someone else. The public Goal `get` action always supplies
the resolved request viewer.

The anonymous sentinel never owns private data. Even if a legacy row has
`author=anonymous`, an unauthenticated request cannot read it.

## Disclosure behavior

- List/search omit inaccessible private rows and do not include them in counts.
- Direct lookup uses the existing not-found response, preventing an existence
  oracle.
- Public rows and a signed-in owner's own private rows retain their current
  response shapes.
