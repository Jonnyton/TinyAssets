## Context

`build-forward-platform-capabilities` tasks 3.1 and 3.2 are successor-outcome trackers that this change now owns — assigned 2026-07-25, unlanded, and deliberately still unchecked in the umbrella, because a successor-outcome tracker completes when its successor *lands*, not when it is authored.

The umbrella names this slice as the one the rest of Track E waits on. Task 3.2's own blocker sentence points at it (*"Forge cannot emit a manifest before the manifest contract exists"*), task 3.3 makes training's mint call it, task 4.4 lists it among hardware's direct edges, and the slice dependency ledger calls manifest and license validation *"the admission gate every downstream training or hardware claim invokes."* Nothing else unowned in the umbrella has that fan-out.

It was also, until 2026-07-25, only partly decidable. Task 3.1 carried a second blocker: the STATUS `host-decision` row for target-spec PLAN conflicts, because *"manifest storage and private-data placement are two of the four positions that row is waiting on."* PR #1761 landed both. This change is authored against `origin/main`'s PLAN.md as of that landing, and cites those positions by rule rather than paraphrasing them into new policy.

The shipped substrate is close enough to be misread as sufficient. `wiki-commons` already gives the commons a page substrate, a seed-not-closed category taxonomy, a draft-then-promote gate, compare-and-swap patching, and a discovery/coordination scope split. `evaluation-outcomes-and-attribution` already gives an append-only contribution ledger with idempotent event ids and attribution edges with clamped credit shares, cycle rejection, and generation depth. What is missing is the *contract*: nothing says what a dataset contribution is, what admits it, what a consumer must call before using it, or what happens at the boundary between a user's private material and the public commons.

## Goals / Non-Goals

**Goals:**

- Give the downstream slices the one thing they all block on: a manifest and license admission contract that fails closed and is invoked, not reimplemented.
- Express contribution as what the commons already is — an entry anyone can write — rather than as a dataset product with its own surface.
- Make provenance complete enough that a derived artifact's restrictions and contributors are recoverable from records alone.
- Make the private→commons boundary a deliberate user act under any custody mode.
- Keep the whole slice non-monetary, so it is buildable before the transaction transport exists.

**Non-Goals:**

- Dataset pricing modes and frozen contributor settlement — umbrella task 3.1's monetary half, retained there.
- Training instruments, checkpoint attestation, capability minting (3.3), and the F3 prohibition (3.4).
- The canonical bundle's write path, commit protocol, redaction ordering, or organization abstraction — `build-brain-canonical-store` owns those.
- The `write_page` commons-destination selector — owned elsewhere (D3).
- Answering the open private-data custody question, in either direction.
- Any new top-level MCP handle (see D4).
- Declaring umbrella 3.1 or 3.2 complete by landing this change. Per the umbrella's own promotion convention, a tracker is completed by its successor **landing**.

## Decisions

### D1 — Scope is the non-monetary contribution half of `data-commons`, and the split is by requirement

The umbrella's `data-commons` delta held six requirements. Four are non-monetary and move here; two are money and stay. The split is recorded as a **partial release**, and physically moving rather than copying is what enforces one owner per requirement — copying would create two active owners of the same text, the defect umbrella task 1.2 called out.

The two that stay are not arbitrary. *Dataset pricing is explicit and independent of compute pricing* defines three seller-chosen payment modes that consume escrow and revenue-share legs; *Contributor settlement is frozen, exact, and auditable* defines apportionment that conserves an input exactly. Both are value movement, both need umbrella D3's single transaction transport, and neither is required for a downstream consumer to *admit* a manifest. That is the seam: **admission is non-monetary; consideration is monetary.** Everything downstream blocks on admission, which is why this half is worth splitting off and building first.

One consequence has to be stated rather than left implicit. The moved manifest requirement lists `pricing terms` and `contributor shares` among the manifest's recorded fields. Those fields stay here as **recorded declarations** — readable terms with no authority — while their semantics stay with the umbrella. This is the same shape the task-4.1 successor used for declared budget posture, and D8 below is why it does not drift.

### D2 — What PR #1761 decided, and what it deliberately left open

Task 3.1's second blocker resolved into two answers of different kinds, and conflating them would produce a wrong design in either direction.

