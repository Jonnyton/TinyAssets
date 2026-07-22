## Context

The canonical `identity-auth-and-access-control` and
`universe-lifecycle-and-soul` specs now own the behavior that the original
`universe-creation` proposal tried to define as a new capability. Verified
runtime behavior already includes atomic serial creation, a seeded linked soul
bundle, founder home binding, and first-contact birth/resolution on opening
`converse`. `get_status` remains a pure read.

Create scope is checked before reservation. An authenticated founder without
create scope currently gets a structured home-create/load error with
`auth_scope_required: true`; no phantom binding is written and this is not an
awaiting card. Execution-resource authority is a separate post-resolution gate.

The unresolved boundary begins after birth. The current first-contact path can
reach provider routing without first proving that all resources needed by the
workload belong to the requester or came from a market offer the requester
accepted. That gap could consume a project maintainer's or platform operator's
credentials, quota, auth home, hardware, or account. Provider-backed speech and
learning extraction therefore remain unbuilt for this contract even though
birth and routing are built.

The old active change also retained requirements already canonicalized or now
owned elsewhere: generic auth/ACL rules, visibility, Branch governance, mobile
clients, the soul bundle shape, and reset semantics. Keeping those here would
create overlapping spec truth.

## Goals / Non-Goals

**Goals:**

- Separate zero-compute universe birth from provider-backed execution.
- Define one complete, fail-closed authority bundle for first-contact execution.
- Ensure provider selection and fallback cannot escape that bundle.
- Apply the boundary to both reply generation and learning extraction.
- Return an actionable structured hold when authority is missing or partial.
- Leave an auditable receipt of which authorized resource class and provider
  were used.
- Retain only the unfinished lifecycle work: public HTTP create retirement,
  public self-serialization, learned-name index projection, existing-root serial
  migration, and existing-root cleanup.

**Non-Goals:**

- Re-specifying already-canonical birth, baseline soul-bundle, soul-edit, reset,
  ACL, visibility, Branch, mobile, or personification behavior.
- Supplying platform compute, model quota, credentials, accounts, or hardware to
  a requester.
- Defining market pricing, matching, settlement, or provider onboarding. This
  change consumes an already accepted compute/model grant.
- Implementing runtime or security-sensitive provider changes in this spec-only
  reconciliation.

## Decisions

### D1 - Modify the owning capabilities; do not create a third capability

First-contact authority is an identity/access-control concern. Public birth and
root migration are lifecycle concerns. Their delta specs therefore live under
the existing capability names. The obsolete
`specs/universe-creation/spec.md` is removed rather than synced.

Alternative considered: keep a broad `universe-creation` capability. Rejected
because it duplicates canonical requirements and obscures which module owns a
security decision.

### D2 - Birth and execution are separate state transitions

An opening authenticated `converse` may reserve, materialize, and bind exactly
one home universe before compute authority exists. That step writes local
universe state but does not authorize any provider invocation. Only the next
execution transition needs a complete authority bundle.

This preserves the built first-contact experience while ensuring missing
compute never turns into a platform-paid call. The result can truthfully include
the new `universe_id` even when execution is held.

### D3 - Execution requires a complete authorized bundle

The authority resolver constructs a request-scoped immutable bundle:

```
compute = requester-owned compute OR requester-accepted market compute
model   = requester-owned model access OR requester-accepted market model grant
complete = compute AND (model when the workload requires separate model access)
```

A provider credential can satisfy both compute and model access when that is
the provider's actual execution contract. The credential must still be owned by
the requester or conveyed by an accepted market grant. A maintainer/founder/
platform-operator credential is not converted into requester authority merely
because it is visible in the process environment.

Alternative considered: treat any configured provider as eligible. Rejected
because configuration visibility proves reachability, not payment or delegation
authority.

### D4 - Selection and fallback are constrained by the bundle

Routing receives only eligible providers derived from the immutable authority
bundle. Retries and fallbacks operate on that set; they do not rescan ambient
environment variables, CLI auth homes, cloud metadata, platform accounts, or
host hardware. Emptying the eligible set produces a hold, not a final attempt
with a maintainer resource.

The isolation boundary must default-deny inherited credential sources. The
concrete runtime design remains gated on the security review and must cover
provider-specific environment variables, cloud credential chains, home/profile
directories, and local subscription auth.

R2-1a owns the generic CLI-subprocess primitive that strips ambient API-key and
subscription-auth environment variables for any explicit universe, then
overlays only that universe's vault values and propagates vault errors. This is
a prerequisite, not request authority. This change's reviewed isolation design
must consume that primitive and extend it to request-bundle overlays, cloud
credential chains, profiles/homes, hardware, and non-subprocess providers.

### D5 - Reply generation and learning extraction share one boundary

The universe intelligence may generate the first-person reply only after the
authority check succeeds. The chatbot forwards the founder's turn and
relays/renders that reply verbatim. Any subsequent model-backed learning
extraction uses the same request-scoped authority bundle; it cannot fall back to
a broader ambient provider set. Reply generation and extraction may select
different providers, provided each selected provider is admitted by that same
authority boundary for its phase.

