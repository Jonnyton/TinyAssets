---
title: Branch Substrate Token-Efficient Reads
date: 2026-05-11
author: codex-wiki-design
status: proposed
request_id: WIKI-DESIGN
github_issue: 794
wiki_source: pages/patch-requests/pr-105-branch-substrate-reads-must-be-token-efficient-read-branch-r.md
wiki_type: patch_request
scope: design-only; no runtime code in this branch
builds_on:
  - PLAN.md#scoping-rules
  - PLAN.md#api-and-mcp-interface
  - PLAN.md#state-and-artifacts
  - docs/audits/2026-04-25-mcp-response-size-audit.md
---

# Branch Substrate Token-Efficient Reads

## 1. Classification

This is a project-design request, not a runtime bug fix in this branch. The
reported failure is architectural: branch read surfaces return enough JSON to
consume a browser-chatbot context window before the chatbot can draft and send
the next `patch_branch` mutation.

The source wiki page is not present in this checkout, so this note is based on
Issue #794's filing text and current repository inspection.

## 2. Problem Shape

`build_branch` and `patch_branch` already learned the right response-size
lesson: summary by default, full branch only behind `verbose=true`. The read
side has not caught up. Current `extensions action=get_branch` returns the full
branch dictionary, including every node's `prompt_template`, `description`,
metadata, edges, conditional edges, related wiki pages, and gate adornments.
Current `describe_branch` is smaller than `get_branch`, but still returns a
large prose summary and graph text, not a machine-targeted edit contract.

For a user-chatbot authoring loop, this creates the wrong order of operations:

1. The chatbot needs a small branch view to decide the next patch.
2. It calls a read action and receives a wall of full branch JSON.
3. The wall pushes relevant instructions, branch intent, or planned mutation
   out of the active context.
4. The following `patch_branch` call is incomplete, malformed, or never made.

This is a control-station failure. The chat client should be able to inspect
the exact contract it needs for a mutation without loading full branch content.

## 3. Recommendation Summary

Implement read-side summary-by-default for branch substrate reads. Keep the
change inside the existing branch action surface rather than adding a new
top-level MCP tool.

The smallest useful runtime follow-up is:

1. Extend `get_branch` with compact default output, explicit `view=full` or
   `verbose=true`, field selection, and pagination over large collections.
2. Add a compact node contract read path, exposed either as
   `describe_node_contract` or as `get_branch view=node_contract`, that returns
   signatures needed for mutation without prompt bodies.
3. Add a delta-oriented branch summary path, exposed either as
   `branch_summary` or as `get_branch view=delta_summary`, that returns only the
   slice relevant to the caller's planned patch.

The naming can be decided during implementation, but the primitive boundary is
fixed: this belongs under the existing `extensions` branch surface. Do not add
a new top-level MCP primitive for branch reading.

## 4. Proposed Read Contracts

### 4.1 `get_branch` Compact Default

Default `get_branch` should return a bounded shape:

```json
{
  "branch_def_id": "...",
  "name": "...",
  "description": "...",
  "entry_point": "draft",
  "node_count": 14,
  "edge_count": 16,
  "conditional_edge_count": 2,
  "state_field_count": 8,
  "skill_count": 1,
  "valid": true,
  "runnable": true,
  "nodes_page": {
    "items": [
      {
        "node_id": "draft",
        "display_name": "Draft response",
        "phase": "draft",
        "input_keys": ["request"],
        "output_keys": ["draft"],
        "body_kind": "prompt_template",
        "body_chars": 1840
      }
    ],
    "offset": 0,
    "limit": 20,
    "next_offset": null
  },
  "edges_page": {"items": [], "offset": 0, "limit": 50, "next_offset": null},
  "state_schema_page": {"items": [], "offset": 0, "limit": 50, "next_offset": null}
}
```

The default must omit heavy node bodies: `prompt_template`, `source_code`,
`few_shot_references`, stats, and large metadata. It may include counts and
body lengths so the chatbot knows when a targeted detail read is needed.

Supported read controls:

- `view=compact|full|node_contract|delta_summary`; default `compact`.
- `fields_json=["nodes","edges","state_schema"]` for coarse field selection.
- `node_fields_json=["node_id","display_name","input_keys","output_keys"]`
  for node-level field selection.
- `offset` and `limit` for paginating `node_defs`; separate offsets may be
  added later for edges and state schema if needed.
- `include_bodies=false` by default; true only with explicit user intent or
  `view=full`.

Backward compatibility should follow the existing write-side convention:
`verbose=true` or `view=full` returns the old full branch shape.

### 4.2 Compact Node Contract

The node contract read path should answer: "What do I need to know to patch or
connect this node safely?"

For one node, return:

```json
{
  "branch_def_id": "...",
  "node_id": "draft",
  "display_name": "Draft response",
  "phase": "draft",
  "inputs": [{"name": "request", "type": "unknown"}],
  "outputs": [{"name": "draft", "type": "unknown"}],
  "incoming": ["START"],
  "outgoing": ["review"],
  "conditional_outcomes": {},
  "body_kind": "prompt_template",
  "body_chars": 1840,
  "editable_fields": [
    "display_name",
    "description",
    "phase",
    "prompt_template",
    "source_code",
    "input_keys",
    "output_keys"
  ]
}
```

