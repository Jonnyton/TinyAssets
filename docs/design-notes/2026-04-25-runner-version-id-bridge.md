---
status: active
---

# Runner branch_version_id Bridge — Sibling-Action Proposal

**Date:** 2026-04-25
**Author:** dev-2
**Status:** Design proposal. Resolves G1 audit blocker #3 (`docs/audits/2026-04-25-canonical-primitive-audit.md`).
**Builds on:** Task #47 variant canonicals; Task #48 contribution ledger; Task #53 route-back verdict (hard dependency on this).
**Convergence:** navigator's run_branch audit (commit 4e608e3) — adopts §D's sibling-action recommendation.
**Scope:** schema/contract design only. No code changes.

---

## 1. Three options surveyed

| Option | Shape | Verdict |
|---|---|---|
| **(a) Accept-either: dual-arg `run_branch`** | Existing `run_branch` accepts EITHER `branch_def_id` OR `branch_version_id`. Internal dispatcher picks the path. | Initially considered; rejected after reconciling with navigator's audit §D — see §2 below. |
| **(b) Explicit `version_to_def` redirect verb** | New MCP verb that resolves `branch_version_id` → fresh `branch_def_id` for the runner to consume. | **REJECTED.** Re-creating a def from snapshot defeats the immutable-snapshot purpose. The fresh def is mutable post-resolve; ANYONE with edit rights can mutate it before the run starts. Race-prone and breaks the canonical's immutability invariant. |
| **(c) Extend canonical to also store `branch_def_id` at bind time** | `canonical_bindings` row carries both `branch_version_id` AND `branch_def_id` snapshot at bind. | **REJECTED.** `branch_def_id` content mutates over time. Two competing pointers create drift: either readers always prefer `branch_version_id` (then why store def_id?) or they pick by rule that drifts. Brief explicitly flagged as unsafe. |

## 2. Recommended — sibling action `run_branch_version`

Pick **a sibling MCP action `run_branch_version`** rather than dual-arg overload of `run_branch`. The runner's internal helper (`execute_branch_version_async`) is the shared implementation; the MCP-layer split is intentional.

### Why sibling-action, not dual-arg overload

Navigator's run_branch audit §D names three reasons that hold here:

1. **Discovery for chatbots.** A separate `run_branch_version` action surfaces in the MCP tool catalog as its own verb. Chatbots authoring gate-series searching for "how do I run a published canonical" find it directly. A dual-arg overload requires reading the docstring to discover the second path.
2. **Convention parity with `publish_version` / `list_versions` / `get_version`.** Versioned operations are already siblings, not overloads. Adding `run_branch_version` matches the existing namespace.
3. **Validation simplicity.** Each action validates exactly one arg shape. No "exactly-one-of" error class needed at the MCP layer; that lives only at the internal helper if it's ever called incorrectly.

The dual-arg path was tempting for "preserve all current callers" but the sibling-action path also preserves them — `run_branch` stays exactly as-is, untouched. Sibling-action wins on every axis.

### MCP action signature

```
extensions action=run_branch_version
  branch_version_id="<branch_def_id>@<sha8>"     # required
  inputs_json='{ ... }'                           # required, same shape as run_branch
  run_name=""                                    # optional
  recursion_limit_override=NN                    # optional, 10-1000
  → returns { run_id, status, error?, validation_errors? }
```

Behavior is identical to `run_branch` from the chatbot's perspective EXCEPT: the snapshot is loaded from `branch_versions.snapshot_json` (immutable), not from the live `branch_definitions` row. State_schema, edges, conditional_edges, entry_point are all read from the snapshot.

### Internal helper (where the actual bridge lives)

```python
# tinyassets/runs.py — new helper sibling to execute_branch_async
def execute_branch_version_async(
    base_path,
    *,
    branch_version_id: str,
    inputs: dict,
    run_name: str = "",
    actor: str = "anonymous",
    provider_call=None,
    recursion_limit_override: int | None = None,
) -> dict:
    """Execute a published branch_version snapshot (immutable)."""
    from workflow.branch_versions import get_branch_version
    bv = get_branch_version(base_path, branch_version_id=branch_version_id)
    if bv is None:
        raise KeyError(
            f"branch_version_id {branch_version_id!r} not found "
            "in branch_versions"
        )
    branch = BranchDefinition.from_dict(bv["snapshot"])
    return _execute_branch_core(
        base_path,
        branch=branch,
        inputs=inputs,
        run_name=run_name,
        actor=actor,
        provider_call=provider_call,
        recursion_limit_override=recursion_limit_override,
        # NEW: tag the run row with branch_version_id for attribution
        branch_version_id=branch_version_id,
    )
```

The shared `_execute_branch_core` is the existing run-execution path with one new optional arg. The current `execute_branch_async` (def-based) keeps using `_execute_branch_core` with `branch_version_id=None`. The new helper passes the id through. Both paths converge to the same execution loop.

