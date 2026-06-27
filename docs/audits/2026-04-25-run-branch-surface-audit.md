# `run_branch` Surface Audit

**Date:** 2026-04-25
**Author:** navigator
**Scope:** read-only audit. Answers questions A-F about the runner / `run_branch` action: signature, internal call chain, what `run_branch_version` would change, backward-compat surface, test footprint, convergence with dev-2-2's Task #54. NO design proposal. Lead routes redesign as follow-on.
**Surfaces read:** `tinyassets/universe_server.py:7248-7370` (`_action_run_branch`); `tinyassets/universe_server.py:4489-4510` (`_resolve_branch_id`); `tinyassets/runs.py:981-1040` (`_prepare_run`); `tinyassets/runs.py:1499-1565` (`execute_branch_async`); `tinyassets/runs.py:1603-1700` (`resume_run`); `tinyassets/runs.py:90-180` (runs DDL); `tinyassets/branch_versions.py:1-240` (publish + storage); `tinyassets/branches.py:692-741` (`BranchDefinition.from_dict`); `tests/test_run_branch_failure_taxonomy.py`, `tests/test_canonical_branch.py`, `tests/test_canonical_branch_mcp.py`, `tests/test_branch_name_resolution.py`, `tests/test_runs_schema_migration.py`.

---

## Summary

The runner today takes **only `branch_def_id`** (live editable identifier) — there is no path to invoke a frozen `branch_version_id` (content-hashed published snapshot). The two id concepts are storage-independent: `branch_def_id` lives in `branch_definitions` (live), `branch_version_id` lives in `branch_versions` (immutable). Canonical-binding points at the latter. So **a Goal's canonical_branch_version_id today cannot be invoked directly** — callers must (a) resolve the version's `branch_def_id`, then (b) pray the live definition still matches the snapshot the canonical was bound to.

There is also a *third* version concept: the runs table records an INTEGER `branch_version` per run-lineage row that tracks "what integer version of the live def was running here." This is unrelated to the content-hashed `branch_version_id` and exists for audit/diff purposes (`compare_runs`, "what changed since the last run"). Three version concepts, none of which currently route to each other end-to-end.

The minimal Phase A item 6 fix (per the primitive-shipment roadmap) is a `run_branch_version` action that resolves a `branch_version_id` → its frozen JSON snapshot → reconstructs a `BranchDefinition` → hands to `execute_branch_async`. The infrastructure exists; the action wiring does not. Backward-compat is clean: `run_branch` stays exactly as-is for live-def callers; `run_branch_version` is a sibling action.

This audit converges with dev-2-2's Task #54 (runner branch_def_id vs. branch_version_id mismatch design) — same gap, different framing. Convergence + divergence noted in §F.

---

## A. Today's `run_branch` action signature

**Location:** `tinyassets/universe_server.py:7248-7370` (`_action_run_branch`).

**Registry:** `_RUN_ACTIONS["run_branch"] = _action_run_branch` at line 8424. `run_branch` is in `_RUN_WRITE_ACTIONS` set at 8438 (mutates durable state, writes to runs table).

**Accepted params** (read from `kwargs`):

| Param | Type | Required | Notes |
|---|---|---|---|
| `branch_def_id` | str | YES | Accepts either a `branch_def_id` OR a branch *name* — `_resolve_branch_id` does case-insensitive fallback by name. |
| `inputs_json` | str | NO | JSON-encoded object of state-field initial values. Empty/missing = empty inputs. |
| `run_name` | str | NO | Display label for the run. |
| `recursion_limit_override` | str | NO | Integer 10-1000; overrides LangGraph's default recursion limit. |

**Not accepted:** `branch_version_id`. There is no parameter that would accept a content-hashed snapshot id. A caller passing `branch_version_id="foo@abc12345"` to this action gets the literal string treated as a `branch_def_id` candidate; `_resolve_branch_id` looks it up in `branch_definitions`, fails, and returns the original string (line 4510); then `get_branch_definition` raises `KeyError`; the action returns `{"error": "Branch 'foo@abc12345' not found."}`.

So the runner does not silently mis-resolve versions to defs — it simply has no version-aware code path.