For all nodes, return the same signature list paginated. This contract should
remain body-free unless the caller asks for a specific body field. A chatbot
can then compose `patch_branch` or `update_node` without carrying every prompt.

### 4.3 Delta-Relevant Branch Summary

The branch summary path should answer: "Which existing branch elements are
relevant to this intended mutation?"

Suggested input:

```json
{
  "branch_def_id": "...",
  "intent": "insert a citation audit node after draft and before review",
  "planned_ops_json": [
    {"op": "add_node", "node_id": "citation_audit"},
    {"op": "remove_edge", "from": "draft", "to": "review"},
    {"op": "add_edge", "from": "draft", "to": "citation_audit"},
    {"op": "add_edge", "from": "citation_audit", "to": "review"}
  ]
}
```

Suggested output:

```json
{
  "branch_def_id": "...",
  "relevant_nodes": [
    {"node_id": "draft", "input_keys": ["request"], "output_keys": ["draft"]},
    {"node_id": "review", "input_keys": ["draft"], "output_keys": ["review"]}
  ],
  "relevant_edges": [{"from": "draft", "to": "review"}],
  "state_fields": [{"name": "draft", "type": "str"}],
  "patch_hazards": [
    "Removing draft -> review requires replacement path to keep review reachable."
  ],
  "recommended_next_read": null
}
```

V1 does not need semantic search over the whole branch. It can mechanically
include nodes and edges named by `planned_ops_json`, their immediate neighbors,
entry point, touched state fields, validation errors, and source-code approval
warnings. Free-text `intent` can be accepted as a hint, not as proof.

## 5. Fit With PLAN.md

This follows the minimal-primitives rule because it reduces token cost inside
the existing branch primitive. `describe_node_contract` and `branch_summary`
are acceptable only as `extensions` branch actions or `get_branch` views, not
new top-level MCP tools.

It follows the control-station model because the chatbot is not the author of
branch content; it is steering existing branch state. The interface should
expose exactly enough typed state for the chatbot to make the next tool call.

It follows the state-and-artifacts principle because compact reads are typed
state, not hidden prompt memory. A small structured contract is more durable
than asking the chatbot to summarize a full branch wall and remember which
parts matter.

## 6. Implementation Boundary

Recommended Phase 1:

1. Add shared serializers in `workflow/api/branches.py` for compact branch,
   node contract, and paginated collections.
2. Change `get_branch` default to compact output while preserving full output
   under `verbose=true` or `view=full`.
3. Add focused tests with a large prompt-heavy branch proving default output is
   bounded and full output remains available.
4. Add action-description or branch-design-guide text that tells chatbots to
   use compact reads before patching and full reads only when inspecting prompt
   bodies.
5. Rebuild the Claude plugin mirror because this touches canonical
   `workflow/*` runtime files.

Recommended Phase 2:

1. Add `view=node_contract` or `describe_node_contract` once the compact
   branch serializer is stable.
2. Add `view=delta_summary` or `branch_summary` with mechanical extraction
   from planned ops.
3. Add a direct canary conversation on both Claude-family and ChatGPT-family
   clients showing: compact read -> single `patch_branch` mutation -> compact
   readback, without a full JSON branch wall.

## 7. Verification Gates

Runtime implementation should not be accepted without:

- Unit tests for compact default, `view=full` or `verbose=true`, field
  selection, pagination, and missing branch errors.
- A response-size regression test using a branch with at least 12 nodes and
  long prompt bodies. Default compact read should stay below a fixed byte cap;
  full read may exceed it only when explicitly requested.
- A patch-loop test showing a chatbot can fetch contracts for the touched
  nodes and produce a valid `patch_branch` operation without reading full node
  bodies.
- Opposite-family checker review, because this changes public MCP behavior.
- Rendered chatbot-surface verification through the live connector for the
  final public-surface claim.

## 8. Non-Goals

- No rewrite of `patch_branch` semantics.
- No new top-level MCP primitive.
- No branch storage migration.
- No semantic whole-branch planner in v1.
- No automatic prompt-template summarization as proof. The contract should be
  derived mechanically from stored branch fields.

## 9. Open Questions

1. Should compact default be a breaking change for `get_branch`, or should v1
   introduce `view=compact` first and flip the default after one release?
   Recommendation: flip now for chatbot safety, with `verbose=true` preserving
   the old shape.
2. Should `describe_branch` also become compact-by-default? Recommendation:
   leave it as prose summary initially and make `get_branch` the structured
   compact read path.
3. What byte cap should tests enforce? Recommendation: start with a 6 KB cap
   for default compact reads on a 12-node prompt-heavy branch, then tighten
   after live canary evidence.

## References

- Issue #794: WIKI-DESIGN / PR-105 branch-substrate reads
- `docs/audits/2026-04-25-mcp-response-size-audit.md`
- `workflow/api/branches.py` current `get_branch`, `describe_branch`,
  `build_branch`, and `patch_branch` handlers
- `PLAN.md` Scoping Rules
- `PLAN.md` API And MCP Interface
- `PLAN.md` State And Artifacts
