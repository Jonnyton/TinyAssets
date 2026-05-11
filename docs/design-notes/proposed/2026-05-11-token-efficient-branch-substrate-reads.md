---
title: Token-Efficient Branch Substrate Reads
date: 2026-05-11
author: codex-wiki-design
status: proposed
request_id: WIKI-DESIGN
github_issue: 795
wiki_source: pages/patch-requests/pr-105-branch-substrate-reads-must-be-token-efficient-read-branch-r.md
wiki_type: patch_request
scope: design-only; no runtime code in this branch
builds_on:
  - PLAN.md#scoping-rules
  - PLAN.md#canonical-work-substrate-vocabulary
  - PLAN.md#api-and-mcp-interface
  - workflow/api/branches.py actions get_branch, describe_branch, patch_branch
---

# Token-Efficient Branch Substrate Reads

## 1. Recommendation Summary

Add token-efficient branch read projections before expanding branch mutation
behavior. The smallest useful project change is a read-side contract that lets
chatbots inspect only the branch fields needed for the next `patch_branch`
mutation:

- field-selectable and paginated `read.branch` behavior over the existing
  branch read surface;
- `describe_node_contract` for compact node signatures;
- `branch_summary` for the delta-relevant slice needed to plan a patch.

This is not a request to redesign branch authoring. It is a context-budget fix
for browser-chatbot users: current `get_branch` style reads can return a
3,400+ token JSON wall before the chatbot has enough room left to generate one
valid `patch_branch` call. The observed PR-104 Phase 1 canary from the
Cowork+ChatGPT dev partnership on 2026-05-11 is direct evidence that full
branch reads are blocking cross-provider patch completion.

## 2. Classification

This filing is `project-design`. It describes an architectural/API contract
gap rather than a localized runtime defect. Implementation should wait for a
follow-up code-change lane with an opposite-family checker, because the
runtime surface affects public MCP behavior and branch mutation workflows.

## 3. Current Shape

`workflow/api/branches.py` already exposes:

| Existing action | Current role | Token problem |
|---|---|---|
| `get_branch` | returns the full branch definition plus gate, wiki, approval, and runnable metadata | too large for patch planning on nontrivial branches |
| `describe_branch` | returns compact topology, validation state, approval warnings, mermaid, related pages | omits enough node contract detail that a chatbot often has to call `get_branch` anyway |
| `patch_branch` | applies transactional ordered patch ops | requires exact node/state/edge context to avoid rejected ops |

The gap is not mutation expressiveness. The gap is selective inspection. A
chatbot needs enough structure to choose a patch, but the only complete read
path overfeeds the context window.

## 4. Contract

Treat these as `read.graph` branch projections in the canonical substrate
vocabulary. Concrete action names may remain compatible with the existing
`extensions` action router.

### 4.1 `read.branch` Projection

`read.branch` is a field-selectable branch definition read. If implemented as
an extension of `get_branch`, the action should keep existing behavior when no
projection parameters are supplied.

Suggested parameters:

| Parameter | Meaning |
|---|---|
| `branch_def_id` | required branch id or resolvable branch name |
| `fields` | optional comma-separated top-level fields, such as `metadata,state_schema,nodes,edges,validation,approval,lineage,wiki` |
| `node_fields` | optional comma-separated node fields, such as `node_id,display_name,phase,inputs,outputs,state_reads,state_writes,llm_policy,requires_sandbox,approved` |
| `node_ids` | optional comma-separated node ids to return |
| `offset` | optional node pagination offset, default `0` |
| `limit` | optional node pagination limit, default `25`, server-capped |
| `include_large_fields` | optional boolean, default `false`; gates `prompt_template`, `source_code`, long examples, and other high-token fields |

Response shape:

```json
{
  "branch_def_id": "branch_...",
  "name": "Citation audit",
  "projection": {
    "fields": ["metadata", "state_schema", "nodes"],
    "node_fields": ["node_id", "display_name", "state_reads", "state_writes"],
    "offset": 0,
    "limit": 25,
    "total_nodes": 64,
    "truncated": true
  },
  "metadata": {},
  "state_schema": [],
  "nodes": [],
  "next_offset": 25
}
```

Error handling should preserve the existing not-found and private-branch
non-disclosure behavior. Projection parameters must not leak private branch
existence.

### 4.2 `describe_node_contract`

`describe_node_contract` returns compact signatures for one or more nodes. It
is the read path a chatbot should use before patching a node.

Suggested parameters:

| Parameter | Meaning |
|---|---|
| `branch_def_id` | required branch id or resolvable branch name |
| `node_ids` | required comma-separated node ids, or `entry_point` as a special selector |
| `include_examples` | optional boolean, default `false`, capped when true |

Response shape:

