# Repo-search primitive: `search_repo_files`

Date: 2026-05-29
Status: proposed (sibling of `read_repo_files`, design note
`docs/design-notes/2026-05-29-read-repo-files-primitive.md`, impl PR #1152)
Writer: Claude. Checker gate: opposite-provider (Codex/Cowork) + host merge key.

## Problem

The user-buildable patch-request loop can now read named files
(`read_repo_files`) and open PRs (`github_pull_request`). The cutover loop
(`patch_request_loop_v3`) feeds on the dispatcher's `bug_investigation` payload
and a `localize` node turns the filed request into `target_paths`. That works
when the `component` field already names a file (e.g. `workflow/api/wiki.py`) or
a dotted module — ~30 of the 68 stuck backlog items. The other ~38 name a
*concept* (`wiki`, `extensions.run_branch provider execution`,
`graph_compiler / node_sandbox / executors`) with no directly-nameable path. The
loop can describe the change but cannot find the file to edit, so it fail-safe
REJECTs. To make the **whole** backlog flow through the new loop at cutover, the
loop needs to discover paths from a free-text description — a repo *search*.

## Decision

Ship one minimal, opaque, platform-trusted callable: **`search_repo_files`**
(domain `workflow`). It lists the repository's file paths and returns those whose
repo-relative path matches the caller's query terms/globs. It is the
localization counterpart to `read_repo_files`: `localize → search_repo_files →
(refine) → read_repo_files → propose → review → open_pr`.

### Why path-search, not content grep

`search_repo_files` matches against **file paths**, via the GitHub Git Trees API
(`GET /repos/{owner}/{repo}/git/trees/{ref}?recursive=1`). The alternative —
GitHub *code search* (`/search/code`, content grep) — was rejected for now:

- Code search **requires authentication**; our default posture is unauthenticated
  reads (subscription-only, no API keys — see `WORKFLOW_ALLOW_API_KEY_PROVIDERS`
  policy). The Git Trees API is unauthenticated for public repos.
- Code search **only indexes the default branch** and **lags behind HEAD**; the
  trees API reflects the exact ref with no indexing lag.
- Path-name search composes well with the LLM: component fields in the backlog
  are module/file/dotted names, which map to paths by name. The `localize` node
  already extracts `file:line` refs from `observed`; search fills the gap for
  concept-named components.

Content grep, if a future need proves path-search insufficient, is a **separate**
minimal primitive (`grep_repo`) gated on a read token — not folded in here
(minimal-primitives discipline: one capability per primitive).

## Contract

Opaque callable `fn(state) -> dict`:

Reads from state:
- `search_destination` — `owner/repo`; falls back to `read_destination` /
  `destination` so it composes with `read_repo_files` without re-declaring.
- `search_query` — whitespace/comma/semicolon-separated terms. A term with glob
  chars (`* ? [ ]`) is matched as an fnmatch glob against the path; otherwise a
  case-insensitive substring. Dotted names (`workflow.api.wiki`) also match the
  slash form (`workflow/api/wiki`).
- `search_ref` — optional branch/tag/sha; empty ⇒ repo default branch.

Writes to state:
- `matched_paths_json` — JSON array of matching repo-relative paths, best-match
  first, capped at the result limit.
- `search_status_json` — `{query, ref, total_blobs, matched, returned,
  truncated, error}`.

Ranking: basename exact/prefix (3) > basename substring or glob (2) > full-path
substring only (1). Ties broken by path for determinism.

## Build decisions (mirror `read_repo_files`)

1. **Read scope.** Resolves a token from `WORKFLOW_GITHUB_READ_CAPABILITIES` —
   search IS a read; it shares the **read** scope, NOT the write map. Empty ⇒
   unauthenticated (works for public repos, rate-limited).
2. **Server-enforced caps.** Result count (`WORKFLOW_GITHUB_SEARCH_MAX_RESULTS`,
   default 50), query length (2000 chars), term count (40) — enforced in the
   callable, never node config. GitHub's own tree `truncated` flag is surfaced.
3. **Distinct error kinds**, never raises: `search_destination_invalid`,
   `no_search_query`, `search_tree_denied` (401/403/404), `search_ref_unresolved`,
   `search_request_failed`.
4. **Platform-trusted opaque callable** — referenced by `(domain_id, node_id)`,
   body not user-supplied; registered at `workflow.effectors` import like
   `read_repo_files`.

## Coverage honesty

Path-search localizes file/module/dotted-named components and disambiguates the
`observed` file:line refs. Pure-concept components (`substrate`, `architecture`)
still have no nameable target and will continue to fail-safe REJECT — that is
correct behavior, not a regression; no single primitive can scope "make the
architecture better." Expected effect: most of the ~38 concept-named backlog
items that actually reference a real module become localizable.

## Out of scope

- Content grep (`/search/code`) — separate future primitive, token-gated.
- Writing/mutating the repo — that is the `github_pull_request` effector.
- Changing the cutover flip mechanics (env var repoint) — separate gated step.