If the approved bundle cannot cover both phases, each uncovered phase is held.
Birth remains valid, but no uncovered provider invocation occurs.

### D6 - Missing authority returns a structured hold

Missing or partial authority returns a machine-readable envelope with:

- `status: held`
- `reason: setup_required`
- the materialized `universe_id` when birth completed
- `missing_authority`, identifying `compute`, `model_access`, or both
- requester-facing setup paths for BYOC and accepted-market fulfillment

The result is not classified as generic `provider_exhausted`, because no
authorized provider pool existed to exhaust. No synthetic universe reply is
fabricated.

### D7 - Receipts identify the authority actually used

Every provider invocation records the authority class (`requester_owned` or
`accepted_market`) and provider identity/grant reference without recording a
secret. Reply generation and learning extraction produce separate phase entries
linked to the same request authority bundle. This makes enforcement testable and
supports billing/audit without implying that TinyAssets supplied compute.

### D8 - Lifecycle residuals are narrow

The remaining lifecycle implementation has five parts:

1. reject/remove public `POST /v1/universes` creation;
2. ensure every public birth path self-generates its opaque serial and accepts
   no caller-chosen `universe_id` (internal migration/dev tooling is separate);
3. keep the root index keyed by immutable id and project the learned name from
   `identity.md`;
4. atomically move existing descriptive-id roots to generated serial roots and
   update live references/bindings; and
5. remove duplicate `self/`, `soul/`, and brain-archive directories plus empty
   starter `notes.json`/`activity.log`, while preserving non-empty historical
   runtime data until it has a typed destination.

No other requirement from the old monolithic change remains in this lane.

### D9 - Existing provider lanes are dependencies, not duplicate ownership

The authority implementation consumes two separately tracked provider primitives:

- **R2-1a** owns the engine/router rule that an assigned engine constrains
  `allowed_providers`, plus the generic explicit-universe subprocess ambient-
  auth strip. This change intersects the persistent ceiling with the request
  authority bundle's eligible set and extends credential isolation across the
  remaining provider-specific surfaces; it does not create a second provider-
  selection mechanism or treat the ceiling as sufficient authority.
- **R2-1b** owns the race-safe provider result/receipt path for both writer calls. This change extends
  that same result object with phase and authority class (and accepted-grant linkage where applicable);
  it does not use a process-global `_last_provider` or create a parallel receipt.

This change owns requester BYOC resolution and accepted-market compute/model grant transport in tasks
4.1 and 4.2; the bundle cannot be complete until those tasks land. All authority contract tests and
runtime work remain blocked until the scheduled opposite-provider security review returns APPROVE,
or every required ADAPT finding is incorporated and re-reviewed to acceptance.

## Risks / Trade-offs

- **Ambient credentials can bypass a superficial allowlist** -> Use an
  allowlisted, default-deny child environment and isolated home/profile/cloud
  config roots, then overlay only the approved bundle. Gate the concrete list on
  opposite-provider security review and mutation tests.
- **A market offer can be accepted but incomplete** -> Represent compute and
  model grants separately and require the full workload-specific bundle before
  invocation.
- **Reply succeeds but extraction silently spends another account** -> Pass one
  immutable authority bundle through both phases and assert phase receipts.
- **A held response is mistaken for provider failure** -> Use `held` plus
  `setup_required`, not `provider_exhausted`, and enumerate the missing elements.
- **Existing-root migration can orphan bindings or lose data** -> Inventory all
  references, stage and verify the serial root, update references atomically,
  retain non-empty historical data, and keep a rollback manifest until proof is
  complete.
- **Public create removal can strand a client** -> Inventory live callers and
  provide the canonical first-contact/chatbot route before removing HTTP.

## Migration Plan

1. Land the spec-truth correction without runtime changes.
2. Obtain opposite-provider APPROVE of the authority isolation boundary, or incorporate every
   required ADAPT finding and have it re-reviewed to acceptance; tests and runtime implementation
   remain blocked until that gate is satisfied.
3. Land and absorb R2-1a's allowed-provider boundary and R2-1b's race-safe provider receipt.
4. Implement this change's requester BYOC and accepted-market compute/model authority transport.
5. Implement a default-deny requester/market authority resolver and red tests
   proving ambient maintainer resources are ineligible.
6. Thread the immutable bundle through provider selection, fallback, reply
   generation, learning extraction, and receipts.
7. Ship the structured held/setup response and verify it through the rendered
   chatbot surface before enabling provider-backed first contact broadly.
8. Inventory public HTTP create callers, remove/reject that route, and prove
   public birth self-serializes.
9. Run existing-root migration and cleanup with backup/rollback manifests,
   reference-integrity checks, and post-migration read/write/status probes.

Rollback never re-enables ambient maintainer authority. If execution causes
unexpected failures, disable provider-backed first contact and retain the born,
bound universe plus held/setup response.

## Open Questions

- The authority invariant is settled. Provider-specific isolation details and
  accepted-market grant transport remain implementation dependencies subject to
  the scheduled opposite-provider security review.
