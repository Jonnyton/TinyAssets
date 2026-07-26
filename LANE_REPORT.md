# Lane report — data-commons successor

**Branch:** `claude/o5-data-commons` (folded in place and pushed; no PR opened)
**Base:** fast-forwarded from `8a76a93d` to `origin/main` `e78a9605` before authoring (branch had no
unique commits, so this was a clean ff, not a rewrite). Umbrella files verified unchanged between the
two.
**Mode:** spec-authoring only. No runtime code written.
**Fold validation (2026-07-25 local):** `openspec validate data-commons-contribution --strict` valid;
`openspec validate --all --strict` 43 passed, 0 failed.
**Validation:** `openspec validate --all --strict` → **43 passed, 0 failed.**

---

## Change name

**`openspec/changes/data-commons-contribution/`** — the prompt's fallback.

Umbrella tasks 3.1 and 3.2 prescribe no change *name*; they name only the **capability** `data-commons`
("no `data-commons` successor change exists"). Naming the change `data-commons` would collide with the
capability its delta targets, so the fallback was used.

On the nomination: task 3.2's text is what points at this slice — *"Forge cannot emit a manifest before
the manifest contract exists"* — i.e. 3.2 nominates **3.1's manifest/validation contract** as its
prerequisite. Task 3.3 makes training's mint invoke it, 4.4 lists it among hardware's direct edges, 5.1
inherits transitively, and the slice dependency ledger calls it *"the admission gate every downstream
training or hardware claim invokes."* Of the umbrella's unowned slices, that is the largest fan-out. The
successor therefore owns **both** 3.1's non-monetary half and 3.2 (Forge moved whole), since Forge's
intake/lineage substructure is explicitly non-monetary and would otherwise wait on a second successor.

**Why it was undecidable before 2026-07-25:** task 3.1 carried a second blocker beyond D1 — the STATUS
`host-decision` row, *"since manifest storage and private-data placement are two of the four positions
that row is waiting on."* PR #1761 landed both, as two different **kinds** of answer:
- **Manifest storage — decided.** Canonical storage is per-domain: commons bundle for commons knowledge,
  Postgres for catalog/ledger/inbox/market, neither canonical for the other's domain.
- **Private-data placement — decided to stay open.** Four custody modes, none ruled in or out; the lane
  obligation is to *name and scope* its assumption, not to encode an answer.

The manifest requirement takes the first; the promotion requirement is custody-agnostic under the second.

---

## Requirement inventory

### `specs/data-commons/spec.md` — ADDED (8 requirements)

| # | Requirement | Origin |
|---|---|---|
| 1 | Commons contribution and discovery ride the canonical page handles | New — the host's 2026-07-25 commons reframe, expressed as the contribution model |
| 2 | A dataset contribution is an immutable content-addressed manifest entry that moves references, not bytes | Moved from umbrella; extended with the #1761 per-domain canonical-form split and immutability |
| 3 | Manifest admission is a fail-closed gate consumers invoke rather than reimplement | Moved from umbrella; restrictive-license policy removed pending host decision |
| 4 | Contamination, privacy, and quality gates precede gate-backed use | Moved from umbrella; extended with pass-and-fail provenance retention |
| 5 | Every contributed example carries exactly one provenance class, and Forge is a remixable commons workflow | Moved from umbrella (task 3.2); complete source lineage, no license propagation |
| 6 | Contribution lineage rides the existing ledgers without redefining their guarantees | New — consumes the attribution and generic remix owners, records no payout |
| 7 | Promotion from private material into the commons is an explicit user act and custody-agnostic | New — Scoping Rule 4 compliance (1B) |
| 8 | The contribution half of data-commons is non-monetary and carries no pricing surface | New — no pricing/share fields and no staged dataset-rights market |

### `specs/evaluation-outcomes-and-attribution/spec.md` — MODIFIED (1 requirement)

Added **after** the first Codex review, then narrowed by the independent fold. Widens the attribution
edge's endpoint kinds to admit the generic `commons-artifact` kind; keeps the set closed and enumerated;
changes no clamp, cycle, depth, idempotency, or append-only semantics. `data-commons` may not sync without
this owner delta.

### `specs/wiki-commons/spec.md` — MODIFIED (1 requirement)

Added by the independent fold. A freeform write targeting an existing immutable content-addressed page is
refused on the write path with a mint-a-new-version instruction, while every other promoted-page write
keeps the landed in-place overwrite behavior. This is a content-class target rule, not a review gate.

### Split disposition — umbrella `data-commons` delta (6 → 4 moved, 2 retained)

**Moved (physically, not copied):** content-addressed manifests · fail-closed manifest validation ·
contamination/privacy/quality gates · Dataset Forge.
**Retained by umbrella:** dataset pricing modes · frozen contributor settlement.
**Seam:** *admission is non-monetary; consideration is monetary* — nothing downstream needs pricing or
settlement to **admit** a manifest, and this lane records none of those fields. Whether the retained
requirements may create a second paid surface is an explicit host decision, not an inference made here.

