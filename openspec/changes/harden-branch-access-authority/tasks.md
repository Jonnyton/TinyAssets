## 1. Contract promotion

- [x] 1.1 Audit current-main branch reads, source reuse, lineage, mutation, deletion, related-wiki projection, run execution, active visibility ownership, and existing tests against the connector-first product boundary.
- [x] 1.2 Define target requirements for authenticated-subject authorship, not-found read equivalence, source reuse, lineage, mutation/deletion authority, action-scope defense in depth, and cross-surface wiki visibility.
- [ ] 1.3 Obtain Opus 5 review of the drafted proposal, design, both delta specs, tasks, and sibling-lane boundary; resolve every Critical and Important finding.
- [ ] 1.4 Run strict OpenSpec validation and land this target change active and unsynced.

## 2. Dependency and claim gates

- [ ] 2.1 Consume the as-built `tinyassets.api.permissions.current_request_actor_id()` seam, assert that `anonymous` carries no branch authority, and mutation-probe the absence and environment-only cases; PR #1691 is not a dependency.
- [x] 2.2 Record current-main evidence that blank-universe page-grant evaluation is fail-closed without changing `visibility.py`: `list_universe_acl` returns `[]` before storage access for `universe_id=""`, and a 2026-07-25 temporary-database raw-DML forge probe showed an injected empty-ID ACL row still cannot make a private root page visible.
- [ ] 2.3 Coordinate `retire-legacy-live-mcp-tools` tasks 4.2/4.4 so every branch mutation and deletion stays non-read and missing metadata denies during registry migration.
- [ ] 2.4 Wait for broad `tests/` claims to release, then claim `tinyassets/api/branches.py`, `tests/test_branch_read_authority.py`, `tests/test_related_wiki_visibility.py`, and `tests/test_branch_mutation_authority.py` before implementation.

## 3. Wave 1 — reads, projections, and lineage

- [ ] 3.1 Add RED tests proving private exact-ID get/describe/validate/fork-tree/node-search responses are byte-identical to missing-branch responses for non-owners, while public and owner reads remain unchanged.
- [ ] 3.2 Add RED related-wiki tests proving visibility filtering precedes matching/sort/cap/count, restricted pages expose no fields or counts, all-hidden results keep `[]`/`0`, and related paths are a subset of wiki-list paths for the same caller.
- [ ] 3.3 Add the shared authenticated-subject branch read/author helper and server-bind branch creation/composite authorship; do not accept environment or caller identity as authority.
- [ ] 3.4 Wire the shared read helper into get, describe, validate, fork-tree root, and exact-branch node search before response construction.
- [ ] 3.5 Wire `page_visible_in_listing` into `_related_wiki_pages` before match/score/sort/cap/count without adding audience filtering or changing stable keys.
- [ ] 3.6 Authorize lineage ancestors and pass the authenticated viewer into descendant enumeration so owners see own private forks and non-owners do not.
- [ ] 3.7 Run the focused Wave 1 tests and surrounding branch/wiki visibility suites; mutation-probe each new gate and resolve every failure.

## 4. Wave 2 — private source reuse

- [ ] 4.1 Add RED tests for foreign-private `node_ref.source` and `fork_from`, including source-code/prompt/tool/provenance non-copy and byte-identical destination state after denial.
- [ ] 4.2 Gate node-reference lookup and fork cloning through the shared read helper before reading or copying source content.
- [ ] 4.3 Prove public and author-owned private reuse remain unchanged, then mutation-probe both source gates.

## 5. Wave 3 — mutation and deletion authority

- [ ] 5.1 Add RED tests for every mutation handler, empty-selection batch patch, source-code approval, deletion persistence, and caller-supplied force bypass.
- [ ] 5.2 Apply one author-authority gate before target expansion or state change in add-node, connect, entry-point, state-field, update-node, patch-nodes, approve-source-code, patch-branch, and delete-branch.
- [ ] 5.3 Separate force from authority: preserve authorized commit-conflict recovery while making non-author denial invariant under force and removing retry-with-force guidance.
- [ ] 5.4 Verify the action-scope registry denies missing metadata and retains non-read classification for every Wave 3 handler.
- [ ] 5.5 Run focused and surrounding mutation/storage tests and mutation-probe every authority gate.

## 6. Sibling canonical execution boundary

- [ ] 6.1 Create and separately claim `harden-run-branch-access-authority` for `tinyassets/api/runs.py` and `tests/test_run_branch_authority.py` after the shared helper and broad test claims are available.
- [ ] 6.2 Make canonical `run_graph` authorize the target branch through the shared read boundary before loading or executing it; preserve public and owner execution.

## 7. Concurrency, public acceptance, and completion

- [ ] 7.1 Run a §14 concurrent cross-actor proof with at least two request contexts interleaving reads, lineage, source reuse, and mutations against one private branch and restricted page set; prove zero cross-actor disclosure or mutation.
- [ ] 7.2 Run focused tests, surrounding suites, Ruff, strict OpenSpec validation, and independent correctness/security/concurrency/diff review; resolve every Critical and Important finding.
- [ ] 7.3 After deploy, pass canonical MCP handle canaries and a rendered two-actor chatbot conversation: actor A creates private branch/restricted material; actor B receives not-found and cannot reuse, mutate, delete, or execute it.
- [ ] 7.4 Record dated post-fix clean-use evidence from real connector activity, or leave a monitoring row explicitly stating that organic evidence is not yet available.
- [ ] 7.5 Sync the graph and wiki requirements into as-built specs and archive only after all owned runtime, sibling execution, proof, and acceptance tasks pass.
