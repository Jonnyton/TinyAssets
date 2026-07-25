## Why

`build-forward-platform-capabilities` records the outbound boundary as a cross-slice target but is an umbrella, not a buildable slice: its design decision D1 requires every independently deployable slice to become a narrower OpenSpec change before implementation. This change is that slice, created by umbrella task 1.2, and is the sole active owner of the released `boundary-layer` delta.

The shipped surface is deliberately narrower than the target. `openspec/specs/external-effect-adapters/spec.md` and `openspec/specs/external-effect-receipts/spec.md` describe landed per-effect authority, exact destination consent, and a caller-hint receipt lifecycle, and the latter states outright that no deterministic goal/schedule/item identity, destination-native reconciliation, or whole-batch guarantee exists yet, "until the active boundary-layer change implements them". Nothing currently makes an outbound connection a first-class revocable resource, separates a numeric action cap from tool permission, or fails an incompatible artifact edge at compile time.

## What Changes

- Make outbound connections first-class resources in a grant ledger: owning user, scope, provider, destination, revocation state, per-universe revocable grant, and no universe-held credential.
- Add machine-readable unprompted-action caps that are independent of tool authorization and of spend caps, with a held receipt and an actionable remediation surface instead of silent behavior.
- Keep adapters credential-blind: scoped domain/verb/redacted contracts only, with secret lookup, network execution, cap enforcement, and receipt writing inside a trusted daemon-side proxy.
- Give every goal and universe a durable addressable webhook URL and email address for typed inbound items, owning ingress/receipt/typing/eligibility-cutoff while `demand-side` owns the timezone-aware schedule that consumes them.
- Make node inputs and outputs content-addressed typed artifacts whose incompatible edges fail at graph compilation, before a run starts or tokens are spent, with decoders and encoders as ordinary commons capability-class nodes.
- Replace caller-supplied dedup hints with system-derived deterministic idempotency identity, journal-before-fire, destination-native reconciliation for ambiguous outcomes, and explicit whole-batch hold instead of partial-silent results.
- Generate the non-MCP long tail as reviewed, remixable, attributed commons adapters from OpenAPI into MCP-shaped scoped actions, so connecting to an API is a universe action rather than a platform integration ticket.

### Ownership boundaries

- **Consumes, does not redefine:** `credential-vault` (secret custody and per-universe overlay), `identity-auth-and-access-control` (authenticated actor and visibility/ownership axes), `external-effect-adapters` and `external-effect-receipts` (landed effect dispatch and receipt lifecycle), `graph-execution-substrate` (compilation and run state).
- **Delegates money:** every value-moving boundary effect settles through the single authenticated transaction transport owned by `paid-market-track-e-wave-2-transport`. This change SHALL NOT create a second accounting path.
- **Delegates price:** quote construction, indicative-versus-firm provenance, ranking, freshness, and executable totals belong to `paid-market-live-price-discovery`. This change carries none of them.
- **Supersession, not silent divergence:** implementing the replay-safety requirement supersedes the named as-built limitation requirement in `openspec/specs/external-effect-receipts/spec.md`. That canonical requirement MUST be modified in the same landing lane that syncs this change; leaving both is spec drift.

## Capabilities

### New Capabilities

- `boundary-layer`: outbound connection grants, action caps, credential-blind adapters, goal/universe inboxes, typed artifact flows, and destination-reconciled replay-safe effect batches.

### Modified Capabilities

- None yet. The `external-effect-receipts` supersession is recorded as a landing-lane obligation in `tasks.md` rather than a pre-written delta, because the as-built requirement is currently true and this change is unimplemented.

## Impact

This is an active, unimplemented target change. Nothing here is shipped behavior. On implementation it will affect the connection/grant storage shape, the effect dispatch and receipt path, adapter execution isolation, graph compilation type checking, inbound webhook/email ingress, and the deployment surface that terminates those addresses. It depends on the umbrella's cross-slice invariants, on `credential-vault` for custody, and on `paid-market-track-e-wave-2-transport` for any value movement. It must not be synced until its requirements are implemented, its §14 concurrency/load proof passes, and a rendered chatbot conversation plus post-fix clean-use evidence exist for any public surface it exposes.