**Manifest storage: decided.** PLAN.md's Design Decisions now record that canonical storage is per-domain, not global — the knowledge bundle is canonical for the commons, Postgres is canonical for the platform's transactional domains (catalog, ledger, inbox, market), and *"neither store is canonical for the other's domain."* A dataset manifest entry is commons knowledge, so its canonical form is the bundle and its entry/full-text/vector stores are rebuildable derived indexes that lose to the bundle on disagreement. A market listing or settlement row that references the same dataset is canonical for the market domain and is **not** manifest truth. This is what was undecidable before: the same dataset has representations in two domains, and until the question was scoped per-domain there was no principled answer to which one wins.

**Private-data placement: decided to stay open.** PLAN.md Scoping Rule 4 was *reopened* on 2026-07-25 — custody is a scoped open research question, per-situation and user-chosen among host machine, private universe brain, vault, and platform-held, with none ruled in or out. The instruction to a lane is exact: do not encode either answer as settled, name the custody mode your lane assumes, scope the lane to it, record the assumption. D5 is this lane's compliance.

Read together they are what makes this change authorable now: the *commons* side of every storage question has a settled canonical form, and the *private* side is handled by refusing to depend on any particular custody mode at all.

### D3 — The commons is an OKF system anyone can write to, so contribution is a page write

Host framing, 2026-07-25: the commons is an OKF system anyone can write to, for community collaboration on shared and similar goals. PLAN.md's Brain module carries the storage half of that (*"For the commons — and as the default organization for a universe brain — the canonical knowledge representation is an OKF bundle"* — markdown with YAML frontmatter, one file per entry, cross-links forming the graph), and Scoping Rule 4 carries the access half (*"Platform-stored data that is in the commons is open-source community data — public-by-definition"*).

The umbrella's delta, read alone, does not obviously land there. Written as a dataset marketplace it invites a dataset registry: a `dataset` verb, a catalog surface, a platform-owned index of who registered what. Read against the reframe, the same behavior is smaller and already-shaped: **a contribution is a commons entry, discovery is a commons read, and a manifest is typed frontmatter on that entry.** OKF requires only a non-empty `type`, so Tiny's typed keys ride as additional frontmatter keys with no profile mechanism invented — exactly the mechanism PLAN.md already names for `goal_id`, `universe_id`, `visibility`, and the rest.

Two properties of the as-built commons make this fit rather than force it. The seed taxonomy is explicitly *not* a closed whitelist — a write to a custom category is accepted, sanitized, and stays queryable — so contribution categories need no platform blessing. And the shared root commons is not gated by the per-universe ownership ACL, only by the auth-scope gate, so "anyone authenticated may write to the commons" is a description of the surface rather than a change to it.

The one thing that is genuinely missing: the canonical `write_page` handle cannot select the commons as a destination today. This is verifiable from code on `main` rather than from a document. `tinyassets/universe_server.py:771-793` defines the single `write_page`; its routing resolves an authenticated caller's omitted `universe_id` to that caller's *home universe* and returns a `relay_to_universe` directive, on the 2026-07-02 reasoning that private canon is written by the universe itself. The consequence is that an authenticated principal has **no freeform commons write at all** — only `kind=` issue filings reach the shared commons, and an unauthenticated freeform write is answered with a 401 challenge. A contribution entry is a freeform page write, so it needs the selector.

The host decided the *shape* on 2026-07-25: the commons stays anyone-writable behind an explicit commons scope. **The owner of the implementation is unresolved, and this design records it as unresolved rather than guessing.** The obvious candidate does not survive checking: `reconcile-universe-personification-relay` tasks 6.1/6.7 own the person-dossier anti-collision *restriction* on the commons write path, which presumes a commons path exists rather than delivering one, and neither task's write-set claims `tinyassets/universe_server.py`'s routing. `live-mcp-connector-surface` and `wiki-commons` are the other plausible homes. Task 0.5 must establish the owner before §1 is built. **Under every outcome this change consumes the selector and defines neither it nor a second commons write path** — a second path is exactly the drift the residual analysis was written to prevent.

