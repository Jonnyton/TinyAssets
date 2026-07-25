## Why

The public wiki commons stores both remixable user knowledge and durable agent
coordination records, but its default search, freshness feed, and ambient
recommendations currently mix the two. That low-signal context already caused a
new-user chatbot to surface internal development history and refuse the user's
actual build request; the same handler also advertises a category filter that it
does not enforce.

## What Changes

- Default wiki search and changed-since feeds to a deterministic `discovery`
  audience; default an exact-read ambient feed to the audience of the source
  page so discovery and coordination cross-reference within their own class.
- Preserve coordination records at their existing paths and support explicit
  core `coordination` and `all` scopes without adding a tool, action, store, or
  privacy boundary.
- Let explicit `audience: discovery|coordination` metadata override a
  deterministic legacy-category fallback.
- Enforce the existing category parameter after authority and audience
  filtering, and fail closed on invalid scope/category input.
- Fix the pre-existing exact-read ambient-feed visibility defect so restricted
  page paths, titles, and excerpts are withheld before relevance filtering.
- Return applied-scope evidence and a non-fatal note when a default scope
  filtered results, avoiding silent narrowing for in-process callers.
- Preserve exact page-body reads, list behavior, universe ACLs, visibility
  filtering, drafts, custom categories, and all stored content.
- Keep the canonical and packaged wiki implementation byte-identical and add a
  named concurrent-search proof.
- Defer advertising a public `read_page.scope` parameter until the active
  universe-server owner releases that interface seam.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `wiki-commons`: Define audience-scoped retrieval defaults, classification,
  category enforcement, authority precedence, invalid-input behavior, and
  concurrent default-search isolation.

## Impact

- OpenSpec: `wiki-commons` only in this phase.
- Runtime: `tinyassets/api/wiki.py` and its packaged Claude-plugin mirror.
- Tests: `tests/test_api_wiki.py` and `tests/test_wiki_tools.py`.
- Public behavior: existing `read_page` calls immediately inherit safer,
  higher-signal default results through the same implementation; the behavior
  changes in this phase even though the MCP parameter schema and seven-tool
  surface do not.
- Excluded: both `universe_server.py` copies, retired directory-server code,
  branch authoring, workflow schema assets, and stored wiki data.
