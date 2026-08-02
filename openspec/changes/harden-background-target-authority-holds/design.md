## Context

`BackgroundBranchAttempt` already has the closed `TARGET_AUTHORITY_HELD` lifecycle and closed hold-reason enum, while `BackgroundBranchAttemptClaimService` already owns exact-fence claim, renew, release, and conclusive reclaim. No service method currently enters or exits the held lifecycle, so callers would otherwise have to construct replacement attempts or translate private resolver failures themselves. The umbrella change specifies queue and source integration later; this successor owns only the dark authority-record seam.

## Goals / Non-Goals

**Goals:**

- Persist one same-attempt, non-runnable hold that monotonically fences any prior claimant.
- Return a stable projection containing only opaque identity, generations, a closed reason, and the permitted recovery class.
- Permit automatic exit only from trusted dead/invalidated-predecessor plus conclusive-boundary evidence.
- Permit reauthorization exit only after the canonical store already contains an authenticated, active, exactly newer binding and fresh resolver evidence proves that every attempt-bound target, source, executor, expiry, and attenuation fact remains authorized.
- Make every mutation an exact attempt CAS inside the authority-store transaction.

**Non-Goals:**

- No `BranchTask`, queue-cap, source-store, dispatcher, runtime, provider, credential, graph, public API, or connector behavior.
- No binding creation/rotation authorization; the existing binding transition owner remains responsible for that decision.
- No prepared cross-store pair, live activation, compatibility parser, or migration.

## Decisions

### 1. Extend the existing claim-lifecycle owner

Hold, recovery, and reauthorization are attempt claim-lifecycle transitions, so the existing `BackgroundBranchAttemptClaimService` remains the sole writer. A new service or queue-owned writer would create a second authority seam. The service constructs every replacement record; callers provide only an exact attempt fence, transition time, and where applicable a requested worker inside the already-pinned executor domain.

### 2. Resolver evidence is re-read, then cross-checked against the transaction

The trusted resolver classifies entry with one closed hold reason and supplies predecessor/boundary evidence for recovery. The service re-reads the binding inside the authority transaction and refuses any resolver/store disagreement. Missing bindings may enter a `binding_missing` hold; they can never exit until a canonical binding exists and passes the reauthorization rules.

Alternative considered: accept a caller-provided exception code or proof. Rejected because strings and caller-built proof objects would become authority by convention and could drift from the canonical resolver/store snapshot.

### 3. Reauthorization consumes an already-authenticated binding generation

The existing binding transition service authenticates and persists rotations. Held-attempt reauthorization accepts no bearer or actor string; it resolves the current binding in the same transaction and requires the same binding ID and immutable authorizer/universe/source/target identity, `ACTIVE` status, an exact generation advance, non-regressing revocation generation, and matching fresh resolver evidence. That evidence must re-resolve the exact attempt branch version/content digest, source revision/digest/generation, operation, executor domain and constraints, current expiry, and attenuation envelope. Existing remaining depth/count/cost are preserved only when each fits inside the new binding and delegation ceilings; any changed or unverifiable pin leaves the attempt held. Only then may the service update the held attempt's binding fence and claim/lease generations. A stale attempt fence loses the CAS and cannot follow a newer binding.

Alternative considered: rotate the binding and update the attempt in this service. Rejected because it would duplicate binding authorization and prematurely absorb the prepared-pair work reserved for umbrella task 2.7.

### 4. Projections are deliberately non-secret and non-authorizing

The projection exposes only opaque attempt ID, typed lifecycle/reason, binding/claim/lease generations, and one closed exit class (`recovery`, `reauthorization`, or `reconciliation`). It excludes principal, universe, branch/source identifiers, content/binding digests, executor identities, resolver diagnostics, credentials, and timestamps. Possessing a projection cannot satisfy any transition method.

### 5. The capability remains dark

No queue or runtime imports the new methods. This lets the record/service invariant land and receive security/concurrency review before later tasks connect queue/source holds and cap accounting.

## Risks / Trade-offs

- **[Risk] A resolver misclassifies a private failure.** → Use a closed reason enum, validate action-specific evidence, and cross-check every available binding fact against the transaction.
- **[Risk] Binding rotation races held-attempt exit.** → Require exact current attempt and binding generations under one authority-store transaction; stale CAS returns typed failure and performs no partial write.
- **[Risk] A hold becomes a silent retry loop.** → Held is non-runnable and projections name only one allowed exit class; no method appends replacement work.
- **[Risk] The dark seam is mistaken for queue readiness.** → Tests assert no queue/runtime import and the spec explicitly excludes activation.

## Migration Plan

Land the dark model/service and packaged mirror with focused tests. Rollback is a code revert because no public path or live queue writes the new transitions. On verified landing, record this as partial foundation under umbrella task 2.6 without checking it; queue/source integration, task 5.3, and activation gates remain open.

## Open Questions

None for this slice. Queue/source projection placement and prepared cross-store reconciliation remain owned by the umbrella tasks.
