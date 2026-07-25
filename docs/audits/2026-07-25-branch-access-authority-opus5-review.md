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
11. `_resolve_branch_id` performs name lookup with `_current_actor()`. When environment identity names a private branch author, a guessed private name can resolve to the stored ID before a later denial emits that canonical ID instead of the original selector.
12. `patch_branch`'s non-author response is itself an oracle: it returns the canonical branch ID, stored author, caller identity, and explicit `force=true` bypass guidance instead of preserving private-or-missing equivalence or a generic readable-object denial.
13. `list_branches` passes `_current_actor()` as `viewer`; an unauthenticated request can therefore inherit `UNIVERSE_SERVER_USER` and enumerate that actor's private branch summaries and counts, including `scope=mine`.
14. New node definitions accept caller-supplied `author`, while approval, authoring-receipt, git, and version-publisher attribution use `_current_actor()`; durable provenance can therefore be caller-selected or environment-attributed instead of request-subject-bound.
15. Global `search_nodes` is public-only because its storage helper omits `viewer`; this does not leak private nodes, but it hides an authenticated author's own private reuse candidates and makes their private nodes contribute to neither cards nor reuse counts.
16. `evaluation.py` publishes any branch with caller-supplied `publisher`, returns/lists immutable versions without branch read authority, and reads node suggestion/history or rolls a foreign node back without shared branch authority.
17. `run_branch_version` executes any guessed immutable version without checking the parent branch. `goals action=run_canonical` delegates to that path, and `set_canonical` / `set_selector` accept any active version without requiring a public/readable parent, so a Goal owner can bind and execute another actor's private snapshot.
18. `goals action=bind` calls `update_branch_definition` for any exact branch ID without a branch read or author check, changing its `goal_id` before commit handling.
19. `gates action=claim`, `claim_from_branch_run`, and branch-scoped `record_conformance_pack` can attach claims/evidence to another actor's branch; the run-derived form also reads arbitrary completed-run output before any branch-owner check.
20. Gate-claim and quality-leaderboard private filters use `_current_actor()` rather than the credential-validated request subject, so environment identity can influence private rows, ranks, counts, recommendations, and selector input.
21. `extensions action=dry_inspect_node|dry_inspect_patch` loads an exact branch definition and returns structural/validation material without branch read authority.

The drafted change additionally records that branch create/build paths accept caller-supplied author values. Server-bound authorship is required because a stored author selected by the caller would undermine every later author check.

## Required ownership boundary

`harden-branch-access-authority` owns:

- authenticated-subject authorship and the shared branch read/author helper;
- authenticated-subject-only branch listing and counts;
- public-plus-own-private reusable-node search with visibility-safe aggregation;
- ID/name selector not-found equivalence without canonical-ID resolution leaks;
- cross-branch source reuse;
- lineage filtering;
- mutation and deletion authority with private-or-missing equivalence and generic readable-object denial;
- separation of commit-conflict force from authority;
- branch-originated related-wiki visibility, counting, and stable empty output.

It does not own:

- universe/page visibility predicate implementation;
- audience or discovery scope;
- `run_branch` implementation in `tinyassets/api/runs.py`;
- branch evaluation/version implementation in `tinyassets/api/evaluation.py`;
- branch-adjacent goal binding, canonical/selector binding, gate/conformance attachment, private-filtered projection, and dry-inspection implementation in `tinyassets/api/market.py`, `tinyassets/api/runtime_ops.py`, `tinyassets/api/engine_helpers.py`, `tinyassets/api/extensions_leaderboard_actions.py`, and any minimal storage validation seam;
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

Four Opus 5 artifact-review attempts on 2026-07-25 exited after seven seconds with no stderr and no verdict. The fourth was attempted after the host reported a rate-limit reset. A direct minimal diagnostic then exposed the hidden provider response: `You've hit your monthly spend limit`. Claude.ai independently rejected the same review with Opus 5 High selected, reporting a $0 monthly spend limit, no credits, and a plan-session reset at 4:00 PM PDT. Billing was not changed. The Claude CLI itself remained installed (`claude --version` returned `2.1.220`). The project retry-loop stop rule remains in force. This is provider-account unavailability, not approval or rejection.

The drafted change passes strict OpenSpec validation and is published as draft PR #1778, but task 1.3 remains open. The branch is review-blocked planning state; it must not become ready, merge, authorize implementation, sync specs, or archive until a real opposite-provider artifact verdict is recorded and every Critical/Important finding is resolved.

A 2026-07-25 dependency freshness check found that PR #1691 owns provider-destination authority, not request-subject resolution. The artifacts were corrected to consume the already-as-built `tinyassets.api.permissions.current_request_actor_id()` contract (`openspec/specs/identity-auth-and-access-control/spec.md`) and to keep `anonymous` fail-closed. PR #1691 is no longer named as an implementation dependency.

The same freshness pass resolved the blank-root wiki grant gate without changing the active visibility owner's files. In current main, `tinyassets.daemon_server.list_universe_acl` returns `[]` immediately for `universe_id=""`. A dated temporary-database probe authenticated `alice`, injected an otherwise-valid ACL row whose universe ID was the empty string through raw DML, and observed `page_visible_in_listing({"visibility": "private"}, "") == False`. Blank-root page grants are therefore fail-closed even under the forged-row case.

The action-scope audit also narrowed task 2.3. `build_action_scope_registry()` currently emits `write` for branch create/build/edit/patch actions and `admin` for `approve_source_code` and `delete_branch`; `action_scope_for("extensions", "missing_branch_action")` returns `None`, and `require_action_scope` rejects that absence. The remaining dependency is preserving those exact-or-stricter effects through `retire-legacy-live-mcp-tools` tasks 4.2/4.4, not inventing classifications in this lane.

A follow-up repository-wide call-site pass on 2026-07-25 found the additional live connector paths in findings 17–21. Internal reserved-branch storage in `extensions.py`, public-only goal-pool discovery, and epoch-1 enqueue's explicit public-only target validation are not authorization defects. `quality_leaderboard.py`, `canonical_dispatch.py`, and `selector_dispatch.py` remain read dependencies unless focused RED tests prove a minimal change is necessary. The target change now specifies a guarded immutable-version execution path and a third separately claimed branch-adjacent sibling rather than silently expanding the core branch-module write-set.