---

## Irreducibility calls (1C — no new top-level handle)

Recorded as a table in `design.md` D4. No irreducibility finding exists for anything here, so nothing ships
as a handle.

| Behavior that could read as a new tool | Call | Lands as |
|---|---|---|
| Dataset registration (`register_dataset`) | Not irreducible — a manifest is a typed entry whose only required key is `type` | `write_page` + frontmatter |
| Dataset registry / catalog surface | Not irreducible — this is what commons search + changed-since already are | `read_page`, existing default discovery scope |
| `validate_manifest` | Not a handle, but manifest completeness/provenance binding is platform enforcement | Server-side fail-closed manifest-admission gate at the run/mint boundary; no caller-facing verb |
| `validate_license` | Neither a handle nor behavior authorized in this lane; the host has not authorized a license-enforcement boundary | No implementation here; declared-identifier resolution/composition consumes `paid-market-economy` |
| Dataset Forge as a platform service | Not irreducible; the corollary applies — many plausible shapes ⇒ user-buildable ⇒ commons | Forkable commons graph via `write_graph`/`run_graph`; replaceable seed set |
| New contamination/dedup/quality evaluators | Not irreducible — gate evaluation is `constraint-evaluation`'s; dedup is ordinary node work | Existing gates + nodes; this change requires only the *binding* to an exact `manifest_hash` |
| Dataset lineage / credit graph | Not irreducible **and it already exists** | `evaluation-outcomes-and-attribution` ledgers (widened in place, not duplicated) |
| `promote_to_commons` | Not irreducible — promotion is a `write_page` of the named entry | `write_page` + existing draft-then-promote lifecycle; this change adds a *constraint*, not a mechanism |

**1B compliance:** promotion is custody-agnostic (host machine / private brain / vault / platform-held all
promote identically), never automatic (four named refusals: crawl, publish-on-run-completion, inference
from adjacency/similarity/co-location/prior-sharing, promotion on a principal's behalf), and never assumes
the platform holds the private source. The commons side is named explicitly — public-by-definition,
platform-held as commons content, exportable — while the private side is left unanswered in both directions.

**Attribution:** referenced, not rebuilt. The contribution ledger needed no change; the attribution edge
needed only a generic endpoint-domain widening, carried as a MODIFIED delta on the same table rather than
a parallel store. Generic multi-parent semantics are consumed from `node-discovery-and-remix`.

---

## Umbrella touchpoints (`build-forward-platform-capabilities`)

- **`tasks.md` 3.1** — owner assigned for the non-monetary half; monetary half recorded as still unassigned;
  both original blockers' resolution recorded; release contents listed; MODIFIED-delta note added.
  **Left unchecked** — and noted as staying unchecked even after landing, since its monetary half remains.
- **`tasks.md` 3.2** — owner assigned; Forge recorded as moved whole; downstream fan-out recorded.
  **Left unchecked** (a successor-outcome tracker completes on its successor *landing*).
- **`design.md`** — the `data-commons` ledger row split into two (contribution/admission half → successor;
  pricing+settlement half → unassigned). Records **no** transaction-owner edge on the released half with the
  D3 reconciliation stated explicitly, and a **`boundary-layer` edge scoped to Forge's corpus fetch only**
  (restored per Codex finding 3).
- **`proposal.md`** — `data-commons` New-Capabilities line narrowed; Released Capabilities entry added;
  ownership convention amended from per-**delta** to per-**requirement**, with a concurrent-amendment note
  naming `claude/o5-demand-side` / PR #1771 (which makes the same amendment from the same base — task 8.6
  carries the reconciliation for whichever lands second).
- **`specs/data-commons/spec.md`** — partial-release header added; four requirements physically removed; two
  retained.
- **Header count `19 tasks, 5 complete, 14 remaining`: unchanged** — nothing was checked (Codex confirmed
  the count is exact).

---

## Codex verdict

**`VERDICT: adapt`** — Codex (gpt-5.x, read-only, 2026-07-25, ~164k tokens), dispatched in-lane via the
stdin route (`codex exec --cd <win-path> --sandbox read-only - < ask.txt`), never argv. Six claims put up
for refutation: **3 CONFIRMED, 3 REFUTED. All three refutations applied.**

| Claim | Verdict | Disposition |
|---|---|---|
| 1 — split correctness / disjointness | CONFIRMED | No change |
| 2 — "no MODIFIED delta needed" | **REFUTED** | **Applied** — see below |
| 3 — irreducibility / no new handle | CONFIRMED | No change |
| 4 — selector consumed-not-owned | **REFUTED** | **Applied** |
| 5 — PLAN #1761 reading | CONFIRMED | No change |
| 6 — umbrella touchpoints | **REFUTED** (partial) | **Applied** |

