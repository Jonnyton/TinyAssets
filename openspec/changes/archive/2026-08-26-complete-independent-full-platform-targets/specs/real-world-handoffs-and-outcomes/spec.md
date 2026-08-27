## ADDED Requirements

### Requirement: Real-world handoffs are declared external-effect outputs
A node version SHALL declare a handoff as a typed external-effect output naming its output field, adapter, adapter action, destination binding, effect class, required credential/capability class, outcome kind, and evidence extraction contract. Invocation SHALL accept a handoff only from the exact immutable node version/run/output that declared it. A handoff SHALL reuse the canonical external-effect adapter and receipt boundary rather than create a second network/credential path.

#### Scenario: Declared output becomes handoff-eligible
- **WHEN** an immutable node run produces the exact declared handoff output
- **THEN** the system can construct a bounded effect request carrying node version, run, output, destination, effect class, and idempotency identity

#### Scenario: Caller substitutes another output or destination
- **WHEN** a caller names an undeclared output or redirects the destination outside the declaration/authority
- **THEN** handoff initiation fails before credential vending or adapter execution

### Requirement: Handoff authority combines destination consent and irreversible-action confirmation
Every handoff SHALL require current authenticated authority for its source artifact/run and exact external destination plus the canonical destination consent grant. A handoff classified as irreversible SHALL additionally require fresh per-invocation confirmation bound to effect summary, destination, source version/hash, and expiry; standing connector consent alone SHALL NOT authorize it. Autonomous execution SHALL pause in a reviewable state when confirmation is required and SHALL NOT manufacture user consent.

#### Scenario: Reversible handoff has destination consent
- **WHEN** the actor owns or controls the source, holds exact destination consent, and the effect is reversible
- **THEN** the effect may proceed through the canonical receipt path

#### Scenario: Irreversible handoff lacks fresh confirmation
- **WHEN** a node reaches an irreversible handoff with standing connector consent but no matching fresh confirmation
- **THEN** it pauses/refuses before adapter execution and exposes the confirmation needed

#### Scenario: Confirmation binds a stale source version
- **WHEN** confirmation names source hash/version N but initiation names a later version
- **THEN** the system rejects the stale confirmation and executes no external effect

### Requirement: Dry runs never create external handoffs or authoritative outcomes
Authoring tests, previews, and explicit dry runs SHALL replace handoff adapter execution with a redacted `would_handoff` record containing destination, effect class, payload schema/summary, evidence expectation, and authority still required. They SHALL NOT reserve a production receipt, create a handoff lifecycle row, create or advance an outcome claim, or contact the destination.

#### Scenario: Dry run reaches an arXiv-like submission
- **WHEN** a dry execution reaches a declared irreversible submission
- **THEN** it returns simulated-effect evidence and makes no provider request, receipt reservation, handoff row, or outcome claim

### Requirement: Exactly-once handoff effects are bound to canonical receipts
Before invoking a real handoff adapter, the system SHALL atomically reserve a receipt using a system-derived idempotency identity over source run/output, adapter action, and destination. Only the reservation owner may finalize or release it. Duplicate concurrent requests SHALL return the existing pending/final evidence or a bounded conflict and SHALL NOT execute a second external effect. An uncertain adapter reply SHALL remain an observable uncertain/pending state and SHALL NOT be retried as a new effect until provider/idempotency reconciliation proves that safe.

#### Scenario: Concurrent same-output submissions race
- **WHEN** two authorized requests initiate the same handoff identity concurrently
- **THEN** one request owns adapter execution and the other returns shared pending/final evidence without a second push

#### Scenario: Adapter times out after sending
- **WHEN** the external call may have reached the destination but no authoritative response is received
- **THEN** the receipt remains uncertain, no duplicate retry is issued under a fresh key, and reconciliation queries provider evidence where supported

#### Scenario: Adapter definitively rejects before effect
- **WHEN** the provider proves no external mutation occurred
- **THEN** the reservation may be released or finalized failed according to receipt policy and no accepted outcome is created

