## Why

Canonical connector branch actions do not share one authenticated-subject authority boundary. A caller can currently reuse executable node content from another actor's private branch, while legacy ID/name selector reads, mutations, deletion, lineage, and related-wiki projections expose or alter private material through inconsistent or missing checks.

## What Changes

- Add one fail-closed branch authority and durable-provenance contract keyed to the authenticated subject, never an environment-derived or caller-supplied actor.
- Make branch listing derive its viewer only from the authenticated subject, and make every ID/name selector read return the same not-found envelope for a nonexistent branch and a foreign private branch without leaking a resolved canonical ID from a guessed private name.
- Gate cross-branch node references and branch cloning before private source content is read or copied.
- Make lineage enumeration preserve the same visibility boundary for roots, ancestors, and descendants.
- Require author authority for branch mutation and deletion; a caller-supplied `force` value may resolve a commit conflict but cannot bypass authority.
- Apply the existing universe/page visibility predicates to branch-originated related-wiki projections before matching, scoring, sorting, counting, or response construction.
- Preserve public behavior, owner access (including owner-private reusable-node search), granted-reader access, and stable empty response keys while eliminating hidden paths, titles, summaries, match metadata, and counts.
- Track canonical `run_graph`/version execution plus later run read/write/output authority as a separately claimed sibling change that consumes the shared helper and stores universe context independently of synthetic actor provenance.
- Track branch-version and node-evaluation reads/mutations in `tinyassets/api/evaluation.py` as a separately claimed sibling change that consumes the same read/author helpers.
- Track scheduled and universe-loop execution as a separately claimed background-authority sibling: an authenticated subject may bind a public target or their own private target, the server creates an immutable binding receipt, and zero-host execution consumes that receipt rather than a live request, environment actor, or caller-supplied owner.
- Track live branch-adjacent `goals`, `gates`, leaderboard, gate-event citation, remix/provenance, and dry-inspection paths as a separately claimed sibling change: branch/version binding, claim/conformance attachment and lifecycle reads, every private-derived projection, attribution edges, and structural previews must consume the same request-subject authority boundary.
- Require a graph-owned `branch-authority-isolation-v1` scenario through the shared production-load-evidence protocol before completion; deterministic two-actor tests and shaped/mock load runs cannot substitute for real canonical connector/storage evidence.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `graph-execution-substrate`: Add branch read, reuse, lineage, mutation, and deletion authority requirements.
- `wiki-commons`: Extend page-listing visibility to related-page projections originating outside the wiki action surface.

## Impact

The core implementation affects `tinyassets/api/branches.py`, the `search_nodes(viewer=...)` storage seam in `tinyassets/daemon_server.py`, and new focused branch-authority tests. Separately claimed siblings own `tinyassets/api/runs.py`, `tinyassets/api/evaluation.py`, and the branch-adjacent goals/gates/projection modules enumerated in the design and tasks. All consume the as-built no-environment-fallback actor resolver in `tinyassets/api/permissions.py`; the core lane reuses `tinyassets/api/visibility.py` and `tinyassets/api/wiki.py` without modifying them, and any predicate change remains owned by `universe-visibility`. The work depends on lockstep action-scope classification in `retire-legacy-live-mcp-tools`, release of broad `tests/` claims, and the shared production-load harness before final proof. This proposal changes no MCP schema, deployment, canonical as-built spec, or Agent Village surface.
