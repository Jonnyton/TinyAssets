## Context

TinyAssets exposes branch authoring and execution through the canonical chatbot connector. Branch visibility currently exists as a storage/listing concept, but exact-ID handlers in `tinyassets/api/branches.py` apply it inconsistently. `get_branch` contains a local owner check, while `describe_branch`, `validate_branch`, lineage reads, cross-branch node reuse, branch cloning, most mutations, and deletion do not share that boundary. `patch_branch` has an author check that a caller can bypass with `force=true`.

The result is not only metadata exposure. A canonical `write_graph` request can copy `source_code`, prompts, tools, and approval provenance from another actor's private branch through `node_ref.source`. The canonical `run_graph` surface can execute a foreign private branch in `tinyassets/api/runs.py`; that runtime is tracked as a separately claimed sibling because this change must not silently broaden its write-set.

Branch-originated `related_wiki_pages` is also a wiki enumeration surface, but it bypasses the existing page-listing visibility predicate used by wiki search, changed-since, ambient feeds, and list. Restricted pages currently contribute paths, titles, summaries, match labels, ordering, cap displacement, and hidden counts.

The active `universe-visibility` owner retains `tinyassets/api/visibility.py`, `tinyassets/api/wiki.py`, and its tests. This successor consumes those predicates; it does not redefine or edit them. The as-built identity contract already provides `tinyassets.api.permissions.current_request_actor_id()`, which returns the credential-validated request subject or `anonymous` without an environment fallback. Implementation consumes that resolver directly and must not multiply the known `_current_actor()` environment fallback.

## Goals / Non-Goals

**Goals:**

- Establish one request-local, credential-validated subject as branch authorship and authority truth.
- Make exact-ID reads of a foreign private branch indistinguishable from a missing branch.
- Gate cross-branch content reuse before executable content is copied.
- Preserve branch visibility across lineage projections.
- Require author authority for every mutation and deletion path.
- Apply existing page-listing visibility before related-wiki matching, ranking, counting, and response construction.
- Preserve public reads, author reads, granted wiki reads, stable response keys, and commit-conflict recovery.

**Non-Goals:**

- Modifying universe/page visibility predicates or audience classification.
- Using audience or discovery scope as authority.
- Implementing `run_branch` authority in this write-set; a sibling change consumes the helper.
- Changing the public MCP handle set or response schema.
- Making filesystem scans constant-time or claiming timing-side-channel resistance.
- Building or validating an Agent Village surface.
- Syncing these target requirements into as-built specs before implementation and acceptance pass.

## Decisions

### 1. Authenticated subject is the only branch authority identity

One branch-authority helper consumes `tinyassets.api.permissions.current_request_actor_id()`, the as-built request-local subject established by validated credentials. It treats `anonymous` as absent authority, does not call an identity helper that can fall back to `UNIVERSE_SERVER_USER`, and does not accept an actor, author, owner, or force value from action arguments.

Branch creation and composite build paths persist the authenticated subject as `author`. A caller-supplied `author` cannot select or impersonate another owner. A creation or mutation that requires authorship fails closed when no authenticated subject is available.

Alternative: reuse `_current_actor()` everywhere. Rejected because its environment fallback is an open authority defect and copying the expression would entrench it across every handler.

### 2. Read authorization returns one not-found envelope

The helper resolves a branch and returns either the branch or the canonical JSON error `{"error": "Branch '<id>' not found."}`. `get_branch`, `describe_branch`, `validate_branch`, `fork_tree`, and exact-branch node search use it before constructing any branch-derived output.

A missing branch and a foreign private branch have byte-identical serialized errors, key order, punctuation, and status behavior. No denial note, existence flag, author, visibility value, or different key set is emitted.

Alternative: return an explicit forbidden error. Rejected because exact IDs are enumerable and the private branch's existence is itself restricted metadata.

### 3. Cross-branch reuse is a read before it is a write

`node_ref.source` and `fork_from` first authorize the source branch using the same read helper. Authorization completes before a node body, `node_defs`, source code, prompt, tool list, or approval provenance is copied into caller-owned state.

Public sources and the authenticated author's private sources remain reusable. A foreign private source produces the same not-found envelope and no partial branch mutation.

Alternative: gate only the destination write. Rejected because authority over a caller-owned destination does not grant read authority over the source.

### 4. Lineage is a projection of readable branches

The root and each ancestor in `fork_tree` pass the read helper. Encountering an unreadable ancestor terminates traversal without a placeholder, count, or metadata row. Descendant enumerations pass the authenticated subject as `viewer`, so public descendants and the viewer's own private descendants appear while foreign private descendants do not.

Alternative: use `include_private=False`. Rejected because it prevents a legitimate owner from seeing their own private forks while still leaving root/ancestor exact-ID reads unguarded.

### 5. Mutation and deletion require author authority

`add_node`, `connect_nodes`, `set_entry_point`, `add_state_field`, `update_node`, `patch_nodes`, `approve_source_code`, `patch_branch`, and `delete_branch` all use one author-authority gate before changing state. Batch and empty-selection forms do not bypass the gate.