### Requirement: Handoff lifecycle separates submission, acceptance, and later real-world outcome
Each real handoff SHALL retain an append-only lifecycle over at least `reserved`, `submitted`, `accepted`, `verified`, `rejected`, `uncertain`, `orphaned`, and `cancelled` states, with provider evidence and legal transitions. A successful adapter transport SHALL prove only submission unless the provider response contract proves destination acceptance. Destination acceptance MAY create an externally verified handoff outcome, but SHALL NOT by itself claim peer review, publication, citation, sales, production use, regulatory approval, or any later impact. Those later outcomes require their own evidence transitions.

#### Scenario: Provider acknowledges queue receipt only
- **WHEN** the adapter proves the destination queued the payload but not that it accepted/published it
- **THEN** the handoff becomes `submitted` and no later-impact badge is marked verified

#### Scenario: Provider returns a stable accepted record
- **WHEN** the provider contract proves acceptance and supplies a stable external identifier
- **THEN** the handoff becomes `accepted` and a linked outcome may carry externally verified acceptance evidence

#### Scenario: Accepted record is later withdrawn
- **WHEN** authoritative provider evidence shows the external record was removed or retracted
- **THEN** the handoff/outcome advances to `orphaned` or an equivalent downgrade without deleting prior acceptance evidence

### Requirement: Handoffs extend the existing outcome registry with exact provenance
Every handoff-derived or user-attested outcome SHALL be represented by the existing `extensions` `outcome_event` registry, extended to link the originating user/account, immutable node/evaluator version, run, output/artifact hash, handoff/receipt when present, outcome kind, evidence source, evidence level, timestamps, and external identifier/reference when available. The handoff service SHALL NOT create a parallel generic outcome registry or user-attestation API. The system SHALL support multiple originating nodes/runs contributing to one external artifact without double-counting the external artifact itself or erasing attribution. Outcome mutation SHALL be append-only evidence transitions or superseding evidence, not silent replacement.

#### Scenario: One run creates an accepted external artifact
- **WHEN** a handoff reaches accepted with a stable external id
- **THEN** its `outcome_event` links the external evidence to the exact source run/output/version and receipt

#### Scenario: Second node contributes to the same external artifact
- **WHEN** another authorized source links to the same normalized outcome-kind/external-id pair
- **THEN** the external artifact is not counted twice while both source contributions remain attributable

### Requirement: Existing outcome recording becomes the user-attestation entry point
The existing `record_outcome` behavior under the canonical extensions router SHALL accept an authenticated user's authorized real-world attestation with outcome kind, narrative, source linkage, and optional evidence reference. The resulting `outcome_event` SHALL begin as `user_attested` or equivalent and SHALL NOT be relabeled externally verified merely because the evidence URL is syntactically valid or reachable. Later verification, dispute, retraction, or moderation SHALL append evidence transitions while preserving the original attestation. Existing `gate_events` SHALL remain the separate cited-in Goal/Branch attestation lifecycle; linking a gate event to an outcome SHALL NOT automatically copy verification state in either direction.

#### Scenario: User reports a journal acceptance
- **WHEN** an authorized user attests acceptance with a narrative and evidence reference but no trusted verifier has confirmed it
- **THEN** the outcome is stored as user-attested and displayed/ranked distinctly from externally verified evidence

#### Scenario: Verifier later confirms the claim
- **WHEN** an authorized verifier proves the same normalized outcome against the bound external source
- **THEN** a new verification transition links the proof while retaining who made the original attestation

#### Scenario: Linked gate event changes state
- **WHEN** a linked gate event is verified, disputed, or retracted
- **THEN** its specialized lifecycle changes independently
- **AND** the outcome evidence state changes only through an explicit authorized outcome transition

