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

- Dataset pricing modes and frozen contributor settlement — umbrella task 3.1's monetary half, retained there. This lane records **no** pricing or contributor-share field at all, not even as an inert declaration (D10).
- Any license restriction policy, license registry, or license enforcement — blocked on an unresolved host decision (D11). This lane consumes the landed `paid-market-economy` lattice where a declared identifier must be resolved, and specifies nothing about which identifiers are acceptable or what terms propagate.
- Any dataset-rights market or second paid surface (D10).
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

One consequence has to be stated rather than left implicit. The moved manifest requirement listed `pricing terms` and `contributor shares` among the manifest's recorded fields. **Those fields are now removed from this half entirely** — see D10; keeping them as "inert declarations" was the wrong call and is what an independent review caught.

### D2 — What PR #1761 decided, and what it deliberately left open

Task 3.1's second blocker resolved into two answers of different kinds, and conflating them would produce a wrong design in either direction.

**Manifest storage: decided.** PLAN.md's Design Decisions now record that canonical storage is per-domain, not global — the knowledge bundle is canonical for the commons, Postgres is canonical for the platform's transactional domains (catalog, ledger, inbox, market), and *"neither store is canonical for the other's domain."* A dataset manifest entry is commons knowledge, so its canonical form is the bundle and its entry/full-text/vector stores are rebuildable derived indexes that lose to the bundle on disagreement. A market listing or settlement row that references the same dataset is canonical for the market domain and is **not** manifest truth. This is what was undecidable before: the same dataset has representations in two domains, and until the question was scoped per-domain there was no principled answer to which one wins.

**Private-data placement: decided to stay open.** PLAN.md Scoping Rule 4 was *reopened* on 2026-07-25 — custody is a scoped open research question, per-situation and user-chosen among host machine, private universe brain, vault, and platform-held, with none ruled in or out. The instruction to a lane is exact: do not encode either answer as settled, name the custody mode your lane assumes, scope the lane to it, record the assumption. D5 is this lane's compliance.

Read together they are what makes this change authorable now: the *commons* side of every storage question has a settled canonical form, and the *private* side is handled by refusing to depend on any particular custody mode at all.

### D3 — The commons is an OKF system anyone can write to, so contribution is a page write

Host framing, 2026-07-25: the commons is an OKF system anyone can write to, for community collaboration on shared and similar goals. PLAN.md's Brain module carries the storage half of that (*"For the commons — and as the default organization for a universe brain — the canonical knowledge representation is an OKF bundle"* — markdown with YAML frontmatter, one file per entry, cross-links forming the graph), and Scoping Rule 4 carries the access half (*"Platform-stored data that is in the commons is open-source community data — public-by-definition"*).

The umbrella's delta, read alone, does not obviously land there. Written as a dataset marketplace it invites a dataset registry: a `dataset` verb, a catalog surface, a platform-owned index of who registered what. Read against the reframe, the same behavior is smaller and already-shaped: **a contribution is a commons entry, discovery is a commons read, and a manifest is typed frontmatter on that entry.** OKF requires only a non-empty `type`, so Tiny's typed keys ride as additional frontmatter keys with no profile mechanism invented — exactly the mechanism PLAN.md already names for `goal_id`, `universe_id`, `visibility`, and the rest.

Two properties of the as-built commons make this fit rather than force it. The seed taxonomy is explicitly *not* a closed whitelist — a write to a custom category is accepted, sanitized, and stays queryable — so contribution categories need no platform blessing. And the shared root commons is not gated by the per-universe ownership ACL, only by the auth-scope gate, so "anyone authenticated may write to the commons" is a description of the surface rather than a change to it.

That destination prerequisite landed after this design was authored. PR #1857 (`72ee903b`, merged 2026-07-29) completed `reconcile-universe-personification-relay` tasks 6.1/6.7 by adding an explicit `scope=commons|universe` selector to the canonical `write_page` handle. The current handler accepts authenticated `scope=commons` freeform writes on the shared page path, keeps universe-targeted writes on the relay path, rejects invalid scope values, and rejects `scope=commons` combined with `universe_id`. Its focused boundary tests cover the commons success path and fail-closed contradictory targets.

