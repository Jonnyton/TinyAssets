## Why

The original `universe-creation` change became a monolithic second source of
truth after its core birth, serial-id, and soul-bundle slices landed and were
backfilled into canonical specs. The remaining work must be expressed as small
deltas to the capabilities that now own it, especially the unresolved rule that
first contact may use only requester-authorized or accepted-market resources.

## What Changes

- Treat the verified first-contact birth path as an existing prerequisite:
  opening `converse` with create scope may reserve, materialize, and bind a home
  universe without invoking a model. Without create scope it creates no binding
  and returns the current structured home-create/load error with
  `auth_scope_required: true` rather than an awaiting card.
- Add a fail-closed execution-authority contract. A provider call requires a
  complete authorized bundle: requester-owned or accepted-market compute, plus
  requester-owned model access or an accepted-market model grant when the
  workload requires model access separately.
- Keep every provider choice and fallback inside that authorized bundle.
  Project-maintainer, project-founder, and platform-operator credentials, quota,
  auth homes, hardware, and accounts are never eligible for another user's
  workload.
- Apply the same authority boundary to the universe intelligence's reply and
  to learning extraction. On success the chatbot only relays/renders the
  universe intelligence's reply; it never authors that reply. The two phases
  may select different providers admitted by the same authority boundary.
- When authority is absent or partial, allow birth/binding to complete but make
  no provider invocation and return a structured held/setup-required result
  with the missing elements and BYOC/market setup paths.
- Retire public HTTP universe creation, make all public birth self-serialize
  without caller-selected ids, project learned names into the immutable-id
  index, and finish existing-root serial migration and cleanup.
- Remove the obsolete proposed `universe-creation` capability. This change now
  modifies the two existing canonical capabilities that own the residual work.

## Capabilities

### New Capabilities

- None.

### Modified Capabilities

- `identity-auth-and-access-control`: Require a complete requester-owned or
  accepted-market authority bundle before reply generation or learning
  extraction, with fail-closed held/setup behavior otherwise.
- `universe-lifecycle-and-soul`: Finish the remaining public creation boundary,
  learned-name index projection, and existing-root migration/cleanup behavior.

## Impact

- Affected runtime areas: first-contact routing, provider selection/fallback,
  requester BYOC resolution, accepted-market execution grants, learning
  extraction, execution receipts, universe creation, the universe index, and
  existing-root migration.
- Public behavior: first contact can birth a universe without consuming compute;
  public callers cannot choose its id; HTTP is not a creation route; execution
  without complete authority is held with actionable setup information.
- Security gate: runtime implementation depends on the requester BYOC and
  accepted-market authority paths plus opposite-provider security review. No
  authority implementation may land from this spec rewrite alone.
