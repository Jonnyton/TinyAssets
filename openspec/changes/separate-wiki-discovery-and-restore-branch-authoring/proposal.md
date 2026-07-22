## Why

The shared wiki is the only knowledge surface a new connector user can search, but it has become an internal agent-coordination archive. A live 2026-07-21 probe found 1,418 pages changed since 2026-05-01 (up from 614 on 2026-05-19) and 40 of 40 top results across four onboarding queries were internal Codex/Cowork/Claude, PR, BUG, gate, or host-approval records. A new user asking for a research tracker was consequently warned away from TinyAssets.

The same live conversation exposed a second break: the seven-handle public surface can patch an existing branch, but `write_graph` has no branch-create payload and the branch definition schema is absent from the discoverable wiki. A willing chatbot therefore cannot create the workflow it was asked to build.

## What Changes

- Make `read_page` search, freshness feeds, and ambient recommendations default to a logical `discovery` scope.
- Preserve every coordination page and exact-page read. Expose coordination history through explicit `scope=coordination` and the complete corpus through `scope=all`.
- Honor the already-advertised `category` search filter.
- Classify legacy mixed wiki content conservatively: `notes`, `plans`, `bugs`, `patch-requests`, and `design-proposals` are coordination unless frontmatter explicitly declares `audience: discovery`; other categories are discovery unless explicitly declared `audience: coordination`.
- Add additive `spec_json` support to `write_graph(target="branch")`: no `branch_id` creates a branch through the existing `build_branch` handler; a `branch_id` continues to patch through `patch_branch`.
- Publish a canonical `audience: discovery` workflow-definition schema page with a minimal valid branch example.

## Capabilities

### Modified Capabilities

- `wiki-commons`: scoped discovery and category filtering over the preserved shared corpus.
- `live-mcp-connector-surface`: additive branch creation and discoverable branch-schema guidance on existing handles.

## Impact

- Runtime: `tinyassets/api/wiki.py`, `tinyassets/universe_server.py`, and byte-parity plugin mirrors.
- Tests: wiki discovery/filter regression coverage and live-handle branch-create/schema coverage.
- Data: no page deletion, move, or rewrite; legacy classification is read-time and explicit frontmatter can override it.
- Compatibility: exact reads and branch patching stay unchanged; callers that intentionally search coordination history must opt into `scope=coordination` or `scope=all`.
- Deployment: requires the normal live connector deploy, public canary, rendered chatbot `ui-test`, and post-fix organic-use watch.