The selector's landed owner is therefore `reconcile-universe-personification-relay`, with the durable surface requirement carried in that change's `live-mcp-connector-surface` delta. This change consumes the selector unchanged. It defines neither another `scope` parameter nor a second commons write path, and it still owns only the contribution/manifest semantics layered on the canonical page handle.

### D4 — No new top-level primitive; the irreducibility calls

PLAN.md Scoping Rule 1, as amended by the host-approved 2026-07-25 irreducibility finding, is the governing rule: a new top-level primitive ships **only** on a recorded finding that the behavior has essentially one working useful shape. The corollary is the operative half — a behavior with many plausible custom shapes is user-buildable by definition and belongs to the commons. No irreducibility finding is recorded for anything in this change, so nothing here ships as a handle. The calls made:

| Umbrella text that could read as a new tool | Irreducibility call | Where it lands |
|---|---|---|
| Dataset registration as a `dataset` / `register_dataset` tool | **Not irreducible.** A manifest is a typed entry in a knowledge bundle whose only required key is `type`; "a page with declared frontmatter" is not a new kind of thing. | `write_page` with contribution-kind, license, provenance, and integrity frontmatter keys. |
| A dataset registry or catalog surface | **Not irreducible.** Finding contributions is what commons search and changed-since already are, and the default discovery scope already separates commons knowledge from coordination history. | `read_page` search / changed-since; contribution entries classify as discovery-audience with no migration. |
| Manifest validation as a `validate_manifest` tool | **Not a handle — but it *is* platform code.** The enforcement test decides it: whether a manifest is complete, whether every example carries exactly one provenance class, and whether each required check result is bound to the exact `manifest_hash` are boundaries a caller must not be able to move. But enforcement belongs at the run/mint admission boundary, invoked before work begins, not as a caller-facing verb a caller could route around. | A server-side fail-closed manifest-admission gate on the existing run and mint paths. No handle. |
| License validation as a `validate_license` tool | **Neither — the question is not this lane's to answer.** The prior draft reasoned from the enforcement test to "license validation is platform code," which skipped the prior question of whether a license *boundary* exists to enforce. It does not, on any authorized position: the landed architecture pins CC0 with no restrictions and states the platform does not build license enforcement. And the pure resolution/composition half already has a landed owner. See D11. | Nothing here. Declared identifier recorded as a declaration; resolution/composition consumed from `paid-market-economy`'s landed lattice; policy and enforcement blocked on a host decision. |
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

A dataset-specific lineage table would be a second source of provenance truth for the same facts, and the two would diverge on the first path that wrote one and not the other. So this change records **onto** those ledgers and defines no store of its own. The division is clean: the ledgers answer *who contributed what, and from what*; the manifest answers *what the artifact declares itself to be and where its bytes live*; **neither answers what anyone gets paid or what legal restrictions apply**, which are excluded by D10/D11.

**But "existing semantics suffice" was false for half of it, and checking beat assuming.** The two ledgers are not equally ready:

- **Contribution events are ready as-is.** `tinyassets/contribution_events.py:40-52` already carries a generic `source_artifact_id` plus a free-text `source_artifact_kind` with no closed-set constraint, so a contribution event about a manifest needs no change to anything canonical.
- **Attribution edges are not.** `tinyassets/attribution/schema.py:33-47` constrains `parent_kind` and `child_kind` with `CHECK (… IN ('branch','node'))`, and the only writer — `tinyassets/api/market.py:898-975` — requires `parent_branch_def_id` / `child_branch_def_id` and inserts the kinds as the literal `'branch'`. A manifest-to-manifest edge is therefore **rejected by the schema**, not merely unwritten by the current call site. Asserting manifest lineage in the `data-commons` delta alone would leave canonical truth describing a substrate that cannot hold it.

So the widening is carried as a **MODIFIED delta** on `evaluation-outcomes-and-attribution`, and `data-commons` may not sync without it. The modification is deliberately the smallest one that closes the gap: it widens the endpoint kind, keeps the set **closed and enumerated** — a free-text kind column would trade a rejected edge for an unvalidated one — and changes no other semantic in the requirement.