---

## 3. Tradeoff table

| Axis | (a) dual-arg overload | (b) explicit redirect verb | (c) bind def_id at canonical | (recommended) sibling action |
|---|---|---|---|---|
| **Caller surface stability** | Existing `run_branch` callers untouched. New callers learn the second arg. | Existing untouched. New callers learn redirect dance. | Existing untouched. Canonical readers learn dual pointers. | Existing untouched. New callers find a clearly-named new verb. |
| **Discovery for chatbots** | Buried in docstring. | Two-step recipe; harder. | Schema introspection only. | Direct catalog hit. **Best.** |
| **Immutability honored** | Yes. | **No.** Re-created def is mutable. | **No.** def_id pointer drifts. | Yes. |
| **Validation cost** | Need "exactly-one-of" check. | New verb has its own validation. | Two-pointer reconciliation rules at every read. | Standard arg validation. |
| **Convention parity (publish/list/get_version)** | Breaks pattern. | Adds a new pattern. | Conflicts with version pattern. | **Matches existing pattern.** |
| **Runner internal complexity** | One dispatcher, two paths. | Two MCP verbs + one runner. | One runner + read-time pointer logic. | Two MCP verbs share one core internal helper. **Cleanest.** |
| **Migration path** | Additive. | Additive. | Schema migration on `canonical_bindings`. | Additive. |
| **Composition with #53 route-back** | Works. | Works (with the redirect dance). | Works but couples concerns. | Works. **Cleanest.** |
| **Test surface** | One handler with branching. | Two handlers + redirect resolver. | Test all canonical readers for pointer drift. | Two thin handlers + one core engine path. **Smallest.** |

Sibling-action wins or ties on every axis. The "convention parity" + "discovery" axes specifically tip the call away from dual-arg overload.

---

## 4. Implementation sketch

```python
# tinyassets/universe_server.py — new MCP handler sibling to _action_run_branch

def _action_run_branch_version(kwargs: dict[str, Any]) -> str:
    """Execute a published branch_version snapshot."""
    from workflow.runs import execute_branch_version_async

    _ensure_runs_recovery()

    bvid = (kwargs.get("branch_version_id") or "").strip()
    if not bvid:
        return json.dumps({"error": "branch_version_id is required."})

    inputs_raw = kwargs.get("inputs_json", "").strip()
    inputs: dict[str, Any] = {}
    if inputs_raw:
        try:
            parsed = json.loads(inputs_raw)
            if not isinstance(parsed, dict):
                return json.dumps({"error": "inputs_json must decode to a JSON object."})
            inputs = parsed
        except json.JSONDecodeError as exc:
            return json.dumps({"error": f"inputs_json is not valid JSON: {exc}"})

    # Recursion-limit parsing reused from _action_run_branch (lines 7310-7324).
    # ... same validation block ...

    try:
        outcome = execute_branch_version_async(
            _base_path(),
            branch_version_id=bvid,
            inputs=inputs,
            run_name=kwargs.get("run_name", ""),
            actor=_current_actor(),
            recursion_limit_override=recursion_limit_override,
        )
    except KeyError as exc:
        return json.dumps({"error": str(exc)})
    # ... existing error handling pattern from _action_run_branch ...
    return json.dumps(outcome, default=str)


# Registered alongside run_branch in _RUN_ACTIONS:
_RUN_ACTIONS["run_branch_version"] = _action_run_branch_version
```

The `_action_run_branch` handler at `universe_server.py:7248` is **untouched**. Existing callers keep working. The new handler is ~30 lines mirroring its sibling's validation logic.

### Schema addition (must land with this)

```sql
ALTER TABLE runs ADD COLUMN branch_version_id TEXT;
CREATE INDEX IF NOT EXISTS idx_runs_branch_version
    ON runs(branch_version_id);
```

NULLABLE so existing rows stay valid; ALTER is additive. The column gets populated only by `execute_branch_version_async`-originated runs. `execute_branch_async` (def-based) leaves it NULL.

