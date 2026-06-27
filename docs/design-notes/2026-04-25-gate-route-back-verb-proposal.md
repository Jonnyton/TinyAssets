---
status: active
---

# Gate-Aware Route-Back — Verdict Extension Proposal

**Date:** 2026-04-25
**Author:** dev-2
**Status:** Design proposal. Resolves G1 audit blocker #2 (`docs/audits/2026-04-25-canonical-primitive-audit.md`).
**Builds on:** Task #47 variant-canonicals proposal (resolution fallback chain); Task #48 contribution ledger (emit on route-back).
**Scope:** schema/contract design for the gate-evaluator route-back primitive. No code changes.

---

## 1. Architectural pivot — verdict extension, not new MCP verb

**The brief asked for a new MCP action verb. The right primitive is a verdict extension instead.**

The original framing — "extensions action=route_back" as an MCP action — would force three round-trips for what should be one engine-side transition: evaluator returns "fail" → engine pauses → chatbot calls route_back action → engine resumes. The decision is INTRINSIC to the evaluator's run; making it external puts the chatbot in a loop it shouldn't own.

Correct primitive: extend `EvalVerdict` to include `"route_back"` and add a `route_to` payload field on `EvalResult`. The evaluator returns the routing decision as part of its evaluation result. The engine handles the new verdict by resolving (goal, scope) via the Task #47 fallback chain, then invoking the runner with patch_notes payload.

### Recommended action signature

The action signature is the EvalResult shape itself, not a separate MCP verb:

```python
# tinyassets/evaluation/__init__.py — extend existing types

EvalVerdict = Literal["pass", "fail", "skip", "error", "route_back"]

@dataclass
class EvalResult:
    score: float
    verdict: EvalVerdict
    kind: EvaluatorKind
    label: str = ""
    details: dict[str, Any] = field(default_factory=dict)
    # NEW — only meaningful when verdict == "route_back"
    route_to: tuple[str, str] | None = None      # (goal_id, scope_token)
    patch_notes: dict[str, Any] | None = None    # payload for the routed run
```

**Two read-only MCP actions surface to chatbots** for compose-time previewing:

- `goals action=resolve_canonical(goal_id, canonical_scope=...)` — preview "what canonical would this resolve to?" before authoring a gate. Returns the same shape as `goals action=get`'s `canonical_branch_version_id` field, but with explicit scope-token-aware fallback chain applied.
- `goals action=get` extension — return shape gains a `canonical_resolved` field showing the resolution result for the calling actor's default scope.

These reads do NOT trigger route-back; they only let chatbots author gate-series confidently. Route-back execution is engine-internal.

---

## 2. Decision shape — gate evaluator's output schema

The evaluator returns one of five verdicts. The engine handles each:

| verdict | Engine behavior | Required fields |
|---|---|---|
| `"pass"` | Continue gate-series to next gate or success node. | `score`, `verdict`, `kind`. |
| `"fail"` | Terminate gate-series with status "rejected". `details` carries reason. | `score`, `verdict`, `kind`, `details`. |
| `"skip"` | Skip this evaluator (e.g., no applicable artifact). Continue as if pass. | `score`, `verdict`, `kind`. |
| `"error"` | Evaluator itself crashed. Engine retries per existing retry policy. | `score`, `verdict`, `kind`, `details` (error trace). |
| `"route_back"` (NEW) | Resolve `route_to` (goal_id, scope_token) → invoke canonical with `patch_notes`. | `score`, `verdict`, `kind`, `route_to`, `patch_notes`. |

**Validation:** `__post_init__` (currently checks score range) extends to:

- If `verdict == "route_back"`, both `route_to` and `patch_notes` must be non-None. ValueError otherwise.
- If `verdict != "route_back"`, `route_to` and `patch_notes` SHOULD be None (not enforced — informational only).

**Why route_to is `tuple[goal_id, scope_token]` not just `branch_version_id`:** the evaluator decides the scope of routing intent, not the destination artifact. The (goal, scope) tuple is stable across canonical changes; binding directly to a `branch_version_id` would silently target a stale snapshot if the canonical for that scope is later updated.

---

## 3. Resolution chain (uses Task #47 fallback)

Engine-side handler for `verdict == "route_back"` calls the resolver from Task #47:

```sql
-- From Task #47 §3, applied here:
SELECT branch_version_id FROM canonical_bindings
 WHERE goal_id = :route_to_goal
   AND (visibility = 'public' OR bound_by_actor_id = :viewer_actor_id)
   AND scope_token IN (:route_to_scope, '')
 ORDER BY
   CASE scope_token
     WHEN :route_to_scope THEN 1
     ELSE 2
   END
 LIMIT 1;
```