`force` remains available only after authority succeeds and only for the existing commit-conflict behavior. It cannot relax an author denial, and denial text never instructs a caller to retry with force.

Action-scope metadata in `retire-legacy-live-mcp-tools` remains an outer classification gate and must migrate in lockstep. It is defense in depth, not a substitute for object-level author authority.

Current-main audit evidence classifies `create_branch`, `build_branch`, `add_node`, `connect_nodes`, `set_entry_point`, `add_state_field`, `update_node`, `patch_nodes`, and `patch_branch` as `write`; `approve_source_code` and `delete_branch` remain the stricter `admin`. `require_action_scope` denies a gated dispatch when metadata is absent. This change preserves or tightens those effects and adds author authority underneath them; it never downgrades approval or deletion to ordinary write.

Alternative: rely on write/costly action classification alone. Rejected because action permission does not prove ownership of the target branch and missing metadata can drift.

### 6. Related wiki projection reuses the existing page-listing predicate

`_related_wiki_pages` parses page frontmatter, calls `visibility.page_visible_in_listing` with the applicable universe context, and excludes denied pages before title/body matching, scoring, sorting, cap application, count calculation, or item construction. It adds no audience/scope filter.

`items` and `truncated_count` are calculated exclusively from visible matches. When all matching pages are denied, the existing keys remain `[]` and `0`, indistinguishable from no matches. No `filtered_count`, caveat, denial note, hidden path, title, summary, `matched_via`, or cap displacement is exposed.

The allowed related-page paths for a caller must be a subset of the paths returned by the wiki listing boundary for the same corpus and authority context. Public pages and pages available to a granted reader remain unchanged.

Alternative: filter after scoring/capping. Rejected because hidden pages would still influence ordering, displace visible results, and leak through `truncated_count`.

### 7. Delivery is split by collision and module ownership

Wave 1 implements exact-ID reads, related-wiki filtering, and lineage in `branches.py`. Wave 2 gates cross-branch node/clone reuse. Wave 3 gates mutation and deletion and removes the force authority bypass. Each wave gets new focused RED-first tests after broad `tests/` claims release.

The sibling `harden-run-branch-access-authority` change owns `tinyassets/api/runs.py` and imports the shared read helper for canonical `run_graph`. Any required change to a universe/page visibility predicate is filed against the active `universe-visibility` owner.

## Risks / Trade-offs

- **[Risk] A local author comparison preserves the environment fallback.** → Block implementation on a request-local authenticated-subject authority seam and mutation-probe it.
- **[Risk] Tightening legacy actions breaks callers that relied on unauthorized behavior.** → Preserve response shapes and authorized behavior; treat unauthorized access as a security defect, not compatibility.
- **[Risk] Hidden wiki pages still affect result counts or ordering.** → Filter before match/score/sort/cap/count and test visible-set equivalence.
- **[Risk] Force semantics are accidentally removed entirely.** → Test that authorized commit-conflict recovery still works while force cannot bypass authority.
- **[Risk] Parallel visibility owners diverge.** → Consume existing predicates without editing their module; use explicit dependency rows for any predicate change.
- **[Risk] A gate exists but tests cannot turn it red.** → Mutation-probe every read, reuse, lineage, mutation, deletion, and projection gate before acceptance.

## Migration Plan

1. Land this reviewed target OpenSpec active and unsynced.
2. Reconfirm the as-built `current_request_actor_id()` no-fallback contract, wait for exact `tests/` claims to release, and claim the implementation files explicitly.
3. Implement Wave 1 reads, wiki projections, and lineage with RED-first tests.
4. Implement Wave 2 source reuse and clone gates with no-partial-copy tests.
5. Coordinate action-scope migration, then implement Wave 3 mutation/deletion authority and force separation.
6. Land the separately claimed `run_branch` sibling using the same helper.
7. Run focused tests, surrounding suites, Ruff, mutation probes, concurrent cross-actor §14 proof, canonical MCP canary, rendered two-actor chatbot acceptance, and post-fix clean-use observation.
8. Sync and archive only after all owned tasks and applicable acceptance evidence pass.

Rollback reverts the unactivated implementation commits. Once activated, rollback must not re-enable unauthorized reads, reuse, mutation, deletion, or execution; a forward fix or fail-closed disablement is required.

## Resolved Questions

- Branch authority consumes `tinyassets.api.permissions.current_request_actor_id()`; PR #1691 is provider-destination authority and is not a dependency of this change.
- Every branch creation surface covered here rejects `anonymous`; legacy anonymous or environment-attributed creation is intentionally retired rather than grandfathered.
- Root-wiki related-page projections pass the same blank `universe_id=""` context as the root wiki surfaces. Current main is already fail-closed because `list_universe_acl` returns `[]` for a blank universe ID before storage access; a 2026-07-25 raw-DML forge probe confirmed even an injected empty-ID ACL row cannot grant root-page visibility.
- Cross-branch `search_nodes` retains readable/public discovery through visibility-aware enumeration. Supplying an exact branch ID uses the byte-identical private-or-missing read boundary.
