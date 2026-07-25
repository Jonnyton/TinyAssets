## Context

TinyAssets exposes branch authoring and execution through the canonical chatbot connector. Branch visibility currently exists as a storage/listing concept, but listing and branch-selector handlers in `tinyassets/api/branches.py` apply it inconsistently. `list_branches` passes the environment-fallback actor as viewer, so an unauthenticated request can inherit the daemon user and enumerate that user's private branch summaries and counts. `get_branch` contains a local owner check, while `describe_branch`, `validate_branch`, lineage reads, cross-branch node reuse, branch cloning, most mutations, and deletion do not share that boundary. `_resolve_branch_id` also performs name lookup with the environment-fallback actor and can translate a guessed private name into its canonical ID before a later denial changes the not-found envelope. `patch_branch` has an author check that a caller can bypass with `force=true`.

The result is not only metadata exposure. A canonical `write_graph` request can copy `source_code`, prompts, tools, and approval provenance from another actor's private branch through `node_ref.source`. The canonical `run_graph` and `run_branch_version` surfaces can execute a foreign private branch or immutable version in `tinyassets/api/runs.py`; `goals action=run_canonical` delegates to that same unchecked version path. `tinyassets/api/evaluation.py` can publish a foreign private branch with caller-selected publisher provenance, return/list its immutable versions, read node suggestion/history material, and roll back a foreign node. Run and evaluation/version hardening are tracked as separately claimed siblings because this change must not silently broaden its write-set.

Other live connector actions cross the same object boundary outside those modules. `goals action=bind` updates any named branch's `goal_id` without branch-author authority. `set_canonical` and `set_selector` accept any active guessed `branch_version_id`; a global binding can therefore retain and later execute a foreign private snapshot. Goal list/search/get responses can return those raw stored version pointers, while Goal get/protocol surfaces can expose private branch IDs and private-derived gate summaries. `gates action=claim`, `claim_from_branch_run`, and branch-scoped `record_conformance_pack` can attach claims or evidence to a foreign branch. Exact claim retraction/bonus checks and conformance-pack get/list return branch-attached records before branch read authority. Gate, quality, Goal metric, common-node, archive-consultation, and gate-event leaderboards/projections either derive private visibility from `_current_actor()` or omit a viewer entirely. Gate events can accept and later enumerate private `branch_version_id` citations. `record_remix` accepts arbitrary parent/child branch IDs and caller-supplied actor attribution; `get_provenance` traverses those IDs without visibility filtering. Scheduler/subscription actions neither authorize the target branch nor server-bind `owner_actor`, and blank list filters enumerate every row. `extensions action=dry_inspect_node|dry_inspect_patch` loads an arbitrary branch before structural preview. These paths are a third separately claimed sibling so the core branch helper remains the shared contract rather than an ever-growing write-set.

Gate-event handlers also accept caller-supplied `attested_by`, `verifier_id`, `disputed_by`, and `retracted_by` values. That broader event-lifecycle identity defect is tracked in a separate outcome-gate authority lane because independent public outcome attestation is not branch authorship. The branch-adjacent sibling owns only the public-parent rule and filtering for cited branch versions.

Branch-originated `related_wiki_pages` is also a wiki enumeration surface, but it bypasses the existing page-listing visibility predicate used by wiki search, changed-since, ambient feeds, and list. Restricted pages currently contribute paths, titles, summaries, match labels, ordering, cap displacement, and hidden counts.

The active `universe-visibility` owner retains `tinyassets/api/visibility.py`, `tinyassets/api/wiki.py`, and its tests. This successor consumes those predicates; it does not redefine or edit them. The as-built identity contract already provides `tinyassets.api.permissions.current_request_actor_id()`, which returns the credential-validated request subject or `anonymous` without an environment fallback. Implementation consumes that resolver directly and must not multiply the known `_current_actor()` environment fallback.

## Goals / Non-Goals

**Goals:**

- Establish one request-local, credential-validated subject as new branch/node authorship, approval/publisher/receipt provenance, and authority truth.
- Make branch listing use only that subject as viewer, with no environment-inherited private rows or counts.
- Make ID/name selector reads of a foreign private branch indistinguishable from a missing branch without exposing a resolved canonical ID.
- Gate cross-branch content reuse before executable content is copied.
- Preserve branch visibility across lineage projections.
- Require author authority for every mutation and deletion path.
- Apply existing page-listing visibility before related-wiki matching, ranking, counting, and response construction.
- Preserve public reads, author reads, granted wiki reads, stable response keys, and commit-conflict recovery.

