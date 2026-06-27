---
status: active
---

# Named-Checkpoint Decision-Routing Contract

**Date:** 2026-04-25
**Author:** dev-2
**Status:** Design proposal. Closes self-evolving-platform-vision §4 row "Decision-routing (named-checkpoint contract)" — partial→full.
**Builds on:** Task #53 route-back verdict; Task #57 surgical rollback (caused_regression metadata extension); attribution-layer-specs §1.5.
**Scope:** schema/contract design only. No code changes.

---

## 1. Recommendation summary

Add `decision_checkpoints: dict[str, str]` field to `BranchDefinition`. Maps stable checkpoint names to graph node_ids. `conditional_edges` and gate decisions reference checkpoint names via `@<name>` syntax; engine resolves at compile time.

**Top tradeoff axis:** decoupling decision contract from graph topology. Today's `conditional_edges` reference raw node_ids; renaming a node breaks every routing reference. Named checkpoints provide a stable layer between "what the gate decides" and "which node implements that target."

---

## 2. Schema

```python
# tinyassets/branches.py — extend BranchDefinition
@dataclass
class BranchDefinition:
    # ... existing fields ...
    decision_checkpoints: dict[str, str] = field(default_factory=dict)
    # Maps "checkpoint_name" → "graph_node_id". Conditional edges and gate
    # decisions may reference "@checkpoint_name" instead of raw node_ids.
    # Engine resolves at compile time. See validation rules in §4.
```

### Naming — `decision_checkpoints`, not `checkpoints`

`tinyassets/branches.py:217` already has `checkpoints: list[dict[str, Any]]` on **NodeDefinition** for per-node **partial-credit checkpoints** (escrow + gate-bonus distribution per `project_designer_royalties_and_bounties`). That's a different concept on a different object.

Disambiguating with `decision_checkpoints` prevents confusion:
- `NodeDefinition.checkpoints` — per-node partial-credit (escrow primitive).
- `BranchDefinition.decision_checkpoints` — branch-level routing (decision-routing primitive).

### Reference syntax

In `conditional_edges`, gate decision targets, and route-back fields, the `@` prefix marks "this is a checkpoint reference, resolve it":

```python
# Today (raw node_id):
{"from": "gate", "conditions": {"accept": "publish", "revise": "draft"}}

# With named checkpoints:
{"from": "gate", "conditions": {"accept": "@patch-applied", "revise": "@manual-review"}}
```

Both forms continue to work — proposal is additive; migration is opt-in.

### Reserved checkpoints

`@END` and `@START` are reserved at engine level. They always resolve to LangGraph's special `END` / `START` node ids regardless of `decision_checkpoints` content. Authors cannot override these by adding their own `END` or `START` keys to `decision_checkpoints` — `validate()` rejects (per §4 rule 4).

---

## 3. Lookup primitive

Internal helper in `tinyassets/branches.py`:

```python
def resolve_checkpoint(branch: BranchDefinition, target: str) -> str:
    """Resolve a routing target to a graph_node_id.

    Args:
        target: either a raw node_id, "START", "END", or an @-prefixed
            checkpoint reference (e.g., "@manual-review").

    Returns:
        The resolved graph_node_id.

    Raises:
        KeyError: if target is "@<name>" but <name> is not in
            branch.decision_checkpoints.
    """
    if not target.startswith("@"):
        return target  # raw node_id, START, or END passes through
    name = target[1:]
    if name in {"START", "END"}:
        return name  # engine-reserved, regardless of decision_checkpoints
    if name not in branch.decision_checkpoints:
        raise KeyError(
            f"Checkpoint '@{name}' not declared in branch.decision_checkpoints. "
            f"Available: {sorted(branch.decision_checkpoints.keys())}"
        )
    return branch.decision_checkpoints[name]
```

### Compile-time resolution