**Finding 2 — the one that mattered.** The successor asserted manifest-to-manifest attribution while
claiming existing ledger semantics sufficed. They do not. On verification the defect is *stronger* than
Codex reported: `tinyassets/attribution/schema.py:33-47` constrains `parent_kind`/`child_kind` with
`CHECK (… IN ('branch','node'))` and `tinyassets/api/market.py:898-975` writes them as the literal
`'branch'` — so a manifest edge is **rejected by the schema**, not merely unwritten by the current call
site. Now carried as a MODIFIED delta (endpoint set widened, kept closed and enumerated; all other
guarantees restated unchanged), with a no-sync-without-both rule, a premise-verification task, and
implementation/test tasks. The *contribution ledger* needed no delta — it already carries a generic
`source_artifact_id`/`source_artifact_kind` with no closed set — so `Modified Capabilities: None` was half
right, and is now exact rather than reversed.

**Finding 4.** Selector ownership was misattributed. `reconcile-universe-personification-relay` 6.1/6.7 own
the person-dossier anti-collision **restriction** on the commons write path — which presumes the path
rather than delivering it — and neither task's write-set claims the routing. Ownership is now recorded as
**UNRESOLVED**, with task 0.5 to establish it before §1 is built. The claim is re-anchored to code on
`main` (`tinyassets/universe_server.py:771-793`: an authenticated freeform write with omitted `universe_id`
resolves to the caller's home and returns `relay_to_universe`, so only `kind=` filings reach the commons)
rather than to `docs/audits/2026-07-22-write-page-commons-residual.md`, which lives only on the unmerged
branch `claude/write-page-commons-residual` and is itself partly stale — it found two `write_page`
definitions where `main` now has one.

**Finding 6.** Dropping the `boundary-layer` edge was unsound: Forge includes a grant-gated corpus fetch,
and `boundary-layer` requires a source node to bind a declared, user-granted, revocable connection class.
Restored, scoped to external corpus/storage access only (manifest movement still transfers references, not
bytes), with a task forbidding a local fetcher that bypasses grant binding. Codex separately **confirmed**
that no transaction-owner edge is needed and the header count is unchanged; since umbrella D3 names `data`
among transaction consumers, the ledger row now states explicitly that the consumption is the *retained*
pricing/settlement half.

Re-validated after applying: `openspec validate --all --strict` → 43 passed, 0 failed.

**Not done (out of scope, by instruction):** no PR opened; no runtime code; nothing synced to
`openspec/specs/`; local review scratch files were not included in the fold commit.

## Independent Codex fold — six findings

The second independent review returned `adapt`. The fold disposition is explicit per finding:

1. **Unauthorized restrictive-license position — OPEN QUESTION / host decision.** Removed the curated
   registry ownership, no-derivatives rejection, restriction propagation, and license enforcement from
   normative behavior. `design.md` now asks whether dataset content is outside the pinned CC0 default and,
   if so, whether platform license enforcement is authorized. The lane does not answer either question.
2. **Duplicate license-lattice owner — CONSUME LANDED OWNER.** `paid-market-economy` remains the single
   owner of declared-identifier resolution and restriction composition. This lane owns only manifest
   admission and carries no ownership-transfer delta or second registry.
3. **Paid-surface leak — FIELDS REMOVED + OPEN QUESTION.** Removed pricing terms and contributor-share
   fields from the manifest, tasks, and acceptance scenarios; removed dataset-market language. Whether a
   dataset-rights paid surface is authorized is a host decision for the umbrella's retained monetary half,
   not behavior staged by this lane.
4. **Wiki overwrite collision — MODIFIED OWNER DELTA.** Added
   `specs/wiki-commons/spec.md`: a freeform write to an existing immutable content-addressed entry refuses
   on the write path and leaves body/frontmatter/index unchanged; ordinary promoted pages still overwrite.
5. **Admission/curation contradiction — RESOLVED TO NON-BLOCKING ANNOTATION.** Curation and moderation are
   post-hoc annotations on already-admitted entries. Authenticated commons writes have no pre-publication
   review gate, matching the sibling collaboration contract.
6. **Derivation overlap / dataset-specific kind — CONSUME OWNERS + MINIMAL MODIFIED DELTA.**
   `data-commons` consumes the landed attribution guarantees and the generic N-parent
   `node-discovery-and-remix` contract. The attribution-owner delta now adds only the generic
   `commons-artifact` endpoint domain; no dataset-specific primitive or second derivation contract remains.

Strict revalidation after the complete fold: the named change is valid and the all-spec run reports
43 passed, 0 failed. The fold is spec-only; no task was checked, no as-built spec was synced, and no PR was
opened.

LANE_RESULT: done - folded all 6 independent-review findings into the spec artifacts and per-finding lane report; strict validation passes and the branch is pushed without a PR.