```json
{
  "branch_def_id": "branch_...",
  "nodes": [
    {
      "node_id": "extract_claims",
      "display_name": "Extract claims",
      "kind": "prompt",
      "phase": "analysis",
      "inputs": ["source_text"],
      "outputs": ["claims"],
      "state_reads": ["source_text"],
      "state_writes": ["claims"],
      "llm_policy": {"source": "node", "provider": "default"},
      "patchable_fields": ["display_name", "prompt_template", "llm_policy"]
    }
  ]
}
```

Do not include full prompt templates or source code by default. The default
contract is a signature, not a body dump.

### 4.3 `branch_summary`

`branch_summary` returns the delta-relevant slice for patch planning. It should
answer: "What can I safely change next, and what identifiers must I preserve?"

Suggested parameters:

| Parameter | Meaning |
|---|---|
| `branch_def_id` | required branch id or resolvable branch name |
| `focus` | optional text such as `node:<id>`, `state`, `edges`, `approval`, `validation`, or `patch:<free text>` |
| `include_recent_runs` | optional boolean, default `false`; if true, return capped run references only |

Response shape:

```json
{
  "branch_def_id": "branch_...",
  "name": "Citation audit",
  "entry_point": "extract_claims",
  "counts": {"nodes": 12, "edges": 14, "state_fields": 8},
  "validation": {"valid": true, "error_count": 0, "errors": []},
  "approval": {"runnable": true, "unapproved_source_code_nodes": []},
  "patch_targets": [
    {
      "node_id": "extract_claims",
      "display_name": "Extract claims",
      "state_reads": ["source_text"],
      "state_writes": ["claims"],
      "patchable_fields": ["prompt_template", "llm_policy"]
    }
  ],
  "recommended_next_reads": [
    {"action": "describe_node_contract", "node_ids": "extract_claims"}
  ]
}
```

`branch_summary` is acceptable despite being a convenience because it closes a
structural gap: without a server-side delta slice, the chatbot must first read
the full branch wall to decide which smaller read would have been useful.

## 5. Scoping Rule Fit

This clears the minimal-primitives rule only if implemented as projections of
the existing branch read family, not as a broad collection of unrelated
chatbot conveniences. The primitive is selective graph inspection under
`read.graph`.

It supports community-build over platform-build because it lets users and
chatbots patch community branches without requiring platform-authored special
cases for each branch shape. The platform owns the context-budget substrate;
the community still owns the branch content and patch policy.

It supports the user capability axis because browser-only MCP users have the
least context and tool-call slack. A fix that works in ChatGPT Developer Mode
and Claude.ai also benefits local-app users, but the design should be tested
against browser-chatbot context limits first.

## 6. Implementation Boundary

A follow-up implementation should be narrow:

1. Add projection parameters to the existing branch read handler or add
   compatible read actions in the branch action map.
2. Reuse existing branch resolution, privacy checks, validation, approval, and
   related-page helpers.
3. Keep old `get_branch` behavior unchanged when no projection params are
   supplied.
4. Add focused tests that prove large prompt/source fields are omitted by
   default, pagination caps nodes, and private branches keep not-found
   behavior for non-owners.
5. Rebuild the Claude plugin mirror if `workflow/*` runtime files are touched.

Out of scope:

- Changing `patch_branch` op semantics.
- Rewriting community-authored branches.
- Adding run execution, merge, approval, or source-code approval behavior.
- Renaming the canonical `read.graph` MCP handle.

## 7. Verification Gates

Before runtime merge, require:

- Unit tests for projection field selection, node pagination, node-contract
  signatures, branch-summary focus, and private branch non-disclosure.
- A focused token-budget canary using a branch large enough that legacy
  `get_branch` exceeds the usable chatbot planning budget.
- A rendered browser-chatbot verification through the live connector where the
  chatbot performs: summary read, node contract read, one `patch_branch`
  mutation, and a compact verification read without exhausting context.
- Opposite-family review of both the contract and the canary evidence.
- Post-fix real-user or loop-use watch item if no actual user has cleanly used
  the affected path after deployment.

## 8. Open Questions

1. Should the compatibility surface be `get_branch` parameters only, or new
   action aliases named `read_branch`, `describe_node_contract`, and
   `branch_summary` under the existing `extensions` router? Recommendation:
   prefer `get_branch` projection parameters for backward compatibility, then
   add aliases only if chatbot tool-selection evidence shows aliases reduce
   mistakes.

2. What default node pagination cap should ship? Recommendation: start at 25
   nodes and cap at 100 unless the canary proves a smaller browser-chatbot
   budget is needed.

3. How should `focus="patch:<free text>"` be implemented? Recommendation:
   defer semantic ranking unless a deterministic selector cannot satisfy the
   PR-104 canary. Field selection and explicit `node_ids` should land first.

## References

- Issue #795 / WIKI-DESIGN
- `PLAN.md` Scoping Rules
- `PLAN.md` Canonical Work Substrate Vocabulary
- `PLAN.md` API And MCP Interface
- `workflow/api/branches.py` branch actions: `get_branch`, `describe_branch`,
  `patch_branch`