**Consume, do not restate — and the endpoint kind is generic.** Two corrections an independent review forced, both in the same direction:

- The `data-commons` requirement originally restated idempotency, per-edge credit clamping, generation depth, and cycle rejection as its own normative text. Those are the landed owner's guarantees; restating them creates a second place they can drift. The requirement now names them as consumed unchanged and asserts only what is genuinely this lane's: that provenance resolves from those ledgers alone, that no second store exists, and that no payout is defined. Multi-parent derivation — atomic all-parent recording, aggregate credit of at most one, retry idempotency on a derivation identity, recorded rationale — is likewise not this lane's: `node-discovery-and-remix` owns that generic artifact-derivation contract, so the dataset case consumes it rather than shipping a second, weaker derivation path. That contract is a **target** on the sibling lane `claude/o5-plan-gated-targets` (`complete-plan-gated-platform-targets`), not as-built, so task 0.9 re-verifies its state before §6 is built; if it does not land, the aggregate-credit guarantee has no owner and that gap must be raised rather than quietly re-owned here.
- The widened kind is **`commons-artifact`, not `dataset-manifest`.** Scoping Rule 1's own discipline applies to substrate concepts, not just handles: a new closed-set member is a new concept, and no irreducibility finding supports a dataset-only one. A dataset manifest is one content-addressed commons artifact among others, so the set gains the class once rather than one kind per artifact type — which would make the enumerated set grow with every future artifact and re-raise the same review each time.

### D7 — **Manifest** admission must be invoked, and "invoked" has to be enforced structurally

A validation contract that a consumer *may* call is a contract that a consumer eventually will not call, and the failure is silent: the run succeeds, the capability mints, and the missing provenance is simply absent from the record.

Two properties make it structural rather than advisory. Admission happens **before** bytes, tokens, payment, or minting — after any of those, refusal is no longer available. And each gate result is **bound to the exact `manifest_hash`**, so a check against a different version does not admit, which closes the version-drift hole that a hash-free "this dataset passed" record would leave open.

**What this gate does and does not cover.** It covers manifest completeness, per-example provenance classification, and gate-result binding — all of which are structurally checkable from the record and none of which depend on a licensing position. It does **not** cover license terms: no restriction check, no rejection class, no propagation into derived records. That half was in the first draft and is removed (D11); the third structural property the draft claimed — a composed restriction set frozen into the derived artifact — went with it, because there is no authorized restriction set to freeze.

The "SHALL NOT reimplement" clause is deliberate and is the same shape as umbrella D2's rule for pure oracles: a second implementation of admission logic is a second answer to the same question, and it will differ. It now applies to *manifest* admission only — for license resolution the single implementation is the landed `paid-market-economy` lattice, and "do not reimplement" points there.

### D10 — The non-monetary half carries no pricing field, and stages no dataset market

The first draft kept `declared pricing terms` and `declared contributor shares` on the manifest as "recorded declarations — readable terms with no authority," fenced by a refusal at the money edge. That is wrong twice over, and both are the kind of wrong that only shows up when someone checks the split against the landed positions rather than against the change's own internal consistency:

- **It is not disjoint.** The two requirements retained by the umbrella are exactly the owners of those fields — *Dataset pricing is explicit and independent of compute pricing* owns pricing modes, and *Contributor settlement is frozen, exact, and auditable* explicitly freezes "contributor identities, accepted contribution weights, and payout terms **in its version manifest**." Recording the same fields here made the split overlap at precisely the seam it was drawn on. A field with no semantics is not a smaller claim than the semantics; it is the same claim staged early, where the owner cannot see it.
- **It implies a paid surface nobody authorized.** The draft's language about downstream marketplace records and a consumer "receiving rights to a dataset" describes a dataset-rights market. The landed architecture position is that the existing paid-request bid market is the **only** paid surface (`docs/design-notes/2026-04-18-full-platform-architecture.md:1355-1370`). Whether datasets get a second one is a host decision, and it has not been made.