`tinyassets/graph_compiler.py` (in `_compile_conditional_edges` and any future `_compile_route_back_targets` for Task #53 integration):

```python
for cond_edge in branch.conditional_edges:
    for outcome, target in cond_edge.conditions.items():
        resolved = resolve_checkpoint(branch, target)
        # Build the LangGraph conditional edge with `resolved` (a real node_id)
```

Resolution happens once at compile time — runtime edges carry node_ids only. No per-decision lookup overhead.

### Runtime preserves checkpoint identity for observability

While the compiled graph uses resolved node_ids, the engine retains the original `@<name>` reference in run metadata for downstream observers (attribution events, run trace, navigator triage):

```python
# When emitting a run_event from a conditional edge transition:
run_event = RunStepEvent(
    ...,
    detail={
        "transition_from": cond_edge.from_node,
        "transition_to": resolved_node_id,
        "transition_via_checkpoint": original_target,  # "@manual-review" or None
    },
)
```

This is the bridge to attribution-layer-specs §1.5 (caused_regression metadata) — see §6.

---

## 4. Validation rules

`BranchDefinition.validate()` extension. All rules apply at branch-validate time (compose-time, not run-time):

1. **Key shape.** Every key in `decision_checkpoints` MUST be a non-empty string. No leading `@`. No spaces. Recommend `^[a-z][a-z0-9-]*$` shape (lowercase + hyphens), but only the first three rules are MUST.
2. **Target validity.** Every value MUST be either (a) a `graph_node_id` that exists in `branch.graph_nodes`, OR (b) the literal string `"START"` or `"END"`.
3. **Reference resolvability.** Every `@`-prefixed target appearing in `conditional_edges[*].conditions[*]` MUST resolve to either (a) a key in `decision_checkpoints`, OR (b) `@START` / `@END`. Dangling references are an ERROR, not a warning. (Mirrors navigator's #60 discipline: "validate-time ERROR not warning".)
4. **Reserved-name rejection.** Authors cannot use `START` or `END` as keys in `decision_checkpoints`. The engine treats these as reserved targets; allowing override is a foot-cannon.
5. **No alias cycles.** A checkpoint cannot point at another checkpoint reference. `decision_checkpoints` values are graph_node_ids, never `@<name>` strings. Validator catches this directly.

Errors surface in `BranchDefinition.validate()` return list, same shape as existing validation errors.

---

## 5. Migration of existing branches

**Purely additive. No breaking changes.**

- Existing branches: `decision_checkpoints = {}` (dataclass default). Their `conditional_edges` use raw node_ids; `resolve_checkpoint` passes them through unchanged. Behavior identical to today.
- New branches: authors opt in by populating `decision_checkpoints` and using `@<name>` syntax in conditional_edges where stability matters.

Branch authors can mix raw node_ids and checkpoint references freely — the resolver handles both. Recommended pattern: name checkpoints for **routing anchors** (gate targets, retry-points, integration-test entries); leave linear edges as raw node_ids.

### Optional follow-up tooling (out of scope)

A `extensions action=convert_to_checkpoints branch_def_id=...` MCP action could scan a branch's `conditional_edges`, identify nodes referenced from multiple decision sites, and propose a `decision_checkpoints` map. Manual today; deferred to v2 per Q4 lead-approval.

### Per-node-id alias support (Q2 lead-approved)

A single graph_node_id MAY appear under multiple checkpoint names:

```python
decision_checkpoints = {
    "manual-review": "review_node",
    "tier-1-integration-test": "review_node",  # same node, different semantic
}
```

Useful for "this node is the manual-review target AND the tier-1 integration-test target initially; we may split them later." Authors get the option without a structural change.

---

## 6. Composition with other primitives

### Task #53 route-back (cross-branch routing)

Task #53's `route_to: tuple[goal_id, scope_token]` is goal-level routing — a different layer. This proposal is BRANCH-INTERNAL. Both coexist:

- Within-branch decisions use `@checkpoint_name` (this proposal).
- Cross-branch decisions use `route_to` (Task #53) + Task #47's resolver.

A gate-series can mix: gate decides `verdict="route_back"` with `route_to` for goal-level escalation; another gate decides `accept` with `@manual-review` for branch-internal routing. Different verdicts, different layers, no interaction.

### Task #57 surgical rollback / attribution-layer-specs §1.5

Per lead's note: when a regression is attributed to a specific node and that node is the target of a checkpoint, the `caused_regression` event metadata records the checkpoint name as well as the node_id:

```python
ContributionEvent(
    event_type="caused_regression",
    actor_id=...,
    source_run_id=...,
    source_artifact_id=branch_version_id,
    weight=-3,  # P1
    metadata_json=json.dumps({
        "node_id": "review_node",
        "checkpoint_name": "manual-review",  # NEW — semantic anchor
        "canary": "PROBE-003",
    }),
)
```

Aids navigator triage. "The regression was at the @manual-review checkpoint, not the underlying review_node implementation" — checkpoint name carries semantic intent that node_id cannot.

### Task #56 sub-branch invocation

`invoke_branch_spec.output_mapping` and `invoke_branch_version_spec.output_mapping` reference parent state keys, not graph node_ids — orthogonal to checkpoints. No interaction.

---

## 7. Open questions

1. **Wildcard checkpoints (`@*`):** REJECTED. Keep one-name-one-target for v1. Wildcards invite "delete-all-routing-targets" foot-cannons. Closed per lead pre-draft note.

2. **Per-node-id aliases (multiple checkpoints → same node):** APPROVED. Validator allows; useful for semantic overlay during branch evolution. Closed.

3. **Cross-branch checkpoint references:** REJECTED for v1. Cross-branch routing goes through goals/canonicals (Task #47/#53). Branch-internal stays branch-internal. Closed.

4. **Migration tooling (`convert_to_checkpoints` MCP action):** Deferred to v2. Manual frontmatter editing for now. Closed.

5. **Default checkpoints (`@start`/`@end` auto-create):** REJECTED. `@START` / `@END` are reserved engine targets, separate from user-defined checkpoints. Don't conflate. Closed.

6. **(Truly open) Per-checkpoint metadata.** A future need: checkpoints carrying author intent (description, expected-arrivals-rate, severity-of-regression-here). Recommend deferring; current `dict[str, str]` is the smallest sufficient v1 schema. Extending to `dict[str, CheckpointSpec]` is non-breaking when needed.

7. **(Truly open) Checkpoint deprecation / rename.** When a branch evolves and a checkpoint name needs to change without breaking external references (e.g., gate definitions in OTHER branches that reference this branch's checkpoint via Task #47/#53), how does deprecation work? Recommend deferring — cross-branch checkpoint refs are out-of-scope (Q3) so the problem doesn't bite v1; revisit when cross-branch refs land.

---

## 8. What this proposal does NOT cover

- **No code changes.** Design only; lead routes implementation as separate dispatch.
- **No `convert_to_checkpoints` MCP action.** Q4 deferral.
- **No cross-branch checkpoint references.** Q3 deferral.
- **No per-checkpoint metadata.** Q6 deferral; `dict[str, str]` is the v1 schema.
- **No automatic refactoring of existing `conditional_edges`.** Authors opt in manually.
- **No checkpoint version-id pinning** (analogous to Task #54's branch_version_id discipline). Checkpoint mappings live in the BranchDefinition; that definition itself can be published as an immutable version. Pinning at finer granularity is unnecessary.

---

## 9. References

- Closes self-evolving-platform-vision §4 row "Decision-routing": `docs/design-notes/2026-04-25-self-evolving-platform-vision.md` line 122.
- Composes with route-back verdict: `docs/design-notes/2026-04-25-gate-route-back-verb-proposal.md` (Task #53).
- Composes with surgical rollback / `caused_regression` metadata: `docs/design-notes/2026-04-25-surgical-rollback-proposal.md` (Task #57); attribution-layer-specs §1.5.
- Disambiguates from existing `NodeDefinition.checkpoints` (partial-credit primitive): `tinyassets/branches.py:205-217`.
- Existing routing primitive being extended: `tinyassets/branches.py:307-308` (`conditional_edges` shape) + `:339-358` (`EdgeDefinition`).
- Compile site: `tinyassets/graph_compiler.py` (whichever `_compile_conditional_edges` or equivalent function builds the LangGraph CompiledGraph from `BranchDefinition`).
- Validate site: `tinyassets/branches.py:920-960` (`BranchDefinition.validate()`).
