## 1. Contract promotion

- [x] 1.1 Audit current-main branch reads, source reuse, lineage, mutation, deletion, related-wiki projection, run execution, active visibility ownership, and existing tests against the connector-first product boundary.
- [x] 1.2 Define target requirements for authenticated-subject authorship, not-found read equivalence, source reuse, lineage, mutation/deletion authority, action-scope defense in depth, and cross-surface wiki visibility.
- [ ] 1.3 Obtain Opus 5 review of the drafted proposal, design, both delta specs, tasks, and sibling-lane boundary; resolve every Critical and Important finding.
- [ ] 1.4 Run strict OpenSpec validation and land this target change active and unsynced.

## 2. Dependency and claim gates

- [ ] 2.1 Consume the as-built `tinyassets.api.permissions.current_request_actor_id()` seam, assert that `anonymous` carries no branch authority, and mutation-probe the absence and environment-only cases; PR #1691 is not a dependency.
- [x] 2.2 Record current-main evidence that blank-universe page-grant evaluation is fail-closed without changing `visibility.py`: `list_universe_acl` returns `[]` before storage access for `universe_id=""`, and a 2026-07-25 temporary-database raw-DML forge probe showed an injected empty-ID ACL row still cannot make a private root page visible.
- [ ] 2.3 Coordinate `retire-legacy-live-mcp-tools` tasks 4.2/4.4 so every branch mutation and deletion stays non-read and missing metadata denies during registry migration. Current-main evidence already proves edits are `write`, approval/deletion are `admin`, and an absent row returns no metadata and is rejected; the remaining gate is lockstep preservation through that migration.
- [ ] 2.4 Wait for broad `tests/` claims to release, then claim `tinyassets/api/branches.py`, the narrow `tinyassets/daemon_server.py::search_nodes` seam, `tests/test_branch_read_authority.py`, `tests/test_related_wiki_visibility.py`, and `tests/test_branch_mutation_authority.py` before implementation.

## 3. Wave 1 — reads, projections, and lineage

- [ ] 3.1 In `tests/test_branch_read_authority.py`, add RED tests for server-bound create/build authorship plus authoring-receipt actor, `anonymous` denial, and an environment-only actor; each test must fail against the current `_current_actor()`/caller-author behavior.
- [ ] 3.2 In the same file, add RED listing tests proving an environment-only actor exposes no private row/count, unauthenticated `scope=mine` is `[]`/`0`, and an authenticated author still sees their own private branch. Add reusable-node search tests proving public-plus-own-private candidates/counts and zero foreign/environment-private influence. Add RED table tests for get/describe/validate/fork-tree private-or-missing byte equivalence, plus a private-name case proving environment identity cannot resolve or replace the original selector with the canonical ID; keep explicit public and owner controls.
- [ ] 3.3 In `tinyassets/api/branches.py`, add `_request_branch_actor() -> str | None`, `_resolve_readable_branch(selector: str, base_path: str) -> tuple[str, dict[str, Any]] | None`, and `_branch_not_found(selector: str) -> str`. These consume `current_request_actor_id()`, treat `anonymous` as absent, resolve names only through visibility-aware enumeration, and preserve the original selector for denial output.
- [ ] 3.4 Server-bind branch create/build authorship and authoring-receipt actor through `_request_branch_actor`, use it as the only `list_branches` viewer, add/pass `viewer` through `daemon_server.search_nodes` before aggregation, then wire `_resolve_readable_branch` before output construction in get, describe, validate, and fork-tree root.
- [ ] 3.5 In `tests/test_related_wiki_visibility.py`, add RED tests for filter-before-match/sort/cap/count, zero hidden fields/counts, all-hidden `[]`/`0`, public/granted controls, and related-path subset equality against wiki list.
- [ ] 3.6 Wire `page_visible_in_listing` into `_related_wiki_pages` before matching without adding audience filtering or changing stable keys.
- [ ] 3.7 Add RED lineage cases for an unreadable ancestor, owner-private descendant, and foreign-private descendant; then authorize each ancestor through `_resolve_readable_branch` and pass `_request_branch_actor()` as the descendant viewer.
- [ ] 3.8 Run `python -m pytest tests/test_branch_read_authority.py tests/test_related_wiki_visibility.py tests/test_universe_visibility.py -q`; require all tests to pass, then independently mutation-probe selector resolution, page filtering, and ancestor/descendant gates before the Wave 1 commit.

## 4. Wave 2 — private source reuse

- [ ] 4.1 Add a RED `node_ref.source` test that snapshots destination bytes, attempts foreign-private reuse, and proves source code, prompt, tools, description, and approval provenance are neither returned nor persisted; include public and owner-private controls proving authorized copied authorship/approval provenance is preserved.
- [ ] 4.2 Gate node-reference lookup through `_resolve_readable_branch` before `_lookup_node_body` reads any source field; run the Wave 2 node-reference cases to green and commit independently.
- [ ] 4.3 Add a RED `fork_from` test that snapshots destination/nonexistence, attempts a foreign-private clone, and proves no `node_defs`, metadata, version, or partial destination survives; include public and owner-private controls.
- [ ] 4.4 Gate fork snapshot loading through `_resolve_readable_branch` before clone materialization; run `python -m pytest tests/test_branch_read_authority.py -q`, mutation-probe both reuse gates, and commit independently.

## 5. Wave 3 — mutation and deletion authority