So the fields are gone, not fenced. The reference-moving property they were bundled with survives on its own: any downstream record binds the manifest hash and the declared storage reference, which is a statement about *bytes not moving* and needs no price. The umbrella's own retained pricing requirement is itself in tension with the only-paid-surface position — that tension belongs to its owner and is raised in the Open Questions rather than silently inherited or silently fixed here.

### D11 — The license position is a host decision, not an inference (position REMOVED, not weakened)

The first draft had this capability own a curated license registry, reject no-derivatives terms at admission, and propagate `share_alike` / `non_commercial` / named redistribution restrictions irrevocably into every derived artifact. That reverses a host-pinned position, and no 2026-07-25 decision authorized the reversal:

- `full-platform-architecture.md:629` (Q16, host-pinned 2026-04-18) resolves workflow-content licensing to **CC0 1.0**, on the host's reading of "completely open" as literal — *"no restrictions, including no share-alike."*
- §19.3 adds that the schema keeps a per-node `content_license` so per-node licenses are *possible later if demand emerges*, but the system ships CC0 as the single default.
- §19.7 is explicit that the platform **does not build license enforcement**: *"Attribution via provenance is social; share-alike is legally enforceable but the platform does not police."*
- PLAN.md contains no licensing position at all (`grep -i license PLAN.md` → no matches), so the four 2026-07-25 PLAN decisions did not change it. Per-domain canonical storage, user-designed brains, open custody, and enforcement-only privacy are each orthogonal to licensing.

Inheriting the position from the umbrella's delta does not authorize it either — the umbrella is a target change, not an authority, and a moved requirement carries its defects with it. Scoping Rule 2 points the same way: *"ship the smallest primitive that closes the gap, not the policy."* A license restriction policy is policy.

There is also a duplicate-owner problem underneath, which is why the fix is not "keep it but soften it." The landed `paid-market-economy` spec already owns *Declared license terms compose fail-closed as a pure lattice* (`openspec/specs/paid-market-economy/spec.md:173-182`): the curated in-process registry, rejection of unregistered and no-derivatives inputs, and the union of restriction flags. It also draws its own boundary — it *"does not authenticate declarations or enforce them at a training-run or mint boundary."* So the landed split is: **resolution and composition are owned and landed; enforcement is deliberately unowned.** This lane owning either half would create two owners for the first and an unauthorized position for the second.

