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

- [ ] 0.1 Before any implementation write, re-verify against `origin/main` that `openspec/specs/wiki-commons/spec.md` still specifies the seed taxonomy as **not a closed whitelist** (custom categories accepted, sanitized, and queryable), the shared root commons as ungated by the per-universe ownership ACL, and the default discovery scope as classifying non-coordination categories as `discovery`. Every one of those is load-bearing for §1. If any has changed, carry the contradiction as a MODIFIED delta before building — do not assert it only in the `data-commons` delta.
- [ ] 0.2 Re-verify that `openspec/specs/evaluation-outcomes-and-attribution/spec.md` still specifies the append-only contribution ledger (idempotent on caller-supplied `event_id`) and attribution edges (credit share clamped to `[0,1]`, cycle rejection via bounded ancestor walk, generation depth from parents). §6 records onto those exact semantics; if they moved, re-anchor §6 rather than reproducing them.
- [ ] 0.2a Re-verify the attribution-edge endpoint constraint that makes the MODIFIED delta necessary: `tinyassets/attribution/schema.py:33-47` constrains `parent_kind`/`child_kind` with `CHECK (… IN ('branch','node'))`, and `tinyassets/api/market.py:898-975` requires branch ids and inserts the kinds as the literal `'branch'` — so a manifest edge is *rejected by the schema*, not merely unwritten. If a later change already widened the set, drop or rewrite the MODIFIED delta rather than restating a constraint that has moved. Also confirm `tinyassets/contribution_events.py:40-52` still carries a generic `source_artifact_id`/`source_artifact_kind` with no closed-set constraint — if that gained a constraint, contribution events need a delta too.
- [ ] 0.3 Confirm `build-brain-canonical-store` has not landed the bundle write path and commit protocol under different guarantees than its delta specifies. Until it lands, implement §2's canonical-form claim against its contract only; do **not** build a bundle write path, commit protocol, or redaction ordering here.
- [ ] 0.4 Re-read PLAN.md Scoping Rules 1, 3, and 4 and the Design Decisions entry for per-domain canonical storage as landed by PR #1761; if the landed wording differs from what `design.md` D2/D4/D5 was authored against, reconcile the design first.
- [ ] 0.5 **Establish the commons write-destination selector's owner — it is UNRESOLVED, not merely uncited.** Verify the gap from code, not from the audit: `tinyassets/universe_server.py:771-793` is the single `write_page` on `main`, and its routing resolves an authenticated caller's omitted `universe_id` to that caller's home universe and returns `relay_to_universe`, so only `kind=` filings reach the shared commons. The host decided the *shape* 2026-07-25 (commons stays anyone-writable behind an explicit commons scope), but `reconcile-universe-personification-relay` 6.1/6.7 own the person-dossier anti-collision *restriction* on that path and neither task's write-set claims the routing — so that lane is not the selector's owner by default. Determine and record the real owner (that lane, `live-mcp-connector-surface`, `wiki-commons`, or a new change) before §1 is built. Do not cite `docs/audits/2026-07-22-write-page-commons-residual.md` as the authority: it lives only on the unmerged branch `claude/write-page-commons-residual` and is partly stale (it found two `write_page` definitions; `main` has one). Under no outcome does this change define the selector or a second commons write path.
- [ ] 0.6 Confirm the umbrella's decisions D1–D8 still hold for this slice and record any divergence as a design change here, not as silent drift.
- [ ] 0.7 Take no requirement from the host-gated open-production-commons reframe. Per umbrella D9 it is provenance only and binds nothing in either direction — "keep the reframe reachable" is not a constraint on this slice and not a review gate against it.
- [ ] 0.8 Classify each task below as live / landed / inverted against current code before building. In particular, confirm no landed change already ships a dataset manifest shape, a license registry, or a dataset lineage table under different names; a grep miss is not proof of absence, so check `tinyassets/api/market.py`, the wiki frontmatter handling, and the contribution-ledger call sites directly.

## 1. Contribution and discovery on the canonical page handles

- [ ] 1.1 Define the contribution entry: a commons entry whose frontmatter declares contribution kind, related Goals, resolved `license_id`, provenance class, and integrity references, as additional keys on an entry whose only structurally required key is `type`. Invent no profile mechanism and no category whitelist.
- [ ] 1.2 Route contribution writes through the canonical `write_page` handle and the commons destination selector owned per 0.5. Add no dataset tool, no contribution action namespace, no platform-owned contribution registry, and no second commons write path.
- [ ] 1.3 Make discovery ordinary commons reads — search and changed-since through `read_page` under the existing default discovery scope — with no dataset catalog surface and no second discovery index.
- [ ] 1.4 Keep the commons anyone-writable: any authenticated principal contributes subject only to the existing auth-scope gate, with no invitation list, curation seat, or platform-approval step consulted.
- [ ] 1.5 Assert by test that the advertised handle set is unchanged after implementation — the `--assert-handles` canonical set, with no contribution, dataset, manifest, forge, or promotion handle added.

