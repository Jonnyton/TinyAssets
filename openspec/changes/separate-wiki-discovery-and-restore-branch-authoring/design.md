## Context

The shared wiki contains both user-remixable knowledge and operational history. Physical relocation would require a risky live-volume migration, break existing page paths/backlinks, and create two storage lifecycles. Deleting or exporting coordination history is forbidden by the task and would discard real project memory.

`read_page` already advertises `category`, but `_wiki_search` discards it through `**_kwargs`. There is no audience boundary. The newest live feed contains 1,418 post-2026-05-01 pages and the tested onboarding queries return only coordination records.

The public `write_graph` router currently sends every `target=branch` call to `patch_branch`; its signature has no `spec_json`. The existing internal `build_branch` handler and validation contract are already mature, so a new primitive is unnecessary.

## Decision

Use one store with two logical read scopes.

- `scope=discovery` is the default for search, since-feed, and ambient results.
- `scope=coordination` exposes only coordination-classified pages.
- `scope=all` preserves the historical unfiltered behavior.
- An exact `page=` read remains addressable in every scope; only its ambient feed is scoped.
- Frontmatter `audience: discovery|coordination` is authoritative.
- Legacy pages without `audience` use a deterministic category fallback. Ambiguous scratch-heavy categories default to coordination; established knowledge/project categories default to discovery.

This is a logical namespace, not a heuristic relevance penalty. It is reversible per call, preserves stable paths, requires no data migration, and lets valuable legacy user pages re-enter discovery by adding one explicit frontmatter field.

Restore branch creation additively on the existing `write_graph` handle:

- `target=branch`, no `branch_id`, `spec_json=<object JSON>` -> existing `build_branch` handler.
- `target=branch`, `branch_id=<id>`, `changes_json=<list JSON>` -> existing `patch_branch` handler.
- Supplying create and patch payloads together returns a structured ambiguity error.

The canonical schema lives at `pages/workflows/workflow-definition-schema.md`, is tagged `audience: discovery`, and is named explicitly in the `spec_json` field description so both schema inspection and wiki search lead to the same contract.

## Rejected Alternatives

### Physically move coordination into another root

Rejected for this fix: it needs a live-volume migration, backlink rewriting, rollback machinery, and dual-root operations before onboarding can recover.

### Move coordination out of the wiki entirely

Rejected: coordination is durable project history and existing tools/links rely on wiki page identity.

### Build three parallel discovery mechanisms

Rejected: it multiplies contracts. A scoped read boundary solves the observed failure and remains compatible with a later physical migration if scale requires it.

## Risks and Mitigations

- Some useful legacy notes/plans become hidden from default search. Mitigation: exact reads remain intact, `scope=all` is available, and `audience: discovery` is a one-field promotion.
- Coordination might be misfiled under a knowledge category. Mitigation: authors can set `audience: coordination`; tests cover explicit override precedence.
- Public branch creation could diverge from internal validation. Mitigation: route directly to the existing `build_branch` handler and assert round-trip behavior rather than reimplementing the schema.