**Non-Goals:**

- Modifying universe/page visibility predicates or audience classification.
- Using audience or discovery scope as authority.
- Implementing `run_branch` authority in this write-set; a sibling change consumes the helper.
- Implementing branch-version/evaluation authority in `tinyassets/api/evaluation.py`; a sibling change consumes the read/author helpers and coordinates run-linked evidence with the run sibling.
- Implementing branch-adjacent goal binding, global canonical/selector binding, gate/conformance attachment, leaderboard/gate projection, or dry-inspection authority in this write-set; a third sibling consumes the same helpers and coordinates version execution with the run sibling.
- Implementing scheduled or universe-loop binding/execution authority in this write-set; a background-authority sibling coordinates the active universe owner, scheduler storage, and the run executor.
- Defining generic gate-event attest/verify/dispute/retract authority; a separate outcome-gate change owns server-bound event actors and lifecycle permissions, while this change covers only cited-branch visibility.
- Changing the public MCP handle set or response schema.
- Making filesystem scans constant-time or claiming timing-side-channel resistance.
- Building or validating an Agent Village surface.
- Syncing these target requirements into as-built specs before implementation and acceptance pass.

## Decisions

### 1. Authenticated subject is the only branch authority identity

One branch-authority helper consumes `tinyassets.api.permissions.current_request_actor_id()`, the as-built request-local subject established by validated credentials. It treats `anonymous` as absent authority, does not call an identity helper that can fall back to `UNIVERSE_SERVER_USER`, and does not accept an actor, author, owner, or force value from action arguments.

Branch creation and composite build paths persist the authenticated subject as branch `author`. Newly authored node definitions, approvals, branch-version publishers, git attribution, and branch-authoring receipts use the same subject. A caller-supplied `author`, `approved_by`, publisher, or receipt actor cannot select or impersonate another principal. Authorized reuse preserves copied source provenance rather than relabeling the source as the copier. A creation or mutation that requires authorship fails closed when no authenticated subject is available.

Alternative: reuse `_current_actor()` everywhere. Rejected because its environment fallback is an open authority defect and copying the expression would entrench it across every handler.

### 2. Selector resolution and read authorization return one not-found envelope

`list_branches` passes `_request_branch_actor()` as viewer. An absent subject sees public branches only, `scope=mine` returns the stable empty list/count, and environment identity cannot add a private row or affect the count. An authenticated author continues to see their own private branches. The global reusable-node search adds a `viewer` parameter to its storage helper and applies the same public-plus-own-private rule before deduplication, reuse counting, ranking, capping, or response construction; foreign private nodes affect neither cards nor counts.

The helper consumes the original caller-supplied ID or name selector, resolves names only through visibility-aware enumeration using `current_request_actor_id()`, and returns either the readable canonical ID plus branch or the canonical JSON error `{"error": "Branch '<selector>' not found."}`. `get_branch`, `describe_branch`, `validate_branch`, and `fork_tree` use it before constructing any branch-derived output.

A missing branch and a foreign private branch have byte-identical serialized errors, key order, punctuation, and status behavior. A denied name selector never changes into or exposes the stored branch ID. No denial note, existence flag, author, visibility value, or different key set is emitted.

Alternative: return an explicit forbidden error. Rejected because caller-supplied IDs and names are enumerable and the private branch's existence or resolved canonical ID is itself restricted metadata.

### 3. Cross-branch reuse is a read before it is a write

`node_ref.source` and `fork_from` first authorize the source branch using the same read helper. Authorization completes before a node body, `node_defs`, source code, prompt, tool list, or approval provenance is copied into caller-owned state.

Public sources and the authenticated author's private sources remain reusable. A foreign private source produces the same not-found envelope and no partial branch mutation.

Alternative: gate only the destination write. Rejected because authority over a caller-owned destination does not grant read authority over the source.

### 4. Lineage is a projection of readable branches

The root and each ancestor in `fork_tree` pass the read helper. Encountering an unreadable ancestor terminates traversal without a placeholder, count, or metadata row. Descendant enumerations pass the authenticated subject as `viewer`, so public descendants and the viewer's own private descendants appear while foreign private descendants do not.