## 2. Manifest entries: immutable, content-addressed, reference-moving

- [ ] 2.1 Specify and implement the manifest entry fields — `manifest_hash`, size, modality, registry-resolved `license_id`, source declarations, curation log, schema, integrity hashes, storage references, declared pricing terms, declared contributor shares, version lineage.
- [ ] 2.2 Make manifest entries immutable: changed content mints a new hash and a new version linked to its predecessor; no in-place mutation of a registered manifest.
- [ ] 2.3 Move references, not bytes: downstream marketplace, training, and workflow records bind the manifest hash and an access grant; assert by test that no path requires bytes to transit platform-owned dataset storage.
- [ ] 2.4 Encode the canonical-form split from PLAN.md's per-domain decision: the commons bundle is canonical for the manifest entry, entry/full-text/vector stores are rebuildable derived indexes that lose to the bundle on disagreement, and a catalog/ledger/inbox/market row referencing the same dataset is canonical only for its own domain and is never consulted as manifest truth. Test the disagreement case explicitly.
- [ ] 2.5 Distinguish declared claims from checked results in the entry, so no consumer can read an unchecked declaration as a passed validation. Registration is declaration plus curation review, not proof.

## 3. Fail-closed license and manifest admission

- [ ] 3.1 Build the curated license registry and the restriction-union composition contract as pure, deterministic, separately testable functions before wiring any call site.
- [ ] 3.2 Resolve dataset and base-model license identifiers against the registry; fail closed with a recorded reason on unknown, missing, expired, no-derivatives, or incompatible terms, with no partial admission, permissive default, best-effort match, or caller-asserted override.
- [ ] 3.3 Propagate the composed restriction union irrevocably to every derived artifact and freeze it into the record of any capability minted from admitted inputs; a derived artifact can never be published or minted under terms more permissive than its union.
- [ ] 3.4 Wire admission into the run and mint boundaries so it precedes data transfer, token processing, payment release, and capability minting. Assert the refusal path before the success path.
- [ ] 3.5 Expose admission as a server-side gate, not a caller-facing handle, and assert that no consumer carries a second local license/manifest admission implementation. Test that a consumer attempting to admit without invoking the contract fails closed.

## 4. Versioned gates bound to the exact manifest

- [ ] 4.1 Require a manifest to name the contamination, PII/privacy, integrity, deduplication, and quality evaluations its use requires.
- [ ] 4.2 Evaluate contamination against the held-out evaluation sets used by the Goal outcome-gate ladders, so gates backed by that data retain meaning.
- [ ] 4.3 Run deduplication as ordinary node work under the caller's own authority and budget; ship no hidden platform dedup service.
- [ ] 4.4 Bind every check result to the exact `manifest_hash` it ran against; a result recorded against a different version does not admit. Test the version-drift case directly — it is the hole a hash-free "this dataset passed" record would leave open.
- [ ] 4.5 Retain every check result, pass and fail, in the manifest's provenance; a later passing run does not delete, overwrite, or hide an earlier failure.

## 5. Per-example provenance and Forge as commons workflow

- [ ] 5.1 Require exactly one provenance class per example — `user-seed`, `corpus[dataset_id]`, or `synthetic[derived_from: ...]` — plus transformation lineage; refuse a manifest containing an example with none or more than one.
- [ ] 5.2 Make synthetic examples inherit every upstream restriction, and prevent an output manifest from publishing under terms more permissive than the inherited union.
- [ ] 5.3 Keep synthesis conditioned only on the contributor's own seed classified `user-seed`, acquiring no restrictions from sources it was not derived from.
- [ ] 5.4 Build Forge as a commons workflow graph over existing graph primitives — seed intake, license-gated corpus fetch, ordinary synthesis nodes, dedup, contamination gates, manifest emission — and ship at most a replaceable seed set. Add no platform Forge service, forge tool, or closed catalog.
- [ ] 5.4a Bind the license-gated corpus-fetch source node to a declared, user-granted, revocable connection class owned by `boundary-layer`; define no ingress, grant, cap, or credential path here. Until `outbound-boundary-layer` lands, implement the fetch node against its contract only — do not stub a local fetcher that bypasses grant binding.
- [ ] 5.5 Test that a user-authored fork of a seeded Forge graph produces an admissible manifest with identical treatment, requiring no platform approval, allowlisting, or platform code edit.
- [ ] 5.6 Assert that no training or gate-backed run starts without a complete admitted manifest whose full provenance set passes §3.