**Returns:**
- Success: `{"status": "queued", "run_id": ..., "text": ...}` — async, run executes in background worker.
- Error (caught + classified): `{"error": ..., "failure_class": ..., "suggested_action": ...}` via `_classify_run_error` at 7338.

---

## B. Internal call chain — where `branch_def_id` threads through

```
MCP request
  │
  ▼
universe_server._action_run_branch(kwargs)              # ln 7248
  │
  ├─► _resolve_branch_id(bid_or_name, base_path)        # ln 7268 → ln 4489
  │     └─► (tries get_branch_definition, falls back to name lookup)
  │
  ├─► get_branch_definition(base_path, branch_def_id)   # ln 7273 → daemon_server:2002
  │     └─► returns dict (live snapshot from branch_definitions table)
  │
  ├─► BranchDefinition.from_dict(source_dict)           # ln 7277
  │     └─► branches.py:692 — reconstructs in-memory object
  │
  ├─► branch.validate()                                 # ln 7278
  │     └─► returns list of validation errors
  │
  ├─► json.loads(inputs_json) (if provided)             # ln 7289
  │
  ├─► provider_call resolution (lazy import)            # ln 7300-7307
  │
  ├─► recursion_limit_override parse (10-1000)          # ln 7310-7324
  │
  └─► execute_branch_async(...)                         # ln 7327 → runs.py:1499
        │
        ├─► _prepare_run(branch=branch, ...)            # runs.py:981
        │     ├─► create_run(base_path, branch_def_id=branch.branch_def_id, ...) ─► writes runs row
        │     ├─► record_event(...) per node ─► writes pending NODE_STATUS_PENDING events
        │     └─► record_lineage(branch_def_id, branch_version=int(getattr(branch,"version",1)))
        │           └─► writes run_lineage row with INTEGER branch_version (NOT branch_version_id)
        │
        └─► executor.submit(_worker)
              └─► _invoke_graph(branch=branch, ...)     # background; full LangGraph execution
                    └─► writes to runs table (status, output, error, finished_at)
```

**Key observation:** the runner consumes a `BranchDefinition` Python object, not an id. The id-shape is decoupled from execution as soon as `from_dict` lands. This makes `run_branch_version` straightforward — only the *resolution* step changes; everything downstream is unchanged.

**Three version concepts threaded through the system:**

1. **`branch_def_id`** — TEXT primary key on `branch_definitions`. Live, mutable. What the runner accepts today.
2. **`branch_version_id`** — TEXT primary key on `branch_versions`. Form `<branch_def_id>@<sha256_prefix8>`. Content-hashed, immutable. What `goals.canonical_branch_version_id` points at.
3. **`branch_version`** — INTEGER column on `run_lineage`. Tracks "what live-def version was running" — used for compare_runs / diff-since-parent. NOT related to `branch_version_id`.

The first two are storage-independent (different tables, no join). The third is a parallel audit-only concept.

---

## C. What `run_branch_version` would do differently

**The single load-bearing change:** resolve `branch_version_id` → frozen `BranchDefinition` at run time, instead of reading the live `branch_definitions` row.

The resolver step:

```python
# Today (run_branch):
source_dict = get_branch_definition(base_path, branch_def_id=bid)   # live row
branch = BranchDefinition.from_dict(source_dict)

# Tomorrow (run_branch_version):
version = get_branch_version(base_path, branch_version_id=bvid)     # branch_versions:182
if version is None:
    return error
source_dict = version.snapshot                                       # frozen JSON dict
branch = BranchDefinition.from_dict(source_dict)
```

That's the entire functional difference. `BranchDefinition.from_dict` already accepts dicts of the same shape — `_canonical_snapshot` in `branch_versions.py:_canonical_snapshot` produces a JSON form deserializable back into a BranchDefinition.

**Where the resolver should live cleanly:** I see three options. **My read of the code says it should live as a thin wrapper inside `runs.py`** alongside `execute_branch_async`. Reasoning:
1. The runner's contract is "give me a BranchDefinition + inputs, I run." Resolving id-shape before that is plumbing.
2. Putting it in `runs.py` means scheduler code, dispatcher code, and gate-routing code (Phase A item 5) can all share one resolver.
3. Putting it in the action handler (`_action_run_branch_version`) duplicates resolution logic at every call site (gate-routing nodes, scheduled invocations, dispatcher claims, etc.).

