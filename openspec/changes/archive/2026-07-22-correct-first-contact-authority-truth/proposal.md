## Why

The canonical identity spec currently treats successful first-contact birth and a successful
provider-generated reply as one guarantee. The implementation guarantees atomic home birth and
binding, then enters a separate conversation path that can fail honestly, so the as-built spec must
stop promising provider speech merely because birth succeeded.

## What Changes

- Clarify that the opening authenticated `converse` call atomically reserves, materializes, and
  binds the founder's home before returning to the conversation entry path.
- Remove the false canonical guarantee that successful birth necessarily returns a first-person
  provider reply.
- Preserve all existing create-scope, concurrency, anonymous, and pure-read guarantees.
- Correct the insufficient-create-scope outcome to the structured `auth_scope_required` creation
  failure the `converse` entry path actually returns, rather than an unimplemented awaiting card.
- Correct the live MCP access wording to the as-built write/admin ACL boundary instead of claiming
  all `converse` calls are founder-only.
- Leave requester/BYOC and accepted-market execution authority as unbuilt work in the active
  `universe-creation` change; this correction does not claim that enforcement exists.

## Capabilities

### New Capabilities

- None.

### Modified Capabilities

- `identity-auth-and-access-control`: Separate the as-built home-birth guarantee from the subsequent
  conversation execution outcome.
- `live-mcp-connector-surface`: Apply the same birth-versus-execution boundary to the public
  first-contact scenario.

## Impact

- Canonical requirement truth only: `identity-auth-and-access-control` and
  `live-mcp-connector-surface`.
- No runtime, API, storage, authorization, or deployment behavior changes.
- The residual execution-authority design remains in `openspec/changes/universe-creation/` and is not
  synced by this correction.
