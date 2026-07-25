# Lane report — complete-plan-gated-platform-targets

**Branch:** `claude/o5-plan-gated-targets` (base `origin/main` 8a76a93d) · pushed, **no PR opened**
**Commits:** `df05220b` — `spec: PLAN-gated full-platform targets (catalog/discovery/presence/portability)`; then the Codex-`adapt` fold commit at this branch's head (§ *Codex verdict + fold*).
**Scope:** spec-authoring only. No runtime code touched.
**Change dir:** `openspec/changes/complete-plan-gated-platform-targets/` (did not exist; created)
**Validation (post-fold):** `openspec validate complete-plan-gated-platform-targets --strict` passes; full tree `openspec validate --all --strict` = **42 passed, 0 failed**. Task count 9/58 (matches `openspec list`).

## Change name

`complete-plan-gated-platform-targets` — five new target-only capabilities.

The three groups the 2026-07-22 full-coverage audit left unowned were all blocked on the same four PLAN positions, which landed on `origin/main` 2026-07-25 via the brain-OKF foldback (#1761). Verified at authoring time (tasks.md 1.1): **1A** = *Design Decisions* per-domain canonical store + user-designed brain organization; **1B** = Scoping Rule 4 custody reopened as open research; **1C** = Scoping Rule 1 irreducibility finding; **1D** = Scoping Rule 3 guidance-vs-enforcement.

Fenced against the two sibling target changes — `complete-independent-full-platform-targets` (moderation, tray, node authoring, handoffs) and `build-forward-platform-capabilities` (boundary, data, demand, hardware, training, pool, token). Neither claims these four groups. No file overlap: this lane writes only its own change dir.

## Target group → requirement inventory

36 requirements across five new capabilities, all `## ADDED` (35 at first authoring; the custody-manifest requirement was added in the fold), plus **one target-only `## MODIFIED`** requirement against the shipped `wiki-commons` typed-filing contract (fold finding 5).

### catalog/collaboration → `collaborative-catalog-and-editing` (7)

1. Catalog is Postgres-canonical and **indexes** commons knowledge without duplicating it — bundle wins on divergence; index is rebuildable; brain organizations are catalog *subjects*, not schema.
2. Collaborative writes are compare-and-swap on a monotonic version; stale writes refused with current version + change description, never merged.
3. Every write appends an immutable revision; revert is recorded **forward** as a new revision.
4. Two collaboration models bind to **content class** and the boundary is enforced — commons-path write to platform code is refused with the fork-and-PR path named.
5. External export is a derived one-way projection; round-trip import re-enters the ordinary authenticated write path with no CAS/authority/visibility/moderation bypass and cannot resurrect withheld content.
6. Catalog projections enforce visibility **including on derived fields and counts**; authority from the authenticated subject, no env fallback.
7. Everything composes under the canonical handle set; invariant test asserts the advertised set is unchanged.

### discovery/remix → `node-discovery-and-remix` (7)

1. One-call composite signal block; uncomputable signals reported **absent**, never defaulted to a value that reads as evidence.
2. Ranking delegated to a user-buildable selector reusing the shipped DESIGN-008 contract — bind-time purity rejection, seeded default, unbind falls back rather than failing.
3. Discovery never reveals unreadable content, **including through derived blocks**; no leakage via rank gaps, totals, pagination, or timing; lineage through a restricted ancestor truncates at an opaque boundary.
4. Commons content ranks equal first-class; no platform-origin weighting outside the selector; cross-domain matches labelled, not filtered.
5. Remix-from-N records every parent edge and credit **atomically**, and **introduces** aggregate credit enforcement (≤ 1.0 across all contributors, checked transactionally) — corrected in the fold: the store enforces only the per-row `[0,1]` range, so this is new enforcement, not a preserved invariant. Cycle rejection and idempotent retry.
6. Convergence is propose-then-ratify with authenticated append-only ratifications, proposer recusal, supersede-not-delete, walkable superseded lineage; policy values are remixable, enforcement properties are not configurable away.
7. Standing similarity interest is a durable owner-bound stored query read back through the ordinary read path; matches survive disconnection; cost scales in outstanding queries, not queries×changes.

### presence → `realtime-collaboration-presence` (6)

1. Presence is advisory and **never a write authority** — CAS is the sole conflict authority (a held record can't block; a lost record can't relax).
2. Presence expires on heartbeat, scoped per artifact, no explicit release required, no inheritance.
3. Versioned-row broadcast, **not** convergent replication; per-artifact CRDT escalation needs its own change.
4. Presence and streams enforce read-visibility at **delivery time**; unauthorized subscription is indistinguishable from subscribing to a nonexistent artifact; revocation stops delivery without client action.
5. Realtime is degradable — every collaborative operation completes with the transport fully down; reconnection is loss-free and duplicate-free.
6. Fan-out bounded by subscription, not global change volume; load sheds delivery, never commit latency or success; §14 proof obligation.

### portability/deletion/succession/feedback → `data-portability-and-deletion` (9) + `platform-succession-and-feedback` (7)

Portability/deletion: **the manifest itself is custody-mode-scoped** — platform records plus a holder registration (not an inventory), assembled at request time with per-mode coverage stated, resolution defined for all four modes, and a post-deletion receipt that resolves through a self-contained document plus a bearer capability rather than the erased identity (added in the fold) · custody mode recorded per item with unknown-fails-safe · export enumerates everything with **enclose-or-descriptor** + explicit completeness statement + partial labelling · every offered custody mode must satisfy the export contract or is non-conforming · unreachable holder yields a **graceful resumable deferral** distinguishable from permanent failure · no cross-principal private content, no elevated-role reach · deletion erases platform-held directly **and issues a verifiable obligation** elsewhere with confirmed/unconfirmed reporting · wiki-orphan survival with no cascade · identity detachment is **resolution-time suppression over append-only ledgers**, not a rewrite · initiator-bound expiring confirmation with pre-confirmation disclosure.

Succession/feedback: machine-checkable successor roster (reports, does not block) · **succession grants no content access in any custody mode** · phase-split executable bus-factor gates, real-value conditions unsatisfiable by a simulated participant · staleness-detectable runbook incl. redeploy-from-nothing · typed authenticated filing **extending the `wiki-commons` contract** with per-invocation attribution presentation and retained abuse binding · publish-authorization enforced with **named refusal, not silent stripping**, scoped to structured/derived elements with prose under explicit publication confirmation, guidance seeded as remixable commons · **the external tracker stays the canonical queue** (architecture §23.1) and the platform-side filing is a durable staging record projected into it by a receipted idempotent outbound effect.

## Irreducibility calls (1C) — **zero new handles, zero new primitives**

Recorded in `design.md` § D2 for all eleven standalone RPCs the architecture named across §§15/16/21/22/23:

| Behavior | Named as | Call | Lands as |
|---|---|---|---|
| Node discovery | `discover_nodes` | not irreducible | `read_graph` action |
| Standing similarity | `subscribe_similar_in_progress` | not irreducible | stored query via `write_graph`, read via `read_graph`; realtime push is a web transport, not a handle |
| Remix from N | `remix_node` | **already expressible** | `write_graph` action; gap is atomicity |
| Convergence propose | `propose_convergence` | not irreducible | `write_graph` action |
| Convergence ratify | `ratify_convergence` | not as a handle; authority boundary is enforcement, policy is commons | `write_graph` + seeded policy |
| Node update | `update_node` | not irreducible | `write_graph` over CAS/revision |
| Comment | `comment` | not irreducible | existing unified-notes substrate |
| Export | `export_my_data` | not irreducible | `read_graph` action |
| Deletion | `delete_account` | not irreducible | `write_graph` action |
| Delete confirmation | `request_delete_confirmation` | not irreducible | `write_graph` action |
| Feedback | `/feedback` | not irreducible | `write_page` typed filing |

**The load-bearing call is remix-from-N**, the strongest new-primitive candidate in the source material. It fails the irreducibility test on *verifiable* grounds rather than judgment: `tinyassets/attribution/schema.py:47` keys `attribution_edge` on `UNIQUE (parent_id, child_id)`, so one child already carries N parent edges — set-valued parentage is shipped substrate. What is actually missing is **two** things: atomicity of the N-edge write, and **new aggregate credit enforcement**. (Corrected in the fold — the first draft of this report called the aggregate bound an existing invariant. It is not: `attribution_credit` enforces `CHECK (credit_share >= 0.0 AND credit_share <= 1.0)` per row and `UNIQUE (artifact_id, actor_id)`, `api/market.py:922` clamps only the individual share, and the aggregate sum is enforced nowhere — it lives in a schema-module design comment and the advisory `RemixProvenance.is_credit_valid`.) Both became requirement 5 of `node-discovery-and-remix`, not a primitive; the no-new-handle result is unchanged.

Self-verified independently: `CANONICAL_HANDLES` in `scripts/mcp_public_canary.py:72` matches the seven; `wiki-commons` § *Typed filings bypass the draft gate with per-kind IDs and dedup* confirms the feedback composition target exists.

## Open questions surfaced

Seven, in `design.md` § *Open Questions* — recorded, not answered (the seventh added in the fold):

1. **(1B)** What evidence upgrades a non-platform deletion from unconfirmed to confirmed (holder attestation? vault-key destruction? nothing verifiable for host-machine custody?), and which custody modes must reach conformance before launch.
2. **(1B + legal)** Is resolution-time identity suppression sufficient for right-to-be-forgotten over append-only ledgers, or is cryptographic erasure required? Jurisdictional; needs the specialist legal review already tracked.
3. **Deletion × convergence** — when a required ratifier's identity is detached by deletion, does the proposal stall, auto-recuse the seat, or fall to quorum? Changes whether ratification is per-identity or per-owner-set. Neither 1B nor 1C settles it.
4. **Repository topology** — is the commons-bundle git snapshot the same repo as the catalog export sink, or two (§16.4 proposed two)? 1A settles canonicity per domain, not repo shape.
5. **Governance of widely-inherited commons seeds** — 1D blesses seeding a remixable default but not who maintains the default discovery selector / convergence policy, nor what review applies to changing a seed users inherit by not choosing.
6. **Named succession principals** — roster holders, real-value-cutover human co-signer, registrar successor. Host/founder action; tasks.md 6.4.
7. **(Host decision, added in the fold)** Should the commons filing ever replace the external tracker as the canonical feedback queue? The landed §23.1 position is specified; the reversal is not adopted and may not be adopted by an implementing lane without this decision. Smallest ask: *keep GitHub canonical, or authorize the commons as canonical with GitHub as the mirror?*

Two things that *looked* like open questions but were resolvable from landed/shipped positions, so they were reconciled in `design.md` rather than filed as open: the realtime substrate (PLAN's architecture reference already fixes versioned-rows as a durable commitment), and §23.7's "anonymous users file feedback equally" against the shipped authenticated-write boundary (D8 — MCP path stays authenticated with pseudonymous *presentation*; genuinely unauthenticated feedback enters via external channels marked lower-trust, so the write boundary is not weakened). The fold added a third: §23.1's canonical-queue position, which the draft had *reversed* rather than reconciled — now specified as landed (D8a), with the reversal itself demoted to open question 7.

## Notes

- **STATUS.md not edited.** The row is `pending` on `origin/main`. This branch is pushed without a PR, so a claim edit here would never land and would only add conflict surface on the fleet's hottest file. The row should flip when this lands.
- **Target-only guard is explicit** in `tasks.md`: `openspec archive` syncs deltas into `openspec/specs/` as a side effect, and that tree is as-built truth — archiving while unbuilt would write five fictional capabilities into canonical truth. Terminal task 7.4 records that zero of five has any implementation on `origin/main`.
- **One MODIFIED delta**, added in the fold: the `wiki-commons` typed-filing contract, so feedback intake has a single owner instead of two (finding 5). The other adjacencies (`shared-goals-and-convergence` exact-identifier common-node discovery, `wiki-commons` hash-guarded deletion, `evaluation-outcomes-and-attribution` append-only ledgers, `knowledge-retrieval-and-memory` OKF bundle export, and `data-commons` dataset manifests/licensing per finding 9) are named as boundaries in `design.md` and specified as *additive*; if an implementing lane must change one, it authors the MODIFIED delta then.
- **Live defect class folded in:** the STATUS P1 concern that branch get/describe leaks restricted wiki path/title/summary via `_related_wiki_pages` is the same derived-block-escapes-the-predicate shape discovery would have at much larger scale. Requirement 3 of `node-discovery-and-remix` and task 3.3 are written against it directly, with negative tests as part of the requirement rather than follow-up hardening.

## Codex verdict + fold

Dispatched in-lane via `codex exec --cd <win-path> - < .codex_review_prompt.txt` (stdin, not argv). Adversarial framing: refute five claims — 1C zero-new-handles, the `attribution_edge` irreducibility evidence, 1B custody-agnosticism, no as-built contamination, no invented positions — plus a vacuous-requirement sweep.

**Verdict: `adapt`** (2026-07-25) — *"structurally sound and strict-valid, but it needs normative handle coverage, custody-manifest closure, feedback ownership reconciliation, and corrected review/task evidence before merge."* Nine findings; seven substantive, one clean pass (#8 target-only/as-built), one no-collision note with a small addition (#9). **All nine folded.** No finding was rejected.

### Per-finding disposition

**1 — Unauthorized position reversal (feedback canonicity). FOLDED, position restored.**
Confirmed against the source: architecture §23.1 says GitHub Issues is the canonical public bug/feature-request surface, §23.2's `/feedback` opens an Issue, and external channels route in — *"GitHub remains the canonical queue."* None of the four 2026-07-25 PLAN decisions touches feedback-record ownership. The draft requirement *"The commons filing SHALL remain the canonical record"* was a reversal this lane had no authority to make.
Fix: requirement renamed and rewritten — the external tracker **stays** canonical; the platform-side filing is a **durable staging and provenance record** projected into the canonical queue as an idempotent receipted effect, reported as *pending projection* rather than *queued* until projection succeeds. That preserves the property the draft was reaching for (a projection failure must not lose the report) without moving canonicity to get it. New `design.md` § D8a records the reversal and why it was withdrawn; **open question 7** files the reversal as a host decision with the smallest concrete ask, and the requirement forbids an implementing lane adopting it without one. Task 6.8 rewritten with the same warning.

**2 — Zero-new-handle conclusion not normative across the change. FOLDED.**
Correct: the only suite-wide-looking SHALL was scoped to *"every catalog and collaboration behavior in this capability."*
Fix: the catalog requirement is rewritten as **one cross-capability normative invariant** — *"Every behavior in this change and its successors routes under the canonical handle set"* — that names all five capabilities, asserts `tools/list` stays exactly the seven (`read_graph`, `write_graph`, `run_graph`, `read_page`, `write_page`, `converse`, `get_status`), fixes the per-behavior routing as a normative list, and is inherited unchanged by every successor split. Each of the eight behaviors Codex enumerated — discovery, remix, convergence, presence, export, deletion, confirmation, succession — additionally carries its own no-new-handle condition plus a scenario, so a successor split that takes one capability cannot drop the invariant. Separately, the Realtime subscription/heartbeat/broadcast path is now **named** as the already-approved non-MCP web transport in both the realtime spec and the invariant, so "under the seven handles or the commons" is not quietly resting on an unnamed fourth transport. Task 2.7 requires the invariant test to cover the change's behaviors as a set.

**3 — Remix evidence overstated the shipped credit invariant. FOLDED, correction accepted.**
Verified independently: `attribution_credit` has `CHECK (credit_share >= 0.0 AND credit_share <= 1.0)` per row and `UNIQUE (artifact_id, actor_id)`; `tinyassets/api/market.py:922` clamps only the individual share; the aggregate sum is enforced **nowhere** — it exists as a design comment in `attribution/schema.py` and the advisory `RemixProvenance.is_credit_valid` helper (`schema.py:202-209`) that no write path must call.
Fix: requirement, D2, task 1.4, task 3.6, and this report now say the gap is **atomic N-edge writing AND new aggregate enforcement**. The requirement adds a scenario asserting the aggregate refusal comes from a check introduced by this capability, and tells an implementing lane to specify treatment of pre-existing violating rows rather than assuming there are none. No-new-handle result unchanged, as Codex noted.

**4 — Custody of the custody manifest unresolved (1B not closed). FOLDED.**
Fix: new requirement *"The custody manifest is itself custody-mode-scoped and the platform is not assumed to own the inventory."* The platform holds its own items plus a **holder registration** (identity, mode, reachability, last-enumeration time) per non-platform holder — explicitly **not** an inventory of contents. Manifests are assembled at request time as the union of platform records and each reachable holder's own enumeration, each entry attributed to its asserting holder, with coverage stated per mode (answered / deferred / unenumerable); every "every owned item" guarantee now reads as scoped to that union plus its coverage statement. Enumeration resolution is defined for all four modes (platform-held direct; brain under owner auth; vault under owner key authority, unenumerable by the platform without it; host when online, deferred when not), and a mode with no defined resolution may not be offered. The post-deletion path no longer depends on the erased identity: a **self-contained receipt document** readable with no platform call, plus a **bearer capability** whose server-side record holds only item/holder references and obligation state. New tasks 5.2 and 5.8; D3 extended.

**5 — Feedback filing duplicates the landed `wiki-commons` typed-filing contract. FOLDED (option A).**
Chose the MODIFIED-delta path over a parallel action, because feedback *is* a typed filing (D2 already routed it there) and forking would duplicate identifier allocation and dedup.
Fix: new **target-only MODIFIED delta** at `specs/wiki-commons/spec.md` extending *"Typed filings bypass the draft gate with per-kind IDs and dedup"* — as-built paragraph and its three scenarios reproduced verbatim (MODIFIED replaces wholesale on sync), then the extension: feedback-only categories get their own prefixes/counters, bug and feature-request feedback reuses the existing BUG/FEAT counters and the same 0.5-threshold duplicate check, `attribute_as` is presentation-only and outside filing identity, `component`/`severity` become optional **for feedback kinds only**. The succession/feedback requirement now names `wiki-commons` as sole owner of filing identity and dedup. `design.md` § D9, proposal *Modified Capabilities*, and the tasks guard updated; the delta is unsyncable like everything else here.

**6 — Two non-checkable acceptance statements. FOLDED, both scoped.**
(a) Free-text body: the hard boundary is now scoped to **structured and platform-derived elements** — references, attachments, derived context/summaries — where a read predicate can resolve the referent. Caller prose goes through an **explicit publication confirmation** plus post-hoc moderation, and the platform explicitly does not claim to have checked it (content classification is what 1D leaves to guidance). Task 6.7 rewritten.
(b) Timing: the absolute "no inference through timing" prohibition becomes a stated **noninterference bound with an executable test model** — one fixed query against two corpora differing only by one restricted artifact, documented sample size/statistic/threshold, violation treated as a defect — plus a constraint that suppression work must not scale observably with suppressed-candidate count. New task 3.4. The other seven leak channels stay absolute, because they are directly enumerable.

**7 — Task 7.1 false completion evidence. FOLDED.**
Unchecked, gate reworded from *"before pushing"* to *"before PR/merge"*, and re-checked only in this fold commit with accurate evidence: strict validation, the `adapt` verdict, and the per-finding disposition below it. It explicitly **does not** claim the folded text was re-reviewed — that is new task 7.2, open. Section 7 renumbered accordingly (terminal sync/archive guard is now 7.5).

**8 — Target-only/as-built claim passes. NO CHANGE NEEDED, re-verified after the fold.**
`git diff` touches nothing under `openspec/specs/`; the new `wiki-commons` delta lives inside the change dir and the sync/archive guard was extended to cover it explicitly (syncing it early would overwrite a live requirement with a partly-unbuilt one).

**9 — No collision with `demand-side` / `data-commons`. FOLDED (the addition).**
`data-commons` added as an explicit **read/boundary dependency**: in the export requirement (dataset assets carry that capability's own manifest reference and retrieval descriptor; licensing, pricing, gating, and contributor provenance are not restated), in `design.md` § Boundaries, in task 5.2, in the proposal's Impact dependencies, and in the successor-split task 7.3 — a portability successor including dataset assets must name it. No delta move, as Codex said.

### Post-fold validation

- `openspec validate complete-plan-gated-platform-targets --strict` → **valid**.
- `openspec validate --all --strict` → **42 passed, 0 failed** (unchanged; the new `wiki-commons` delta validates inside the change).
- `openspec list` → **9/58 tasks** (was 9/54: +1 timing-acceptance, +2 custody-manifest/post-deletion-receipt, +1 confirming-review pass; the 9 complete are section 1's eight plus 7.1).
- Diff scope: 10 files, all inside the change dir plus this report. `git diff --stat -- openspec/specs` is empty.

**Not claimed:** the folded text is unreviewed. Task 7.2 holds the confirming opposite-provider pass as a pre-PR/merge gate — not dispatched in this turn because the host scoped it to fold-and-push with no PR, so the gate is not yet live.

LANE_RESULT: done - all 7 substantive Codex findings folded (position reversal withdrawn + filed as host decision, cross-capability handle invariant, corrected credit evidence, custody-manifest closure, single-owner filing delta, two scoped acceptance methods, task-truth fix) plus finding 9's data-commons dependency; strict-valid, 42/42 tree, no as-built contamination, committed and pushed.
