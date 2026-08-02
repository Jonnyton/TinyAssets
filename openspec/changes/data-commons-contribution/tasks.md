> **Target-only change — nothing here is built.** Every requirement in
> `specs/` describes intended behavior, not behavior on `main`. Authored
> 2026-07-25 as the successor for `build-forward-platform-capabilities` tasks
> 3.1 (non-monetary half) and 3.2, per that umbrella's decision D1 (a slice
> must become a narrower change before implementation).
>
> **Archive guard — do NOT archive this change, and do NOT run
> `openspec archive data-commons-contribution --yes`.** `openspec archive`
> syncs the change's delta specs into `openspec/specs/` as a side effect, and
> `openspec/specs/` is **as-built truth**. Archiving or syncing while these
> tasks are unchecked would write unbuilt behavior into canonical truth — the
> exact defect the archived `reclassify-forward-vision-specs` change removed by
> deleting eight forward-only capability directories. Sync and archive are
> §8 below and are gated on every preceding task being genuinely complete.
>
> **The umbrella's 3.1 and 3.2 stay unchecked until this change LANDS.**
> Authoring a successor does not complete a successor-outcome tracker; the
> umbrella's own task classification says so. 3.1 additionally stays unchecked
> after landing, because its monetary half (pricing modes, contributor
> settlement) remains with the umbrella.

## 0. Premise verification and prerequisites

- [x] 0.1 Before any implementation write, re-verify against `origin/main` that `openspec/specs/wiki-commons/spec.md` still specifies the seed taxonomy as **not a closed whitelist** (custom categories accepted, sanitized, and queryable), the shared root commons as ungated by the per-universe ownership ACL, and the default discovery scope as classifying non-coordination categories as `discovery`. Every one of those is load-bearing for §1. If any has changed, carry the contradiction as a MODIFIED delta before building — do not assert it only in the `data-commons` delta.
  > Verified 2026-07-29 against `origin/main` `6b4c45c`: the canonical `wiki-commons` requirements still state all three premises, including custom/category-less pages defaulting to discovery. No delta reconciliation is needed.
- [x] 0.2 Re-verify that `openspec/specs/evaluation-outcomes-and-attribution/spec.md` still specifies the append-only contribution ledger (idempotent on caller-supplied `event_id`) and attribution edges (credit share clamped to `[0,1]`, cycle rejection via bounded ancestor walk, generation depth from parents). §6 records onto those exact semantics; if they moved, re-anchor §6 rather than reproducing them.
  > Verified 2026-07-29 against `origin/main` `6b4c45c`: the canonical contribution-and-attribution requirement retains the caller-supplied `event_id`, unit-interval clamp, 50-hop ancestor walk, and parent-derived depth semantics. §6 remains correctly anchored.
- [x] 0.2a Re-verify the attribution-edge endpoint constraint that makes the MODIFIED delta necessary: `tinyassets/attribution/schema.py:33-47` constrains `parent_kind`/`child_kind` with `CHECK (… IN ('branch','node'))`, and `tinyassets/api/market.py:898-975` requires branch ids and inserts the kinds as the literal `'branch'` — so a manifest edge is *rejected by the schema*, not merely unwritten. If a later change already widened the set, drop or rewrite the MODIFIED delta rather than restating a constraint that has moved. Also confirm `tinyassets/contribution_events.py:40-52` still carries a generic `source_artifact_id`/`source_artifact_kind` with no closed-set constraint — if that gained a constraint, contribution events need a delta too.
  > Verified 2026-07-29 against `origin/main` `6b4c45c`: the attribution schema still enumerates only `branch` and `node`, the remix writer still requires branch ids and inserts literal `branch` kinds, and contribution events still accept an unconstrained artifact id/kind pair. The existing MODIFIED delta remains necessary and sufficient.
