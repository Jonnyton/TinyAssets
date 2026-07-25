## 0. Prerequisites and premise verification

- [ ] 0.1 Before any implementation write, re-verify against `origin/main` that `openspec/specs/external-effect-receipts/spec.md` still describes caller-supplied hint semantics and no batch guarantee; if a later change already landed system-derived identity, reclassify these tasks instead of building over them.
- [ ] 0.2 Confirm `paid-market-track-e-wave-2-transport` has landed its single authenticated transaction transport before implementing any value-moving boundary effect; until then, implement only non-value-moving boundary behavior.
- [ ] 0.3 Confirm the umbrella `build-forward-platform-capabilities` decisions D1–D8 still hold for this slice and record any divergence as a design change here, not as silent drift.
- [ ] 0.4 Take no requirement from the host-gated open-production-commons reframe (`.agents/handoffs/2026-07-19-distributed-execution-resume/RESUME-SPEC.md` §9). It is unapproved context, blocked on a host Q6 confirmation and PLAN.md foldback approval, and per umbrella D9 it binds nothing in either direction: "keep the reframe reachable" is not a design constraint on this slice and not a review gate against it. Build to D1–D8 and this change's own requirements. If the reframe is ever approved, it arrives as its own change.

## 1. Connection resource ledger and grants

- [x] 1.1 Add connection-class and grant persistence with owning user, scope, provider, destination, per-universe binding, and revocation state, plus the next numbered storage migration.
- [x] 1.2 Resolve a scoped proxy for a node's declared connection class from the ledger, failing closed on absent, revoked, or ambiguous grants with no ambient or maintainer-credential fallback.
- [x] 1.3 Keep raw credential material out of graph state, artifacts, run snapshots, and error text; add an adversarial test that an adapter cannot recover a secret from state, environment, request metadata, or proxy errors.
- [x] 1.4 Make connector definitions and their MCP client configuration commons artifacts that carry attribution through remix.

## 2. Action caps and held effects

- [x] 2.1 Add a machine-readable unprompted-action cap evaluated independently of tool authorization and of any spend cap.
- [x] 2.2 Execute below-cap authorized actions automatically; hold above-cap actions with a receipt naming the cap, consuming no funds or quota, until an authorized confirmation is recorded.
- [x] 2.3 Surface held effects with actionable remediation rather than silence, and test that the same action at or below the cap executes without a hold.

## 3. Replay safety, reconciliation, and batches

- [x] 3.1 Derive the effect key from durable goal, schedule-period, and item-fingerprint identity; journal intent before firing and consult the journal on every replay.
- [x] 3.2 Reconcile ambiguous outcomes with the destination where the destination supports it, and persist a terminal result in every case.
- [x] 3.3 Hold a batch as a whole when any item fails admission, effect, or reconciliation, exposing every item and reason; prohibit partial-silent results. Do not claim rollback of already-terminal effects — test that the reported outcome distinguishes "nothing further fired" from "earlier effects reversed".
- [x] 3.5 Replace time-only pending-row reclamation with destination reconciliation, holding for remediation where the destination exposes no reconciliation interface.
- [x] 3.4 Migrate existing effectors from caller-hint identity to system-derived identity behind a flag, with dual-write parity proof before the flag flips.

## 4. Inboxes and typed artifacts

- [ ] 4.1 Give each goal and universe a durable addressable webhook URL and email address, with source approval, receipt, typing, and eligibility cutoff owned here and scheduled execution left to `demand-side`.
- [ ] 4.2 Admit an eligible item into exactly one scheduled batch and record the inbox receipt and cutoff used.
- [ ] 4.3 Make node inputs and outputs reference content-addressed artifacts carrying MIME type and optional validated schema, with decoders and encoders as ordinary commons capability-class nodes.
- [ ] 4.4 Fail graph compilation on an incompatible edge or unknown required type before run start or token spend, naming producer, consumer, and incompatible types; never silently map an unknown declared type to `Any`. Ship report-only first, then enforce.

## 5. Non-MCP long tail

- [ ] 5.1 Discover native MCP servers at connect time from `{server, auth, scopes}` grants.
- [ ] 5.2 Generate scoped, typed, cap-aware, credential-blind MCP-shaped actions mechanically from an OpenAPI description, run them as workflows, and require review before a universe can bind them.
- [ ] 5.3 Prove a new destination can be connected without a platform-side code change or support ticket.

## 6. Verification and foldback

- [ ] 6.1 Run focused unit/integration/security tests for grants, caps, credential blindness, replay identity, reconciliation, batch hold, inbox admission, and compile-time typing.
- [ ] 6.2 Run the §14 concurrency/load matrix: concurrent replays of one effect key, crash between effect and finalization, batch failure under contention, duplicate inbox delivery, and grant revocation racing an in-flight effect.
- [ ] 6.3 Sync the `external-effect-receipts` and `external-effect-adapters` modified deltas in the same operation as `boundary-layer`, never `boundary-layer` alone; then confirm no as-built limitation requirement about caller-supplied hints or time-only reclamation survives in canonical specs.
- [ ] 6.4 For any public surface exposed here, run the live connector canary with `--assert-handles`, complete a rendered chatbot conversation, and record freshness-stamped post-fix clean-use evidence before claiming acceptance.
- [ ] 6.5 Obtain independent opposite-family review of the implementation diff, then sync and archive.
