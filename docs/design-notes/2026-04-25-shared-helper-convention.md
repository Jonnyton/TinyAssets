---
status: active
---

# Shared-Helper Convention for Def/Version Sibling Primitives

**Date:** 2026-04-25
**Author:** navigator
**Status:** Convention doc. Captures a recurring pattern in the substrate before further primitives bake it in inconsistently.
**Builds on:** Task #54 (`runner-version-id-bridge`), Task #56 (`sub-branch-invocation-proposal`), v2 vision §2 meta-pattern.
**Scope:** project convention; not a code change.

---

## 1. Pattern statement

When a primitive has both a **live def** form (mutable, picks up edits) and a **frozen version** form (content-hashed snapshot, immutable), the right shape is:

```
thin def-form  ────────┐
                       │
                       ├──→  shared core helper  ──→ execution
                       │
thin version-form  ────┘
```

- **Thin def-form**: caller-facing entry point for live-def usage. Resolves `branch_def_id` → BranchDefinition, calls core.
- **Thin version-form**: caller-facing entry point for frozen-version usage. Resolves `branch_version_id` → frozen BranchDefinition, calls core.
- **Shared core**: takes a resolved BranchDefinition + the original ids (so it can record provenance), runs execution. **Single source of truth for the actual work.**

The split is at the **resolution boundary**, not at the **execution boundary**. Both forms converge on the same execution loop.

---

## 2. Existing instances

### Instance 1 — Runner (#54)