### Requirement: Verification workers use authenticated evidence, bounded polling, and replay-safe webhooks
Provider-specific verification SHALL use explicit adapters that normalize identifiers, authenticate requests where required, validate response provenance, and map evidence to legal lifecycle transitions. Polling SHALL use age/provider-aware schedules, per-provider budgets, bounded batches, backoff, and jitter. Webhooks SHALL verify provider signature, timestamp/replay window, destination binding, and event identity before mutation; polling SHALL reconcile missed webhooks without producing duplicate transitions. A 404 or not-yet-indexed response SHALL follow provider-specific grace policy rather than immediately prove orphaning.

#### Scenario: Signed webhook and poll overlap
- **WHEN** a valid webhook and scheduled poll observe the same provider transition concurrently
- **THEN** one idempotent evidence transition becomes authoritative and both observations remain auditable

#### Scenario: Webhook signature or replay window is invalid
- **WHEN** an event fails signature, destination, timestamp, or replay validation
- **THEN** it is rejected without changing handoff/outcome state and a bounded security event is recorded

#### Scenario: Provider returns 429
- **WHEN** a verification adapter receives a rate-limit response
- **THEN** its provider budget backs off with bounded jitter and the item remains retryable without a tight loop

### Requirement: Handoff and outcome disputes use the moderation owner
Users SHALL be able to flag a public handoff/outcome claim through the canonical moderation capability. A dispute SHALL preserve the external-effect receipt and original evidence, MAY suppress the claim from public ranking while under review, and SHALL NOT revoke a valid external artifact or rerun the handoff. Moderation resolution MAY restore, annotate, downgrade, or remove public presentation according to policy while retaining authorized audit history.

#### Scenario: Outcome claim is disputed
- **WHEN** an eligible user flags a public user-attested outcome and it crosses the review threshold
- **THEN** public presentation becomes under-review without deleting the receipt, source provenance, or external artifact

#### Scenario: Review finds attribution false but external artifact real
- **WHEN** moderation determines that the claiming source did not contribute to a real external artifact
- **THEN** that source attribution is downgraded/removed while the normalized external artifact and other valid attributions remain intact

### Requirement: Outcome consumers preserve evidence level and avoid fixed engagement optimization
Any discovery, selection, impact, or host dashboard that consumes real-world outcomes SHALL receive structured counts/references separated by evidence state and outcome kind. It SHALL NOT flatten user-attested, submitted, accepted, verified, disputed, rejected, or orphaned evidence into one success count. Platform presentation SHALL favor completion/evidence utility without making DAU, session time, message count, or a fixed platform formula the authoritative meaning of impact.

#### Scenario: Two sources have different evidence strength
- **WHEN** one source has a user attestation and another has externally verified acceptance for the same outcome kind
- **THEN** consumers receive distinct evidence levels and cannot present both as equally verified

#### Scenario: Outcome is disputed or orphaned
- **WHEN** a previously positive outcome enters disputed or orphaned state
- **THEN** public aggregate/presentation updates without erasing the historical evidence transition

### Requirement: Handoff completion includes authority, race, provider, and rendered-surface proof
The capability SHALL NOT be considered implemented until automated proof covers consent/confirmation, receipt reservation, duplicate concurrent submission, uncertain replies, source-version races, webhook replay, webhook/poll overlap, provider 404/429/5xx behavior, normalized-id deduplication, multi-source attribution, moderation, and evidence downgrade. The §14 proof SHALL run the projected provider mix at 10× launch volume with bounded queue age, request rate, retries, and storage contention and SHALL show exactly one authoritative external effect per idempotency identity. Final acceptance SHALL include a rendered chatbot handoff conversation through the live connector plus post-fix clean-use evidence.

#### Scenario: Ten-times-load provider mix
- **WHEN** the §14 harness drives concurrent handoffs, polling, webhooks, retries, and duplicates at the declared 10× mix
- **THEN** every provider stays within configured budget, queue age and error bounds are reported, and no duplicate external effect or lost evidence transition occurs

#### Scenario: Live chatbot performs an irreversible handoff
- **WHEN** a real user-like chatbot conversation reviews the exact effect, confirms it, receives an external receipt, and later reads linked outcome state
- **THEN** the transcript/trace proves canonical-handle routing, faithful confirmation, source/receipt linkage, and evidence-level narration