A note on that analysis, because it is the kind of citation that rots: `docs/audits/2026-07-22-write-page-commons-residual.md` is the detailed treatment, but it exists only on the unmerged branch `claude/write-page-commons-residual`, so a future reader on `main` cannot open it — and it is already partly stale, since it found *two* `write_page` definitions while `main` now has exactly one (`directory_server.py`'s is gone; `git grep -c "def write_page" -- tinyassets/` returns 1). Cite the code.

### D4 — No new top-level primitive; the irreducibility calls

PLAN.md Scoping Rule 1, as amended by the host-approved 2026-07-25 irreducibility finding, is the governing rule: a new top-level primitive ships **only** on a recorded finding that the behavior has essentially one working useful shape. The corollary is the operative half — a behavior with many plausible custom shapes is user-buildable by definition and belongs to the commons. No irreducibility finding is recorded for anything in this change, so nothing here ships as a handle. The calls made:

| Umbrella text that could read as a new tool | Irreducibility call | Where it lands |
|---|---|---|
| Dataset registration as a `dataset` / `register_dataset` tool | **Not irreducible.** A manifest is a typed entry in a knowledge bundle whose only required key is `type`; "a page with declared frontmatter" is not a new kind of thing. | `write_page` with contribution-kind, license, provenance, and integrity frontmatter keys. |
| A dataset registry or catalog surface | **Not irreducible.** Finding contributions is what commons search and changed-since already are, and the default discovery scope already separates commons knowledge from coordination history. | `read_page` search / changed-since; contribution entries classify as discovery-audience with no migration. |
| License validation as a `validate_license` tool | **Not a handle — but it *is* platform code.** Scoping Rule 3's own test decides it: this is a boundary a user must not be able to move, so it is enforcement, and enforcement is platform. But enforcement belongs at the run/mint admission boundary, invoked before work begins, not as a caller-facing verb a caller could route around. | A server-side fail-closed admission gate on the existing run and mint paths. No handle. |
| Dataset Forge as a platform service | **Not irreducible, and the corollary applies directly.** "What should a dataset-synthesis pipeline look like" has many plausible shapes, so it is user-buildable by definition and belongs to the commons — the same call the task-4.1 successor made for onboarding archetypes and PLAN.md made for brain organization. | A forkable commons workflow graph over existing graph primitives via `write_graph` / `run_graph`; the platform ships a replaceable seed set. |
| Contamination / dedup / quality checks as new platform evaluators | **Not irreducible.** Gate evaluation belongs to `constraint-evaluation` + `evaluation-runtime-and-scenarios`; the umbrella already requires dedup to run as ordinary priced node work rather than a hidden platform service. | Existing gate capabilities plus ordinary nodes; this change requires the *binding* of a versioned result to an exact `manifest_hash`, not a new evaluator kind. |
| A dataset lineage / credit graph | **Not irreducible — and it already exists.** The append-only contribution ledger and attribution edges already provide idempotent events, clamped credit shares, cycle rejection, and generation depth. | `evaluation-outcomes-and-attribution`, referenced. See D6. |
| A `promote_to_commons` tool | **Not irreducible.** Promotion is a `write_page` of the entry the contributor names, then the existing draft-then-promote lifecycle. What this change adds is a *constraint* on when that may happen (D5), not a mechanism. | `write_page` plus the existing `promote` action. |

The pattern is the same each time: the platform ships the enforcement boundary and the substrate, and the commons ships the shape.

### D5 — Promotion is an explicit act, and the lane is custody-agnostic by construction

Scoping Rule 4 obliges every lane touching private data to name its custody mode and record the assumption; a lane that stays silent is the thing the rule forbids. This lane's position has two halves, and they are different:

**The commons side is named and settled.** Commons entries are public-by-definition and platform-held as commons content, exportable in full as a portable bundle — the same no-lock-in guarantee PLAN.md's Brain module attaches to the bundle export and Scoping Rule 4 owes the customer.

**The private side is deliberately unassumed.** The promotion path may not depend on the platform holding the private source. Whether the material lives on the user's host machine, in their private universe brain, in a vault whose key is outside platform reach, or in platform-held storage, promotion behaves identically — and where the source is unreachable because no host is online, the attempt reports that condition rather than degrading to a cached copy or a different custody mode. The async-availability allowance in Scoping Rule 4 covers exactly this case.

The "never automatic" clause is where the real risk is, and it is written as a list of specific refusals rather than one general sentence, because the general sentence closes only the obvious case. A background crawl, a publish-on-run-completion, a promotion inferred from similarity or co-location or prior sharing, and a promotion performed on a principal's behalf are four distinct shapes of the same defect, and a system that closes only the first still leaks. The failure mode this guards against is severe and irreversible in the way that matters: commons content is public-by-definition, so an accidental promotion is a publication, and no later deletion un-publishes it.

The converse clause matters too. A commons entry must not imply, require, or create platform custody of the private original — otherwise "contribute to the commons" quietly becomes "hand us your data", which is the lock-in Scoping Rule 4 names as the thing the customer will build a ground-up alternative to escape.

### D6 — Attribution rides the existing ledgers; that substrate is the moat, not a thing to rebuild

Verifiable provenance plus funding is the platform's stated advantage over commodity compute, and the ledgers that carry it already exist as canonical behavior: a single append-only contribution table idempotent on a caller-supplied event id, and attribution edges with credit shares clamped into the unit interval, a bounded ancestor walk that rejects cycles before insert, and generation depth derived from parents.

A dataset-specific lineage table would be a second source of provenance truth for the same facts, and the two would diverge on the first path that wrote one and not the other. So this change records **onto** those ledgers and defines no store of its own. The division is clean: the ledgers answer *who contributed what, and from what*; the manifest answers *what the artifact is and what terms it carries*; **neither answers what anyone gets paid**, which is D8's boundary and the umbrella's retained requirement.

**But "existing semantics suffice" was false for half of it, and checking beat assuming.** The two ledgers are not equally ready:

- **Contribution events are ready as-is.** `tinyassets/contribution_events.py:40-52` already carries a generic `source_artifact_id` plus a free-text `source_artifact_kind` with no closed-set constraint, so a contribution event about a manifest needs no change to anything canonical.
- **Attribution edges are not.** `tinyassets/attribution/schema.py:33-47` constrains `parent_kind` and `child_kind` with `CHECK (… IN ('branch','node'))`, and the only writer — `tinyassets/api/market.py:898-975` — requires `parent_branch_def_id` / `child_branch_def_id` and inserts the kinds as the literal `'branch'`. A manifest-to-manifest edge is therefore **rejected by the schema**, not merely unwritten by the current call site. Asserting manifest lineage in the `data-commons` delta alone would leave canonical truth describing a substrate that cannot hold it.

So the widening is carried as a **MODIFIED delta** on `evaluation-outcomes-and-attribution`, and `data-commons` may not sync without it. The modification is deliberately the smallest one that closes the gap: it adds a dataset-manifest endpoint kind to a set that stays **closed and enumerated** — a free-text kind column would trade a rejected edge for an unvalidated one — and restates clamp, cycle rejection, generation depth, idempotency, and append-only uniqueness unchanged. Widening an endpoint domain on the existing table is still referencing the moat; a parallel table would have been rebuilding it.

### D7 — Validation must be invoked, and "invoked" has to be enforced structurally

A pure license lattice is not enforcement — umbrella D5 says so directly, and it is the failure this requirement exists to prevent. A validation contract that a consumer *may* call is a contract that a consumer eventually will not call, and the failure is silent: the run succeeds, the capability mints, and the restriction is simply absent from the record.

Three properties make it structural rather than advisory. Admission happens **before** bytes, tokens, payment, or minting — after any of those, refusal is no longer available. The composed restriction set is **frozen into the derived artifact's record** at admission, so the enforcement outlives the call that performed it. And the gate result is **bound to the exact `manifest_hash`**, so a check against a different version does not admit, which closes the version-drift hole that a hash-free "this dataset passed" record would leave open.

The "SHALL NOT reimplement" clause is deliberate and is the same shape as umbrella D2's rule for pure oracles: a second implementation of admission logic is a second answer to the same question, and it will differ.

### D8 — The money edge refuses rather than degrades

Umbrella D3 requires all value movement to converge on one authenticated transaction boundary. The risk here is not that this change deliberately builds a payment surface — it is that a manifest's *declared* pricing terms and contributor shares drift into spend authority, or that an admission path quietly writes a local balance row because the transport does not exist yet. Both are how a second accounting path gets born, and this change carries declarations of exactly the shape that invites it.

So declared terms are specified as readable declarations that no spend path accepts as authorization, and a value-moving action **refuses and names its required capability** rather than degrading to a best-effort local debit. It names the `paid-market-economy` capability rather than the change slug currently building its transport, because change names are provenance and expire on archive while the capability is the durable contract.

### D9 — Umbrella D9 binds nothing here

Per umbrella D9, the 2026-07-19 open-production-commons reframe is provenance only and non-normative in both directions. No requirement in this change is taken from it, and nothing here is designed, blocked, or reviewed *for* it. "Keep the reframe reachable" is not a constraint on this slice and is not grounds for rejecting this design.

## Dependency boundaries

| This change | Depends on | Why the edge exists |
|---|---|---|
| Contribution entries and discovery | `wiki-commons` | The page substrate, custom-category acceptance, draft-then-promote, compare-and-swap patch, and the discovery/coordination scope split are as-built; a contribution is an entry on that substrate, not a parallel object. |
| Commons write destination | host decision 2026-07-25; **implementation owner UNRESOLVED** (task 0.5) | An authenticated freeform `write_page` relays to the caller's home rather than reaching the commons (`tinyassets/universe_server.py:771-793`). The host decided the shape; no change's tasks or write-set currently claims building the selector — the relay lane's 6.1/6.7 own the anti-collision restriction *on* that path, not the path. This change consumes the selector and defines neither it nor a second commons write path. |
| Canonical form and durability of the entry | `build-brain-canonical-store` (unbuilt) | That owner holds the bundle write path, commit protocol, and redaction ordering. This change states which store is canonical for a manifest; it defines no durability mechanism and must not be implemented ahead of that contract. |
| Contributor and derivation provenance | `evaluation-outcomes-and-attribution` (+ MODIFIED delta) | The contribution ledger's generic artifact columns are ready as-is; the attribution edge's endpoint kinds are a closed `('branch','node')` set that rejects a manifest edge, so the widening is carried as a MODIFIED delta. Recorded onto, never duplicated. |
| Outbound corpus / storage access inside a Forge graph | `outbound-boundary-layer` (unbuilt) | Manifest *movement* needs no outbound path — references move, bytes do not — but a license-gated corpus fetch is an external read, and `boundary-layer` requires a source node to bind a declared, user-granted, revocable connection class. Grants, caps, and credential blindness stay with that owner. |
| Authenticated contribution and visibility | `identity-auth-and-access-control` | The authenticated principal and the auth-scope gate are that capability's; this change adds no actor model and no second ACL. |
| Contamination, privacy, quality gate evaluation | `constraint-evaluation`, `evaluation-runtime-and-scenarios` | Gate evaluation is not redefined here; this change requires the binding of a versioned result to an exact manifest hash. |
| Contamination reference sets and Goal relatedness | `shared-goals-and-convergence` | Contamination is measured against the held-out sets the outcome-gate ladders use, so those gates retain meaning; a contribution's related Goals are read through the existing Goal records. |
| Forge graphs | `graph-execution-substrate` | A Forge graph is an ordinary compiled graph; no execution engine, node kind, or scheduler is added. |
| Any value movement | `paid-market-economy` (transport building in `paid-market-track-e-wave-2-transport`) | Umbrella D3's single money transport. This change refuses at the edge instead of consuming it. |
| Dataset pricing modes, contributor settlement | `build-forward-platform-capabilities` task 3.1 (monetary half) | Retained by the umbrella; out of scope by D1 of this change. |
| Training instruments and capability minting | `build-forward-platform-capabilities` task 3.3 | The consumer of this change's admission contract, not part of it. Landing this change does not unblock 3.3 until the contract is *built*. |

## Risks / Trade-offs

- [Risk] A validation contract that consumers may skip. → D7 puts admission before bytes/tokens/payment/mint, freezes the composed restrictions into the derived record, and binds every gate result to the exact `manifest_hash`; the acceptance tasks include a consumer that attempts to admit without calling it.
- [Risk] "Contribute to the commons" silently becomes "give us your private data". → D5 forbids automatic promotion in four named shapes, requires identical behavior under every custody mode, and states that a commons entry creates no custody claim over the private original. The adversarial task asserts that no scan, similarity match, or run-completion path publishes anything.
- [Risk] A second provenance store appears because the dataset case "needs extra fields". → D6 records onto the existing ledgers; the acceptance task asserts no dataset-specific lineage table exists and that provenance is resolvable from those ledgers alone.
- [Risk] Widening the attribution edge's endpoint kinds becomes an open door — a free-text kind column that admits anything. → The MODIFIED delta keeps the set closed and enumerated and requires an unenumerated kind to be *rejected* rather than coerced; the acceptance test asserts no coercion to `'branch'` and no untyped-identifier fallback. A free-text column would trade a rejected edge for an unvalidated one.
- [Risk] The `evaluation-outcomes-and-attribution` MODIFIED delta is dropped and `data-commons` syncs alone, leaving canonical truth describing a substrate that cannot hold manifest lineage. → Task 6.6 forbids syncing one without the other, and task 0.2a re-verifies the constraint before the delta is trusted.
- [Risk] Declared pricing terms drift into spend authority. → D8 specifies them as readable declarations with an explicit refusal scenario; the acceptance task asserts no spend path accepts a declaration as authorization.
- [Risk] The manifest grows into a new primitive by accretion. → D4 records the irreducibility call per behavior; a future field that cannot be expressed as frontmatter on a commons entry under the seven canonical handles is the signal to stop and record an irreducibility finding, not to add a handle.
- [Risk] This change is implemented ahead of the canonical bundle's commit protocol, so "canonical in the bundle" is asserted while the bundle has no durable write path. → Task 0.3 makes the `build-brain-canonical-store` durability contract an explicit prerequisite; until it exists, this change is implementable only against that contract.
- [Trade-off] Requiring exactly one provenance class per example rejects contributions that would otherwise register. → Deliberate. An unclassified example is one whose restrictions cannot be composed, and admitting it would make every downstream restriction claim unsound; the rejection happens at registration where a contributor is present, not at mint time where the artifact already exists.
- [Trade-off] Immutable manifests mean a typo mints a new version. → Deliberate, and the cheaper failure. A mutable manifest breaks every gate result bound to its hash and every restriction frozen from it.

## Migration Plan

1. Add the contribution frontmatter keys and the manifest entry shape as commons-entry conventions; no parallel store, no new category whitelist.
2. Build the curated license registry and the restriction-union composition contract as pure, testable functions before wiring any call site.
3. Wire the fail-closed admission gate into the run and mint boundaries so admission precedes bytes, tokens, payment, and minting; assert the refusal path before the success path.
4. Bind gate results to the exact `manifest_hash` and retain pass and fail results in provenance.
5. Record contribution and derivation onto the existing contribution ledger and attribution edges; add no lineage table.
6. Add the explicit promotion path with its four refusals and its custody-mode parity tests.
7. Seed replaceable Forge graphs as commons content; verify a user-authored fork produces an admissible manifest with no platform approval.
8. Only then run focused tests, the §14 concurrency/load matrix, canaries, rendered chatbot acceptance, and post-fix clean-use evidence.

Rollback is per step: the registry and composition functions are pure and revertible; the admission gate is the only step that changes existing run/mint behavior and needs a tested rollback plan; Forge graphs are commons content; and manifest entries are immutable, so no rollback rewrites a published entry.

## Open Questions

- Which licenses enter the curated registry, and what counsel process approves additions? (Inherited from the umbrella's Open Questions; unchanged and still unanswered.)
- What privacy/PII scanning gate precedes public dataset use — which scanner, at what threshold, and who reviews a flagged result? (Inherited from the umbrella.)
- What is the curation-review step in practice for a commons contribution — who or what reviews, and does a failed review block admission or only annotate the entry? The requirement says registration is declaration plus curation review; it does not say who reviews.
- Should a contribution's related-Goal declaration be verified against the Goal record, or remain an unverified declaration like its source declarations? Verification is cheap here but is a different trust posture than the rest of the manifest.
- How does a contributor withdraw a commons contribution whose private source they have revoked, given that commons entries are public-by-definition and manifests are immutable? Redaction ordering belongs to `build-brain-canonical-store`; what a *withdrawal* means for downstream artifacts frozen against the manifest does not yet have an owner.