A sketch (NO DESIGN — just shape):

```python
# in runs.py
def execute_branch_version_async(
    base_path, *, branch_version_id, inputs, run_name, actor, ...
) -> RunOutcome:
    from workflow.branch_versions import get_branch_version
    version = get_branch_version(base_path, branch_version_id)
    if version is None:
        raise KeyError(...)
    branch = BranchDefinition.from_dict(version.snapshot)
    # ... validation, then delegate to existing _prepare_run + executor.submit path
```

This puts the resolver one layer below the MCP action, reusable by all version-aware callers.

**Other things `run_branch_version` should preserve / handle:**

- **Validation.** Frozen snapshots are validated at *publish* time, but the runner should still call `branch.validate()` defensively. A snapshot that was valid at publish might violate constraints introduced after (new validation rules in `branches.py`). Validation cost is low.
- **Lineage.** `_prepare_run`'s lineage write currently uses `branch.branch_def_id` (which IS in the snapshot). Fine. But the `branch_version` INTEGER column should ideally record the published version's identity, or a flag indicating "this run is from a frozen version." Leaving it as-is means version-runs and live-runs blend in the lineage table — workable for v1 but fuzzes "what was actually running."
- **Provider call resolution.** Today's `_action_run_branch` lazy-imports `domains.fantasy_author.phases._provider_stub`. This is domain-coupled (BUG-???: lives in the engine, references the fantasy domain). Worth not extending into `run_branch_version` — pass `provider_call` from the caller, which is the cleaner contract anyway.
- **Recursion-limit override.** Identical handling. Same accepted range (10-1000).
- **Async + executor + tracking.** Identical — `_prepare_run` + `executor.submit` work unchanged.

**No additional state migration needed.** The runs table already has `branch_def_id` (extracted from snapshot); `run_lineage` already has `branch_version` INTEGER; no new columns required. A future refinement would add a `branch_version_id` TEXT column to `runs` to record "this run executed against this frozen version" — but that's a separate scoping decision (see §F convergence with #54).

---

## D. Backward-compat surface

**Recommended: new sibling action `run_branch_version`, NOT a dual-arg overload of `run_branch`.**

Reasoning, ranked by importance:

