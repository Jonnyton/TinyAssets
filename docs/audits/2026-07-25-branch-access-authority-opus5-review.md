# Branch access authority — Opus 5 review

**Date:** 2026-07-25

**Environment:** clean detached worktree at then-current `origin/main` `0b8fb8c1`

**Reviewer:** Claude Opus 5, read-only current-main pass

**Verdict:** **ADAPT — promote a separate spec-only successor with broader scope**

## Decision

The filed restricted-wiki metadata leak is real, but a change named only for related-wiki visibility would leave larger authority failures open in the same connector path. The accepted successor name is `harden-branch-access-authority`.

The successor remains separate from `universe-visibility`. That owner retains `tinyassets/api/visibility.py`, `tinyassets/api/wiki.py`, and its tests. Branch code must consume the existing visibility predicates; any predicate change is filed against that owner.

The canonical chatbot connector is the acceptance surface. Agent Village is deferred and out of scope.

## Verified current-main defects

1. Canonical `write_graph target=branch` can use `node_ref.source` to copy another actor's private branch node, including source code, prompt, tool allowances, and approval provenance.
2. `fork_from` can clone private source branch content without source read authority.
3. Branch `related_wiki_pages` bypasses page-listing visibility and can expose restricted path, title, summary, and match labels.
4. Hidden wiki matches contribute to `truncated_count` and displace visible matches from the cap.
5. `describe_branch`, `validate_branch`, and fork-tree root/ancestor reads do not share `get_branch`'s private not-found gate.
6. Descendant enumeration excludes even the owner's private forks because it does not pass a viewer.
7. Most branch mutation handlers and `delete_branch` do not require author authority.
8. `patch_branch` has a caller-controlled `force=true` authority bypass.
9. Canonical `run_graph` can execute another actor's private branch; this belongs to a named sibling lane because it writes `tinyassets/api/runs.py`.
10. Existing direct author checks use `_current_actor()`, whose environment fallback is an open authority defect and must not be propagated.

The drafted change additionally records that branch create/build paths accept caller-supplied author values. Server-bound authorship is required because a stored author selected by the caller would undermine every later author check.

## Required ownership boundary

`harden-branch-access-authority` owns:

- authenticated-subject authorship and the shared branch read/author helper;
- exact-ID not-found equivalence;
- cross-branch source reuse;
- lineage filtering;
- mutation and deletion authority;
- separation of commit-conflict force from authority;
- branch-originated related-wiki visibility, counting, and stable empty output.

It does not own:

- universe/page visibility predicate implementation;
- audience or discovery scope;
- `run_branch` implementation in `tinyassets/api/runs.py`;
- legacy action-registry migration;
- Agent Village.

## Proof requirements

Implementation requires RED-first focused tests and mutation probes for every gate. The §14 proof must interleave at least two authenticated request contexts against the same private branch and restricted wiki set and prove zero cross-actor disclosure or mutation.

Final public acceptance requires:

- canonical MCP handle canaries;
- a rendered two-actor chatbot conversation through `https://tinyassets.io/mcp`;
- actor B receiving not-found and being unable to reuse, mutate, delete, or execute actor A's private branch;
- post-fix organic connector evidence, or an explicit monitoring row if none is available.

## Promotion state

This review approves drafting a target-only change, not implementation. The completed proposal/design/delta specs/tasks require a second Opus 5 review before they become implementation authority. The change remains active and unsynced until runtime, concurrency, rendered-chatbot, and clean-use gates pass.

## Draft-artifact review state

Two Opus 5 artifact-review attempts on 2026-07-25 exited after seven seconds with no stderr and no verdict. The Claude CLI itself remained available (`claude --version` returned `2.1.220`), while the local fleet floor state recorded three blocks. This is provider/harness unavailability, not approval or rejection.

The drafted change passes strict OpenSpec validation, but task 1.3 remains open. The branch may be published only as review-blocked planning state; it must not merge, authorize implementation, sync specs, or archive until a real opposite-provider artifact verdict is recorded and every Critical/Important finding is resolved.
