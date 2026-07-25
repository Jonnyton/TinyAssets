## Why

Canonical connector branch actions do not share one authenticated-subject authority boundary. A caller can currently reuse executable node content from another actor's private branch, while legacy ID/name selector reads, mutations, deletion, lineage, and related-wiki projections expose or alter private material through inconsistent or missing checks.

## What Changes

- Add one fail-closed branch authority contract keyed to the authenticated subject, never an environment-derived or caller-supplied actor.
- Make every ID/name selector read return the same not-found envelope for a nonexistent branch and a foreign private branch, without leaking a resolved canonical ID from a guessed private name.
- Gate cross-branch node references and branch cloning before private source content is read or copied.
- Make lineage enumeration preserve the same visibility boundary for roots, ancestors, and descendants.
- Require author authority for branch mutation and deletion; a caller-supplied `force` value may resolve a commit conflict but cannot bypass authority.
- Apply the existing universe/page visibility predicates to branch-originated related-wiki projections before matching, scoring, sorting, counting, or response construction.
- Preserve public behavior, owner access, granted-reader access, and stable empty response keys while eliminating hidden paths, titles, summaries, match metadata, and counts.
- Track canonical `run_graph` execution of a foreign private branch as a separately claimed sibling change that consumes the shared helper.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `graph-execution-substrate`: Add branch read, reuse, lineage, mutation, and deletion authority requirements.
- `wiki-commons`: Extend page-listing visibility to related-page projections originating outside the wiki action surface.

## Impact

The later implementation affects `tinyassets/api/branches.py` and new focused branch-authority tests. It consumes the as-built no-environment-fallback actor resolver in `tinyassets/api/permissions.py`, and reuses `tinyassets/api/visibility.py` and `tinyassets/api/wiki.py` without modifying them; any predicate change remains owned by `universe-visibility`. It depends on lockstep action-scope classification in `retire-legacy-live-mcp-tools` and release of broad `tests/` claims. This proposal changes no runtime, MCP schema, deployment, canonical as-built spec, or Agent Village surface.