| Layer | Symbol | Source |
|---|---|---|
| Thin def-form | `execute_branch_async(branch=...)` | `tinyassets/runs.py` |
| Thin version-form | `execute_branch_version_async(branch_version_id=...)` | `tinyassets/runs.py` (NEW per #54) |
| Shared core | `_execute_branch_core(branch=..., branch_version_id=None)` | `tinyassets/runs.py` (NEW per #54) |
| MCP wrappers | `_action_run_branch` (existing) + `_action_run_branch_version` (NEW) | `tinyassets/universe_server.py` |

The version-form resolves `branch_version_id` via `get_branch_version` → `BranchDefinition.from_dict(snapshot)` → calls `_execute_branch_core` with `branch_version_id` populated for run-row provenance.

### Instance 2 — Sub-branch invocation (#56)

| Layer | Symbol | Source |
|---|---|---|
| Thin def-form spec | `invoke_branch_spec` (existing) on NodeDefinition | `tinyassets/branches.py` |
| Thin version-form spec | `invoke_branch_version_spec` (NEW per #56) on NodeDefinition | `tinyassets/branches.py` |
| Thin def-form builder | `_build_invoke_branch_node` (existing) | `tinyassets/graph_compiler.py` |
| Thin version-form builder | `_build_invoke_branch_version_node` (NEW per #56) | `tinyassets/graph_compiler.py` |
| Shared core | `_DispatchInvokeBranchCommon` (NEW per #56) | `tinyassets/graph_compiler.py` |

`_DispatchInvokeBranchCommon` holds the input-mapping + output-mapping + `on_child_fail` policy logic. The two builders construct closures around it; the only difference between def-form and version-form is the resolution step (`get_branch_definition` vs. `get_branch_version`).

---

## 3. When to apply

Apply this pattern whenever a new primitive needs to operate on either a live def OR a frozen version of the same underlying entity. Likely future candidates:

- **`cancel_run` / `resume_run`** — when a run was launched against a version_id, cancellation/resume should respect that provenance, not silently fall through to the live def. Today both take `run_id` only; if version-aware semantics ever surface as a need, this pattern applies.
- **`bid_on_branch` / paid-market claims** — bidding on a known frozen version (production canonical) is a different decision than bidding on a live def (in-development). Two thin verbs + shared-core bid logic.
- **`clone_branch` / `fork_branch`** — forking from a live def vs. forking from a frozen version are different lineage events. Same primitive shape, different `fork_from` provenance.
- **`describe_branch` / introspection verbs** — when introspection should reflect "what was running" (frozen) vs. "what would run now" (live). Today `describe_branch` is def-only.
- **Cross-run state query** — a query against runs of a specific def vs. against runs of a specific version. Probably one query verb with optional version filter; if the resolution logic grows, factor.

---

## 4. When NOT to apply

The pattern is overhead when the primitive is inherently single-shape:

- **Pure live-edit operations** — `add_node`, `connect_nodes`, `patch_branch`, `update_branch_definition`. Versions are immutable; editing a version is meaningless. Def-only.
- **Pure version-archive operations** — `publish_version`, `list_branch_versions`, `get_branch_version` archive history readers. Defs are mutable; "publishing a def" is exactly the act of creating a version. Version-only.
- **Operations that consume opaque ids without semantic discrimination** — e.g. a hypothetical `delete_artifact(id)` that doesn't care whether it's a def or version. Don't artificially fork.
- **Read-only catalog enumeration** — `list_branches`, `list_branch_versions` already separate by table; pattern is implicit, no shared core needed.

The decision rule: **does the work this primitive does differ between the two id shapes?** If yes, apply the pattern. If no, don't.

---

## 5. Naming convention

- **Shared core**: `_<verb>_core` (snake_case, leading underscore for module-internal). Examples: `_execute_branch_core`, `_DispatchInvokeBranchCommon`. The latter uses CamelCase because it's a closure factory rather than a function — convention follows existing project usage, not strict.
- **Thin def-form**: `<verb>` (no suffix). Existing callers find it where they expect it. Examples: `execute_branch_async`, `invoke_branch_spec`.
- **Thin version-form**: `<verb>_version` (suffix `_version`). Examples: `execute_branch_version_async`, `invoke_branch_version_spec`. Mirrors `branch_version_id` naming.
- **MCP action wrappers**: `_action_<verb>` (existing) and `_action_<verb>_version` (NEW). Example: `_action_run_branch` + `_action_run_branch_version`.

The suffix `_version` is preferred over `_v2` or `_frozen` because it explicitly names the resolution mechanism (a `branch_version_id`), not a generic versioning concept.

---

## 6. Test convention

- **Shared core has its own test file.** Tests cover the actual work (graph execution, state mapping, etc.) without duplicating dispatch logic. Examples: `tests/test_execute_branch_core.py`, `tests/test_dispatch_invoke_branch_common.py`.
- **Thin wrappers test the dispatch layer only.** Verify "given def_id, calls core with resolved BranchDefinition + branch_version_id=None"; verify "given version_id, calls core with resolved BranchDefinition + branch_version_id=<id>". Don't re-test execution semantics — that's the core's responsibility.
- **One semantic test per shape pair**: "frozen snapshot beats live edit" (publish v1, edit live def, run v1 via version-form, assert v1's behavior runs). This is the load-bearing semantic test that proves immutability — must exist.
- **Schema-drift error path**: tests should cover the `BranchDefinition.from_dict(snapshot)` raises case (snapshot was published before a schema migration). Per pair-read #59, surface as `failure_class="snapshot_schema_drift"`.

---

## 7. Refactor priority

**Existing instances are already ratified at design layer:**
- `_execute_branch_core` is named in #54 §2 (committed `dc7d2cb`) — implementation is the precursor refactor for Phase A item 6.
- `_DispatchInvokeBranchCommon` is named in #56 §3 — implementation is part of Phase A item 5a dispatch.

**Pair-read recommendation already captured (per #59 §3 + #60 §4):**
- The `_execute_branch_core` extraction should be its own dispatch unit BEFORE the new helper-add work, so the refactor's behavior-preservation can be verified against existing tests in isolation.
- Same pattern applies to `_DispatchInvokeBranchCommon`: extraction first, then new spec field + new builder layered on.

**Next instance to ratify against this convention:** when Task #59 (`goals action=resolve_canonical`) lands, check whether resolution naturally splits into a def-form + version-form pair (it might be version-only since canonicals point at versions; in that case the pattern doesn't apply). If a future cross-run state query primitive surfaces, apply.

---

## 8. Open questions

1. **Should the shared core be exported (no leading underscore) for cross-module use?** Today `_execute_branch_core` is module-private. If future callers (scheduler, dispatcher, gate-routing) need to invoke it, the underscore signals "internal" and discourages reuse. Recommendation: keep underscore for now; promote to public if external callers materialize. Avoid premature exposure.

2. **Does the pattern compose with the dispatcher / claim layer?** Phase A items + Phase B contribution ledger may need the dispatcher to claim by version_id (frozen) vs. def_id (live) — same shape pattern at the claim layer. Worth checking whether `dispatcher.prefers_request_type` needs a `branch_version_id` claim filter analog. Not in scope here; flag for #59 / dispatcher-evolution work.

3. **Should the `_v2` / `_frozen` alternative naming be reserved for primitives that aren't def/version but do have two shapes?** E.g. a primitive with two completely different semantic shapes (not just live vs. frozen) might want a different suffix. Not yet a real case; leaving open in case it surfaces.

---

## 9. References

- v2 vision: `docs/design-notes/2026-04-25-self-evolving-platform-vision-v2.md` §2 meta-pattern.
- Instance 1: `docs/design-notes/2026-04-25-runner-version-id-bridge.md` (#54).
- Instance 2: `docs/design-notes/2026-04-25-sub-branch-invocation-proposal.md` (#56).
- Pair-reads ratifying both: `docs/audits/2026-04-25-pair-54-vs-56-convergence.md` §3 + §4; `docs/audits/2026-04-25-pair-50-vs-56-convergence.md` §4.
- Run_branch surface audit (origin of the resolver-placement recommendation): `docs/audits/2026-04-25-run-branch-surface-audit.md` §B + §D.
- Schema-drift test concern (per #59 §3): pair-read #59 §1 Divergence 4.
