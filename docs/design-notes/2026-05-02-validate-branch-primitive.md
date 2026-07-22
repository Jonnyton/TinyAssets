---
title: validate_branch — pre-run validation primitive (BUG-044 prep)
date: 2026-05-02
author: dev (claude-code)
status: design (pre-dispatch)
audience: lead, navigator, dev (whoever picks up the work row)
gates_on: navigator dispatch + Codex's #23/#25 land (avoid runs.py / branches.py overlap)
companion:
  - .claude/agent-memory/navigator/2026-05-01-bug044-045-scoping.md (verdict: structural primitive gap)
  - workflow/branches.py:874 (existing `BranchDefinition.validate()` — most of the work is done)
  - workflow/graph_compiler.py:46 (CompilerError) + L1957 (compile-time validate gate)
  - PLAN.md "Engine and Domains" L340 + Module Layout L113 (validate_branch is engine, not domain)
  - PLAN.md L162 trust-critical-tools / self-auditing-tools pattern
  - docs/design-notes/2026-04-19-self-auditing-tools.md
load_bearing_question: How should the existing `validate_branch` MCP action be extended to catch BUG-044 + sibling shape gaps?
---

## 1. Problem

`run_branch` fails *after starting* on a class of authoring errors that are statically detectable from the branch shape. Mark's `change_loop_v1` is the live failure case (BUG-044): a node_id collides with a state_schema key, the chatbot's `build_branch` / `add_node` / `patch_branch` calls all accept the spec without error, and only `run_branch` surfaces the failure — by then a Run row exists with all-pending node_statuses and a wasted compile attempt.

**Both the in-process validator AND the MCP-callable surface already exist.** `BranchDefinition.validate()` at `workflow/branches.py:874` runs a comprehensive in-process shape check; `_ext_branch_validate` at `workflow/api/branches.py:662` is the registered MCP `validate_branch` action (action map at L2525) that wraps it and returns `{branch_def_id, valid, errors, runnable, unapproved_source_code_nodes, sandbox_warnings}`. The action is exercised today by `tests/test_community_branches_phase2.py:314`.

**The work item is narrower than it first looked: extend the existing `validate_branch` action with the shape-checkable failure modes the underlying `validate()` doesn't catch yet** — most importantly node_id-vs-state_key collision (BUG-044), plus six sibling gaps. The MCP surface already exists; no new tool is needed.

**Hard Rule #8 fail-loudly upgrade (load-bearing for the value proposition):** the §3.b new checks land in `BranchDefinition.validate()` itself. `graph_compiler.compile_branch` at L1957 already calls `validate()` as its pre-flight gate — every `run_branch` invocation will pick up the new checks automatically and raise `CompilerError` at compile time instead of failing mid-run. Pre-flight earlier = fail loudly earlier. This is not a side benefit; it's half the value.

The validation gap is acknowledged in code at `workflow/branches.py:11`:

> "Phase 3 — state_schema is stored as an unvalidated JSON blob (formal validation deferred to Phase 3)."

## 2. Why platform-ship, not community-evolve

Per Scoping Rule 1 (minimal primitives) + Rule 2 (community-build over platform-build), check the structural-impossibility test:

- **Validation is engine-level** per PLAN.md "Engine and Domains" (L340) — the engine owns graph correctness; domains own content. Branch-shape validation is the engine's contract with the chatbot, not a per-domain concern.
- **No primitive composes around this gap.** The chatbot can't reproduce LangGraph's compile-time checks from prompt-template tricks. There's no smaller primitive set the chatbot could combine to get "this branch will compile cleanly."
- **Trust-critical-tools pattern (PLAN.md L162, `2026-04-19-self-auditing-tools.md`)** applies: a community-composed approximation of the validator would diverge from the real compiler, producing false greens that look correct until `run_branch` fails. Validation is exactly the kind of evidence-bearing tool that must come from the engine, not from the chatbot's reasoning over partial shape introspection.
- **The primitive already exists end-to-end.** `BranchDefinition.validate()` is comprehensive; `_ext_branch_validate` is its MCP wrapper; `validate_branch` is the registered action. The work is extending the underlying validator with seven additional checks — not introducing a new action.

Verdict: extend in place.