Alternative: use `include_private=False`. Rejected because it prevents a legitimate owner from seeing their own private forks while still leaving root/ancestor exact-ID reads unguarded.

### 5. Mutation and deletion require author authority

`add_node`, `connect_nodes`, `set_entry_point`, `add_state_field`, `update_node`, `patch_nodes`, `approve_source_code`, `patch_branch`, and `delete_branch` first resolve the target through the shared readable-branch helper, so a foreign private target remains indistinguishable from a missing selector. A readable target then passes one author-authority gate before changing state. Batch and empty-selection forms do not bypass either gate.

A readable public branch owned by someone else returns one generic author-authority denial without the stored author, target internals, or retry guidance. A foreign private target returns the original-selector not-found envelope instead; mutation errors never turn a privacy denial into an existence or author oracle.

`force` remains available only after authority succeeds and only for the existing commit-conflict behavior. It cannot relax an author denial, and denial text never instructs a caller to retry with force.

Action-scope metadata in `retire-legacy-live-mcp-tools` remains an outer classification gate and must migrate in lockstep. It is defense in depth, not a substitute for object-level author authority.

Current-main audit evidence classifies `create_branch`, `build_branch`, `add_node`, `connect_nodes`, `set_entry_point`, `add_state_field`, `update_node`, `patch_nodes`, and `patch_branch` as `write`; `approve_source_code` and `delete_branch` remain the stricter `admin`. `require_action_scope` denies a gated dispatch when metadata is absent. This change preserves or tightens those effects and adds author authority underneath them; it never downgrades approval or deletion to ordinary write.

Alternative: rely on write/costly action classification alone. Rejected because action permission does not prove ownership of the target branch and missing metadata can drift.

### 6. Related wiki projection reuses the existing page-listing predicate

`_related_wiki_pages` parses page frontmatter, calls `visibility.page_visible_in_listing` with the applicable universe context, and excludes denied pages before title/body matching, scoring, sorting, cap application, count calculation, or item construction. It adds no audience/scope filter.

`items` and `truncated_count` are calculated exclusively from visible matches. When all matching pages are denied, the existing keys remain `[]` and `0`, indistinguishable from no matches. No `filtered_count`, caveat, denial note, hidden path, title, summary, `matched_via`, or cap displacement is exposed.

The allowed related-page paths for a caller must be a subset of the paths returned by the wiki listing boundary for the same corpus and authority context. Public pages and pages available to a granted reader remain unchanged.

Alternative: filter after scoring/capping. Rejected because hidden pages would still influence ordering, displace visible results, and leak through `truncated_count`.

### 7. Stored versions and branch-adjacent actions preserve the parent branch boundary

An immutable version does not become public merely because its identifier is guessed or stored on a Goal. Before direct version execution, global canonical/selector binding, version retrieval, or any branch-derived projection, the system resolves the version's `branch_def_id` and applies the parent branch boundary. A missing parent branch fails closed.

`run_branch_version` and personal canonical execution allow only a public parent branch or the authenticated subject's private parent branch. A Goal-wide canonical or selector is callable by other users, so it may bind only a public parent branch. Denials occur before provider work, selector execution, leaderboard aggregation, or canonical history changes and do not expose the parent branch ID.

Live branch-adjacent writes apply object authority before mutation: `goals action=bind` requires branch author authority; `gates action=claim`, `claim_from_branch_run`, and branch-scoped `record_conformance_pack` require branch author authority before reading run output or persisting an attachment. Globally readable Goal protocols accept public branch steps only. Goal list/search/get sanitizes legacy canonical/selector/protocol pointers and recomputes branch/gate summaries from the readable set; personal canonical resolution uses the request subject. Claim retraction and bonus lifecycle, exact/listed conformance packs, gate claims, Goal metric/common-node/archive projections, gate/quality leaderboards and recommendations, and gate-event citations filter through the request subject before returning branch-derived records, identifiers, actors, counts, ranks, or cap influence. Because gate events are globally readable today, new event citations accept public-parent branch versions only; legacy private-parent citations are filtered from get/list/leaderboard output.