1. **Different semantics.** `run_branch` runs the *live* def — picks up edits the user made since last run. `run_branch_version` runs a *frozen* snapshot — guaranteed reproducibility. These are different user intents; collapsing them into one action with optional args invites caller confusion ("if I pass both, which wins?").
2. **Different authority models long-term.** Live runs are author-permissioned; version runs may eventually be canonical-permissioned (a non-author can run their own scope's canonical even if the underlying branch is private). Different code paths make the authority delta cleaner.
3. **Existing callers unchanged.** Every test, every chatbot tool description, every cached MCP catalog entry continues to work. `run_branch` keeps its current contract verbatim.
4. **Discovery-friendly.** Tool catalog surfaces `run_branch_version` as its own verb with its own parameter doc. Casual users searching "run a frozen version" find it; current "run_branch" docs don't grow muddier.
5. **Mirrors the publish/list/get split.** `publish_version`, `get_branch_version`, `list_branch_versions` are already discrete actions. `run_branch_version` continues the convention.

**Signature for `run_branch_version` (sketched, not designed):**

| Param | Type | Required | Notes |
|---|---|---|---|
| `branch_version_id` | str | YES | Form `<branch_def_id>@<sha-prefix>`. Resolved via `get_branch_version`. |
| `inputs_json` | str | NO | Identical to run_branch. |
| `run_name` | str | NO | Identical. |
| `recursion_limit_override` | str | NO | Identical. |

**Errors to handle distinctly from `run_branch`:**

- `branch_version_id not found` — surface "version was unpublished or never published" hint.
- `snapshot_json fails to decode` — corrupted version row; should never happen but defense-in-depth.
- `BranchDefinition.from_dict(snapshot) raises` — schema drift between publish-time and run-time; surface "this version was published before a schema migration; needs re-publish."

The third is the most interesting failure mode. As the BranchDefinition schema evolves (new fields, deprecated fields), older snapshots may not deserialize. v1 should treat this as a graceful error, not a crash. v2+ may want a per-snapshot "schema_version" tag and migration shim.

**Also consider: should canonical-bound goals get a `run_canonical(goal_id, scope)` ergonomic wrapper?** Per Phase A item 3 (`lookup_canonical`), this is the obvious helper — reads the canonical, calls `run_branch_version` with it. Not in scope for #56 audit but flagging the convergence with item 3.

---

## E. Test footprint

**Files exercising `run_branch` today** (15+ test files reference `run_branch` and/or `branch_def_id`):

| Test file | What it covers |
|---|---|
| `tests/test_run_branch_failure_taxonomy.py` | Error classification (`empty_llm_response`, recursion, timeout, quota). 5 references to id-shape — all `branch_def_id`. |
| `tests/test_canonical_branch.py` | Canonical-binding storage layer. 26 references to id-shape — mix of `branch_def_id` and `branch_version_id` (since canonical points at version_id). Already has tests for canonical-version validation. |
| `tests/test_canonical_branch_mcp.py` | MCP-action wrapper for set_canonical. 7 references — runs canonical-binding MCP integration. |
| `tests/test_branch_name_resolution.py` | `_resolve_branch_id` name fallback path. |
| `tests/test_runs_schema_migration.py` | Runs table DDL + new `branch_version` lineage column. |
| `tests/test_branch_definitions_db.py` | Live `branch_definitions` table behavior. |
| `tests/test_branches.py` | `BranchDefinition` + `from_dict` round-trip. |
| `tests/test_node_ref_reuse.py` | Node-ref semantics across runs. |
| `tests/test_node_timeout.py` | Per-node timeout handling during execution. |
| `tests/test_outcome_evaluators.py` | RunOutcome shape + error classification. |
| `tests/test_bug_investigation_*.py` (3 files) | The bug-investigation pipeline that already wants to invoke a canonical version. **These tests are the strongest signal that `run_branch_version` is needed** — they currently work around the missing primitive by passing `branch_def_id` and assuming it matches the canonical's def. |
| `tests/test_community_branches_phase{2,3,4,5}.py` | Visibility + community-branch flows. |

**`run_branch_version` test additions needed:**

| Test class | Coverage |
|---|---|
| Happy path | Publish a version, then run it via `run_branch_version`. Assert run completes; assert lineage records the version. |
| Frozen snapshot beats live edit | Publish v1, then edit live branch_def, then run_branch_version on v1's id. Assert v1's behavior runs, NOT the edited live version's. **This is the load-bearing semantic test.** |
| Unpublished version_id | Pass a nonexistent `branch_version_id`. Assert structured error. |
| Corrupted snapshot | Stub a `branch_versions` row with broken `snapshot_json`. Assert graceful error, not crash. |
| Schema-drift snapshot | Publish under one schema, evolve `BranchDefinition.from_dict` to require a new field, re-run. Assert clear error message naming the schema mismatch. |
| Authority on canonical-bound version | Once Phase A item 1 (storage-layer authority refactor) lands, verify run_branch_version honors per-scope authority for version-id execution. |
| Lineage with parent_version_id | Publish v1, fork to v2 (parent_version_id=v1's id), run v2, assert lineage walks back via `parent_version_id`. |

**Test additions should NOT regress `run_branch`** — that action's tests stay intact verbatim.

**Estimated test footprint:** ~150 lines of new test code in `tests/test_run_branch_version.py` (new file). Plus 1-2 line additions in `test_canonical_branch_mcp.py` to add an end-to-end "set_canonical → run_branch_version on the canonical" smoke.

---

## F. Convergence + divergence with dev-2-2's Task #54

**Task #54 framing (from TaskList): "runner branch_def_id vs branch_version_id bridge."** Same primitive gap as roadmap Phase A item 6.

**Convergence:**

- **Both name the same gap:** runner accepts only live-def id; canonical points at frozen-version id; no bridge.
- **Both unblock the same downstream work:** Mark's gate series (gap #4 from G1 audit) needs to invoke a canonical version on send-back routing; the dispatcher's `enqueue_investigation_request` semantically wants to queue runs against canonical versions; scheduled-trigger flows want frozen-snapshot invocation for reproducibility.
- **Both observe the snapshot/from_dict round-trip already works** at the storage layer — `publish_branch_version` writes a deserializable JSON, `get_branch_version` returns it, `BranchDefinition.from_dict` reconstructs it. Plumbing is in place.

**Divergence (where this audit goes deeper than #54's brief):**

- **Three version concepts.** This audit names the `run_lineage.branch_version` INTEGER column as a third, unrelated version concept. #54's title only references the two. The three-concept reality affects `_prepare_run`'s lineage writes — where the version-aware run records its provenance.
- **Resolver placement.** #54 will likely propose a runner-side resolver. This audit recommends `runs.execute_branch_version_async` (one layer below the MCP action) for shared use across all version-aware call sites, not just the MCP action.
- **New sibling action vs. dual-arg overload.** Audit explicitly recommends sibling action with five reasons. #54 will need to make this call; flagging the recommendation here so it doesn't get re-litigated.
- **Schema-drift failure mode.** Audit names the deserializability-of-old-snapshots edge case as a real production concern. Test coverage explicitly required for this. #54 may or may not surface this depending on how design-narrow the brief is.
- **Convergence with `lookup_canonical` (Phase A item 3).** Audit notes the obvious downstream is `run_canonical(goal_id, scope)` — wrap version-resolution + run into one call. #54 might leave this as future work; flagging it here as a near-term ergonomic.

**No conflict** between this audit and what #54 will likely propose. Audit is shape-only; #54 is design. Audit's recommendations should land in #54's design doc as constraints/precedents.

---

## What this audit does NOT cover

- **Design proposal for `run_branch_version`.** Lead routes to dev-2-2's #54 (or new dispatch). Audit ends with sketches and constraints, not a full design.
- **Authority model deltas** between live-def and version invocation. Storage-layer authority refactor (roadmap Phase A item 1) is the prerequisite for any author/scope-driven authority on version invocation; out of scope here.
- **Scheduler / dispatcher integration.** Once `run_branch_version` exists, the scheduler and dispatcher want to invoke it. Wiring those callers is downstream work; audit only scopes the runner action itself.
- **`run_canonical(goal_id, scope)` ergonomic wrapper.** Flagged as obvious next-step composition with `lookup_canonical`; not designed here.
- **Live runtime probe.** Paper audit only. Behavior under a real running daemon (e.g., what error shape Claude.ai sees when invoking a missing version_id) is not verified.
- **Performance.** Frozen-snapshot deserialization is one extra JSON parse per run; expected sub-millisecond. Not benchmarked.

---

## References

- `tinyassets/universe_server.py:7248-7370` — `_action_run_branch`.
- `tinyassets/universe_server.py:4489-4510` — `_resolve_branch_id` (live-def resolver).
- `tinyassets/universe_server.py:8424` — `_RUN_ACTIONS` registry.
- `tinyassets/universe_server.py:8438` — `_RUN_WRITE_ACTIONS` set.
- `tinyassets/universe_server.py:8489` — `_action_publish_version`.
- `tinyassets/runs.py:981-1040` — `_prepare_run` + run_lineage write.
- `tinyassets/runs.py:1499-1565` — `execute_branch_async`.
- `tinyassets/runs.py:1603-1700` — `resume_run` (handles `branch_version_mismatch` reason).
- `tinyassets/runs.py:90-180` — runs + run_lineage + node_edit_audit DDL.
- `tinyassets/branch_versions.py:25-41` — `branch_versions` DDL.
- `tinyassets/branch_versions.py:109-179` — `publish_branch_version`.
- `tinyassets/branch_versions.py:182-239` — `get_branch_version` + `_row_to_version`.
- `tinyassets/branches.py:692-741` — `BranchDefinition.from_dict`.
- `tinyassets/daemon_server.py:2002` — `get_branch_definition` (live).
- `tests/test_run_branch_failure_taxonomy.py`, `tests/test_canonical_branch*.py`, `tests/test_branch_name_resolution.py`, `tests/test_bug_investigation_*.py`, `tests/test_runs_schema_migration.py`.
- Roadmap reference: `docs/design-notes/2026-04-25-primitive-shipment-roadmap.md` Phase A item 6.
- G1 audit: `docs/audits/2026-04-25-canonical-primitive-audit.md` Gap #4.
- Variant-canonicals proposal: `docs/design-notes/2026-04-25-variant-canonicals-proposal.md`.
