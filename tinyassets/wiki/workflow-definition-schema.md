---
title: Workflow Definition Schema
type: workflow-schema
audience: discovery
status: canonical
updated: 2026-07-21
tags: [workflow, branch, schema, spec_json, write_graph]
---

# Workflow Definition Schema

Create a workflow branch with the existing public graph-write handle:

```text
write_graph(target="branch", spec_json="<the JSON object below>")
```

Do not pass `branch_id` when creating. To edit an existing branch, pass its
`branch_id` and an ordered `changes_json` patch list instead.

## Minimal valid definition

```json
{
  "name": "Research claims tracker",
  "description": "Collect and review research claims",
  "entry_point": "collect",
  "node_defs": [
    {
      "node_id": "collect",
      "display_name": "Collect claims",
      "prompt_template": "Extract the important claims and their sources."
    }
  ],
  "edges": [
    {"from": "START", "to": "collect"},
    {"from": "collect", "to": "END"}
  ],
  "state_schema": [
    {"name": "topic", "type": "str"},
    {"name": "claims", "type": "list", "default": []}
  ]
}
```

The create is transactional: the server validates the full definition before
persisting it. Invalid definitions return concrete suggestions; no partial
branch becomes visible.

## Top-level fields

| Field | Required | Meaning |
|---|---|---|
| `name` | yes | Human-readable branch name. |
| `entry_point` | yes | First node id after `START`. |
| `node_defs` | yes | Node definition objects. |
| `edges` | yes | Directed edges, including a path from `START` to `END`. |
| `state_schema` | yes | Named state fields shared by nodes. |
| `description` | no | What the workflow accomplishes. |
| `skills` | no | Snapshotted text skills available as branch context. |
| `conditional_edges` | no | Label-to-node routing declared separately from normal edges. |
| `goal_id` | no | Shared Goal to bind after validation. |
| `fork_from` | no | Parent branch/version reference for lineage. |

## Node definitions

Every node needs a unique `node_id` and one implementation source:

- `prompt_template` for an LLM prompt node;
- `source_code` for an approved code node; or
- `node_ref` to copy a node from another branch.

Common optional fields are `display_name`, `input_keys`, `output_keys`,
`timeout_seconds`, `model_hint`, `llm_policy`, `retry_policy`, and `effects`.
`input_keys` and `output_keys` are JSON arrays of state-field names, never
comma-separated strings.

## Edges and state

- Normal edges use `{"from": "node_a", "to": "node_b"}`.
- Every workflow must be reachable from `START` and have a path to `END`.
- State fields use `name` plus a supported `type` such as `str`, `int`, `float`,
  `bool`, `list`, or `dict`.
- `default` is optional. Reducers are optional; without one, later writes
  replace earlier values.

After creation, inspect the result with `read_graph(target="branch",
branch_id="<returned branch id>")`, then execute it with
`run_graph(branch_def_id="<returned branch id>", inputs_json="{...}")`.