- [x] 0.3 Confirm `build-brain-canonical-store` has not landed the bundle write path and commit protocol under different guarantees than its delta specifies. Until it lands, implement §2's canonical-form claim against its contract only; do **not** build a bundle write path, commit protocol, or redaction ordering here.
  > Verified 2026-07-29 against `origin/main` `6b4c45c`: `build-brain-canonical-store` remains active at 3/14 tasks; its bundle writer and commit protocol are unchecked, and no canonical commons bundle writer or commit protocol exists. The relevant wiki path remains a one-way exporter. PR #1761 relocated rather than implemented that build work.
- [x] 0.4 Re-read PLAN.md Scoping Rules 1, 3, and 4 and the Design Decisions entry for per-domain canonical storage as landed by PR #1761; if the landed wording differs from what `design.md` D2/D4/D5 was authored against, reconcile the design first.
  > Verified 2026-07-29 against `origin/main` `6b4c45c` and merged PR #1761: PLAN still requires irreducibility for new primitives, community-built privacy guidance with platform enforcement boundaries, custody-agnostic commons-first placement, and per-domain canonical stores. `design.md` D2/D4/D5 matches those positions, so no design reconciliation is needed.
- [x] 0.5 Establish the commons write-destination selector's owner before §1 is built, without defining a second commons write path here.
  > Verified 2026-08-01 against `origin/main` `1dd8d7ba` and merged PR #1857 (`72ee903b`): `reconcile-universe-personification-relay` tasks 6.1/6.7 landed the additive `write_page scope=commons|universe` selector, including fail-closed invalid/contradictory-target tests. `proposal.md` and `design.md` now record that owner; this change only consumes the selector.
- [x] 0.6 Confirm the umbrella's decisions D1–D8 still hold for this slice and record any divergence as a design change here, not as silent drift.
  > Verified 2026-08-01 against the current umbrella design and PLAN.md: D1's successor slicing, D2's single pure-oracle ownership, D3's single money boundary, D4's daemon-side credentials, D5's provenance-before-mint gate, D6's demand ordering, D7's hard legal/research gates, and D8's authenticated open eligibility remain consistent with this change. No divergence requires a design amendment.
- [x] 0.7 Take no requirement from the host-gated open-production-commons reframe. Per umbrella D9 it is provenance only and binds nothing in either direction — "keep the reframe reachable" is not a constraint on this slice and not a review gate against it.
  > Revalidated 2026-08-01: D9 remains explicitly non-normative in both directions. This change continues to derive its requirements from PLAN.md and named capability owners, not from the reframe.
- [x] 0.8 Classify each task below as live / landed / inverted against current code before building.
  > Classified 2026-08-01 against `origin/main` `1dd8d7ba`, then corrected 2026-08-02 against fresh main and executable acceptance: the generic frontmatter/custom-category write, explicit commons selector, authenticated auth-scope boundary, default discovery search/changed-since, and exact-seven canary already supplied 1.1, 1.2, 1.4, and 1.5 without a new registry or handle. Task 1.3 had one live defect: a path returned by discovery was re-resolved fuzzily by slug and could open a same-slug page from another category. This bounded slice fixes that exact-path contract with containment guards. Sections 2–5, 6.1, 6.2a–6.6, and 7–8 remain live/unbuilt; section 2 still waits on `build-brain-canonical-store`, 5.4a waits on `outbound-boundary-layer`, and 6.2 waits on the generic N-parent owner. `tinyassets.paid_market.license_terms`, the generic contribution ledger, and the attribution writer retain their existing ownership.
- [x] 0.9 Re-verify whether the sibling `complete-plan-gated-platform-targets` change has landed its generic `node-discovery-and-remix` N-parent artifact-derivation contract (atomic all-parent insertion, aggregate credit at most one, retry idempotency on a derivation identity, and recorded rationale).
  > Verified 2026-08-01 against `origin/main` `1dd8d7ba`: the contract exists only in the active sibling delta (`openspec/changes/complete-plan-gated-platform-targets/specs/node-discovery-and-remix/spec.md`); no landed implementation provides its atomic all-parent write, aggregate-credit enforcement, derivation-identity retry idempotency, or rationale record. §6 therefore remains dependency-gated and SHALL NOT reproduce a weaker dataset-only contract.

## 1. Contribution and discovery on the canonical page handles

