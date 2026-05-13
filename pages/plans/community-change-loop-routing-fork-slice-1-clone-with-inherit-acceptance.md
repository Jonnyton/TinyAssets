---
title: Slice-1 clone-with-inherit substrate acceptance
type: plan
status: working-draft
source_issue: 856
wiki_source_path: pages/plans/community-change-loop-routing-fork-slice-1-clone-with-inherit-acceptance.md
wiki_source_updated: 2026-05-13T05:08:19.752550Z
wiki_source_sha256: 0031ac0f69bab4591edf19f6276ae602431727dae65baae0dd9152badc534b9a
---

# Slice-1 — clone-with-inherit substrate acceptance

**Status:** WORKING DRAFT — depends on [[Move-A patch_request]] landing in substrate.
**Authors:** claude-code (claude-opus-4-7) + ChatGPT (dev-partner via `chatgpt_chat.py` CDP route).
**Lineage:** Slice-0 ([[default-change-loop-v1-slice-0-routing-policy-probe]]) discovered six compounding substrate gaps blocking the original "fork experiment_designer and amend" target. ChatGPT reshaped slice-1 acceptance around closing the single highest-leverage gap (Move A: clone-with-inherit).

## Why slice-1 has narrow acceptance

ChatGPT's exact verdict 2026-05-13:

> "Move A is the actual unlock. Either fork_from must clone inherited node_defs, edges, state schema, tags, and parent metadata into a new draft branch, or there needs to be an explicit clone_branch action. Without that, 'fork this live loop and amend one node' remains impossible... Slice 1 should be reshaped around Move A: clone-with-inherit."

Slice-1 is therefore not "build a feature." It is "verify the substrate primitive needed to make slice-0's original goal executable." Once slice-1 acceptance lands, slice-0 can re-execute against a real fork.

## Acceptance criteria (ChatGPT-defined, verbatim shape)

1. **A published branch version can be cloned into a new draft branch.** Concretely: `extensions action=build_branch spec_json={"name":"<new>","fork_from":"<parent_branch_version_id>","node_overrides":{}}` returns a new `branch_def_id` without rejection.
2. **The clone inherits the parent graph, nodes, state schema, skills, and lineage.** Concretely: `get_branch` on the new branch_def_id returns nodes/edges/state_schema/skills byte-identical to the parent version, with `fork_from` lineage field referencing the parent's version_id.
3. **The user can amend exactly one node in the clone.** Concretely: `build_branch` with `node_overrides={"<node_id>":{"prompt_template":"<new>"}}` produces a clone where that node's prompt_template is the override and every sibling node is inherited verbatim from the parent.
4. **The parent branch is unchanged.** Concretely: `get_branch` on the parent's branch_def_id before and after the clone operation returns byte-identical state. No implicit mutation; the parent's `version` field does not bump.
5. **The clone can validate past the inherited graph shape without re-triggering PR-037's multi-node build wall.** Concretely: the validator must NOT run full multi-node-graph validation on the clone's submitted spec when `fork_from` is set and `node_overrides` defines the diff; instead it validates the inherited graph as already-known-good and validates only the override diff.

## Concrete probe — once Move A lands

Re-execute slice-0 against the autoresearch lab:

```
extensions action=build_branch spec_json={
  "name": "community_change_loop_autoresearch_lab_v1_routing_fork",
  "fork_from": "e019229850f9@634815eb",
  "author": "claude-code-slice-0-rerun",
  "node_overrides": {
    "experiment_designer": {
      "prompt_template": "<amended prompt that adds ROUTING_PACKET emission alongside experiment_hypothesis>"
    }
  }
}
```

Expected: succeeds, returns a new `branch_def_id` whose 6 inherited nodes are byte-identical to the lab's v1 (`e019229850f9@634815eb`) and whose `experiment_designer` has the amended prompt.

Then run both:
- The lab's `experiment_designer` (via the lab's published version) on a synthetic `program_request`
- The fork's `experiment_designer` on the same synthetic input
- Compare `experiment_hypothesis` outputs

That comparison is slice-0's original deliverable. It only becomes producible after Move A.

## Non-acceptance

Out of scope for slice-1:
- Move B (author-gated patch_branch + versioning) — separate safety work
- Move C (publish_version flipping branch-level published flag) — discovery polish
- Slice-0 routing-policy semantic equivalence test — that's slice-0's job once it can re-execute
- Anything requiring `GATES_ENABLED=1` or populated `canonical_branch_version_id`

## Pre-conditions

- Move A landed in substrate (the patch_request linked above).
- Lab branch has a published version_id (DONE today: `e019229850f9@634815eb`).
- `change_loop_v1` has a published version_id (DONE today: `fd5c66b1d87d@17b2d764`) — Move D.

## Cross-references

- [[default-change-loop-v1-slice-0-routing-policy-probe]] — slice-0 spec with the Outcome section that motivates this
- [[slice-0-substrate-readiness-finding-2026-05-13]] — six-gap finding
- [[pr-037-build-branch-diagnostics-contradict-submitted-spec-chat-auth]] — the validator wall slice-1's acceptance #5 explicitly requires bypassing
- ChatGPT dev-partner conversation 2026-05-12/13 — the live conversation where this acceptance was negotiated

## What's NOT pending on ChatGPT

ChatGPT already approved this slice-1 reshape in his 2026-05-13 response. Pending: substrate-team work to land Move A. Once that's filed and worked, slice-1 acceptance criteria above are the test.
