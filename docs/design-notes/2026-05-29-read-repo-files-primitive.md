# read_repo_files: the read primitive that lets a user-buildable loop edit existing files

**Status:** DESIGN — writer:claude, needs checker:codex cross-family review before build.
**Date:** 2026-05-29
**Follows:** BUG-111 (write side: effector materializes a branch + opens a PR, merged PR #1145).

## Why

`patch_request_loop_v1` (branch `026a9f8c4833`) runs end-to-end and opens real PRs
(proven: run `96a3fa0d853a48ae` → PR #1148). But it can only service patch
requests for **new files**, or edits where the **user pastes the current file
contents into the request**. A real patch request against a maintained repo is
almost always "change how existing file X behaves" — which the loop cannot do,
because nothing in it can **read** X's current contents. The loop's
`propose_changes` node is explicitly instructed to omit any edited file whose
current contents weren't provided, rather than guess.

So the goal — "a user-buildable loop running the user's patch requests" — is not
met for the common case. The gating primitive is a **read**: fetch named repo
files' current contents into run state so a downstream node can base a correct
edit on them.

## What's missing (grounded in the compiler)

There is no user-composable way for a node to read repo files today:

- **prompt_template** nodes have no I/O — pure LLM.
- **source_code** nodes can do anything but require host approval
  (`_validate_source_code` raises `UnapprovedNodeError` when `approved` is false),
  so they break "user-buildable without host intervention." The node→MCP-action
  invoker (`_build_node_mcp_invoker`) is wired **only** into source_code nodes
  (`graph_compiler.py:1307`) and its alias map exposes only `goals` / `gates`
  actions — no file read.
- **opaque domain-registry** nodes (`_build_opaque_node`, resolved by
  `(domain_id, node_id)` via `resolve_domain_callable`) run mid-graph as the node
  body with **no approval wall** — they are platform-trusted code, not user
  source. This is the same class of primitive the write side rides on. **Nothing
  is registered for reads yet.**

## Options

**Option A — opaque domain callable `read_repo_files` (recommended).**
Register a platform callable for `(domain_id="workflow", node_id="read_repo_files")`
via `register_domain_callable`. A user authors a node named `read_repo_files`
(domain `workflow`) with an input key carrying the target paths and an output key
for the contents map; the compiler resolves it to the platform callable. The
callable reads each path from the destination repo via the **GitHub Git Data /
contents API using the same capability token** the write effector uses
(`WORKFLOW_GITHUB_PR_CAPABILITIES`, keyed by destination), and writes
`{path: contents}` JSON to the output key. No approval wall, runs mid-graph,
symmetric with the write effector. Trade-off: keyed on `node_id` (the existing
opaque-node convention) — effectively a reserved node id.

**Option B — source_code node + new MCP read action.** Add a `read_repo_files`
action to an MCP tool and to `_NODE_MCP_ACTION_ALIASES`. Rejected: the invoker is
source-code-only, so it hits the approval wall and isn't user-composable.

**Option C — new `reads` node attribute + pre-run hook (symmetric to `effects`).**
A node declares `reads: ["github_repo_files"]`; a new compiler hook fetches the
paths and populates an input key before the node body runs. Cleanest conceptual
symmetry with `effects`, but the largest compiler change (a new pre-run phase),
and reads-must-return-into-state is awkward to model as a post-hoc sweep the way
`effects` is. Defer unless review prefers it.

## Recommendation

**Option A.** It reuses the exact capability/token path the write side already
proved, requires no approval wall, and composes directly into the existing loop:

```
intake → read_repo_files → propose_changes → review_gate ──KEEP──→ open_pr → log → END
```

`read_repo_files` reads `target_paths` → `current_contents_json`; `propose_changes`
already consumes `current_contents_json`. The loop then edits existing files
correctly with no user-pasted contents.

## Open questions for review (checker:codex)

1. **Read scope vs write scope.** Reading public repo files needs only
   `Contents: read`; the token already has `Contents: write` (BUG-111 cutover).
   Confirm we should reuse `WORKFLOW_GITHUB_PR_CAPABILITIES` for reads, or whether
   reads should resolve through a separate read-capability so a universe can be
   granted read-only without write.
2. **Path source + limits.** Which state field carries the paths, and what caps
   (max files, max bytes/file) prevent a runaway read? Propose `target_paths`
   (JSON array or comma list) + a per-call file/byte cap with a structured
   `read_truncated` signal.
3. **Missing-file semantics.** A path that doesn't exist at the ref should return
   an explicit `null` (so `propose_changes` knows it's a new-file create), not an
   error that fails the run.
4. **Error kinds.** Distinct kinds per failure (`read_ref_lookup_failed`,
   `read_contents_denied` for 401/403/404 = scope signal, `read_file_too_large`),
   never collapsed — same discipline as the BUG-111 write path.
5. **Scope boundary.** This stays a platform-trusted opaque callable (the user
   references it but cannot supply its body), consistent with reads being a
   universe capability, not arbitrary user code. Confirm.

## Out of scope

- The autoresearch-lab retrofit (separate branch).
- Binding `patch_request_loop_v1` to goal 4ff5862cc26d as a competing entrant
  (separate step once read lands).