Remix recording authorizes the parent as readable and the child as author-owned before persisting an edge, server-binds the attribution actor, and leaves no partial edge/credit after denial. Provenance traversal filters its root and every ancestor/edge through branch readability. Scheduling and subscription creation require author authority on the target branch and persist only the request subject as owner. Exact unschedule/pause/subscription mutations resolve ownership from that subject; list actions ignore caller-supplied owner filters and return only the subject's rows. Foreign-private/missing targets and foreign/missing schedule IDs are non-oracular. Dry inspection is a branch read and uses the same private-or-missing boundary. Monetary bonus settlement semantics remain with the paid-market owner; this lane only adds the prior branch privacy gate and non-oracular denial.

Alternative: treat publication or possession of a version ID as read authority. Rejected because published versions retain private branch code and provenance, and their IDs are enumerable capability-shaped strings without capability semantics.

### 8. Zero-host background execution consumes persisted authenticated authority

Direct MCP branch/version runs authorize with the live credential-validated request subject. Scheduled runs, subscriptions, and universe loops have no live request at fire time, so their authority is established earlier: an authenticated subject binds an exact public branch/version or their own private branch/version to the schedule or universe, and the server atomically persists an immutable receipt with `schema_version`, `binding_kind`, `binding_id`, `target_kind`, `target_id`, `authorized_by`, and `issued_at` in the server-owned `.runs.db`. The editable `soul.md` loop declaration is target intent, never authority. Caller-supplied `owner_actor`, environment identity, branch-authored inputs, and queue payload fields cannot create or alter a receipt. Changing a binding's target invalidates the old receipt and requires a fresh authenticated authorization.

At fire/claim time, the worker consumes only that server-owned receipt, requires its binding kind/ID and target kind/ID to match the current server record or universe loop declaration exactly, and revalidates that the target still exists and is public or remains authored by `authorized_by`. A missing, legacy-unreceipted, malformed, mismatched, or revoked private binding fails before provider work, delivery marking, run-row creation, or target-derived output. Any authenticated subject can bind and keep using a public branch; an author-owned private branch remains runnable 24/7 after a valid binding even with every human host offline.

The existing epoch-1 in-node enqueue path remains public-only because its task row carries no authenticated authority receipt. It MUST NOT be broadened to private targets until the distributed-execution owner adds an equivalent server-bound receipt.

Alternative: require a live request subject for every run. Rejected because it breaks the project's zero-host-online contract. Alternative: trust the schedule's actor string or universe ID alone. Rejected because caller-controlled owner fields and universe collaboration do not prove private branch authority.

### 9. Delivery is split by collision and module ownership

Wave 1 implements request-subject listing/search, ID/name selector resolution and reads, related-wiki filtering, and lineage in `branches.py` plus the narrow `daemon_server.search_nodes(viewer=...)` seam. Wave 2 gates cross-branch node/clone reuse. Wave 3 gates mutation and deletion, removes the force authority bypass, and removes mutation-response existence/author oracles. Each wave gets new focused RED-first tests after broad `tests/` claims release.

The sibling `harden-background-branch-execution-authority` owns universe-loop and scheduler/subscription binding receipts in `tinyassets/api/universe.py`, the scheduler seams in `tinyassets/api/runtime_ops.py`, and `tinyassets/scheduler.py`; it reads the loop declaration through `tinyassets/universe_soul.py` but never stores authority in `soul.md`. It coordinates with the active universe-creation owner and lands before the run executor consumes those receipts.

The sibling `harden-run-branch-access-authority` change owns `tinyassets/api/runs.py` and the narrow execution gate in `tinyassets/runs.py`: direct live-branch/version execution uses the request subject, while trusted background execution consumes the server-owned binding receipt. `goals action=run_canonical` remains safe only by delegating to that guarded version path. The sibling `harden-branch-evaluation-access-authority` owns `tinyassets/api/evaluation.py`: publish/get/list branch versions, suggest/list/rollback node paths, publisher provenance, and any run-linked conjunction with the run sibling.