- [x] 1.1 Define the contribution entry: a commons entry whose frontmatter declares contribution kind, related Goals, resolved `license_id`, provenance class, and integrity references, as additional keys on an entry whose only structurally required key is `type`. Invent no profile mechanism and no category whitelist.
  > Verified 2026-08-02 by `TestOpenCommonsContribution`: an ordinary `type: contribution` page in the custom `agent-blueprints` category round-trips `contribution_kind`, `related_goals`, `license_id`, `provenance_class`, and `integrity_references` without a profile or category enum change.
- [x] 1.2 Route contribution writes through the canonical `write_page` handle and the commons destination selector owned per 0.5. Add no dataset tool, no contribution action namespace, no platform-owned contribution registry, and no second commons write path.
  > Verified 2026-08-02 through `write_page(scope="commons", ...)`; the implementation changes only canonical page path resolution and its packaged mirror and creates no write action, registry, or storage path.
- [x] 1.3 Make discovery ordinary commons reads — search and changed-since through `read_page` under the existing default discovery scope — with no dataset catalog surface and no second discovery index.
  > RED 2026-08-02: a discovery result path opened an alphabetically earlier same-slug page from another category. GREEN 2026-08-02: exact containment-checked `pages/` or `drafts/` resolution precedes legacy fuzzy slug lookup; search, changed-since, and exact read pass through `read_page` with `scope=discovery` and no new index.
- [x] 1.4 Keep the commons anyone-writable: any authenticated principal contributes subject only to the existing auth-scope gate, with no invitation list, curation seat, or platform-approval step consulted.
  > Verified 2026-08-02 with a non-founder, non-maintainer `ordinary-contributor` identity holding only `tinyassets.wiki.write` and `tinyassets.wiki.read`; the explicit commons write and subsequent reads succeed without another gate.
- [x] 1.5 Assert by test that the advertised handle set is unchanged after implementation — the `--assert-handles` canonical set, with no contribution, dataset, manifest, forge, or promotion handle added.
  > Verified 2026-08-02 by the offline canonical-handle canary, including named rejection probes for `contribution`, `dataset`, `manifest`, `forge`, and `promotion`; the full claimed regression set reports 125 passed.

## 2. Manifest entries: immutable, content-addressed, reference-moving

- [ ] 2.1 Specify and implement the manifest entry fields — `manifest_hash`, size, modality, declared `license_id`, source declarations, curation log, schema, integrity hashes, storage references, and version lineage. Include no pricing term, fee, contributor-share weight, payout term, or settlement field.
- [ ] 2.2 Make manifest entries immutable through the `wiki-commons` MODIFIED contract: changed content mints a new hash and version linked to its predecessor; a freeform write targeting an existing immutable entry is refused on the write path with a mint-a-new-version instruction, leaving its body, frontmatter, and index entry unchanged. Test that an ordinary non-immutable promoted page still overwrites in place.
- [ ] 2.3 Move references, not bytes: downstream training, workflow, catalog, and transactional records bind the manifest hash and a declared storage reference; assert by test that no path requires bytes to transit platform-owned dataset storage.
- [ ] 2.4 Encode the canonical-form split from PLAN.md's per-domain decision: the commons bundle is canonical for the manifest entry, entry/full-text/vector stores are rebuildable derived indexes that lose to the bundle on disagreement, and a catalog/ledger/inbox/market row referencing the same dataset is canonical only for its own domain and is never consulted as manifest truth. Test the disagreement case explicitly.
- [ ] 2.5 Distinguish declared claims from checked results in the entry, so no consumer can read an unchecked declaration as a passed validation. Curation and moderation are non-blocking annotations on an already-admitted entry, never a pre-publication approval step; test that a curation concern does not block the authenticated write.

## 3. Fail-closed manifest admission; license policy remains host-blocked

