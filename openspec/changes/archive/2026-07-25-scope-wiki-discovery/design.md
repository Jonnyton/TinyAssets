## Context

The root wiki is a public-by-definition commons under PLAN's commons-first
architecture. It contains two useful but different relevance classes:
user-facing knowledge meant for discovery/remix and durable coordination
history meant for operators and agents who intentionally inspect it. Current
retrieval treats both as one corpus, and the existing `category` parameter is
not enforced.

This change must preserve the existing authority model. Universe ACLs and
`page_visible_in_listing` decide whether a caller may discover a page at all;
audience classification only narrows already-visible material for relevance.
The active universe-creation lane owns `universe_server.py`, so this phase
changes the shared implementation's default behavior without changing the MCP
tool schema.

## Goals / Non-Goals

**Goals:**

- Give omitted-scope retrieval a deterministic, high-signal discovery default.
- Preserve coordination history and explicit in-process access to it.
- Make the advertised category filter truthful.
- Preserve ACL/visibility semantics, exact reads, list behavior, custom
  taxonomy, storage layout, and the seven-tool MCP surface.
- Prove canonical/plugin parity and concurrent default isolation.

**Non-Goals:**

- Privacy, confidentiality, redaction, or authorization.
- A new tool, action, store, index, taxonomy whitelist, or content migration.
- Publicly advertising `read_page.scope` in this phase.
- Branch creation, workflow-definition schema, or any retired directory
  runtime.

## Decisions

### Audience is a read-time relevance classification

The implementation classifies each candidate at read time. Explicit
frontmatter `audience: discovery|coordination` wins after trimming surrounding
whitespace and casefolding. An absent, empty, or whitespace-only audience is
unset and falls back deterministically by normalized category: `notes`,
`plans`, `bugs`, `feature-requests`, `patch-requests`, and
`design-proposals` are coordination; every other valid category, including
custom categories, is discovery. A page directly under `pages/` or `drafts/`
has no category component and defaults to discovery.

A set but unrecognized audience value fails closed toward coordination; it
never falls back to a discovery category. The response's applied scope makes
the filtering legible without process-global warning state or per-candidate log
amplification. This keeps the taxonomy open, avoids a migration, and prevents a
typo such as `audience: internel` from widening relevance.

Alternative rejected: move coordination pages to another store. That would
break stable paths, duplicate the commons primitive, and turn a relevance
problem into a migration.

### Authority filters precede relevance filters

For every search, since-feed, and ambient candidate:

1. parse scope/category inputs once and reject invalid input before enumeration;
2. parse candidate metadata;
3. apply existing universe ACL/`page_visible_in_listing`;
4. apply audience scope;
5. apply normalized category;
6. only then score or construct response fields.

Audience/category filters can only narrow material the caller could already
list. `scope=all` never bypasses authority. Exact page-body reads keep their
existing ACL and path behavior; only their optional ambient recommendations are
filtered.

Current main does not pass `universe_id` into `_ambient_relevance_feed` and
does not call `page_visible_in_listing` there. This phase threads the universe
context and fixes that pre-existing defect before audience filtering, under the
in-flight universe-visibility change rather than implying already-canonical
visibility truth.

Alternative rejected: audience before visibility. It is not an authority bug
by itself, but it obscures which layer owns disclosure decisions and makes
future changes easier to get wrong.

### Core scope lands before public schema advertisement

The implementation entry point trims `scope` and treats an omitted, empty, or
whitespace-only value as unset. Search and since resolve unset scope to
`discovery`. Exact-read ambient recommendations resolve it to the source
page's audience class, computed by the same classifier applied to candidates,
so an unrecognized audience on the source yields coordination, not its
category fallback. This preserves coordination-to-coordination
cross-referencing before the public router advertises a scope parameter.

The existing canonical `read_page` forwarding immediately gets safer defaults.
Explicit `coordination` and `all` are available to reviewed in-process callers,
including compiled read-only wiki aliases, but are not advertised as a public
MCP parameter until the current `universe_server.py` owner releases that seam.
That owner must also forward `category` on exact reads and allow
`changed_since` plus `category` to reach the since action; both public-wrapper
category gaps are deferred with the schema seam rather than hidden here.

No compatibility shim preserves the unsafe default. Internal callers that
intend coordination discovery must become explicit. Exact reads and `list`
remain available for inspection and recovery.

Every search, since, and exact-read response with an ambient feed reports the
applied `scope`. When scope was omitted and audience filtering removed one or
more candidates that would otherwise have entered the result set, the response
also reports a short non-fatal `scope_note` explaining how an in-process caller
can request coordination or all. Invalid-scope responses report an error
rather than an applied scope; unchanged list responses remain unscoped. This
follows the self-auditing-tools principle and turns narrowing into legible
behavior without adding noise for unrelated zero-scoring pages.

### Category uses the existing open-taxonomy normalizer

A supplied category is normalized with the same safe slug rule used by writes.
For search or since, an explicitly supplied value whose normalized slug is
empty returns a structured error and no results. An exact read still returns
the requested body unchanged, while its nested ambient feed reports the
invalid-category error with no recommendation items. A valid but currently
absent/custom category is allowed and returns zero or matching results; it is
not rejected against the seed taxonomy. Filtering compares the normalized
category segment for both pages and drafts.

### One implementation, mirrored bytes

Helpers and handler changes live in `tinyassets/api/wiki.py`. The supported
`python packaging/claude-plugin/build_plugin.py` generator refreshes the
packaged Claude-plugin copy, which SHALL be byte-identical. No new module or
abstraction is added.

## Risks / Trade-offs

- **Legacy notes or plans intended for users disappear from ambient results** →
  add `audience: discovery`; exact reads and list remain stable.
- **An internal caller depended on mixed default search** → require explicit
  `scope=coordination|all`, and return applied-scope evidence plus a note when
  default filtering occurred; do not retain a compatibility alias.
- **Custom coordination category defaults to discovery** → authors can declare
  `audience: coordination`; open taxonomy and commons-first behavior make
  discovery the least surprising fallback for unknown categories.
- **Audience is mistaken for privacy** → responses/specs call it relevance and
  tests prove visibility denial still wins under every scope.
- **Concurrent requests leak mutable filter state** → helpers are pure and
  request-local; a 256-call mixed-corpus proof verifies single-process
  determinism without claiming the separate full-platform §14 load suite.
- **Stale draft PRs carry incidental edits to the same files** → treat them as
  source only unless their owners restore a current STATUS claim; never merge
  or resurrect retired directory code.

## Migration Plan

1. Land the OpenSpec delta and RED tests on current main.
2. Implement request-local classification/filtering and mirror exact bytes.
3. Run focused, surrounding, parity, strict OpenSpec, and concurrency gates.
4. Independently review the exact head.
5. Sync the implemented delta into canonical `wiki-commons` and archive the
   change in the same code-landing lane, as required by the project OpenSpec
   contract; do not include the deferred public scope parameter.
6. Deploy from main, prove the deployed SHA, rerun the contamination probes,
   and prove the exact-seven
   `https://tinyassets.io/mcp` surface, run a rendered chatbot onboarding
   conversation, then watch for post-fix organic use.

Rollback reverts the runtime/spec commit. It never moves or rewrites wiki data,
so no data rollback is required.

## Open Questions

- Whether the later public `read_page.scope` phase should expose
  `coordination|all` to anonymous callers or require authenticated/operator
  authority. That interface decision is deliberately outside this core-default
  phase.