- [ ] 5.1 In `tests/test_branch_mutation_authority.py`, add RED non-author and owner controls for add-node, connect, entry-point, and state-field mutations, asserting byte-identical branch state after denial; foreign-private ID/name cases must match missing selectors, readable-public non-owner cases must expose no stored author, and a caller-supplied new-node author must be replaced by the authenticated subject.
- [ ] 5.2 Add `_branch_authorized(branch: dict[str, Any]) -> bool` using `_request_branch_actor`; resolve targets through `_resolve_readable_branch`, gate the four structural mutations before target expansion or persistence, server-bind new-node/git/receipt attribution, and emit one generic no-author-details denial for readable non-owned branches. Run only those cases to green and commit.
- [ ] 5.3 Add RED non-author and owner controls for update-node, patch-nodes (including empty selection), and approve-source-code, asserting no source/provenance or batch expansion changes after denial, private-or-missing response equivalence, and authenticated-subject approval/new-node attribution.
- [ ] 5.4 Resolve targets through `_resolve_readable_branch`, then gate update-node, patch-nodes, and approve-source-code through `_branch_authorized` before selection expansion or persistence; server-bind new provenance through `_request_branch_actor`, run those cases to green, and commit.
- [ ] 5.5 Add RED patch-branch tests proving private-or-missing equivalence, generic readable-public non-author denial, identical denial under `force=true`, no stored-author/retry-with-force guidance, and preserved authorized conflict recovery.
- [ ] 5.6 Resolve patch-branch through `_resolve_readable_branch`, move `_branch_authorized` ahead of force/conflict handling, and server-bind version publisher/git/receipt attribution; run the patch cases to green and commit without changing authorized force semantics.
- [ ] 5.7 Add RED delete tests proving private-or-missing equivalence and that a readable-public non-author cannot remove the branch, versions, or backing files while the author still can.
- [ ] 5.8 Resolve the target through `_resolve_readable_branch`, then gate delete through `_branch_authorized` before any deletion call and run the delete cases to green.
- [ ] 5.9 Add registry assertions that structural/node/patch actions are `write`, approval/deletion are `admin`, and missing metadata is denied; coordinate these exact effects with retirement tasks 4.2/4.4.
- [ ] 5.10 Run `python -m pytest tests/test_branch_mutation_authority.py tests/test_branch_read_authority.py -q`, surrounding branch/storage suites, and mutation probes for every authority call site before the Wave 3 commit.

## 6. Sibling canonical execution boundary

- [ ] 6.1 Create and separately claim `harden-run-branch-access-authority` for `tinyassets/api/runs.py` and `tests/test_run_branch_authority.py` after the shared helper and broad test claims are available.
- [ ] 6.2 Add RED tests proving a foreign-private run selector matches the missing-selector response and starts no run/provider work; include public and owner-private controls.
- [ ] 6.3 Import `_resolve_readable_branch` lazily in `tinyassets/api/runs.py` and authorize before branch loading or execution, preserving the original selector on denial.
- [ ] 6.4 Run `python -m pytest tests/test_run_branch_authority.py -q`, the surrounding run/branch suites, and a mutation probe that removes the helper call and makes the foreign-private test fail.

## 7. Sibling branch evaluation and version boundary

- [ ] 7.1 Create and separately claim `harden-branch-evaluation-access-authority` for `tinyassets/api/evaluation.py` and `tests/test_branch_evaluation_authority.py` after the shared helpers and broad test claims are available.
- [ ] 7.2 Add RED publish/get/list branch-version tests proving foreign-private-or-missing equivalence, no version snapshot/count disclosure, author-only publish, authenticated-subject publisher provenance, and unchanged public/owner reads.
- [ ] 7.3 Add RED suggest-node-edit/list-node-versions/rollback-node tests proving private-or-missing equivalence, author-only rollback with byte-identical state after denial, and no run-linked disclosure without both branch and run read authority.
- [ ] 7.4 Import `_resolve_readable_branch`, `_branch_authorized`, and `_request_branch_actor` lazily in `tinyassets/api/evaluation.py`; authorize before branch/version/node/run material is loaded or mutated and server-bind publisher/rollback provenance.
- [ ] 7.5 Run `python -m pytest tests/test_branch_evaluation_authority.py -q`, surrounding evaluation/version/run suites, and mutation probes that independently remove each read/author gate.

## 8. Concurrency, public acceptance, and completion

- [ ] 8.1 Run a §14 concurrent cross-actor proof with at least two request contexts interleaving listing/search, selector reads, lineage, source reuse, mutation/deletion, execution, version/evaluation reads, and rollback against one private branch and restricted page set; prove zero cross-actor disclosure or mutation.
- [ ] 8.2 Run focused tests, surrounding suites, Ruff, strict OpenSpec validation, and independent correctness/security/concurrency/diff review; resolve every Critical and Important finding.
- [ ] 8.3 After deploy, pass canonical MCP handle canaries and a rendered two-actor chatbot conversation: actor A creates private branch/restricted material; actor B receives not-found and cannot list/search, reuse, mutate, delete, execute, version, inspect history, or roll it back.
- [ ] 8.4 Record dated post-fix clean-use evidence from real connector activity, or leave a monitoring row explicitly stating that organic evidence is not yet available.
- [ ] 8.5 Sync the graph and wiki requirements into as-built specs and archive only after all owned runtime, both sibling boundaries, proof, and acceptance tasks pass.
