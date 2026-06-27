# MCP Response Size Audit — build_branch / patch_branch

**Date:** 2026-04-25
**Trigger:** ChatGPT "Something went wrong while generating the response" on multi-node branch builds (Mark's bug-to-patch workflow).
**Scope:** `_ext_branch_build`, `_ext_branch_patch`, `_action_run_branch`.

---

## Measured Sizes — Pre-Fix

All measurements use a representative node with a realistic prompt_template (~600 chars).

| Action | Node count | Current (bytes) | Summary (bytes) | Reduction |
|--------|-----------|----------------|-----------------|-----------|
| build_branch | 3 | 4,806 | 496 | 90% |
| build_branch | 5 | 7,508 | 496 | 93% |
| build_branch | 8 | 11,567 | 496 | 96% |
| build_branch | 12 | 16,991 | 499 | 97% |
| patch_branch | 3 | 4,893 | 495 | 90% |
| patch_branch | 5 | 7,595 | 495 | 93% |
| patch_branch | 8 | 11,654 | 495 | 96% |
| patch_branch | 12 | 17,081 | 501 | 97% |

**ChatGPT estimated stream budget:** ~32,000 bytes.
Even a 3-node branch with detailed prompt templates was pushing 5 KB, and real-world branches with longer prompts routinely exceed 30 KB on 8+ nodes.

---

## Size Driver

The `"branch": saved` field in both success responses is the full serialized `BranchDefinition` dict. It contains:

- Full `node_defs` list — each with `prompt_template`, `description`, `tags`, `stats`, `few_shot_references`, timestamps
- Full `edges` + `conditional_edges` lists
- `state_schema` dict
- All metadata fields

The `prompt_template` alone can be 300–2,000 chars per node. For an 8-node branch, the saved dict is ~11 KB, which is the entire response payload.

`run_branch` was **not a problem** — it returns `run_id + status`, always lean.

---

## Fix Applied

**SUMMARY by default; full post-state via `verbose=true`.**

Both `_ext_branch_build` and `_ext_branch_patch` now:

1. Read a `verbose` kwarg (truthy = `"true"`, `"1"`, `"yes"`).
2. Default response (verbose=false): `{text, status, branch_def_id, name, node_count, edge_count, entry_point, validation_summary}` — ~500 bytes for any branch size.
3. `verbose=true` response: adds `"branch": saved` — full backwards-compatible shape.

`patch_branch` retains the `patched_fields` and `post_patch` identity block in both modes — the BUG-030 readback invariant is satisfied.

**Files changed:**
- `tinyassets/universe_server.py` — canonical
- `packaging/claude-plugin/plugins/tinyassets-universe-server/runtime/tinyassets/universe_server.py`
- `packaging/dist/tinyassets-universe-server-src/tinyassets/universe_server.py`

---

## Contract Change Note

Existing chatbots that parsed the `"branch"` field from the default response will no longer receive it. The field still exists under `verbose=true`.

Known chatbot consumers of the `"branch"` field: none identified in prompts.py rules. The `post_patch` identity block (always present) covers the BUG-030 use case. Add `verbose=true` to any script/flow that needs the full post-state definition.

---

## Verification Targets

- Default response is SUMMARY shape and < 5 KB for any branch size.
- `verbose=true` returns full post-state (regression of pre-fix behavior).
- `patched_fields` always present in patch_branch response.
- BUG-030 readback invariant: `post_patch.branch_def_id` always present.
