# Solo Audit — #69 Storage-Layer Authority Refactor

**Date:** 2026-04-25
**Author:** navigator
**Audit target:** `docs/design-notes/2026-04-25-storage-auth-refactor-proposal.md` (#69, dev-2 — Task #69 in current TaskList).
**Audit shape:** SOLO audit. No navigator-side audit pre-exists. Same shape as #62 audit-of-#53.
**Constraints checked against:** v1/v2 vision, primitive-shipment roadmap, all 5 paired-converged design proposals (#47, #48, #53, #54, #55, #56, #57, #58, #59), navigator's #65 pair-read finding (which surfaced this gap).

---

## Stamp

**AUDIT CLEARS.** All eight verdict-band dimensions are sound. No material flags. Two minor opens surface from the audit (one cross-doc invariant worth tightening; one open Q from #69 itself worth pinning).

This is the cleanest-to-clear design proposal in the substrate. **Phase A item 1 design is closed.**

---

## 1. Verdict bands per dimension

| Dimension | Verdict | Rationale |
|---|---|---|
| **Explicit-arg vs decorator vs context-manager** | **CORRECT — least-magic wins decisively** | §3 tradeoff table is sharp. The "forgot-to-apply / forgot-to-enter" failure modes for decorator and context-manager would silently disable auth — the exact defense-in-depth gap we're closing. Explicit `actor_id` arg makes failure mode loud (TypeError on missing arg) instead of silent (auth doesn't fire). Per-helper boilerplate cost is bounded (6 helpers in Phase 1). Same architectural shape as memory's "Fail loudly, never silently." |
| **Phase 1 helpers list (6 items)** | **CORRECT scope — high blast-radius slice** | The six helpers (`set_canonical_branch`, `set_canonical_binding`, `update_branch_definition`, `save_branch_definition`, `delete_goal`, `mark_branch_version_rolled_back`) are exactly the load-bearing writes — every one mutates either authority-gated artifact state (canonicals) or version-permanent state (branches/rollbacks). The "structural callout" that `set_canonical_binding` is Phase 1 by definition is sharp: auth lands at first-use, not as a retrofit. **Story stays clean: every binding ever written goes through the new authority module.** This avoids the "authority added later" debt class entirely. |
| **v2 deferral list (right tier-2 split?)** | **CORRECT — risk-tier appropriate** | Five v2 deferrals: `update_goal` (gate-ladder edits — important, not catastrophic); `save_goal` (initial create — caller becomes author by definition, nothing to check against); `record_event` (audit-log writes; broad-trust, not security-load-bearing); `save_node_definition` (less load-bearing than branches); `update_run_status` (run state transitions; trusted internal callers). The "audit-log + run-state" exclusions are right: those are operational data flows, not artifact-creation events. Different threat surface. |
| **Migration plan 4-step additive (load-bearing-clean?)** | **CORRECT — additive backward-compat through Step 3** | Step 0 adds the module; Step 1 adds optional `actor_id` arg with `default="host"`; Step 2 wires in checks; Step 3 flips default after callers migrated. **Two-week sunset window** is reasonable. The deprecation warning at Step 1 (`warnings.warn` when default fires) gives operators visibility into which callers haven't migrated yet — that's the right shape for migration observability. **Rollback safety** explicit: revert Step 2 only if regression; Step 0 + Step 1 stay. No data loss. |
| **Composition with #57 rollback authority (defense-in-depth literal?)** | **CORRECT — both barriers must hold** | §6 explicitly: "MCP-layer check is one barrier; storage-layer check is the second. Defense-in-depth literal — both must hold for rollback to fire." This is the right semantics. If the MCP layer is bypassed (direct `daemon_server` call from a test, future internal automation, or scheduled job), storage-layer prevents the action. The rollback case is THE highest-blast-radius write in the substrate (it modifies canonical_bindings, marks versions inactive, repoints goal canonicals); having two-barrier defense is appropriate. |
| **Composition with #47 variant canonicals (set_canonical_binding lifts auth from §4?)** | **CORRECT — literal lift** | §6 verifies the lift: `scope_token == ''` → goal author or host (current set_canonical behavior); `scope_token == 'user:<actor>'` → that actor only; `scope_token.startswith('tier:'/'team:')` → policy-pending; reject with informative error. **Cross-checked against #47 §4:** matches exactly. The §4 authority model is the source of truth; #69's `check_set_canonical_authority` is the storage-side enforcement. **No drift.** |
| **Composition with #48 contribution ledger (orthogonal — auth at writes, ledger appends are universal)** | **CORRECT — sharp distinction** | §6 names this: "`record_contribution_event(..., actor_id=...)` already requires the actor as a row field (event author). NOT auth-related at the storage layer — the ledger is append-only, every actor records their own events. `actor_id` for events is identity, not authorization." This is the right framing. Per #48 §1's invariant — events are facts; you don't need permission to record what you did, you just record it. Auth is for state-mutating writes; ledger is identity-tagged history. Mixing them would invite "auth-gated event suppression" where bad actors hide their own bad acts. |
| **Composition with #56 sub-branch on_child_fail policy (Q6 — does AuthorizationError map cleanly?)** | **CORRECT shape, with one nuance** | §7 Q6 (still open) says AuthorizationError raised mid-graph is governed by parent's `on_child_fail` policy from #56 §4 — `propagate` default raises in parent context; `default` falls through; `retry` re-fires (will fail again, bounded by retry_budget). **The retry case is the nuance:** retrying an AuthorizationError makes no sense — the failure is deterministic (the actor's authority doesn't change retry-to-retry). **Recommendation: AuthorizationError should short-circuit retry to propagate.** This is a small implementation-time clarification, not a #69 design gap. Filing as [PENDING #69-impl-retry-shortcircuit-on-auth]. |

---

## 2. Cross-doc consistency check

| Cross-ref | Resolution |
|---|---|
| Cites #47 §4 authority model | ✓ §6 explicit lift |
| Cites #57 §5 rollback host-only | ✓ §6 defense-in-depth |
| Cites navigator #65 pair-read as gap source | ✓ §1 explicit attribution |
| Cites #48 ledger as orthogonal | ✓ §6 sharp distinction |
| Cites #66 TypedPatchNotes as orthogonal | ✓ §6 — `patch_notes.author_actor_id` is identity, not auth |
| Cites #56 sub-branch on_child_fail composition | ✓ §7 Q6 |
| Cites design-proposal-pattern convention | ✓ §9 references convention |

**One subtle missing citation worth flagging:** #69 doesn't explicitly cite #59 (`resolve_canonical`). But: read operations don't need authority checks per #59 §5 ("Read-only. No authority required"). The composition is the absence of a check — implicit. **Recommendation:** §6 of #69 should add a one-liner: "Read-only operations (#59 resolve_canonical, etc.) do not need authority checks; symmetric privacy filtering is enforced at SQL-level via row-visibility, not at the operation layer." This makes the read/write asymmetry explicit. Small wording fix; not a design gap.

**Cross-doc invariant worth tightening (NEW from this audit):** the `AuthorizationError` class should be importable from a stable surface that downstream callers (sub-branch invocation per #56, MCP perimeter handlers, future scheduler) can `except AuthorizationError:`. The current proposal puts it in `tinyassets/storage/authority.py`. **Recommendation:** ensure the import path is stable (e.g., re-export from `workflow.exceptions` if such a module exists, or document `workflow.storage.authority.AuthorizationError` as the canonical path). Implementation-time concern; small.

---

## 3. Open-Q resolution status (#69 had 6 open Qs)

| Q | Status |
|---|---|
| Q1 AuthorizationError → MCP error class mapping | **CLOSED.** `_format_authorization_error` helper in universe_server.py returning structured `{status, error, authority_required, actor_id}`. Standard MCP shape. |
| Q2 Host actor identification | **CLOSED.** Reuses `os.environ.get("UNIVERSE_SERVER_HOST_USER", "host")` via `_host_actor()` helper. Single source of truth; matches universe_server.py + #57. |
| Q3 Cross-process policy enforcement | **CLOSED — punted to v2.** Today single-process; federation work surfaces this. |
| Q4 Authority caching | **CLOSED.** Recompute every check; SQLite query is sub-millisecond. Cache-invalidation complexity not earned. |
| Q5 Goal author transferability (truly open) | **STILL OPEN — defer to separate proposal.** Different concern (governance), shouldn't load-bear on auth refactor. v3+ thing. |
| Q6 AuthorizationError as engine signal in sub-branch (truly open) | **PARTIALLY CLOSED by this audit.** §1 dimension 8 verdict: AuthorizationError should short-circuit retry to propagate (deterministic failure). Filing as [PENDING #69-impl-retry-shortcircuit-on-auth]. |

**4 of 6 closed cleanly.** Q5 is correctly deferred (governance, not auth). Q6 is sharpened by this audit's dimension 8 verdict; the retry-short-circuit clarification belongs in implementation.

---

## 4. Roadmap deltas

**Phase A item 1 (storage authority refactor) — DESIGN COMPLETE.**

**Phase A is now ENTIRELY DESIGNED:**

| Phase A item | Status |
|---|---|
| 1 storage authority refactor | **CLOSED (this audit)** |
| 2 variant_canonicals table | DESIGNED + IMPLEMENTED Step 0+1; Step 2 in flight |
| 3 lookup_canonical | DESIGNED (#59, paired as J) |
| 4a verdict (route_back) | DESIGNED (#53, audited solo as #62) |
| 4b named-checkpoint | DESIGNED (#58, paired as L) |
| 5a invoke_branch_version_spec | DESIGNED (#56, paired as #60) |
| 5b structured failure propagation | DESIGNED (#56) |
| 5c two-pool concurrency | DESIGNED (#56) |
| 6 run_branch_version | DESIGNED (#54, paired as #59); IMPL ACTIVE (#65a/b) |
| 7 gate-series typed-output contract | FULLY CLOSED (#53 + #58 + #66 TypedPatchNotes) |

**11 of 11 Phase A items have landed designs.** Implementation is actively dispatching for items 2 (Step 2) and 6 (#65a/b in flight).

**Implementation prerequisites that #69 unlocks:**
- **Phase A item 2 Step 2** (`set_canonical_binding` dual-write) — must call `check_set_canonical_authority`. Without #69 ratified + impl'd, the new write path lacks storage-layer auth.
- **Phase E item 23 (#57 rollback)** — `mark_branch_version_rolled_back` must call `check_rollback_authority`. Phase E impl is gated on #69 impl.
- **Phase A item 5 sub-branch invocation impl** (#56) — `on_child_fail=propagate` flow must handle `AuthorizationError` cleanly per Q6 nuance from §1 dimension 8.

**Implementation sequence implication:** **#69 should impl-dispatch FIRST in Phase A's impl sweep**, before #57 / #47 Step 2 / #56 implementations. Otherwise downstream impls have to retrofit auth checks, which is exactly the debt class we're avoiding.

---

## 5. What this audit does NOT cover

- **No re-design of #69.** Audit clears it; one wording tweak (§2 read-op asymmetry note) and one impl-time clarification (retry short-circuit).
- **No live MCP probe.** Paper audit only.
- **No code-touching review.** #69 is design-only.
- **No verification of v2 deferred helpers.** v2 covers later.
- **No federation / multi-process consideration.** Q3 deferral honored.

---

## 6. References

- Audit target: `docs/design-notes/2026-04-25-storage-auth-refactor-proposal.md` (#69, dev-2).
- Pair-read finding source: `docs/audits/2026-04-25-pair-57-surgical-rollback-convergence.md` (#65, navigator) §4 — flagged the storage-layer trust gap; #69 directly addresses.
- Substrate cross-checked:
  - `docs/design-notes/2026-04-25-variant-canonicals-proposal.md` (#47 §4 authority model).
  - `docs/design-notes/2026-04-25-surgical-rollback-proposal.md` (#57 §5 rollback_merge host-only).
  - `docs/design-notes/2026-04-25-contribution-ledger-proposal.md` (#48 — orthogonal identity-vs-auth).
  - `docs/design-notes/2026-04-25-typed-patch-notes-spec.md` (#66 — orthogonal identity-vs-auth).
  - `docs/design-notes/2026-04-25-sub-branch-invocation-proposal.md` (#56 §4 on_child_fail).
  - `docs/design-notes/2026-04-25-resolve-canonical-action-proposal.md` (#59 §5 — read-only no auth).
- Sibling pair-reads + audits: complete suite of seven (#59, #60, #62, #65, #66, #67, #68 in audit-numbering).
- v2 vision: `docs/design-notes/2026-04-25-self-evolving-platform-vision-v2.md` §6 Phase A phasing.
- Concrete gap reference: `tinyassets/daemon_server.py:2453-2475` (`set_canonical_branch` "Caller must validate authority").