- [ ] 3.1 Build the manifest-admission predicate — required-field completeness/parsing, exactly-one provenance classification, and required check-result binding to the exact `manifest_hash` — as pure, deterministic, separately testable functions before wiring any call site.
- [ ] 3.2 Record a declared `license_id` without asserting a license policy. Build no license registry, unknown/no-derivatives rejection, restriction union, restriction propagation, or enforcement hook in this lane while the two-part license host decision in `design.md` is open.
- [ ] 3.3 Where an existing consumer must resolve or compose a declared license identifier, invoke the single landed lattice owned by `paid-market-economy` and do not reimplement its registry or composition answer. Keep its own rejection behavior and its explicit non-enforcement boundary unchanged.
- [ ] 3.4 Wire **manifest** admission into the run and mint boundaries so it precedes data transfer, token processing, payment release, and capability minting. Assert the refusal path before the success path.
- [ ] 3.5 Expose manifest admission as a server-side gate, not a caller-facing handle, and assert that no consumer carries a second local manifest-admission implementation. Test that a consumer attempting to admit without invoking the contract fails closed, and test that admission neither rejects on a license-restriction class nor propagates restrictions while the host decision is open.

## 4. Versioned gates bound to the exact manifest

- [ ] 4.1 Require a manifest to name the contamination, PII/privacy, integrity, deduplication, and quality evaluations its use requires.
- [ ] 4.2 Evaluate contamination against the held-out evaluation sets used by the Goal outcome-gate ladders, so gates backed by that data retain meaning.
- [ ] 4.3 Run deduplication as ordinary node work under the caller's own authority and budget; ship no hidden platform dedup service.
- [ ] 4.4 Bind every check result to the exact `manifest_hash` it ran against; a result recorded against a different version does not admit. Test the version-drift case directly — it is the hole a hash-free "this dataset passed" record would leave open.
- [ ] 4.5 Retain every check result, pass and fail, in the manifest's provenance; a later passing run does not delete, overwrite, or hide an earlier failure.

## 5. Per-example provenance and Forge as commons workflow

- [ ] 5.1 Require exactly one provenance class per example — `user-seed`, `corpus[dataset_id]`, or `synthetic[derived_from: ...]` — plus transformation lineage; refuse a manifest containing an example with none or more than one.
- [ ] 5.2 Make every synthetic example record every upstream source it was actually derived from, so its complete derivation set resolves from lineage alone. Specify no restriction inheritance or license-propagation semantics while the host decision is open.
- [ ] 5.3 Keep synthesis conditioned only on the contributor's own seed classified `user-seed`, attributing no source it was not derived from.
- [ ] 5.4 Build Forge as a commons workflow graph over existing graph primitives — seed intake, grant-gated corpus fetch, ordinary synthesis nodes, dedup, contamination gates, manifest emission — and ship at most a replaceable seed set. Add no platform Forge service, forge tool, or closed catalog.
- [ ] 5.4a Bind the grant-gated corpus-fetch source node to a declared, user-granted, revocable connection class owned by `boundary-layer`; define no ingress, grant, cap, credential, or license-enforcement path here. Until `outbound-boundary-layer` lands, implement the fetch node against its contract only — do not stub a local fetcher that bypasses grant binding.
- [ ] 5.5 Test that a user-authored fork of a seeded Forge graph produces an admissible manifest with identical treatment, requiring no platform approval, allowlisting, or platform code edit.
- [ ] 5.6 Assert that no training or gate-backed run starts without a complete admitted manifest whose full provenance set passes §3.

## 6. Lineage on the existing ledgers