## 3. Collision classes (what the validator must catch)

Read off `workflow/graph_compiler.py` `raise CompilerError` sites (31 raises) plus `workflow/branches.py` (1 raise) = 32 CompilerError raises total, plus `BranchDefinition.validate()` checks (`workflow/branches.py:874-1115`) and the existing `_ext_branch_validate` envelope (`workflow/api/branches.py:662-720`). Three tiers:

### 3.a. Statically detectable from branch shape (validate() catches today)

These are caught by `BranchDefinition.validate()` and bundled into `compile_branch`'s pre-flight at L1957. A `validate_branch` MCP action is a thin wrapper over the existing `validate()` return value:

1. **Empty / missing branch name** (`branches.py:892`).
2. **Empty graph** — no `node_defs` and no `graph_nodes` (L895).
3. **Duplicate node_def IDs** (L900).
4. **Duplicate graph_node IDs** (L907).
5. **Missing entry_point when graph has nodes** (L917).
6. **Entry_point references undefined node** (L919).
7. **Graph node references unknown `node_def_id`** (L924).
8. **Edge from-node / to-node references undefined node** (L933).
9. **Conditional edge from-node / target references undefined node** (L946).
10. **Orphan nodes** — graph nodes unreachable from entry_point or START (L959).
11. **Cycles without an exit to END** (L971).
12. **Duplicate state_schema field names** (L983).
13. **Prompt-template placeholders not in input_keys ∪ state_schema** (L998 — the build-time half of the runtime CompilerError at compiler.py:802 / 808).
14. **`default_llm_policy` shape errors** (L1013).
15. **Per-node `llm_policy` shape errors** (L1019).
16. **Checkpoint shape errors** — duplicate checkpoint_id, missing earns_fraction, cumulative > 1.0 (L1026, helper at L517).
17. **`invoke_branch_spec` validation** — missing `branch_def_id`, invalid `wait_mode`, mutual-exclusion with prompt_template/source_code, output_mapping vs parent state_schema (L1038).
18. **`invoke_branch_version_spec` validation** — missing `branch_version_id`, `wait_mode`, `on_child_fail` shape, mutual-exclusion with both `prompt_template/source_code` AND `invoke_branch_spec` (L1063).
19. **`await_run_spec` validation** — missing `run_id_field`, mutual-exclusion (L1103).

### 3.b. Already surfaced by the EXISTING `validate_branch` envelope (not in `validate()`, but in the wrapper)

The MCP action wrapper at `workflow/api/branches.py:662-720` already adds two failure surfaces on top of `validate()`:

20. **Unapproved `source_code` nodes** — returned as `unapproved_source_code_nodes: [{node_id, display_name}]`. Filed against BUG-031. The chatbot sees the list and routes to the approval flow before `run_branch`.
21. **`requires_sandbox=True` nodes when host bwrap is unavailable** — returned as `sandbox_warnings: [str]`. Non-fatal warning surface; the run still proceeds but the chatbot can warn the user.

These already exist; mentioning them here so contributors don't re-add them. The work item below extends the envelope further.

### 3.c. Statically detectable but NOT caught today (the BUG-044 + sibling gaps)

The primary work item. These are validatable from the spec without compile/run, but `validate()` doesn't currently check them:

22. **node_id collides with state_schema key** (BUG-044 root). LangGraph's `StateGraph.add_node(node_id)` raises "is already being used as a state key" when `node_id` matches a TypedDict field name. Surfaces only after compile starts. Fix: cross-check `seen_graph` ids against the state_schema field-name set in `validate()`. Reserved names `START`/`END` are already excluded from graph_nodes; the new check is `seen_graph ∩ field_names == ∅`.
23. **`source_code` contains disallowed pattern** (`graph_compiler.py:983` raises `CompilerError`). Pure-shape checkable; complements the existing unapproved-source-code surface.
24. **Node has both `prompt_template` and `source_code`** (`graph_compiler.py:1781` runtime raise). `validate()` checks invoke-spec mutual exclusion but not template-vs-source.
25. **Node has neither prompt_template / source_code / invoke_*_spec / await_run_spec / opaque-domain registration / capability-pack body** (`graph_compiler.py:1841` runtime raise). The "body-less node" case. **Forward-compat caveat:** per `project_node_software_capabilities`, a future external-tool node-kind with `required_capabilities` declared but no template/source/invoke/await is *valid* (the body is the host-installed software). The check must whitelist nodes that declare a capability-pack body; otherwise it rejects a legitimate node-kind that's already in the design pipeline.
26. **`invoke_branch_spec.branch_def_id` references nonexistent branch** (validate-time DB read; today only fails at run when `get_branch_definition` returns None). Optional — adds a DB read to validate, may want a flag to skip for performance.
27. **`invoke_branch_version_spec.branch_version_id` references nonexistent version**. Same caveat.
28. **JSON-output-contract structural mismatch** (`graph_compiler.py:944,952,961` runtime raises on parse failure / missing key / coercion failure). Cannot be statically validated without running the LLM — *out of scope*; included here so the design note explicitly draws the boundary.