## 6. Lineage on the existing ledgers

- [ ] 6.1 Record contribution events on the existing append-only contribution ledger, idempotent on the caller-supplied event id; test that a replayed event inserts once.
- [ ] 6.2 Record derivations as parent-to-child attribution edges on the existing substrate, with clamped credit shares, derived generation depth, and cycle rejection before insert; test the cyclic case.
- [ ] 6.3 Make every admitted manifest, derived manifest, and promoted entry resolvable to its contributors and upstream sources from those ledgers alone.
- [ ] 6.2a Widen the attribution edge's endpoint-kind constraint to admit a dataset-manifest kind, with the next numbered storage migration, keeping the set **closed and enumerated** — never a free-text kind column, which would trade a rejected edge for an unvalidated one. This is what the `evaluation-outcomes-and-attribution` MODIFIED delta covers; do not implement §6.2 for manifests while that delta is absent or stale (see 0.2a).
- [ ] 6.2b Test that manifest edges inherit every existing guarantee unchanged — clamp, bounded ancestor walk and cycle rejection, parent-max-plus-one depth, append-only uniqueness — and that an endpoint kind outside the enumerated set is rejected rather than coerced to `'branch'`, stored under a substituted kind, or written as an untyped identifier.
- [ ] 6.4 Assert by test that no dataset-specific lineage table, credit graph, provenance store, or attribution surface is created; the existing ledgers, widened in place, are the only home for these facts.
- [ ] 6.5 Define no contributor share weight, payout term, apportionment, or settlement here. Those remain with umbrella task 3.1's monetary half; test that this capability writes none of them.
- [ ] 6.6 Do not sync `data-commons` without the `evaluation-outcomes-and-attribution` MODIFIED delta. A synced manifest-lineage guarantee beside an attribution substrate whose canonical text admits only branch and node endpoints is the drift `reclassify-forward-vision-specs` removed.

## 7. Explicit, custody-agnostic promotion

- [ ] 7.1 Make publishing private material into the commons an explicit act by the holding principal, naming exactly what is published.
- [ ] 7.2 Refuse automatic promotion in each named shape, with a test per shape: no background crawl, no publish-on-run-completion, no promotion inferred from adjacency/similarity/co-location/prior sharing, and no promotion performed on a principal's behalf by the platform, a maintainer, or another universe.
- [ ] 7.3 Prove custody-agnosticism: material held on a user's host machine, in a private universe brain, in a vault whose key is outside platform reach, or in platform-held storage promotes through the same path with the same result, and the path requires no platform-held copy of the private source.
- [ ] 7.4 Make an unreachable source report that condition and complete nothing — never a fallback to a cached copy, a different custody mode, or a platform-held substitute.
- [ ] 7.5 Record in the implementation (not only in `design.md`) that commons entries are public-by-definition, platform-held as commons content, and exportable in full as a portable bundle, while the custody of the private source is the user's choice and is not answered here in either direction.
- [ ] 7.6 Test that a commons entry asserts no custody claim over the private original: revoking, relocating, or deleting the private source stays entirely under the contributor's control and is not prevented by the promoted entry's existence.

## 8. Acceptance, sync, and archive

- [ ] 8.1 Run focused unit, integration, and security tests for §§1–7 plus the full §14 concurrency/load matrix before treating any part as implemented.
- [ ] 8.2 Obtain opposite-provider review of the admission gate (§3) and the promotion refusals (§7) before either goes live; log the verdict as a durable artifact. These are the two irreversible surfaces — a skipped admission mints an unrestricted capability, and an accidental promotion is a publication no deletion undoes.
- [ ] 8.3 For any public surface: live connector canary including `--assert-handles`, a real rendered chatbot conversation logged to `output/user_sim_session.md`, and freshness-stamped post-fix clean-use evidence.
- [ ] 8.4 **Gated on 8.1–8.3.** Only once every task above is genuinely complete: sync **both** delta specs (`data-commons` and the `evaluation-outcomes-and-attribution` MODIFIED delta — never one without the other, per 6.6) into `openspec/specs/` and archive this change. Until then this change stays active and unsynced — see the archive guard at the top of this file.
- [ ] 8.5 **After this change lands**, check `build-forward-platform-capabilities` task 3.2 and update the `data-commons` slice-dependency-ledger rows. Task 3.1 stays unchecked even then: its pricing and contributor-settlement half remains with the umbrella. Not before landing — authoring a successor does not complete a successor-outcome tracker.
- [ ] 8.6 Reconcile the umbrella ownership-convention amendment with `claude/o5-demand-side` (PR #1771), which makes the same requirement-granularity amendment from the same base. Whichever lands second folds the two into one amended sentence rather than stating it twice.
