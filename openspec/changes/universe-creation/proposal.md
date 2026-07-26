## Why

The original `universe-creation` change became a monolithic second source of
truth after its core birth, serial-id, and soul-bundle slices landed and were
backfilled into canonical specs. The remaining work must be narrowed to the
lifecycle behavior this change still owns. Provider authority, eligible
provider selection, setup-route readiness, and provider receipts now have
approved owners in `constrain-set-engine-provider-authority` and its named
successors.

## What Changes

- Treat the verified first-contact birth path as an existing prerequisite:
  opening `converse` with create scope may reserve, materialize, and bind a home
  universe without invoking a model. Without create scope it creates no binding
  and returns the current structured home-create/load error with
  `auth_scope_required: true` rather than an awaiting card.
- Consume the server-owned provider-authority request carrier and typed
  hold/result interfaces without constructing an authority bundle, selecting
  eligible providers, or minting provider authority in the universe layer.
- Preserve completed birth/home binding when provider execution holds. The
  action layer maps the typed hold to the canonical setup-required payload and
  advertises only successor-proven paths that are live for the request surface
  after the effective provider-authority V2 cutover. While that gate is dark,
  the provider owner preserves shipped setup-path behavior; cutover cannot
  retain raw API-key deposit or unavailable desktop/market routes.
- On success the chatbot only relays/renders the universe intelligence's reply;
  it never authors that reply. Reply generation, learning extraction,
  fulfillment evidence, and provider fallback remain governed by their
  provider-authority and receipt owners.
- Retire public HTTP universe creation, make all public birth self-serialize
  without caller-selected ids, project learned names into the immutable-id
  index, and finish existing-root serial migration and cleanup.
- Remove the obsolete proposed `universe-creation` capability. This change now
  modifies only the existing lifecycle capability that owns its residual work.

## Capabilities

### New Capabilities

- None.

### Modified Capabilities

- `universe-lifecycle-and-soul`: Finish the remaining public creation boundary,
  learned-name index projection, and existing-root migration/cleanup behavior.

## Impact

- Affected runtime areas: first-contact birth/result integration, universe
  creation, the universe index, and existing-root migration. Provider
  selection, requester-host authority, accepted-market execution, and receipts
  are dependencies rather than implementation owned here.
- Public behavior: first contact can birth a universe without consuming compute;
  public callers cannot choose its id; HTTP is not a creation route; execution
  without complete authority is held with actionable setup information.
- Security gate: provider-backed first contact remains dark until
  `constrain-set-engine-provider-authority`, the appropriate requester-host or
  connector successor, and provider-attempt receipts land their reviewed
  interfaces. This change may consume those interfaces but SHALL NOT implement
  a parallel provider-authority path.
