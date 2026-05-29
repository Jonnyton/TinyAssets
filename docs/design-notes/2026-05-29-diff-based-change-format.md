# Diff-based change format: `edits_json` (search/replace blocks)

Date: 2026-05-29
Status: proposed (extends the github_pull_request effector materialize path,
PR #1145 / design note 2026-05-29-github-pr-effector-materialize-branch.md)
Writer: Claude. Checker gate: opposite-provider review + host merge key.

## Problem

The patch-request loop's `propose` step emits `changes_json = {path: FULL new
file contents}`, and the effector commits those full contents. For small/medium
files this works (proven: PR #1192 calc.py, PR #1196 idempotency.py). For **large
files** (~100 KB, e.g. `workflow/api/wiki.py`) the writer model degrades to
placeholders like `# ... existing content unchanged ...` when asked to reproduce
the whole file. The review gate correctly REJECTs (it would corrupt the file),
so no bad PR is opened — but the edit cannot flow through. This is the documented
blocker to cutting the bug-investigation handler over to the user-buildable loop
(the cheat branch fails 100%; the new loop must cover large files too).

## Decision

Add a second, optional way to express a change in the `external_write_packet`
payload: **`edits_json`** — `{path: [{"search": <str>, "replace": <str>}, ...]}`.
The effector resolves it to full file contents **server-side** and feeds the
existing blob → tree → commit → ref materialize path. The writer emits only the
changed hunks, anchored on exact text it already has from `read_repo_files`, so
it never has to reproduce (and never truncates) a large file.

`changes_json` (full-file create/replace/delete) stays exactly as-is. A packet
may carry `changes_json`, `edits_json`, or both (disjoint paths). At least one
non-empty is required (no silent empty-branch PR).

### Why search/replace blocks, not a unified diff

Search/replace (the Aider / Claude-Code-Edit model) is the most LLM-robust edit
format: no line numbers (which drift and break), the anchor is verbatim existing
text, and correctness is locally checkable. Unified diffs fail to apply when the
model's context lines or offsets are slightly off. Since `read_repo_files`
already hands the writer the exact current contents, anchoring on a verbatim
slice is natural and reliable.

## Application semantics (fail-closed)

For each `edits_json` path, the effector:
1. Fetches the file at `base_branch` via the Contents API
   (`GET /repos/{repo}/contents/{path}?ref={base}`), base64-decoded.
   404 → `edit_target_missing` (cannot edit a file that doesn't exist — use
   `changes_json` to create it). >1 MB / no inline content → fetch error.
2. Applies blocks **in order**; each later block sees earlier results.
3. Each `search` must occur **exactly once**:
   - 0 matches → `edit_search_not_found`
   - >1 matches → `edit_search_not_unique` (writer must add surrounding context)
   This is the same exact-unique-match contract as the Claude Code Edit tool and
   guarantees an edit can never silently land in the wrong place or corrupt the
   file. Any failure aborts **before** any blob/commit/ref is created.

Caps: ≤100 blocks/file (`_MAX_EDIT_BLOCKS_PER_FILE`); non-string search/replace
or empty search → `invalid_edits`. A path present in both `changes_json` and
`edits_json` → `invalid_edits` (ambiguous).

## Contract additions

`payload.edits_json` (optional): `{ "<repo-relative path>": [ {"search": "...",
"replace": "..."}, ... ] }`. Resolved against `base_branch`. Distinct error
kinds: `edit_target_missing`, `edit_fetch_failed`, `edit_search_not_found`,
`edit_search_not_unique`, `invalid_edits` (plus the existing materialize kinds).
Auth reuses the same write capability token (it has read access). Never raises.

## Loop side (separate, post-merge)

This PR is the **effector capability** only. The loop's `propose` node must then
be updated (a connector-side branch rebuild — patch_request_loop v5) to emit
`edits_json` for existing-file edits (anchored on the `read_repo_files` contents)
and reserve `changes_json` for new-file creates. That rebuild + a re-validation
against a large-file backlog item (e.g. BUG-109 → `wiki.py`) is the proof that
unblocks the cutover flip.

## Out of scope
- Unified-diff / patch(1) application (rejected above).
- Fuzzy / whitespace-insensitive matching — exact match only, fail-closed.
- The cutover flip itself (separate gated deploy step).