**The fold, precisely:** the restrictive-license policy is removed from normative text. A declared `license_id` stays as a declaration (which §19.4's per-node column already supports). Resolution or composition, where a consumer needs it, invokes the landed lattice — whose own rejection behavior is untouched and remains its owner's, so nothing that works today stops working. Restriction inheritance in the provenance requirement is reduced to *source* lineage: a synthetic example records every upstream source it was derived from, which is provenance and independently required, while what legal terms that derivation carries awaits the decision. The corpus-fetch node is `grant-gated` rather than `license-gated` — the grant is `boundary-layer`'s declared, user-granted, revocable connection class, which is authorized and is the property that actually needs to hold. The two questions the host must answer are in the Open Questions below, marked as host decisions and load-bearing for §3.

### D12 — Manifest immutability collides with the landed page-write contract, so it is carried as a `wiki-commons` MODIFIED delta

The draft asserted two things that cannot both be true without a delta: a manifest entry is an *ordinary* commons entry written through `write_page` with no special path, and a manifest entry can *never* be mutated in place. Landed `wiki-commons` requires a freeform write to a slug whose promoted page already exists to **overwrite that page in place** (`openspec/specs/wiki-commons/spec.md:54-65`, and its "writing an existing promoted page updates in place" scenario says so unconditionally). A content-addressed slug does not save it: a hash-shaped slug is still a slug, and nothing stops a later write from targeting it.

So immutability is a change to the existing page-write contract for this content class, and it is carried where that contract lives — a `wiki-commons` MODIFIED delta that adds an explicit **refusal** on the write path for pages whose frontmatter marks them immutable content-addressed entries, leaving every other freeform write's in-place overwrite unchanged. Refusal rather than silent versioning is the right shape: a caller who thought they were editing needs to learn they were not, and a silent redirect to a new hash would leave them believing their edit landed.

Two guardrails on the exception, because a "some pages are special" clause is exactly how a second write path gets born: it keys off the **content class** (immutable-entry frontmatter), never off caller identity or role, matching the landed rule that content class and not caller preference selects the collaboration model; and it is not a review gate — it refuses *overwrites of immutable entries*, not *new contributions*, so the anyone-writable property is untouched.

### D13 — Curation is non-blocking annotation, resolved rather than left open

The draft's manifest requirement made "curation review" part of registration while its contribution requirement promised no platform approval step, and `design.md` left "does a failed review block admission" as an open question. That is a contradiction inside one change, and an open question on the point that decides whether the commons is anyone-writable at all is not a safe place to leave it: an implementer reading the manifest requirement would build a gate.

It is resolved as **non-blocking**, and not by preference — by matching the owners. The sibling `complete-plan-gated-platform-targets` delta requires commons artifacts to take the wiki-open model: *"direct authenticated writes with compare-and-swap, no pre-publication review gate, and post-hoc moderation."* The landed architecture's moderation posture is the same shape — community-flagged, reviewed after the fact against a rubric, not proactive. So curation annotates an admitted entry, moderation is post-hoc through the existing flag/review path, and a curation concern never blocks a contribution from landing. The "declaration, not proof" property that the review step was carrying is kept directly, which is what it was there for.

### D8 — The money edge refuses rather than degrades

Umbrella D3 requires all value movement to converge on one authenticated transaction boundary. The risk here is not that this change deliberately builds a payment surface — D10 removes every pricing and contributor-share field — but that an admission path quietly writes a local balance row because the transport does not exist yet. That is how a second accounting path gets born.

So a value-moving action **refuses and names its required capability** rather than degrading to a best-effort local debit. It names the `paid-market-economy` capability rather than the change slug currently building its transport, because change names are provenance and expire on archive while the capability is the durable contract.

### D9 — Umbrella D9 binds nothing here

Per umbrella D9, the 2026-07-19 open-production-commons reframe is provenance only and non-normative in both directions. No requirement in this change is taken from it, and nothing here is designed, blocked, or reviewed *for* it. "Keep the reframe reachable" is not a constraint on this slice and is not grounds for rejecting this design.

## Dependency boundaries

| This change | Depends on | Why the edge exists |
|---|---|---|
| Contribution entries and discovery | `wiki-commons` | The page substrate, custom-category acceptance, draft-then-promote, compare-and-swap patch, and the discovery/coordination scope split are as-built; a contribution is an entry on that substrate, not a parallel object. |
| Manifest immutability on the write path | `wiki-commons` (+ MODIFIED delta) | The landed freeform-write contract overwrites an existing promoted page in place, which an immutable manifest entry cannot allow. Carried as a MODIFIED delta adding a refusal for the immutable-entry content class; every other write is unchanged. See D12. |
| Declared license identifier resolution / composition | `paid-market-economy` (landed lattice) | `openspec/specs/paid-market-economy/spec.md:173-182` already owns the curated registry and restriction-union composition as a pure helper, and explicitly does not enforce at a run or mint boundary. Consumed as the single implementation; this lane owns no registry, no policy, and no enforcement. See D11. |
| Multi-parent derivation semantics | `node-discovery-and-remix` (**target**, sibling lane `claude/o5-plan-gated-targets`) | Atomic all-parent recording, aggregate credit ≤ 1, retry idempotency on derivation identity, and recorded rationale are that capability's generic artifact-derivation contract. Consumed, never re-specified for the dataset case. Not as-built — task 0.9 re-verifies before §6 is built. |
| Commons write destination | `reconcile-universe-personification-relay` (landed by PR #1857) | The canonical `write_page` handle now accepts explicit `scope=commons|universe`, preserves authenticated commons writes, routes universe writes through the relay boundary, and fails closed on invalid or contradictory targets. This change consumes the selector and defines neither it nor a second commons write path. |
| Canonical form and durability of the entry | `build-brain-canonical-store` (unbuilt) | That owner holds the bundle write path, commit protocol, and redaction ordering. This change states which store is canonical for a manifest; it defines no durability mechanism and must not be implemented ahead of that contract. |
| Contributor and derivation provenance | `evaluation-outcomes-and-attribution` (+ MODIFIED delta) | The contribution ledger's generic artifact columns are ready as-is; the attribution edge's endpoint kinds are a closed `('branch','node')` set that rejects a commons-artifact edge, so the widening is carried as a MODIFIED delta adding a generic `commons-artifact` kind. Idempotency, clamp, depth, and cycle rejection are consumed unchanged and not restated here. See D6. |
| Outbound corpus / storage access inside a Forge graph | `outbound-boundary-layer` (unbuilt) | Manifest *movement* needs no outbound path — references move, bytes do not — but a grant-gated corpus fetch is an external read, and `boundary-layer` requires a source node to bind a declared, user-granted, revocable connection class. Grants, caps, and credential blindness stay with that owner; licensing is not the gate this lane specifies. |
| Authenticated contribution and visibility | `identity-auth-and-access-control` | The authenticated principal and the auth-scope gate are that capability's; this change adds no actor model and no second ACL. |
| Contamination, privacy, quality gate evaluation | `constraint-evaluation`, `evaluation-runtime-and-scenarios` | Gate evaluation is not redefined here; this change requires the binding of a versioned result to an exact manifest hash. |
| Contamination reference sets and Goal relatedness | `shared-goals-and-convergence` | Contamination is measured against the held-out sets the outcome-gate ladders use, so those gates retain meaning; a contribution's related Goals are read through the existing Goal records. |
| Forge graphs | `graph-execution-substrate` | A Forge graph is an ordinary compiled graph; no execution engine, node kind, or scheduler is added. |
| Any value movement | `paid-market-economy` (transport building in `paid-market-track-e-wave-2-transport`) | Umbrella D3's single money transport. This change refuses at the edge instead of consuming it. |
| Dataset pricing modes, contributor settlement | `build-forward-platform-capabilities` task 3.1 (monetary half) | Retained by the umbrella; out of scope by D1 of this change. |
| Training instruments and capability minting | `build-forward-platform-capabilities` task 3.3 | The consumer of this change's admission contract, not part of it. Landing this change does not unblock 3.3 until the contract is *built*. |

## Risks / Trade-offs

- [Risk] A validation contract that consumers may skip. → D7 puts manifest admission before bytes/tokens/payment/mint and binds every gate result to the exact `manifest_hash`; the acceptance tasks include a consumer that attempts to admit without calling it. No license restriction is frozen or enforced by this lane.
- [Risk] "Contribute to the commons" silently becomes "give us your private data". → D5 forbids automatic promotion in four named shapes, requires identical behavior under every custody mode, and states that a commons entry creates no custody claim over the private original. The adversarial task asserts that no scan, similarity match, or run-completion path publishes anything.
- [Risk] A second provenance store appears because the dataset case "needs extra fields". → D6 records onto the existing ledgers; the acceptance task asserts no dataset-specific lineage table exists and that provenance is resolvable from those ledgers alone.
- [Risk] Widening the attribution edge's endpoint kinds becomes an open door — a free-text kind column that admits anything. → The MODIFIED delta keeps the set closed and enumerated and requires an unenumerated kind to be *rejected* rather than coerced; the acceptance test asserts no coercion to `'branch'` and no untyped-identifier fallback. A free-text column would trade a rejected edge for an unvalidated one.
- [Risk] The license host decision is answered "yes, enforce," and this lane has to grow the policy back after the substrate is built. → Cheaper in that direction than the reverse. The removed material is preserved verbatim in the Open Questions below, the admission gate is already the structural place a term check would hook into, and the landed lattice is already the resolver — so a yes is an addition at a named seam. A no leaves nothing to unbuild. Building it first and being told no would mean unwinding propagation from every derived record.
- [Risk] The removed license policy is read as a safety regression — "the draft failed closed on no-derivatives and now it does not." → It was never enforcement in the first place: nothing in this lane is built, and the landed lattice that *does* reject unregistered and no-derivatives inputs is untouched, so no shipped behavior changes in either direction. What changed is which capability claims to own the question.
- [Risk] The `wiki-commons` immutability exception becomes a general "special pages" mechanism. → The delta keys the refusal off the content class only, never off caller identity or role, and states that it is not a review gate and not a new write path. The acceptance test asserts an ordinary freeform write to a non-immutable promoted page still overwrites in place.
- [Risk] The `evaluation-outcomes-and-attribution` MODIFIED delta is dropped and `data-commons` syncs alone, leaving canonical truth describing a substrate that cannot hold manifest lineage. → Task 6.6 forbids syncing one without the other, and task 0.2a re-verifies the constraint before the delta is trusted.
- [Risk] Declared pricing terms drift into spend authority. → Closed structurally rather than fenced: D10 removes the pricing and contributor-share fields from this half entirely, so there is no declaration to drift. The acceptance task asserts a manifest entry read back under this capability carries none of those fields, and the money edge still refuses and names `paid-market-economy` (D8).
- [Risk] The manifest grows into a new primitive by accretion. → D4 records the irreducibility call per behavior; a future field that cannot be expressed as frontmatter on a commons entry under the seven canonical handles is the signal to stop and record an irreducibility finding, not to add a handle.
- [Risk] This change is implemented ahead of the canonical bundle's commit protocol, so "canonical in the bundle" is asserted while the bundle has no durable write path. → Task 0.3 makes the `build-brain-canonical-store` durability contract an explicit prerequisite; until it exists, this change is implementable only against that contract.
- [Trade-off] Requiring exactly one provenance class per example rejects contributions that would otherwise register. → Deliberate. An unclassified example is one whose upstream sources cannot be recovered, and admitting it would make every downstream provenance claim unsound; the rejection happens at registration where a contributor is present, not at mint time where the artifact already exists.
- [Trade-off] Immutable manifests mean a typo mints a new version, and the write is refused rather than silently redirected. → Deliberate, and the cheaper failure both times. A mutable manifest breaks every gate result bound to its hash, and a silent redirect would leave a caller believing an edit landed where it did not.

## Migration Plan

1. Add the contribution frontmatter keys and the manifest entry shape as commons-entry conventions; no parallel store, no new category whitelist, no pricing or contributor-share field.
2. Land the `wiki-commons` immutable-entry write refusal before any manifest entry can be written, so immutability holds from the first entry rather than being retrofitted onto entries already overwritable.
3. Build the manifest-admission predicate — completeness, per-example provenance classification, gate-result binding — as pure, testable functions before wiring any call site. Build no license registry and no restriction policy (D11); where a declared identifier must be resolved, call the landed `paid-market-economy` lattice.
4. Wire the fail-closed admission gate into the run and mint boundaries so admission precedes bytes, tokens, payment, and minting; assert the refusal path before the success path.
5. Bind gate results to the exact `manifest_hash` and retain pass and fail results in provenance.
6. Record contribution and derivation onto the existing contribution ledger and attribution edges, consuming the multi-parent derivation contract rather than re-specifying it; add no lineage table.
7. Add the explicit promotion path with its four refusals and its custody-mode parity tests.
8. Seed replaceable Forge graphs as commons content; verify a user-authored fork produces an admissible manifest with no platform approval.
9. Only then run focused tests, the §14 concurrency/load matrix, canaries, rendered chatbot acceptance, and post-fix clean-use evidence.

Rollback is per step: the manifest-admission predicate is pure and revertible; the admission gate is the only step that changes existing run/mint behavior and needs a tested rollback plan; the immutable-write refusal needs its own rollback test preserving ordinary page overwrites; Forge graphs are commons content; and manifest entries are immutable, so no rollback rewrites a published entry.

## Open Questions

### HOST DECISION 1 — Is dataset content outside the CC0 default, and is license enforcement authorized? (blocks §3's license half)

**Smallest ask, two parts:**

1. **Are dataset contributions inside or outside the CC0-default position?** The landed position (`full-platform-architecture.md:629`, §19.3, host-pinned 2026-04-18) is CC0 1.0 as the single shipped default for content, chosen on the literal reading of "completely open" — *no restrictions, including no share-alike* — with a per-node `content_license` column kept only so per-node licenses become *possible* later if demand emerges. A dataset contribution is arguably a different animal from a workflow node: it may carry an upstream corpus whose terms are not ours to relicense.
2. **If datasets can carry restrictive terms, does the platform enforce them?** §19.7 currently says no: *"Does not build license enforcement. Attribution via provenance is social; share-alike is legally enforceable but the platform does not police."* Enforcement is also the half the landed `paid-market-economy` lattice deliberately does **not** own (*"does not authenticate declarations or enforce them at a training-run or mint boundary"*), so answering yes assigns a currently-unowned responsibility.

**Why it cannot be inferred:** PLAN.md holds no licensing position at all, so none of the four 2026-07-25 PLAN decisions moved it, and none of per-domain storage / user-designed brains / open custody / enforcement-only privacy touches licensing. Inheriting the position from the umbrella's delta does not authorize it — the umbrella is a target, and a moved requirement carries its defects.

**Removed material, preserved verbatim so a yes costs nothing.** This is what the first draft asserted and what §3 will restore, at the admission seam, if the answer is yes (attribution: umbrella `data-commons` delta, moved here 2026-07-25):

> This capability SHALL own the curated license registry, full-provenance manifest validation, and the restriction-union composition contract […]. Dataset and base-model license identifiers SHALL resolve against the curated registry before any consumer admits a manifest; an unknown, missing, expired, no-derivatives, or incompatible term SHALL fail validation closed, with a recorded reason and no partial admission. Composed restrictions — `share_alike`, `non_commercial`, named redistribution terms, and every other restriction in the union — SHALL propagate irrevocably to every derived artifact and SHALL be frozen into the record of any capability minted from the admitted inputs.
>
> Plus, from the provenance requirement: synthetic examples SHALL inherit every restriction of every upstream source they were derived from, and an output manifest SHALL NOT publish under terms more permissive than that inherited union.

**If yes, note the ownership consequence:** resolution and composition stay with the landed `paid-market-economy` lattice (two capabilities cannot own the registry), so this lane would own only the *enforcement* hook, carried as a MODIFIED delta transferring or extending that owner's boundary — not as a second registry.

**If no:** §3 stays as folded — declared identifier, no policy, no enforcement — and umbrella task 3.1's inherited open question ("which licenses enter the curated registry, and what counsel process approves additions?") is answered by being void rather than by being staffed.

### HOST DECISION 2 — Is there a dataset paid surface at all? (blocks the umbrella's retained monetary half, not this lane)

The landed architecture position is that the existing paid-request bid market is the **only** paid surface (`full-platform-architecture.md:1355-1370`, host directive 2026-04-18 Q4). The umbrella's two retained `data-commons` requirements — *Dataset pricing is explicit and independent of compute pricing* (three seller-chosen payment modes) and *Contributor settlement is frozen, exact, and auditable* — describe a second one. This lane no longer records pricing or contributor-share fields at all (D10), so it is not blocked; the question is raised here because the fold is what surfaced it, and because whoever builds the retained monetary half needs the answer before writing a schema. Smallest ask: **is a dataset-rights paid surface authorized as a second paid surface, or must dataset consideration ride the existing bid market?**

### Remaining (not host decisions)

- What privacy/PII scanning gate precedes public dataset use — which scanner, at what threshold, and who reviews a flagged result? (Inherited from the umbrella.)
- Should a contribution's related-Goal declaration be verified against the Goal record, or remain an unverified declaration like its source declarations? Verification is cheap here but is a different trust posture than the rest of the manifest.

*(The former "does a failed curation review block admission" question is resolved — non-blocking annotation, D13.)*
- How does a contributor withdraw a commons contribution whose private source they have revoked, given that commons entries are public-by-definition and manifests are immutable? Redaction ordering belongs to `build-brain-canonical-store`; what a *withdrawal* means for downstream artifacts frozen against the manifest does not yet have an owner.