The sibling `harden-branch-adjacent-access-authority` owns the narrow action seams in `tinyassets/api/market.py`, the dry-inspection seam in `tinyassets/api/runtime_ops.py`, `tinyassets/api/engine_helpers.py`, `tinyassets/api/extensions_leaderboard_actions.py`, and any minimal `tinyassets/daemon_server.py` canonical/selector validation seam. It covers goal binding, global canonical/selector public-parent enforcement, gate/conformance attachments and reads, request-subject Goal/gate/quality/archive/common-node projections, gate-event cited-branch visibility, remix/provenance, and dry inspection. `quality_leaderboard.py`, `canonical_dispatch.py`, `selector_dispatch.py`, attribution storage, and gate-event storage are read dependencies unless RED tests prove a minimal owned change is required; any write-set expansion must pass claim collision checks first. A separate `harden-outcome-and-gate-event-authority` lane follows it in the same module and owns outcome/run authority plus server-bound gate-event actors and attest/verify/dispute/retract permissions.

Before either sibling implements a legacy action, it re-checks the action's current MCP reachability after `retire-legacy-live-mcp-tools`. If an action is gone from every registered/compatibility route, deletion plus an absence regression satisfies the public-boundary requirement; dead code is not hardened for its own sake. Any required change to a universe/page visibility predicate is filed against the active `universe-visibility` owner.

## Risks / Trade-offs

- **[Risk] A local author comparison preserves the environment fallback.** → Block implementation on a request-local authenticated-subject authority seam and mutation-probe it.
- **[Risk] Tightening legacy actions breaks callers that relied on unauthorized behavior.** → Preserve response shapes and authorized behavior; treat unauthorized access as a security defect, not compatibility.
- **[Risk] Hidden wiki pages still affect result counts or ordering.** → Filter before match/score/sort/cap/count and test visible-set equivalence.
- **[Risk] Force semantics are accidentally removed entirely.** → Test that authorized commit-conflict recovery still works while force cannot bypass authority.
- **[Risk] Parallel visibility owners diverge.** → Consume existing predicates without editing their module; use explicit dependency rows for any predicate change.
- **[Risk] A gate exists but tests cannot turn it red.** → Mutation-probe every read, reuse, lineage, mutation, deletion, and projection gate before acceptance.

- **[Risk] A two-actor concurrency test is mislabeled as §14 load proof.** → Register a required `branch-authority-isolation-v1` scenario with the shared production-load-evidence protocol, run it on the real canonical connector/storage substrate, and forbid shaped/mock evidence from passing.

## Migration Plan

1. Land this reviewed target OpenSpec active and unsynced.
2. Reconfirm the as-built `current_request_actor_id()` no-fallback contract, wait for exact `tests/` claims to release, and claim the implementation files explicitly.
3. Implement Wave 1 reads, wiki projections, and lineage with RED-first tests.
4. Implement Wave 2 source reuse and clone gates with no-partial-copy tests.
5. Coordinate action-scope migration, then implement Wave 3 mutation/deletion authority and force separation.
6. Land the background binding-authority sibling after its active universe/scheduler owners release, then land the direct/background run executor gate.
7. Land the separately claimed branch-evaluation/version sibling using the same helpers.
8. Land the separately claimed branch-adjacent goals/gates/projection sibling using the same helpers and the guarded version-execution path.
9. Run focused tests, surrounding suites, Ruff, mutation probes, the deterministic cross-actor concurrency proof, the required `branch-authority-isolation-v1` production-load scenario, canonical MCP canary, rendered two-actor chatbot acceptance, and post-fix clean-use observation.
10. Sync and archive only after all owned tasks and applicable acceptance evidence pass.

Rollback reverts the unactivated implementation commits. Once activated, rollback must not re-enable unauthorized reads, reuse, mutation, deletion, or execution; a forward fix or fail-closed disablement is required.

## Resolved Questions

- Branch authority consumes `tinyassets.api.permissions.current_request_actor_id()`; PR #1691 is provider-destination authority and is not a dependency of this change.
- Every branch creation surface covered here rejects `anonymous`; legacy anonymous or environment-attributed creation is intentionally retired rather than grandfathered.
- Root-wiki related-page projections pass the same blank `universe_id=""` context as the root wiki surfaces. Current main is already fail-closed because `list_universe_acl` returns `[]` for a blank universe ID before storage access; a 2026-07-25 raw-DML forge probe confirmed even an injected empty-ID ACL row cannot grant root-page visibility.
- Cross-branch `search_nodes` retains readable/public discovery through visibility-aware enumeration. Supplying an exact branch ID uses the byte-identical private-or-missing read boundary.