**Why this column lands now, not later:**
- Task #48 contribution ledger needs it for `source_artifact_id` resolution at attribution time.
- Task #53 route-back's contribution event emit explicitly references the routed run's `branch_version_id`.
- Phase B lineage walk (Task #48 §4 bounty calc) joins `runs.branch_version_id` to the recursive `fork_from` chain.

Skipping the column now means a Schema Migration #2 in ~weeks. Add it once.

---

## 5. Migration plan

### Step 0 — schema add

`ALTER TABLE runs ADD COLUMN branch_version_id TEXT` + new index. Idempotent; runs on next daemon start. Zero changes to `branch_definitions`, `branch_versions`, `canonical_bindings`.

### Step 1 — internal helper lands

Add `execute_branch_version_async` to `tinyassets/runs.py`. Refactor `execute_branch_async` to call shared `_execute_branch_core(branch_version_id=None)`. Existing tests must continue passing — the refactor is shape-equivalent.

### Step 2 — MCP handler lands

Add `_action_run_branch_version` to `universe_server.py` registered in `_RUN_ACTIONS`. Add it to MCP tool catalog (whatever the tool-discovery surface is — see Task #28/#29 audit docs for the universe_server decomposition).

### Step 3 — chatbot tooling

The chatbot now sees `extensions action=run_branch_version` in the catalog. Direct invocation works. Task #53 route-back execution path uses this internally.

**Rollback:** drop the new MCP handler from `_RUN_ACTIONS`; the column on `runs` stays harmlessly NULL for new rows. Full revert = remove the column, but that's a forward-incompatible break for any in-flight contribution events from Task #48.

**No data loss.** All existing runs keep their `branch_def_id`. The new column only populates for new version-based runs.

---

## 6. Composition with Task #53 route-back

Task #53 route-back execution explicitly requires this proposal to ship first. The route-back handler:

1. Receives `EvalResult(verdict="route_back", route_to=(goal_id, scope))`.
2. Resolves (goal, scope) → `branch_version_id` via Task #47 fallback chain.
3. **Requires this proposal:** invokes `execute_branch_version_async(branch_version_id, inputs=patch_notes, ...)`.
4. Blocks synchronously per Task #53 §5 sync-only recommendation.
5. Inherits the routed run's terminal status as the gate-series's continuation signal.

Without this proposal, route-back would have to either:
- Use `execute_branch_async` against a fresh def created from snapshot (rejected option (b)).
- Pin a `branch_def_id` at canonical-bind time (rejected option (c)).

Both are unsafe. Sibling-action sync helper is the clean primitive.

**Sequencing reminder:** #54 lands before #53 implementation. The proposals are independent design docs; their landings are sequenced.

---

## 7. Open questions

1. **Validation when both args given to a hypothetical dual-action.** Moot — we picked sibling actions. Each handler validates its own single arg. **Closed.**

2. **Run row schema column add timing.** Per lead's pre-draft note: add `branch_version_id` column NOW as part of this proposal. **Closed — recommended in §4.**

3. **State-schema drift between `branch_versions.snapshot.state_schema` and current `branch_definitions.state_schema`.** When a version was published months ago and the live def has since gained/dropped state fields, version-based runs use the snapshot's schema (immutable invariant). Open Q: does the runner validate the inputs against the snapshot's schema OR the live def's? Recommend: **snapshot's**. The whole point of immutability is consistent behavior. Inputs that don't match the snapshot's schema fail validation.

4. **publish_version side effects on in-flight runs.** When a new version is published while runs are in flight, do those runs reference the new version_id, or stay tagged with their original? Recommend: **stay tagged with original**. Once a run starts, its `branch_version_id` (or NULL for def-based runs) is immutable. Re-tagging would obscure attribution.

5. **Cancellation semantics.** Per lead's note: **identical to def-based runs**. Same `run_cancels` table at `tinyassets/runs.py:129-132`. **Closed.**

---

## 8. What this proposal does NOT cover

- **No code changes.** Design only; lead routes implementation as separate dispatch.
- **No `run_branch` modification.** The existing handler at `universe_server.py:7248` is untouched. Backward compat preserved.
- **No route-back execution wiring.** That's Task #53. This proposal only declares the API the route-back handler will call.
- **No `branch_version_id` discovery surface for chatbots.** Existing `extensions action=list_versions` / `extensions action=get_version` MCP actions (per `branch_versions.py` namespace) cover discovery; not in scope here.
- **No schema-drift backfill.** Old runs with NULL `branch_version_id` stay NULL forever. No retroactive attribution from def-based runs to a version (would require unsafe def-mutation reasoning).
- **No version-based resume / interrupt recovery.** The existing terminal-on-restart guarantee for runs (per `_action_run_branch` docstring) applies identically to version-based runs.

---

## 9. References

- G1 audit blocker #3: `docs/audits/2026-04-25-canonical-primitive-audit.md`.
- Variant canonicals: `docs/design-notes/2026-04-25-variant-canonicals-proposal.md` (Task #47).
- Contribution ledger: `docs/design-notes/2026-04-25-contribution-ledger-proposal.md` (Task #48 — needs `runs.branch_version_id` for attribution).
- Route-back verdict: `docs/design-notes/2026-04-25-gate-route-back-verb-proposal.md` (Task #53 — hard dependency on this proposal).
- Navigator's run_branch audit: commit 4e608e3 (sibling-action recommendation, §D).
- Existing run handler: `tinyassets/universe_server.py:7248-7340` (`_action_run_branch`).
- Branch versions storage: `tinyassets/branch_versions.py:25-67` (DDL + dataclass).
- Publish helper: `tinyassets/branch_versions.py:109` (`publish_branch_version`).
- Run-cancel primitive (reused as-is): `tinyassets/runs.py:129-132` (`run_cancels` table).