`:viewer_actor_id` is the actor on whose behalf the gate-series is running (the run's `actor` field, `runs.actor`). The fallback chain prefers the requested scope, falls back to default unscoped, ensuring rejected-patch routing works even when the requested scope has no specific binding.

**Why scope honors the viewer:** when Mark's gate-series rejects a patch, "MY canonical for goal G" must mean Mark's canonical, not the gate author's canonical or the goal author's canonical. Resolution is viewer-aware via the `runs.actor` field already populated at run-claim time.

**Cycle detection (MUST-have, not open question):** every patch_notes payload carries a `_route_history` metadata field that the engine appends to on every route-back. **Max depth = 3.** If a route-back would push history beyond 3 entries, OR if the new (goal, scope) is already in `_route_history`, the engine short-circuits with terminal status `"route_back_loop"`. The 3-entry cap is policy; cycle detection by visited-set is the safety net.

---

## 4. Failure modes

| Failure | Engine behavior | Status / details |
|---|---|---|
| `route_to` is None when verdict is `"route_back"` | EvalResult fails its `__post_init__` validation. Evaluator's run is the offender; engine logs "evaluator returned route_back without route_to" and treats verdict as `"error"`. | terminal status = `"error"`, error class = `evaluator_contract_violation`. |
| `(goal_id, scope_token)` resolves to no canonical (no row in `canonical_bindings`) AND default scope `''` also unbound | Engine terminates gate-series with terminal status. NOT silent — visible to evaluator's downstream graph. | `"no_canonical_bound"` with `details = {goal_id, scope_token, fallback_attempted: ['unscoped']}`. |
| `(goal_id, scope_token)` resolves to a `branch_version_id` that no longer exists in `branch_versions` (deleted/orphaned) | Engine terminates with distinct error class. Suggests a navigator-triage condition: a canonical pointer outlived its target. | `"canonical_artifact_missing"` with `details = {goal_id, scope_token, branch_version_id}`. |
| Cycle detected (visited (goal, scope) OR depth > 3) | Engine short-circuits, terminal status. | `"route_back_loop"` with `details = {history: [...], cycle_detected_at: (goal, scope)}`. |
| Routed canonical's run itself errors / times out | Inherits existing runner timeout + retry policy. The route-back gate-series's status reflects the routed run's status. | Existing primitives — no new behavior here. |

**Default fallback policy (§6 Q5 punted):** when (goal, scope) is unbound, recommendation is **fail-fast** (`"no_canonical_bound"`), NOT hold-for-host-bind. Async pause-and-wait creates state-management hell; the chatbot can re-author the gate or bind a canonical, then re-run.

---

## 5. Composition with existing branch-run primitives

### Hard dependency on Task #54

The route-back execution **requires Task #54 to land first or concurrently**. Today's runner takes `branch_def_id` (live editable definition); the canonical resolves to a `branch_version_id` (immutable snapshot). Without #54's bridge between the two, the engine cannot actually invoke a canonical without an unsafe redirect-through-def-id step.

This proposal cannot ship before #54 is in place. The proposals are sequenced:
1. Task #54 — runner accepts `branch_version_id`.
2. Task #47 — variant canonicals table.
3. Task #53 (this) — verdict extension + route_back handler.

All three need to be in place for Mark's gate-series user-story (G1 blocker #2) to actually work.

### Engine-side handler sketch

```
on EvalResult with verdict == "route_back":
    1. Validate route_to + patch_notes are present (else → error verdict).
    2. Append (goal, scope) to patch_notes._route_history.
    3. If len(_route_history) > 3 OR (goal, scope) in earlier history:
         terminate with "route_back_loop" status.
    4. Resolve (goal, scope) via #47 fallback chain → branch_version_id.
    5. If unresolved: terminate with "no_canonical_bound".
    6. If branch_version_id orphaned: terminate with "canonical_artifact_missing".
    7. Invoke runner with branch_version_id (Task #54 bridge) + patch_notes as inputs.
    8. Block synchronously on routed run completion (sync-only, per §6 Q4).
    9. Emit `code_committed`-like contribution event (Task #48) crediting the routing chain.
    10. Return routed run's terminal status as the gate-series's continuation signal.
```

### Sync-only execution

Route-back execution is synchronous from the gate-series's perspective. The originating gate-series blocks on the routed run returning a terminal status, then continues based on that status.

**Why sync:** async route-back creates state-management hell (gate-series paused indefinitely; patch_notes in limbo). Long-running routed branches are themselves a separate concern handled by the existing runner timeout + retry primitives. Sync is consistent with how `evaluate(state)` already returns synchronously in the evaluator protocol (`tinyassets/evaluation/__init__.py:67`).

**Compositional note:** sync-only means a single rejected-patch's route-back chain executes serially across max 3 hops. Total wall-clock = sum of routed runs' durations. Acceptable for current low-frequency routing; revisit at high volume.

### Contribution ledger emission

Each route-back resolution emits a `code_committed`-style event to the contribution ledger (Task #48 §1) crediting the original patch author + the routing chain's intermediate authors. The routing event metadata records the (goal, scope) that triggered the route-back so post-hoc analysis can attribute reputation correctly.

---

## 6. Open questions

1. **Verdict-string vs separate decision-shape primitive.** Today the proposal overloads `EvalVerdict` with `"route_back"`. Alternative: introduce a separate `GateDecision` union type (`Pass | Fail | Skip | Error | RouteBack(route_to, patch_notes)`) returned alongside `EvalResult`. Cleaner type discrimination but doubles the contract surface. Recommend keeping verdict-string for v2 simplicity; revisit if verdict states grow beyond ~6.

2. **Patch_notes payload schema.** Today proposed as `dict[str, Any]` (opaque). Alternative: typed `PatchNotes` dataclass with required fields (`reason`, `evidence`, `suggested_changes_json`). Typed wins on chatbot-author guidance; opaque wins on flexibility. Recommend typed when the gate-series typed-output contract from navigator's v1 vision §2 lands; opaque until then.

3. **Cycle detection — visited-set vs depth-only.** This proposal mandates BOTH: depth ≤ 3 AND no repeated (goal, scope) in history. Belt-and-braces. Open Q: is depth=3 the right number, or does the platform need a config-tunable max-depth? Recommend config-tunable (`TINYASSETS_ROUTE_BACK_MAX_DEPTH`, default 3) so emergency adjustments don't require migration.

4. **Sync vs async route-back execution.** Recommended: SYNC. Reasons in §5. Open Q: does any persona require async / fire-and-forget routing semantics? Mark's gate-series story is sync. Future personas with multi-day human-in-the-loop gates may need async; mark for revisit when that surfaces.

5. **Fallthrough chain — fail-fast vs hold-for-host-bind.** Recommended: FAIL-FAST (`"no_canonical_bound"`). Holding a gate-series indefinitely for a host to bind a canonical is the same async hell §5 calls out. Chatbot can re-author the gate after binding. Open Q: should the fail-fast surface a chatbot-actionable hint ("bind a canonical for `(goal, scope)` then re-run")? Recommend yes — include in `details.suggested_action`.

---

## 7. What this proposal does NOT cover

- **No code changes.** Design only; lead routes implementation as separate dispatch.
- **No `goals action=resolve_canonical` MCP action wiring.** That ships with Task #47's resolver implementation; this proposal only names it as a chatbot-side preview surface.
- **No routed-run interruption / cancellation primitives.** If the originating gate-series is cancelled while waiting on a routed run, today's run-cancel primitive (`run_cancels` table per `runs.py:129-132`) handles it. No new primitive needed.
- **No reputation calculation.** The `caused_regression` event Task #48 introduces is the negative-credit primitive; reputation aggregation is downstream.
- **No solution to the runner version-id mismatch.** Punted to Task #54 as a hard dependency; this proposal only declares the dependency.
- **No Mark-specific persona walkthrough beyond G1 blocker #2.** The proposal is general-purpose.

---

## 8. References

- G1 audit blocker #2: `docs/audits/2026-04-25-canonical-primitive-audit.md`.
- Variant canonicals: `docs/design-notes/2026-04-25-variant-canonicals-proposal.md` (Task #47).
- Contribution ledger: `docs/design-notes/2026-04-25-contribution-ledger-proposal.md` (Task #48).
- Navigator v1 vision: `docs/design-notes/2026-04-25-self-evolving-platform-vision.md` §2 (decision-routing primitive named-checkpoint contract).
- Existing evaluator contract: `tinyassets/evaluation/__init__.py:32-54` (`EvalVerdict` enum + `EvalResult` dataclass).
- Existing evaluator implementations: `tinyassets/outcomes/evaluators.py` (PublishedPaperEvaluator, MergedPREvaluator, DeployedAppEvaluator) — pattern reference for typed evaluator subclasses.
- Existing run-cancel primitive: `tinyassets/runs.py:129-132` (`run_cancels` table) — reused for routed-run interruption.

---

## 9. v2 Amendments — TypedPatchNotes shape (added 2026-04-25 post-#66)

These amendments fold Task #66 (`docs/design-notes/2026-04-25-typed-patch-notes-spec.md`) into this proposal. The semantics are unchanged; the type discipline is sharpened. Every original section above remains valid as the v1 reference; this §9 names the v2 deltas.

### 9.1 EvalResult.patch_notes — typed, not opaque

The v1 sketch in §1 had:

```python
patch_notes: dict[str, Any] | None = None    # payload for the routed run
```

**v2:** the type tightens to:

```python
from workflow.evaluation.patch_notes import PatchNotes  # NEW per Task #66

@dataclass
class EvalResult:
    # ... existing fields ...
    route_to: tuple[str, str] | None = None
    patch_notes: "PatchNotes | None" = None   # was dict[str, Any] | None
```

`PatchNotes` is the frozen dataclass from Task #66 — content-hashed `patch_notes_id`, structured `evidence_refs: list[EvidenceRef]`, in-payload `route_history: list[tuple[str, str]]`. Validation in `__post_init__` per #66 §3.

### 9.2 Cycle detection — typed field, not magic-dict-key

The v1 §3 cycle-detection used an opaque dict magic key:

```python
visited = patch_notes.get("_route_history", [])
if len(visited) > 3 or (goal, scope) in visited:
    terminate("route_back_loop")
```

**v2:** the typed field replaces the magic key:

```python
if len(notes.route_history) > 3 or (goal, scope) in notes.route_history:
    terminate("route_back_loop")
```

Engine logic identical in semantics. The `TINYASSETS_ROUTE_BACK_MAX_DEPTH` env var (v1 §6 Q3) still tunes the depth cap.

When the engine appends a hop to `route_history`, it constructs a new PatchNotes via `dataclasses.replace`:

```python
new_notes = dataclasses.replace(
    notes, route_history=[*notes.route_history, (goal, scope)]
)
# __post_init__ recomputes patch_notes_id automatically
```

### 9.3 Evidence references — structured EvidenceRef

The v1 spec had no specific shape for citing evidence; gate evaluators populated arbitrary fields in `patch_notes`. v2 uses `EvidenceRef` per #66 §2:

```python
notes_with_cite = dataclasses.replace(
    notes,
    evidence_refs=[
        *notes.evidence_refs,
        EvidenceRef(kind="wiki_page", id="bugs/BUG-042", cited_by="evaluator_xyz"),
    ],
)
```

The gate runner inspects `len(notes.evidence_refs) > 0` before emitting `feedback_provided` events — anti-spam invariant from attribution-layer-specs §1.4.

### 9.4 patch_notes_id stabilizes cite chains

When a gate cites a PatchNotes as decision input, attribution-layer-specs §1.4 records `notes.patch_notes_id` in `feedback_provided` event metadata. **The id is the entity-identity-per-state**, not a stable identity-across-states (per #66 §4 immutability contract). Subsequent route-back hops produce new PatchNotes with new ids; lineage is preserved in `route_history`. This composes correctly because cite events reference the id AT cite-time, and route-back evolution doesn't invalidate prior cites.

### 9.5 Open questions delta

| v1 Q | Status post-v2 |
|---|---|
| Q1 verdict-string vs separate decision-shape | Unchanged — still open. Verdict-string remains the v2 default. |
| **Q2 patch_notes opaque vs typed** | **RATIFIED — closed by Task #66.** TypedPatchNotes is the v2 shape. |
| Q3 cycle-detection config-tunable max-depth | Unchanged — `TINYASSETS_ROUTE_BACK_MAX_DEPTH` env, default 3. |
| Q4 sync vs async route-back | Unchanged — recommended sync. |
| Q5 fallthrough fail-fast vs hold-for-host-bind | Unchanged — recommended fail-fast. |

The v2 amend closes Q2 specifically; the other 4 open Qs carry forward unchanged.

### 9.6 Implementation sequencing

Task #66 must land before #53 implementation can consume the typed shape. Sequence:

1. Task #66 lands: `tinyassets/evaluation/patch_notes.py` ships PatchNotes + EvidenceRef.
2. (Concurrent) Task #54 already landed `dc7d2cb` — `execute_branch_version_async` available.
3. Task #53 implementation: route-back handler consumes `PatchNotes` via the typed field on `EvalResult.patch_notes`.

During the 2-week sunset window per #66 §7 Step 3, `EvalResult.__post_init__` accepts both `dict` and `PatchNotes`; the dict path emits a deprecation warning + auto-converts. After sunset, dict path raises `TypeError`.

### 9.7 Cross-proposal consistency check

This v2 amend does NOT change interactions with sibling proposals:

- **Task #54 sibling-action pattern** — still describes the runner ABI; PatchNotes lives at the EvalResult layer above.
- **Task #56 sub-branch invocation** — `output_mapping` references parent state keys, not patch_notes; no interaction.
- **Task #57 surgical rollback** — `caused_regression` event metadata is independent; rollback doesn't observe patch_notes shape.
- **Task #58 named-checkpoint contract** — orthogonal layer (within-branch routing); patch_notes flows through both layers but the checkpoint contract sees only the route_to tuple, not patch_notes contents.
- **Task #59 resolve_canonical** — read primitive doesn't touch patch_notes.

The 10-document series remains coherent with this v2 amend folded in.
