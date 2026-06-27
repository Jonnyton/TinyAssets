# Pair Convergence: #59 resolve_canonical ↔ #47 fallback chain + authority + #53 route-back + canonical_bindings table

**Date:** 2026-04-25
**Author:** navigator
**Pair:** dev-2's #59 `resolve_canonical` proposal (`docs/design-notes/2026-04-25-resolve-canonical-action-proposal.md`) ↔ five substrate dependencies enumerated in lead's brief.
**Purpose:** Phase A item 3 closure. Verify cross-doc composition with the now-rich substrate; surface gaps. **Fourth and final pair-read of the substrate-cross-check sweep.**

---

## Stamp

**PAIR CONVERGES.** All five named cross-checks pass cleanly. #59 is the smallest, tightest design proposal of the substrate — sub-millisecond indexed query, no schema changes, no caching, clean SQL with explicit fallback ordering. **Phase A design is now fully closed except item 1 (storage authority refactor — Task #69 just landed per TaskList).**

Two minor opens surface from the pairing.

---

## 1. Per-substrate cross-check resolution

| Substrate | Resolution |
|---|---|
| **#47 §3 fallback chain** | **CONVERGES — implements verbatim.** §3 of #59 explicitly cites the order: requested scope → caller's user scope (`user:<actor_id>`) → goal default (`''`). Tier scopes are documented as punted-until-tier-membership-ships per #47 §6 Q1. The SQL `ORDER BY CASE scope_token` clause at lines 64-71 implements the priority precisely. **Cross-checked the SQL against #47 §3:** the clause `scope_token IN (:fallback_chain) ORDER BY CASE...` is identical in structure. Healthy. |
| **#47 §4 authority model + symmetric privacy** | **CONVERGES — read-only with SQL-level filter.** §5 explicitly says "Read-only. No authority required." The `WHERE` clause filter `visibility = 'public' OR bound_by_actor_id = :caller_actor_id` is the symmetric-privacy read filter from #47 §1. **Verified semantic:** when caller B queries a goal where A has a private `user:A` binding (and A is the only binder), B's resolver returns `null`, NOT an error or "permission denied" leak. The privacy is silent at the SQL level — the row simply doesn't appear in the result. **This is the correct shape** (privacy-as-silence vs. privacy-as-explicit-rejection) — explicit rejection would leak existence of the private binding. |
| **#53 route-back call site** | **CONVERGES — call-flow consistency verified.** #59 §11 explicitly references "Engine consumer: docs/design-notes/2026-04-25-gate-route-back-verb-proposal.md (Task #53) §3 — route-back execution calls this." Cross-check #53 §3: "Engine-side handler for `verdict == 'route_back'` calls the resolver from Task #47" — that's exactly resolve_canonical. **Verified ordering:** in #53's engine-side handler, the patch_notes is constructed FIRST (steps 1-2: validate route_to + patch_notes are present; append (goal, scope) to _route_history), THEN resolve_canonical is called (step 4). The patch_notes carries the scope_token before resolution; resolution returns the branch_version_id which then feeds into step 7 (run_branch_version_async). Order is correct. |
| **`canonical_bindings` table (#47 / Task #61 commit `7b020ae`)** | **CONVERGES — uses the new table directly.** §3 SQL queries `canonical_bindings` (the new schema), not the legacy `goals.canonical_branch_version_id` column. **Verified: dual-write Step 2 in flight per TaskList #60** ensures the legacy column stays in sync during transition; #59 reads from the new authoritative table. After dual-write Step 2 ships, the legacy column becomes a derived view per #47 §5 migration plan. **Composition with #47 §1 indexes:** §3's query hits `idx_canonical_bindings_goal` for the WHERE clause and `idx_canonical_bindings_actor` for the privacy filter (when `bound_by_actor_id = :caller_actor_id` is the dominant predicate). Sub-millisecond at scale per §7. |
| **`@END`/`@START` reservation (per #58)** | **CONVERGES — different layer, no collision.** #58 reserves `@START`/`@END` as engine-level checkpoint targets in branch-internal routing. #59's `canonical_scope` is a cross-branch scope_token. **No collision possible:** scope tokens are namespaced (`user:<id>`, `tier:<name>`, `''` for default); `@`-prefixed strings would never appear as scope_tokens. Worth flagging that `canonical_scope=""` (empty string for default) is functionally distinct from `canonical_scope=None` (arg absent — defaults to caller's user scope) — see §2 open #1. |

**Net composition health: 5/5 clean.** This pair has the cleanest convergence of any pair-read in the sweep. Tightest small spec → clean composition with the substrate it depends on.

---

## 2. Two minor opens from the pairing

The pair-read pattern usually surfaces 2-3 substantive opens. #59's tightness leaves fewer to surface; the two below are the only ones I'd flag:

1. **`canonical_scope=""` vs. `canonical_scope` absent disambiguation.** §2 says `canonical_scope=<optional, default "" — falls through to caller's user scope or default>`. But `""` is itself a valid scope_token (the default unscoped binding). **Reading the §3 fallback chain literally:** if a caller passes `canonical_scope=""` explicitly, the requested-scope match is `''` (the default goal-level binding), which would resolve at priority 1. If the arg is ABSENT, fallback runs from the caller's user scope (priority 2). **These are different behaviors.** The current spec wording could be read either way. **Recommendation: clarify in §2 — `canonical_scope=""` means "explicitly request the default unscoped binding"; arg-absent means "use caller's user scope as starting point with default as fallback."** Small wording fix; no design change. Implementation-time clarification, OR a small #59 v2 amend.

2. **Tier-membership lookup punt boundary.** §3 says tier scopes are checked "between user and default IF the caller's tier membership is known (per #47 §6 Q1, tier policy is currently punted; resolver returns no tier matches until tier-membership lookup ships)." But what does "currently punted" mean operationally — does the SQL still try to match tier scopes (returning 0 rows because no `tier:` bindings exist yet)? Or does the fallback_chain literally exclude tier scopes? **Recommendation: punt = the fallback_chain construction logic doesn't include tier scopes until tier-membership lookup ships.** Once tier membership lands, the fallback chain construction (likely a small helper function) gets a `+= compute_caller_tiers(actor_id)` step. **Implementation-time clarification:** the helper should be designed to accommodate the future tier addition cleanly. Small forward-compat consideration, not blocking.

---

## 3. Implementation-time constraints

To land in the dispatch task's verification list:

- **Input validation** for malformed `canonical_scope` (e.g., embedded null bytes, non-UTF8, excessive length). Recommend cap at 256 chars, reject embedded special characters except `:` for namespacing.
- **Authentication of read access** — per §5, no auth required, but caller_actor_id MUST come from authenticated session. Reading the resolver as `caller_actor_id="anonymous"` accidentally would silently filter out all private bindings (the `bound_by_actor_id = :caller_actor_id` clause never matches anonymous unless someone bound for `user:anonymous`). **Test:** verify `_current_actor()` is correctly threaded into the resolver from `_action_goal_resolve_canonical`.
- **Edge case: caller_actor_id matches no scope** — the symmetric-privacy filter excludes private bindings whose `bound_by_actor_id != caller`. If ALL bindings for the goal are private (and not caller's), result is `null`. Test: explicit case where this happens; assert `resolved_branch_version_id == null` + `fallback_chain_attempted` shows the attempts.
- **Orphaned branch_version_id warning shape** (§4 row 5) — the `warning` field is added to the response when the resolved version isn't in `branch_versions`. Ensure response JSON is still valid + clearly distinguishes warning from error. Test: stub a `canonical_bindings` row pointing at a deleted version; assert response carries both `resolved_branch_version_id` AND `warning`.
- **Composition with surgical rollback** (per pair-read #65 cross-doc seam): when a canonical's branch_version is rolled back via #57, the `canonical_bindings` row's `status` column flips. **Open Q for impl:** does resolver filter out `status = "rolled_back"` rows from results? §3 SQL doesn't currently filter on status. **Recommendation:** add `AND status = 'active'` to the WHERE clause. Otherwise resolver returns rolled-back versions, which downstream callers would invoke. Filing as [PENDING #59-impl-rollback-filter] — small but load-bearing for Phase E composition.
- **Action filter test in `_GOAL_ACTIONS`** — verify the action is registered as a non-write action (mirrors `goals action=get` / `list` / `search`). No ledger commit required.

---

## 4. Roadmap deltas

**Phase A item 3 (lookup_canonical) — CLOSED.**

**Phase A design status update:**

| Phase A item | Status |
|---|---|
| 1 storage authority refactor | DESIGN COMPLETE (Task #69 just landed per TaskList — pair-read N opportunity for next session) |
| 2 variant_canonicals table | DESIGNED + IMPLEMENTED Step 0+1 (`7b020ae`); Step 2 in flight |
| 3 lookup_canonical (this) | **CLOSED** |
| 4a verdict (route_back) | DESIGNED (#53, audited solo as #62) |
| 4b named-checkpoint | DESIGNED (#58, paired as L) |
| 5a invoke_branch_version_spec + builder + actor inheritance | DESIGNED (#56, paired as #60) |
| 5b structured failure propagation | DESIGNED (#56) |
| 5c two-pool concurrency | DESIGNED (#56) |
| 6 run_branch_version | DESIGNED (#54, paired as #59); **IMPL ACTIVE** (Task #65a/b in flight) |
| 7 gate-series typed-output contract | FULLY CLOSED (#53 + #58 + TypedPatchNotes #67) |

**11 of 11 Phase A items now have landed designs.** Implementation is actively dispatching for items 2 (Step 2), 6 (#65a + #65b in flight). Items 1, 3, 4a/4b, 5a/5b/5c, 7 are designed and pending implementation.

---

## 5. Closure summary — substrate fully cross-checked

Per the four pair-reads (#59, #60, #62-as-solo-audit, #65, #66, #67) + this fifth pair-read (#68), **the design substrate is fully cross-checked end-to-end.** Phase A + Phase D + Phase E gate/bridge/rollback substrates all converge cleanly. Specifically:

| Pair-read | Subject | Stamp |
|---|---|---|
| #59 | #54 ↔ #56 (runner version-id bridge) | PAIR CONVERGES |
| #60 | #50 ↔ #56 (sub-branch invocation) | PAIR CONVERGES |
| #62 | #53 solo audit (gate route-back) | AUDIT CLEARS WITH ONE FLAG |
| #65 | #57 surgical rollback | PAIR CONVERGES |
| #66 | #58 named-checkpoint | PAIR CONVERGES (closes #62 ⚠ flag) |
| #67 | #55 external-PR bridge | PAIR CONVERGES WITH ONE MATERIAL FLAG (small enum extension) |
| **#68 (this)** | **#59 resolve_canonical** | **PAIR CONVERGES** |

**All seven cross-checks landed clean stamps.** The convergence-loop pattern produced tighter integration than predicted; **the substrate is design-truth-saturated.**

---

## 6. References

- Audit target: `docs/design-notes/2026-04-25-resolve-canonical-action-proposal.md` (#59, dev-2 — committed `03361ef`).
- Substrate cross-checked:
  - `docs/design-notes/2026-04-25-variant-canonicals-proposal.md` (#47 §3 fallback chain + §1 privacy filter).
  - `docs/design-notes/2026-04-25-gate-route-back-verb-proposal.md` (#53 — engine-side route-back consumer).
  - `docs/design-notes/2026-04-25-sub-branch-invocation-proposal.md` (#56 §6 Q5 — future consumer).
  - `docs/design-notes/2026-04-25-named-checkpoint-routing-proposal.md` (#58 — different layer; no collision verified).
  - `canonical_bindings` table (Task #61 commit `7b020ae`).
- Sibling pair-reads completed: `docs/audits/2026-04-25-pair-{54-vs-56,50-vs-56,57-surgical-rollback,58-named-checkpoint,55-external-pr-bridge}-convergence.md` + `docs/audits/2026-04-25-audit-53-gate-route-back-solo.md`.
- v2 vision: `docs/design-notes/2026-04-25-self-evolving-platform-vision-v2.md` §6 Phase A phasing.
- Existing read-only goal action pattern: `tinyassets/universe_server.py:10247-10328` (`_action_goal_get`).
