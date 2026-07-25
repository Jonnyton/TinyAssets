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
22. Exact claim retraction reads claim/Goal metadata before branch authority and returns a full already-retracted claim without any actor check. Conformance-pack get/list similarly returns branch-attached evidence without branch visibility filtering.
23. Goal leaderboard metrics, common-node aggregation, archive consultation, gate-event ranking, and the `goals metric=outcome` alias do not consistently consume the request subject; the as-built shared-goals spec itself records that the outcome alias omits the gate leaderboard's presentation filter.
24. Gate events accept arbitrary branch-version citations and expose them through exact/list/leaderboard surfaces without validating a public/readable parent. The same handlers accept caller-supplied event actor fields; generic gate-event lifecycle identity is a separate outcome-authority defect, not branch authorship.
25. Goal list/search/get return raw stored canonical/selector pointers; Goal get/get-protocol expose protocol branch IDs and `goal_gate_summary` aggregates private claims without a viewer. Global protocol definition validates Goal binding but not public branch visibility.
26. Gate bonus stake/release paths load exact claims and emit claimant, Goal-owner, host, and stake/lifecycle details before any branch privacy gate. Paid-market authority checks exist, but they do not make foreign private branch metadata public.
27. `record_remix` accepts arbitrary parent/child branch IDs plus caller-selected attribution actors and writes edges/credits without branch authority. `get_provenance` traverses those edges and exposes private branch IDs, actors, credit shares, and counts without visibility filtering.
28. Scheduler/subscription create actions do not authorize the target branch and persist caller-supplied `owner_actor`; list actions accept any owner or blank-for-all, while exact pause/unpause/remove actions trust the same caller-supplied owner.
29. Outcome record/list/get actions accept arbitrary run IDs and expose outcome evidence/payloads without run/branch authority. This belongs to the separate outcome-and-gate-event lane, not branch authorship.
30. A request-only branch gate would break 24/7 private scheduled/universe-loop execution. Current schedule rows carry a caller-selectable owner and universe soul bundles carry only a branch ID, so neither is a trustworthy offline authority receipt. Epoch-1 in-node enqueue correctly stays public-only for the same reason.
31. The initial sibling file inventory named nonexistent `tinyassets/soul.py`. The real `tinyassets/universe_soul.py` reads and writes editable `soul.md`, so it is a read dependency and cannot hold authority. The server-owned `.runs.db` must atomically bind an immutable receipt to the schedule/subscription/universe-loop target; editable target intent must only match, never create or mutate, that receipt.
32. Binding authority is target-sensitive, not blanket branch authorship: any authenticated connector user may bind a public branch to their own schedule/subscription/universe loop, while only the author may bind a private branch. Requiring authorship for public targets would break first-class reuse of public workflows; caller-selected owner fields still grant nothing.
33. The initial two-actor/one-worker proof was a deterministic concurrency test, not §14 load evidence. Completion now requires the graph-owned `branch-authority-isolation-v1` scenario through the shared production-load-evidence protocol on a real canonical connector/storage substrate; shaped or mock evidence cannot pass.
34. Legacy public schedules cannot be silently trusted merely because their targets are readable: their owner and inputs may have been caller-selected. Receipt migration may use only independent credential-bound server provenance; otherwise the row becomes inactive and requires a fresh authenticated binding before delivery or execution.
35. Gate claims and conformance packs are independent evidence, not branch mutations. The initial blanket author-only attachment rule conflicted with the as-built authorized-writer model. Public branches remain claimable by independent authorized writers with server-bound claimant/pack identity; private branches require the author, and run-derived claims additionally require run-read authority.
36. `_run_read_allowed` derives universe scope only from an `actor="universe:<uid>"` prefix and returns true for every other actor. Scheduler/subscriber runs use synthetic actors, and universe ACL alone does not protect a private parent branch inside a public universe. Run records therefore need server-bound universe context independent of actor provenance, and all later reads/writes must conjoin universe ACL with parent-branch authority.

## Opus 5 draft-artifact verdict — 16:10 PDT

The post-reset Claude Opus 5 read-only review completed successfully in 616.6 seconds and returned `VERDICT: adapt`. The complete raw verdict is retained locally in `.codex-branch-auth-opus5-reset.md`.

The two Critical findings were accepted:

- Cross-capability Goal/gate/run/background/evaluation requirements were removed from this change's graph delta. They are now explicit non-blocking successor handoffs, each required to file under its as-built owning capability.
- The conflicting run/action-registry rules were removed from this ADDED graph delta. Run authority must arrive as a MODIFIED graph requirement in its successor; action classification remains a dependency on `retire-legacy-live-mcp-tools`.

Every Important finding was applied before re-review:

- missing and denied node/version reuse now require byte-identical typed envelopes;
- `set_fork_from` and unreadable stored `fork_from` projection are explicit;
- the core defines one readable-version-to-parent helper for successors;
- public branch-action ledger attribution is request-subject-bound and tested;
- related-wiki uses explicit blank root context and public-only controls;
- `test-identity-and-reset`, the authenticated-subject fixture, and the environment-identity test inventory are explicit dependencies/tasks;
- receipt inventory/re-authorization/go-dark risk moved to the background successor, with STATUS promotion required if operator action proves necessary;
- sibling task bodies no longer gate this change's sync/archive;
- the load registry entry includes all shared-protocol classification/reference fields;
- the nonexistent exact-branch `search_nodes` claim was removed; and
- universe-loop receipt atomicity is owned solely by the successor's `.runs.db` authority record, never `soul.md`.

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
- scheduled/universe-loop binding receipts and offline execution authority, tracked as `harden-background-branch-execution-authority` with active universe-owner coordination;
- generic outcome record/read authority plus gate-event attest/verify/dispute/retract actor and lifecycle authority, tracked as the sequential `harden-outcome-and-gate-event-authority` lane; this change owns only cited-branch public-parent validation and privacy-safe projection;
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

A follow-up repository-wide call-site pass on 2026-07-25 found the additional live connector paths in findings 17–29. Internal reserved-branch storage in `extensions.py`, public-only goal-pool discovery, and epoch-1 enqueue's explicit public-only target validation are not authorization defects. `quality_leaderboard.py`, `canonical_dispatch.py`, `selector_dispatch.py`, scheduler/attribution storage, and gate-event storage remain read dependencies unless focused RED tests prove a minimal change is necessary. The target change now specifies a guarded immutable-version execution path and a third separately claimed branch-adjacent sibling rather than silently expanding the core branch-module write-set. Generic outcome and gate-event lifecycle identity remains a fourth, sequential outcome-authority lane because independent public attestation cannot be modeled as branch ownership.

Isolated temporary-database probes on 2026-07-25 confirmed the call-site findings against the current branch without changing repository state. With Alice as Goal owner and Bob as private-branch author, `goals action=set_canonical` and `set_selector` each returned `status="ok"` and persisted Bob's private `branch_version_id`; `goals action=bind` returned `status="bound"` and persisted Alice's Goal ID on Bob's private branch. With Alice as caller, direct `run_branch_version` of Bob's valid private graph returned `status="queued"` plus a new `run_id`. With Mallory as caller, `gates action=claim` returned `status="claimed"` and persisted `claimed_by="mallory"` against Bob's private branch. With Alice as caller, `extensions action=dry_inspect_node` returned no error and included Bob's `secret_node` plus its private prompt template. These are direct authorization failures, not inferred timing or count side channels.
