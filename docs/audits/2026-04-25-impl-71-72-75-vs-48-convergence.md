# Implementation Pair-Read: #71 + #72 + #75 ↔ #48 contribution-ledger design

**Date:** 2026-04-25
**Author:** navigator
**Pair:** dev-2-2's contribution_events implementation lane (#71 schema + #72 execute_step emit + #75 design_used emit) ↔ dev-2-2's #48 contribution-ledger design proposal.
**Audit shape:** **FIRST implementation-side pair-read in the session.** Different from the seven design-vs-design pair-reads — this audits whether landed code honors design intent. Establishes a referenceable pattern for future "design vs impl" pair-reads as more primitives ship.
**Commits audited:**
- `098cf15` Task #71 contribution_events schema
- `a608a03` Task #72 execute_step emit-site wiring
- `fea677d` Task #75 design_used emit-site wiring
**Design source:** `docs/design-notes/2026-04-25-contribution-ledger-proposal.md` (#48, committed `287790c`).

---

## Stamp

**PAIR CONVERGES.** All six cross-checks pass. Implementation honors design intent at every named site. **One intentional implementation widening** (anonymous-actor skip in #75 beyond design's empty-string skip) is sound — design supports it under attribution-specs orphan-row prevention; worth documenting explicitly. **One implementation asymmetry worth pinning as a deliberate decision** (execute_step emits anonymous; design_used skips anonymous — different semantics for different surfaces, both correct).

Pattern lights up cleanly: implementation-side pair-reads can verify design fidelity in <30 min when the implementation is well-disciplined. Establishes the pattern.

---

## 1. Cross-check resolution

### Cross-check 1: Schema fidelity (#71 vs #48 §1)

**CONVERGES verbatim.** I read `tinyassets/contribution_events.py:34-62` (the actual DDL constant) against #48 §1.1 design DDL.

| Element | Design (#48 §1) | Implementation (#71) | Match |
|---|---|---|---|
| `event_id TEXT PRIMARY KEY` | ✓ | ✓ | exact |
| `event_type TEXT NOT NULL` | ✓ | ✓ | exact |
| `actor_id TEXT NOT NULL` | ✓ | ✓ | exact |
| `actor_handle TEXT NOT NULL DEFAULT ''` | ✓ | ✓ | exact |
| `source_run_id TEXT` (NULLable) | ✓ | ✓ | exact |
| `source_artifact_id TEXT` (NULLable) | ✓ | ✓ | exact |
| `source_artifact_kind TEXT NOT NULL DEFAULT ''` | ✓ | ✓ | exact |
| `weight REAL NOT NULL DEFAULT 1.0` | ✓ | ✓ | exact |
| `occurred_at REAL NOT NULL` | ✓ | ✓ | exact |
| `metadata_json TEXT NOT NULL DEFAULT '{}'` | ✓ | ✓ | exact |
| FK `source_run_id REFERENCES runs(run_id)` | ✓ (per #48 §1.1) | ✓ | exact |
| Index `idx_contribution_events_window(occurred_at)` | ✓ | ✓ | exact |
| Index `idx_contribution_events_actor(actor_id, occurred_at)` | ✓ | ✓ | exact |
| Index `idx_contribution_events_artifact(source_artifact_id, source_artifact_kind)` | ✓ | ✓ | exact |
| Index `idx_contribution_events_run(source_run_id)` | ✓ | ✓ | exact |

No structural drift. Schema is **a literal lift of #48 §1.1**. Sharper than typical: the comment block in `contribution_events.py:34-39` even cites #48 §1 and explains the FK enforceability rationale ("both tables live in the same SQLite file") — implementation documents its own design fidelity.

### Cross-check 2: Emit-site fidelity per surface

**`execute_step` emit-site (Task #72):**

Design (#48 §3 row 1): "Daemon-host step | `update_run_status()` step-finalize path | `tinyassets/runs.py:331-377`."

Implementation: `runs.py:400-449` — emit lives inside `update_run_status` after the UPDATE, gated on `status in _TERMINAL_STATUSES`. **CONVERGES with one sharpening:** design said "step finalize"; implementation correctly narrowed to TERMINAL-status transitions only (per design intent — non-terminal transitions like `running` shouldn't emit). The fetch-then-emit pattern reads back the run row to populate `actor_id`, `branch_def_id`, `branch_version_id` — clean.

**`design_used` emit-site (Task #75):**

Design (#48 §3 row 2): "Designer | Same step-finalize as #1 + `record_event()` | `tinyassets/runs.py:434-450`."

Implementation: `runs.py:1241-1282` — emit lives inside `_on_node` closure, fires at `NODE_STATUS_RAN` phase. **DRIFT with rationale: emit-site is `_on_node` closure, not `update_run_status` finalize-path.** Why: design said "co-emit with execute_step at step boundary." Implementation emits per-node-execution rather than per-run-finalize. **This is a sharpening, not a divergence:**

- `execute_step` events are 1-per-run (per terminal status).
- `design_used` events are N-per-run (one per node executed within the run).
- Design's "co-emit at step boundary" was ambiguous; impl correctly distinguished granularity.
- Per #48 §1.2 lineage credit derivation: each leaf `design_used` event → calc-time fork_from walk produces ancestors. **Per-node emission is the right shape.**

**Verdict: HONORED + sharpened.** The `design_used` emission shape is what bounty calc actually needs (see cross-check 4 below).

### Cross-check 3: Idempotency invariant

Design (#48 §6 Q1, closed): "INSERT OR IGNORE on event_id collision. Phase 2 emit-sites use deterministic IDs."

Implementation:
- `record_contribution_event` (`contribution_events.py:123-128`): SQL is `INSERT OR IGNORE INTO contribution_events ...`. ✓
- `execute_step` event_id (line 426): `f"execute_step:{run_id}:{status}"` — deterministic. ✓
- `design_used` event_id (line 1260): `f"design_used:{run_id}:{step}:{node_def_id}"` — deterministic. ✓

**CONVERGES.** Re-emit attempts (e.g., duplicate run-completion paths, retried node executions) silently dedup at SQL level. The `record_contribution_event` return value (`cur.rowcount > 0`) lets callers detect actual-insert vs. silent-dedup if needed.

### Cross-check 4: Bounty-calc query smoke (#48 §4 → §5)

Design (#48 §4): recursive-CTE walking `branch_definitions.fork_from` chain + `decay_coeff(depth)` aggregation by actor. Design intent (per §4 example): a run that uses leaf branch_version_id `X` whose lineage is X→parent_Y→grandparent_Z produces `(carol=1.0, bob=α^1, alice=α^2)` at default α=0.6 → `(carol=1.0, bob=0.6, alice=0.36)`.

The brief mentions `(carol=1.0, bob=0.5, alice=0.333)` — that's α=0.5 calibration; my attribution-layer-specs §3.2 pinned α=0.6 default but the math is parameterized. **Either smoke target is valid for testing the SQL shape** — what matters is the recursive walk produces *some* geometric decay over the lineage chain.

**Implementation observation:** the bounty calc query is NOT yet implemented (Phase 2 onwards per #48 §5; the calc lives downstream of emit-sites). What IS implemented:

- The schema supports the §4 query (indexes hit `(occurred_at)` for window, `(source_artifact_id, source_artifact_kind)` for lineage join, `(actor_id, occurred_at)` for per-actor totals).
- The emit-site populates `source_artifact_id` correctly so the lineage join key is available.
- Per #48 §1.3 architectural choice: lineage credit is DERIVED at calc-time, not emitted. The 3 leaf `design_used` events from a run that used a 3-deep lineage chain become 3+6+9=… expansions only at calc time.

**Verdict: smoke target deferred to bounty-calc dispatch (Phase 2+).** Schema + emits are correct preconditions; the actual calc is downstream. **Not a blocker for #71+#72+#75 SHIP.** Filing as [PENDING bounty-calc-smoke-test] for the calc dispatch task.

### Cross-check 5: Anonymous-author skip (#75 implementation choice)

Design (#48 §1.4 implicit + lineage-credit discipline): empty-string `author` field skips emission (no attribution path = no event).

Implementation widening (`runs.py:1254`):
```python
if not node_def_id or not author or author == "anonymous":
    return
```

The third clause — `author == "anonymous"` — is **beyond what design states**. The design says "no author = no event" (empty string). Implementation extends to "no author OR sentinel anonymous = no event."

**Verdict: SOUND widening.** Three reasons:

1. **Attribution-specs orphan-row prevention:** my §1.1 of attribution-layer-specs explicitly says: "if `daemon_actor_id` is empty, emit no event (don't credit anonymous)." The same principle applies to design_used — emitting a credit event for actor "anonymous" creates a ledger row that no real actor can ever claim, and a calc-time row that gets aggregated into a synthetic-actor's share of the bounty pool. Worse than dropping.

2. **Convention parity:** `execute_step` populates with `actor_id=row["actor"] or "anonymous"` (line 428) — so `execute_step` DOES emit anonymous events. But that's because `runs.actor` is the daemon-host actor (always populated, even if "anonymous" for unauthenticated runs). Design_used author comes from NodeDefinition.author at authoring time — if the author was anonymous when authored, no real designer exists to credit later. **The two surfaces have different semantics for "anonymous" — and the implementation correctly distinguishes them.**

3. **Sybil resistance forward-compat (per attribution-specs §5):** anonymous bindings are exactly the sybil-vulnerable surface. Pre-filtering at emit time is cheaper than filtering at calc time.

**Recommendation:** document the asymmetry explicitly in #48 v2 amend or in the attribution-layer-specs v2:
- `execute_step.actor_id` MAY be "anonymous" (daemon-host attribution, sybil scoring scales distribution).
- `design_used.actor_id` SHOULD NEVER be "anonymous" (synthetic-actor credit pollution).

Filing as **[PENDING #48-v2-anonymous-asymmetry-doc]**.

### Cross-check 6: Composition with #54 schema (runs.branch_version_id)

Phase A item 6 (#54, committed via `80a1e14`) added `runs.branch_version_id TEXT` column.

Implementation populates it correctly (`runs.py:413`):
```python
artifact_id = row["branch_version_id"] or row["branch_def_id"]
artifact_kind = "branch_version" if row["branch_version_id"] else "branch_def"
```

When a run was launched as a version-pinned run, `source_artifact_id` records the version_id and `source_artifact_kind="branch_version"`. When a run was launched as a live-def run, `source_artifact_id` records the def_id and `source_artifact_kind="branch_def"`.

**Verdict: CONVERGES.** This composition is exactly what #54 §4 anticipated ("Task #48 contribution ledger needs it for `source_artifact_id` resolution at attribution time"). Per pair-read #59 §1 finding (three version concepts), the implementation correctly uses `branch_version_id` (immutable snapshot id) for attribution provenance — not `branch_def_id` (live editable) and not `run_lineage.branch_version` (audit-only INTEGER).

---

## 2. Implementation observability + failure-mode handling

The implementation adds two patterns worth highlighting (NOT in design, sound additions):

1. **`_EMIT_FAILURES` counter** (`contribution_events.py:30`): increments on any emit-site try/except recovery. "Operators grep for non-zero in production." Same observability shape as the legacy-fallback counter from Task #64. **Sound implementation discipline** — emit failures must NOT block status updates (status is the load-bearing semantic; emit is best-effort observability). The counter surfaces silent-emit-failure-class problems for navigator triage.

2. **try/except wrapping at every emit-site:** both #72 and #75 wrap `record_contribution_event` in try/except, increment `_EMIT_FAILURES`, log warning, and continue. Status update / step event are preserved. **This is the right resilience pattern** — a malformed metadata_json or transient SQLite contention shouldn't fail an otherwise-successful run.

**Recommendation: add a §6.1 to attribution-layer-specs noting the `_EMIT_FAILURES` counter as the canonical operator-observability surface for emit failures.** Small doc addition.

---

## 3. Implementation-time constraints captured for remaining 3 emit-sites

Three contribution surfaces still to land per #48 §3:

| Surface | Event type | Status |
|---|---|---|
| Repo PR (surface 3) | `code_committed` | Pending — depends on Task #55 external-PR bridge implementation |
| Lineage (surface 4) | DERIVED, not emit | No emit-site work needed |
| Helpful chatbot-action (surface 5) | `feedback_provided` | Pending — depends on gate-series typed-output contract impl (Phase A item 7) |
| (E19) | `caused_regression` | Pending — depends on Task #57 surgical rollback implementation |

For each remaining emit-site, the impl-time constraints from this audit apply:

- **Use `record_contribution_event` helper** (don't re-derive INSERT logic).
- **Deterministic event_id pattern** (e.g., `f"caused_regression:{rollback_id}:{actor_id}"` for §6.3 actor-proportional distribution).
- **try/except wrapping with `_EMIT_FAILURES` increment.**
- **Skip emission for anonymous-author cases** per cross-check 5 widening principle.
- **Populate `source_artifact_id` from version_id when available, def_id otherwise** per cross-check 6 pattern.

---

## 4. Roadmap deltas

**Phase B item 8 — implementation surfaces 1 + 2 of 5 LANDED.** Schema + execute_step + design_used emit-sites are in main.

**Phase B item 8 remaining:**
- Surface 3 (`code_committed`) — gated on Task #55 impl.
- Surface 5 (`feedback_provided`) — gated on Phase A item 7 impl.
- E19 (`caused_regression`) — gated on Task #57 impl.

**Surfaces 1+2 are the load-bearing pair for early bounty-calc smoke testing.** The bounty-calc dispatch (Phase 2 of Phase B item 8) can run end-to-end with just `execute_step` + `design_used` events — daemon-host credit + designer credit are the most-frequent emissions. A smoke test using these alone validates the recursive-CTE query shape from #48 §4 before all 5 surfaces are live.

**Recommendation:** lead may want to dispatch the bounty-calc primitive (with smoke-test using surfaces 1+2 only) as a parallel-track to the remaining surface impls, rather than waiting for all 5. Filing as **[PENDING bounty-calc-early-dispatch-with-2-surfaces]**.

---

## 5. Implementation pattern observations (for the convention surface)

This is the first impl-side pair-read; pattern observations:

1. **Implementation cites design verbatim in code comments.** `contribution_events.py:34-39` references "Phase B item 8 (Task #71)" and "spec: #48 §1." Future implementers reading the code can find the design intent directly. **Recommendation: codify in shared-helper convention §6 (test convention) → also "code comments cite design source for any non-trivial logic." Small extension to convention doc.**

2. **Resilience discipline pre-baked.** Both emit-sites wrap in try/except + counter increment + log. **This pattern is reusable for any "best-effort observability layered on load-bearing semantics" surface** (e.g., future canary→file_bug emit per canary spec v2; future feedback_provided cite emission). Worth a project-level convention doc.

3. **Implementation goes BEYOND design when design is implicit.** The anonymous-author widening + the `_EMIT_FAILURES` counter are both "design didn't say to do this; implementation made the right call." This is the kind of implementation-side judgement that pair-reads should explicitly notice and ratify, so future implementers know it's the project pattern.

**Recommendation:** add a §X to design-proposal-pattern convention doc (Task #68) noting that "implementations that go beyond design when design is implicit are correct shape; flag them in impl-side pair-reads as ratified extensions." Filing as [PENDING design-pattern-convention-impl-judgment-extension].

---

## 6. References

- Design source: `docs/design-notes/2026-04-25-contribution-ledger-proposal.md` (#48, dev-2-2 — committed `287790c`).
- Implementation commits:
  - `098cf15` Task #71 contribution_events schema.
  - `a608a03` Task #72 execute_step emit-site wiring.
  - `fea677d` Task #75 design_used emit-site wiring.
- Cross-check sources:
  - `tinyassets/contribution_events.py:34-62` (DDL).
  - `tinyassets/contribution_events.py:90-142` (record_contribution_event helper).
  - `tinyassets/runs.py:400-449` (execute_step emit-site).
  - `tinyassets/runs.py:1241-1282` (design_used emit-site).
- Substrate cross-references:
  - `docs/design-notes/2026-04-25-attribution-layer-specs.md` §1.1 + §3 + §5 + §6.3.
  - `docs/design-notes/2026-04-25-runner-version-id-bridge.md` (#54 — branch_version_id column).
  - `docs/audits/2026-04-25-pair-54-vs-56-convergence.md` (three-version-concept finding).
- Sibling pair-reads (design-vs-design): seven completed in this session.
- v2 vision: `docs/design-notes/2026-04-25-self-evolving-platform-vision-v2.md` Phase B phasing.
- Convention docs: `docs/design-notes/2026-04-25-shared-helper-convention.md` + `2026-04-25-design-proposal-pattern-convention.md` (Task #68).