The new checks (22–27) are additions to `BranchDefinition.validate()`. Once added, `compile_branch`'s pre-flight at L1957 picks them up automatically — i.e., the existing run path ALSO gets the new checks, not just the existing MCP action. (See §1 — this is the load-bearing fail-loudly upgrade.)

### 3.d. NOT statically detectable (out of scope for validate_branch)

Document the boundary so the chatbot doesn't expect false confidence:

- Provider availability / fallback chain correctness at run-time (covered by `get_status` self-auditing surface per PLAN.md L290).
- Empty-LLM-response / response-not-JSON / output-coercion failures (run-time only, see BUG-029 + BUG-038 + BUG-039 cluster).
- LLM-template producing prose instead of JSON (model-behavior, not shape).

Sandbox unavailability is partly covered today via §3.b's `sandbox_warnings`; richer host-state checks (e.g., bwrap version drift) remain run-time-only.

A `validate_branch` green verdict means **the branch shape is statically correct AND the host's static gates are satisfied**. It does NOT mean a run will succeed. The response envelope must say so explicitly.

## 4. Proposed shape

### 4.a. Recommendation: extend the existing `validate_branch` action in place (Option D)

Earlier drafts pressure-tested a new-action vs. fold-into-`describe_branch` decision. Both premises were wrong: `validate_branch` already exists at `workflow/api/branches.py:662` (`_ext_branch_validate`), registered in the action map at L2525, exercised by `tests/test_community_branches_phase2.py:314`. The handler already returns `errors`, `unapproved_source_code_nodes`, and `sandbox_warnings`.

**Recommendation: Option D — extend the existing `validate_branch` action with §3.c new checks, `class`-string envelope, and `caveat` text. No new tool surface; `describe_branch` stays describe-only.**

Why Option D dominates the alternatives:

- **Scoping Rule 1 is satisfied via the primitive that already exists**, not by adding one. The tool count stays flat; the action gets richer checks.
- **The action is already named "validate."** Folding into `describe_branch` (the previously-recommended Option B) would have added validation work to a tool already doing its own job; Option D extends a tool already named for the job.
- **Trust-critical-tools compliance for `describe_branch` is one line**: include `"validation_status": "see validate_branch"` in the `describe_branch` envelope so a chatbot reading describe knows where to ask for shape-correctness evidence. No payload duplication.
- **Backward compat is automatic.** The existing `valid` / `errors` / `runnable` keys stay; new fields (`class` strings, `caveat`, `checks_run`) are additive.
- **`validate()` return-type refactor blast radius is contained.** 7 internal call sites total: `workflow/api/branches.py` (5 — including the existing `_ext_branch_validate` itself), `workflow/api/runs.py` (1), `workflow/graph_compiler.py` (1). Zero external callers. Mechanical refactor.

Earlier alternatives A/B/C all assumed `validate_branch` did not exist. Drop them.

### 4.b. Response envelope extension (additive on the existing surface)

The existing `_ext_branch_validate` returns:

```json
{
  "branch_def_id": "...",
  "valid": true | false,
  "errors": ["..."],                          // string list today; becomes structured per below
  "runnable": true | false,
  "unapproved_source_code_nodes": [{...}],
  "sandbox_warnings": ["..."]
}
```

Extension turns `errors` into a list of structured records and adds `checks_run` + `caveat`:

```json
{
  "branch_def_id": "...",
  "valid": true | false,
  "errors": [
    {
      "class": "node_id_collides_with_state_key",
      "node_id": "investigation_gate",
      "state_key": "investigation_gate",
      "message": "Node 'investigation_gate' has the same id as a state_schema key. LangGraph's compile step will reject this. Rename the node or the state key.",
      "fix_hint": "rename_node OR rename_state_key"
    },
    ...
  ],
  "runnable": true | false,
  "unapproved_source_code_nodes": [...],            // unchanged from today
  "sandbox_warnings": [...],                        // unchanged from today
  "checks_run": ["node_id_collides_with_state_key", "duplicate_node_ids", "edge_target_exists", ...],
  "checks_skipped": [],
  "caveat": "Static shape validation only. Provider availability, LLM output shape, and bwrap-version drift are not checked — see get_status for runtime evidence."
}
```

`class` values are stable strings (one per item in §3.a + §3.c). The chatbot's user-facing narrative composes over `errors[].class` + `fix_hint`, not over `message` text — text drift is allowed; class drift is breaking.

`checks_run` + `checks_skipped` matter when an opt-in DB-read class is added (e.g., #26/#27 cross-branch existence). If the validator skips a class for performance, the response says so explicitly.

`describe_branch` adds ONE field, not the full envelope: `"validation_status": "see validate_branch"`. That satisfies the trust-critical-tools "structured caveat" expectation without payload duplication.

### 4.c. Engine-level changes

1. Extend `BranchDefinition.validate()` at `workflow/branches.py:874` with the six new checks from §3.c (items 22–27; #28 is out of scope per §3.d). Each new check returns a stable `class` string alongside the error message. The capability-pack forward-compat caveat for #25 is part of the implementation, not a follow-up.
2. Refactor `validate()` return type from `list[str]` → `list[ValidationError]` (a small dataclass with `class: str`, `node_id: str | None`, `state_key: str | None`, `edge: tuple[str, str] | None`, `message: str`, `fix_hint: str`). **Keep `ValidationError` internal** — module-private (`_ValidationError`), don't export from `workflow.branches` in v1. Reduces public-API surface to revisit. Refactor blast radius is contained: 5 call sites in `workflow/api/branches.py`, 1 in `workflow/api/runs.py`, 1 in `workflow/graph_compiler.py` — 7 internal sites total, 0 external. Mechanical: callers that want strings call `[e.message for e in result]`.
3. Extend the existing `_ext_branch_validate` handler at `workflow/api/branches.py:662` to emit the new envelope: serialize each `_ValidationError` to its dict shape, populate `checks_run` from the validator's run-list, populate `caveat`. ~20 LOC delta. The action map registration at L2525 stays.
4. Add the one-line `validation_status` pointer to the `describe_branch` envelope (handler shares the same module).
5. Plugin mirror for both files (canonical → mirror parity).

### 4.d. Non-changes

- `compile_branch` at L1957 keeps calling `validate()` and raising `CompilerError` on errors — see §1; the new checks land there automatically.
- Existing `BranchValidationError` at `workflow/branches.py:2153` (the load-time exception class) is orthogonal — that fires on persisted-row corruption, not on authoring shape. Out of scope.
- The existing `unapproved_source_code_nodes` and `sandbox_warnings` keys stay in the response. Do not collapse them into `errors` — they're separate failure tiers (one is approval-pending; one is host-state warning) and folding them into the unified errors list would lose that semantic.

## 5. Out of scope (for navigator's later atomization)

- New capabilities (e.g., a "fix this branch" action that auto-renames colliding ids). Validation surfaces the problem; resolution is a separate primitive.
- Runtime-state validation (provider chain correctness, JSON-output coercion, bwrap-version drift). Owned by `get_status` per the self-auditing-tools rollout.
- Cross-branch reference validation (#26, #27 above) on the default path. Add as opt-in `include_cross_branch_checks: bool = false` if/when host wants it; otherwise skip.
- BUG-045 plumbing (`invoke_branch_spec` thread-through in `_apply_node_spec`). Tracked separately per navigator memo §"BUG-045"; pure plumbing, ~30-45 min.
- Public `ValidationError` dataclass export. Keep internal in v1.

## 6. Proposed test surface

Extend `tests/test_community_branches_phase2.py` (the existing `validate_branch` test home — `:314`) with one test per new collision class in §3.c (items 22–27) for happy + sad paths. ~12-14 tests, many trivially parametrizable. Plus envelope-shape tests asserting:

- `errors[].class` is present, stable across calls.
- `checks_run` is populated (non-empty list).
- `checks_skipped` is `[]` by default.
- `caveat` present and non-empty.
- Existing keys (`valid`, `errors`, `runnable`, `unapproved_source_code_nodes`, `sandbox_warnings`) keep their semantics.

If the existing test file is already large, a second file `tests/test_validate_branch_classes.py` can carry the new shape-check coverage without bloating the phase-2 file.

Existing `BranchDefinition.validate()` tests (search `tests/test_branch_definitions_db.py` + `tests/test_branches.py` at dispatch) likely already cover §3.a; the new tests focus on §3.c additions + envelope shape.

Live MCP probe via `mcp_probe.py --tool branches --args '{"action":"validate_branch","branch_def_id":"<bad>"}'` → expect `valid=false` with the right `class` strings, `caveat` present, existing keys unchanged.

## 7. Effort estimate

Smaller than the v1 draft (which assumed building the action surface + handler from scratch). Revised breakdown:

- §3.c new validation checks (6 items, #28 skipped as out-of-scope): 2-3h. Most are 5-10 LOC each over the existing `validate()` body; #25 capability-pack forward-compat adds ~10 LOC for the whitelist; #26/#27 cross-branch DB-read checks are larger and optional in v1.
- `_ValidationError` dataclass (internal) + class-string registry + return-type refactor: 1-2h. 7 internal call sites (5 in `workflow/api/branches.py`, 1 in `workflow/api/runs.py`, 1 in `workflow/graph_compiler.py`) — all mechanical.
- Existing `_ext_branch_validate` handler envelope extension: 30-45min. ~20 LOC delta. The action surface and registration already work.
- `describe_branch` `validation_status` pointer: 5min. One line.
- Test surface: 2-3h (down from 3-5h; existing test file means scaffolding is reused).
- Plugin mirror parity + ruff + targeted pytest: 30-60min.

**Total: 6-9h** (was 8-13h in v1 draft). Still fits the navigator-cited 1-2 dev-day estimate; closer to the lower end now that the handler doesn't need to be created.

## 8. Dispatch readiness

This memo is dispatch-ready when:

1. Lead picks Option D per §4.a (or pushes back).
2. Codex's #23 + #25 land (Arc B Phase 2 + 3) — both touch `tests/` and `workflow/api/branches.py` neighborhoods; sequencing avoids merge conflict.
3. The work row is filed with a Files cell naming `workflow/branches.py`, `workflow/api/branches.py`, the plugin mirrors, plus the test extensions.
4. BUG-045 is filed separately (per navigator memo §"BUG-045"; ~30-45 min plumbing) and does not block this row.

---

**Cross-refs:**
- Navigator scoping memo: `.claude/agent-memory/navigator/2026-05-01-bug044-045-scoping.md`.
- Existing validator: `workflow/branches.py:874` (`BranchDefinition.validate()`).
- Existing MCP action handler: `workflow/api/branches.py:662` (`_ext_branch_validate`).
- Action map registration: `workflow/api/branches.py:2525` (`"validate_branch"`).
- Existing test: `tests/test_community_branches_phase2.py:314`.
- Compile-time validation gate: `workflow/graph_compiler.py:1957`.
- Capability-pack forward-compat: memory `project_node_software_capabilities`.
- Self-auditing-tools pattern: `docs/design-notes/2026-04-19-self-auditing-tools.md`.
- Scoping Rules 1 + 2: `PLAN.md:25-43`.
- Engine-and-Domains principle: `PLAN.md:340`.
- Trust-critical-tools cross-cutting: `PLAN.md:162`.
- BUG-044 wiki page slug: `bug-044-change-loop-v1-compile-fails-because-node-id-collides-with-s`.
- BUG-045 (sibling, separate dispatch): same navigator memo §"BUG-045".
