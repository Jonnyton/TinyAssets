## Context

Canonical `identity-auth-and-access-control` and
`universe-lifecycle-and-soul` already contain the landed first-contact birth,
serial-id, founder-home, and soul-bundle behavior. Opening authenticated
`converse` may reserve, materialize, and bind one home without invoking a
provider; `get_status` remains a pure read.

Provider-backed speech is a later transition. The approved
`constrain-set-engine-provider-authority` target (PR #1784, exact reviewed
candidate `abdca5fe`) owns the server-derived request carrier, engine
assignment, eligible-provider boundary, typed hold, migration, and surface
readiness rules. Its published handoff requires this change to remove the
caller-built authority bundle, raw BYOC/market promises, and provider receipt
`authority_class` ownership. Named successors own requester-host activation and
Tier-1 accepted-market remote execution; `provider-attempt-receipts` owns
result-local provider evidence.

The residual `universe-creation` change therefore has one design job: finish
the lifecycle migration and consume the provider owners' interfaces at the
action boundary without becoming another authority issuer.

## Goals / Non-Goals

**Goals:**

- Preserve the separation between zero-compute birth and provider execution.
- Pass only canonical server-derived target universe/request lineage into the
  provider-authority owner.
- Preserve completed birth when provider execution holds and map the typed hold
  to the canonical setup-required payload.
- Relay a successful universe reply verbatim and carry the same opaque provider
  request capability across model-backed learning extraction without widening
  it.
- Finish public self-serialization, learned-name index projection,
  descriptive-root migration, reference verification, and safe legacy-root
  cleanup.

**Non-Goals:**

- Constructing requester/market authority bundles or eligible provider sets.
- Resolving BYOC, local host, subscription, hardware, or accepted-market
  grants.
- Isolating provider child processes or defining fallback.
- Minting provider authority, extending credential authority enums, or creating
  a parallel receipt.
- Advertising raw API-key deposit or a setup route not proven live on the
  current request surface.
- Re-specifying canonical birth, soul, reset, ACL, visibility, Branch, mobile,
  or personification behavior.

## Decisions

### D1 - Keep one lifecycle delta

The obsolete broad `universe-creation` capability is gone. This change retains
only its `universe-lifecycle-and-soul` delta. The duplicate
`identity-auth-and-access-control` delta is removed because
`constrain-set-engine-provider-authority` owns the canonical provider-hold and
surface-readiness requirements.

### D2 - Birth and execution remain separate transitions

Opening authenticated `converse` may complete the existing atomic
founder-home birth transaction before provider authority is ready. Successful
birth proves only that the universe exists and is bound; it does not imply that
provider execution or a first-person reply succeeded. A hold preserves the
materialized `universe_id`.

### D3 - Universe creation consumes authority; it never issues it

The universe action layer passes canonical target universe and request lineage
to the provider-authority owner. It MUST NOT accept a caller-built authority
bundle, derive an eligible provider set, scan ambient credentials, translate
queue/host identity into provider permission, or mint a provider receipt.

`constrain-set-engine-provider-authority` owns
`ProviderAuthorityHeldError`, `ProviderRequestCapability`, engine assignment,
provider selection/fallback, and the rule that ordinary maintainer resources
are never requester authority. Requester-host and connector-market successors
own their distinct capability issuance and execution seams.

### D4 - The action layer maps outcomes without inventing setup paths

When the provider owner returns a typed authority hold, the universe action
layer preserves completed birth and maps it directly to the canonical
`engine_setup_required_payload`. The result contains `status=held`,
`reason=setup_required`, the materialized `universe_id`, typed missing
elements, and only setup paths the owning successor proves live and completable
for that surface. It MUST NOT require provider exhaustion or fabricate a
universe reply.

Raw `byo_api_key` deposit is not advertised. Accepted-market setup appears only
after `activate-connector-requester-authority` lands its connector-visible
agreement/result and B2/B13 remote-dispatch path. Host/local setup appears only
after `activate-requester-host-engines` lands its attested account-to-host
capability. If neither is live, the hold remains truthful without a dead
instruction and cutover stays blocked.

On success the chatbot relays the universe's reply verbatim. The same opaque
provider request capability may cross reply generation and model-backed
learning extraction according to the provider owner; the universe layer does
not inspect or widen it. Result evidence uses
`fulfillment_class=requester_owned|accepted_market`; credential
`authority_class` remains separately owned by credential/provider receipts.

### D5 - Lifecycle residuals are narrow

The remaining lifecycle work is:

1. keep public HTTP creation absent;
2. require every public birth path to self-generate an opaque serial while
   preserving explicit internal migration tooling;
3. keep the root index keyed by immutable id and project the learned name from
   `identity.md`;
4. atomically move descriptive-id roots to generated serial roots and update
   bindings/references with rollback evidence; and
5. remove duplicate `self/`, `soul/`, brain-archive, and empty starter
   artifacts while preserving non-empty historical data.

### D6 - Dependency direction is explicit

- `constrain-set-engine-provider-authority` syncs its provider-hold and request
  carrier requirements before this change archives. This change removes its
  duplicate identity header rather than relying on archive order.
- `provider-attempt-receipts` owns result-local
  `authority_held`/credential evidence; this change only consumes it.
- `activate-requester-host-engines` owns attested Tier-2/Tier-3/plugin local
  execution and its setup path.
- `activate-connector-requester-authority` owns Tier-1 accepted-market setup,
  result, and pre-routing B2/B13 execution with no desktop or web-app
  dependency.
- Paid-market and distributed-execution own agreement, remote grant, execution,
  and settlement. Universe creation does not duplicate them.

## Risks / Trade-offs

- **Provider authority drifts back into the universe layer** -> Tests reject
  caller-built bundles, provider allowlists, raw setup deposits, and parallel
  receipts at the action boundary.
- **A truthful hold becomes a dead onboarding instruction** -> Advertise only
  successor-proven routes; block cutover when no current surface route is
  completable.
- **Reply succeeds while learning widens authority** -> Carry the same opaque
  provider request capability and verify result-local evidence without
  inspecting or minting it.
- **Root migration or cleanup loses data** -> Inventory first, stage and verify
  the serial root, update references atomically, retain non-empty history, and
  keep a rollback manifest until read/write/run/status probes pass.

## Migration Plan

1. Land this spec-truth correction with no runtime changes.
2. Wait for the approved provider-authority target and the applicable
   requester-host or connector successor to publish their interfaces.
3. Integrate only canonical target/request lineage, typed hold mapping, verbatim
   reply relay, and result consumption at the universe action boundary.
4. Run the descriptive-root migration and cleanup through reviewed,
   rollback-safe host operations.
5. Verify success and setup-required paths in rendered Claude.ai and ChatGPT
   connector conversations, then freshness-stamp real-user evidence or retain
   an explicit watch item.

Rollback never restores ambient provider authority or raw setup deposit. If
provider integration fails, birth remains valid and execution stays held.

## Open Questions

- Exact activation timing belongs to the provider-authority and successor
  changes. This lane cannot declare a requester-host or connector-market route
  ready on their behalf.
