## Context

TinyAssets currently reaches outward through effector packets dispatched after a run completes, gated by per-universe destination consent and deduplicated by a caller-supplied idempotency hint. That path is real and landed, and `openspec/specs/external-effect-receipts/spec.md` documents its limits honestly: an empty hint opts out of deduplication entirely, a pending row can be reclaimed after 600 seconds so a crash between the external effect and finalization can still duplicate, and there is no batch guarantee at all.

The target the full-platform architecture describes is different in kind, not degree: a connection is a revocable resource a user grants to a universe, an adapter never sees a secret, an action above a cap holds instead of firing, an item that arrives in a goal's inbox joins exactly one scheduled batch, and a batch either holds as a whole or reports every failure. This change owns that gap. It does not own money, price, or scheduling.

## Goals / Non-Goals

**Goals:**

- Give outbound connectivity one authority model: a resource ledger of user-owned, per-universe, revocable grants.
- Make credential blindness structural rather than conventional — adapter code that tries to read a secret gets nothing and leaves an audit record.
- Replace caller-supplied dedup identity with system-derived identity so exactly-once is not opt-in.
- Make artifact incompatibility a compile-time failure, before a run starts or tokens are spent.
- Keep every connector definition and generated adapter a remixable commons artifact with attribution.

**Non-Goals:**

- Implementing any of it inside this change's proposal stage. Requirements here are targets; nothing is claimed as shipped.
- Owning quote, price, ranking, or forward semantics — those are `paid-market-live-price-discovery`.
- Owning the accounting transaction transport, migrations, or ledger boundary — those are `paid-market-track-e-wave-2-transport`.
- Owning the timezone-aware standing-goal schedule that consumes inbox items — that is `demand-side` in the umbrella.
- Changing the canonical public MCP handle set. Boundary behavior rides the existing routers; a new advertised handle requires its own connector-surface change and rendered-chatbot acceptance.

## Decisions

### B1 — This change is the sole active owner of the `boundary-layer` delta

Umbrella task 1.2 released `openspec/changes/build-forward-platform-capabilities/specs/boundary-layer/` into this change, mirroring how task 1.1 released the `paid-market-economy` delta to `paid-market-track-e-wave-2-transport` and task 2.1 released the price-index delta to `paid-market-live-price-discovery`. The archived `reclassify-forward-vision-specs` change required every removed canonical requirement to have exactly one explicit active future owner; duplicating the delta across the umbrella and this change would break that property. The umbrella retains only the cross-slice invariants.

### B2 — Credentials stay daemon-side; adapters receive a scoped proxy

Secret resolution, network execution, cap enforcement, and receipt writing live in a trusted daemon-side proxy. Adapter code receives a scoped domain, a verb, and a redacted request/response contract. This restates umbrella decision D4 and inherits custody from `credential-vault`; this change adds no second secret store and no new custody model. A universe never owns the credential, and raw credential material never enters graph state or an artifact.

### B3 — Idempotency identity is system-derived, and superseding the as-built receipt limitation is a landing obligation

The effect key SHALL be derived by the system from durable goal, schedule-period, and item-fingerprint identity rather than supplied by the caller. This directly contradicts the shipped requirement "Receipt guarantees are per effect and caller-supplied, not batch atomicity" in `openspec/specs/external-effect-receipts/spec.md`, which is currently a true statement about `main` and names this change as the future owner.

The contradiction is deliberate and time-ordered, and it is carried as RENAMED + MODIFIED deltas against `external-effect-receipts` and against the two `external-effect-adapters` requirements that currently let an omitted hint proceed unreceipted. A delta in an active change describes post-change behavior; it does not alter canonical truth until sync. So while this change is unimplemented the as-built requirements remain true and remain canonical, and the deltas are the mechanism that makes the supersession enforceable rather than a note someone must remember.

Two consequences follow. First, `boundary-layer` SHALL NOT sync without those modified deltas — a synced boundary beside an unmodified as-built limitation is exactly the drift `reclassify-forward-vision-specs` was created to remove (task 6.3). Second, the modified text preserves a distinction the target must not overstate: whole-batch hold is not rollback. An already-terminal external effect may be irreversible at its destination, so the guarantee is explicit reporting and no further firing, not reversal of completed work.

An earlier draft of this design postponed the deltas on the theory that writing them now would assert something untrue about `main`. That inverted OpenSpec's delta semantics, and the cross-family review on 2026-07-24 corrected it.

### B4 — A batch holds as a whole; partial-silent success is prohibited

If any item in a batch cannot be admitted, effected, or reconciled, the batch holds or fails with every item and reason visible. Stale-timeout reclamation alone is insufficient for value-moving effects: ambiguous outcomes must be reconciled with the destination when the destination supports it, and a terminal result must be persisted either way. Remediation must be actionable — naming the cap, the item, and the reason — because a silent hold is indistinguishable from a hang to the user.

### B5 — Connector definitions are commons primitives, not platform integrations