- [ ] 6.1 Record contribution events through the existing append-only contribution-ledger contract. Consume its caller-supplied-event-id idempotency unchanged; do not define a dataset-specific event contract or implementation.
- [ ] 6.2 Record multi-parent derivations through the generic artifact-derivation contract owned by `node-discovery-and-remix` and onto the existing attribution-edge substrate. Consume atomic all-parent insertion, aggregate-credit bounds, derivation-id retry idempotency, rationale, per-edge clamping, depth, and cycle behavior from their owners; do not redefine them for datasets.
- [ ] 6.3 Make every admitted manifest, derived manifest, and promoted entry resolvable to its contributors and upstream sources from those ledgers alone.
- [ ] 6.2a Widen the attribution edge's endpoint-kind constraint to admit the generic `commons-artifact` kind, with the next numbered storage migration, keeping the set **closed and enumerated** — never a free-text kind column. No irreducibility finding supports a dataset-only substrate kind. This endpoint-domain widening, and only this widening, is what the `evaluation-outcomes-and-attribution` MODIFIED delta covers.
- [ ] 6.2b Test the endpoint-domain modification directly: a commons-artifact edge is admitted; an endpoint kind outside the enumerated set is rejected rather than coerced to `'branch'`, stored under a substituted kind, or written as an untyped identifier; the existing owner's other guarantees remain unchanged.
- [ ] 6.4 Assert by test that no dataset-specific lineage table, credit graph, provenance store, or attribution surface is created; the existing ledgers, widened in place, are the only home for these facts.
- [ ] 6.5 Define no contributor share weight, payout term, apportionment, or settlement here. Those remain with umbrella task 3.1's monetary half; test that this capability writes none of them.
- [ ] 6.6 Do not sync `data-commons` without both ownership deltas: `evaluation-outcomes-and-attribution` for the generic commons-artifact endpoint and `wiki-commons` for immutable-entry write refusal. Syncing only the local assertion while either canonical owner still contradicts it is forbidden.

## 7. Explicit, custody-agnostic promotion

- [ ] 7.1 Make publishing private material into the commons an explicit act by the holding principal, naming exactly what is published.
- [ ] 7.2 Refuse automatic promotion in each named shape, with a test per shape: no background crawl, no publish-on-run-completion, no promotion inferred from adjacency/similarity/co-location/prior sharing, and no promotion performed on a principal's behalf by the platform, a maintainer, or another universe.
- [ ] 7.3 Prove custody-agnosticism: material held on a user's host machine, in a private universe brain, in a vault whose key is outside platform reach, or in platform-held storage promotes through the same path with the same result, and the path requires no platform-held copy of the private source.
- [ ] 7.4 Make an unreachable source report that condition and complete nothing — never a fallback to a cached copy, a different custody mode, or a platform-held substitute.
- [ ] 7.5 Record in the implementation (not only in `design.md`) that commons entries are public-by-definition, platform-held as commons content, and exportable in full as a portable bundle, while the custody of the private source is the user's choice and is not answered here in either direction.
- [ ] 7.6 Test that a commons entry asserts no custody claim over the private original: revoking, relocating, or deleting the private source stays entirely under the contributor's control and is not prevented by the promoted entry's existence.

## 8. Acceptance, sync, and archive

- [ ] 8.1 Run focused unit, integration, and security tests for §§1–7 plus the full §14 concurrency/load matrix before treating any part as implemented.
- [ ] 8.2 Obtain opposite-provider review of the manifest-admission gate (§3) and the promotion refusals (§7) before either goes live; log the verdict as a durable artifact. These are the two irreversible surfaces — skipped admission can mint against incomplete or unbound provenance, and accidental promotion is a publication no deletion undoes.
- [ ] 8.3 For any public surface: live connector canary including `--assert-handles`, a real rendered chatbot conversation logged to `output/user_sim_session.md`, and freshness-stamped post-fix clean-use evidence.
- [ ] 8.4 **Gated on 8.1–8.3.** Only once every task above is genuinely complete: sync **all three** delta specs (`data-commons`, the `evaluation-outcomes-and-attribution` endpoint-domain MODIFIED delta, and the `wiki-commons` immutable-write MODIFIED delta — never the local requirement without either owner, per 6.6) into `openspec/specs/` and archive this change. Until then this change stays active and unsynced — see the archive guard at the top of this file.
- [ ] 8.5 **After this change lands**, check `build-forward-platform-capabilities` task 3.2 and update the `data-commons` slice-dependency-ledger rows. Task 3.1 stays unchecked even then: its pricing and contributor-settlement half remains with the umbrella. Not before landing — authoring a successor does not complete a successor-outcome tracker.
- [ ] 8.6 Reconcile the umbrella ownership-convention amendment with `claude/o5-demand-side` (PR #1771), which makes the same requirement-granularity amendment from the same base. Whichever lands second folds the two into one amended sentence rather than stating it twice.