Native MCP servers are discovered at connect time from `{server, auth, scopes}`. The non-MCP long tail is generated mechanically from OpenAPI into MCP-shaped scoped actions and reviewed as ordinary commons artifacts that can be remixed with attribution. This restates the released delta's own requirement that connecting to an API is a universe action rather than a platform integration ticket: the platform ships the generation, scoping, typing, cap-awareness, and credential-blindness machinery, and users compose the specific integrations.

### B6 — The boundary never becomes a second money path

Value-moving boundary effects settle through the single authenticated transaction transport owned by `paid-market-track-e-wave-2-transport`, and any priced comparison reads through `paid-market-live-price-discovery`. The boundary layer contributes authority, caps, journaling, reconciliation, and receipts — never its own accounting. This applies the umbrella's approved decision D3 ("`paid-market-economy` owns one money transport before market expansion") at the outbound edge; real-fund wallet and chain effects stay with the separately reviewed §18.6 successor.

Scope note: this decision is only about not forking a second accounting path. It makes no claim about platform custody — `credential-vault` is the canonical daemon-side credential custody owner and this change consumes it, and escrow custody belongs to `paid-market-economy`. The stronger "platform never holds custody" framing belongs to the host-gated open-production-commons reframe recorded in `.agents/handoffs/2026-07-19-distributed-execution-resume/RESUME-SPEC.md` §9, which is explicitly not authorized for implementation and is therefore not a requirement here.

### B7 — Grants are the only source of outbound authority

An effect fires only under a current, unrevoked, per-universe grant bound to the authenticated owning user. Absent, revoked, or ambiguous grants fail closed. The boundary layer does not inherit host or maintainer authority, and it does not fall back to ambient credentials when a grant is missing — a retired or unresolved connection is an error, not an escalation.

### B8 — Typed GitHub reconciliation uses a digest marker and commit association

The repository-to-spec automation supplies the outbound owner an immutable
server-authored identity containing `universe_id`, `automation_id`, `claim_id`,
`repository`, `intended_head_sha`, and the fixed
`github_pull_request` effect kind. The outbound owner canonicalizes and hashes
that identity, places only the digest in a GitHub pull-request body marker, and
looks up pull requests associated with the intended commit through the existing
credential-blind scoped connection proxy. Opaque internal identifiers never
appear in the public marker, and the reconciler never receives credential
material.

Reconciliation is read-only. Repository owner/name components must be
dot-segment-free. Exactly one pull request whose repository, head SHA, and
single well-formed reserved body marker all match is terminal success. A body
with a duplicate, conflicting, or malformed reserved marker is ambiguous even
when it also contains the expected marker. A successful authoritative
commit-association query with no exact match is conclusive absence. Multiple
exact matches, malformed responses, transport failures, and any partial match
are indeterminate and MUST NOT authorize a retry. This typed adapter remains
dark until the automation owner passes the server-authored identity directly;
legacy Branch packets cannot opt into it by adding fields.

## Risks / Trade-offs

- [Risk] System-derived idempotency identity breaks existing callers that rely on hint-based dedup. → The implementation lane must migrate existing effectors and keep the caller-hint path working until every effector is converted, then modify the canonical requirement in one lane.
- [Risk] Destination-native reconciliation is not available for every destination. → Reconciliation is required "when possible" and a terminal persisted result is required always; destinations without a reconciliation API must declare that limitation in their adapter contract rather than silently degrading to timeout semantics.
- [Risk] Generated OpenAPI adapters expand the attack surface faster than review can cover. → Generated surfaces are inert until scoped, typed, cap-aware, credential-blind, and reviewed; grant binding is a separate user action.
- [Risk] Compile-time artifact typing rejects graphs that used to run. → The rejection is the point, but the rollout needs a reporting mode that names producer, consumer, and incompatible types before enforcement flips on.
- [Risk] Inbox addresses are unauthenticated ingress. → Ingress authority, source approval, and eligibility cutoffs are boundary-owned requirements; an unapproved source produces a receipt and no scheduled work.

## Migration Plan

1. Land the connection/grant resource ledger and read paths with no effector behavior change.
2. Convert effectors to system-derived idempotency identity behind a flag, dual-writing the caller-hint row until parity is proven.
3. Add journal-before-fire, destination reconciliation, and batch hold semantics; prove replay under interruption.
4. Add caps, held receipts, and the remediation surface.
5. Add inbox ingress and typing; hand scheduled execution to `demand-side`.
6. Add compile-time artifact typing in report-only mode, then enforce.
7. Sync this change and modify the superseded `external-effect-receipts` requirement in the same lane.

Rollback is per step: keep the flag dark and revert the step. No step may leave a partially converted idempotency scheme live, because two dedup identities for one effect is worse than either alone.

## Open Questions

- What is the exact fingerprint input for item identity, and who owns its stability across schema changes?
- Which destinations expose a reconciliation API today, and what is the declared behavior for those that do not?
- Where do inbox webhook and email addresses terminate in the deployed topology, and what rate/abuse controls apply before typing?
- Does the action cap live per grant, per universe, per goal, or per destination class, and which wins on conflict?
- What review process admits a generated OpenAPI adapter into the commons?
