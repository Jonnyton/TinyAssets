---
date: 2026-05-28
severity: P0
status: pending-merge
related_issue: https://github.com/Jonnyton/Workflow/issues/1118
related_run: https://github.com/Jonnyton/Workflow/actions/runs/26605636623
---

# Wiki bug sync structuredContent incident

## Symptoms

Community loop watch issue #1118 stayed red after PR #1125 recovered the public MCP canary. The remaining red intake stage was `wiki-bug-sync.yml` run `26605636623`, which crashed in `scripts/wiki_bug_sync.py` while parsing `wiki action=list`.

## Evidence Snapshot

- `wiki-bug-sync.yml` run `26605636623` failed at 2026-05-28T22:20Z.
- Stack trace: `json.decoder.JSONDecodeError` at `wiki_list = json.loads(_parse_text_result(list_result))`.
- The failure class matches PR #1125: MCP tool text is now a short preview and the full payload is in `structuredContent`.
- Post-#1125 public MCP canary run `26606206467` was green, so the MCP surface itself was healthy.
- Local live dry-run after this branch's fix: `python scripts/wiki_bug_sync.py --url https://tinyassets.io/mcp --include-community-requests --dry-run` exited 0 and found BUG-109 plus PR-144 without parser failure.

## Immediate Fix Applied

`scripts/wiki_bug_sync.py` now prefers MCP `structuredContent` for wiki list/read results and keeps the old text JSON fallback. Regression tests cover preview-text plus structuredContent for both `wiki action=list` and `wiki action=read`.

## Verification

- Reproduction tests failed before the code fix:
  - `test_sync_no_new_bugs_accepts_structured_content_list_preview`
  - `test_fetch_wiki_page_detail_accepts_structured_content_preview`
- Focused tests after fix: `python -m pytest tests/test_wiki_bug_sync.py tests/test_canary_scripts_import_smoke.py -q` -> 88 passed.
- Compile check: `python -m compileall -q scripts/wiki_bug_sync.py scripts/_canary_common.py` -> passed.
- Live dry-run against `https://tinyassets.io/mcp` -> passed.
- Full recovery proof remains pending until the PR merges and `wiki-bug-sync.yml` plus `community-loop-watch.yml` run green on `main`.

## How Did The Loop Break This Time?

The live MCP server shifted large tool payloads into `structuredContent`, leaving human-readable preview text in `content[].text`. PR #1125 fixed the public uptime canaries, but `wiki_bug_sync.py` was an independent MCP client and still parsed only text. The intake sync therefore crashed before it could bridge new wiki BUG/PR filings into GitHub.

## How Can The Loop Notice This Break Next Time, Automatically?

Community loop watch already noticed the intake sync stage red, but the failure signature should be classified as an MCP structuredContent parser regression rather than a generic workflow failure. The stack trace plus preview-text marker is distinctive: `Full payload is in structuredContent` combined with `JSONDecodeError`.

## How Can The Loop Fix This Break Next Time, Automatically?

All repo-owned MCP client scripts should share one helper for tool-result payload extraction. When one client learns a new response shape, the loop should either run a scanner for remaining text-only parse sites or open a follow-up patch automatically for each affected script.

## How Can The Loop Avoid This Break In The First Place Next Time?

Move `_extract_structured_tool_payload` out of canary-specific naming into a general MCP client utility, then require every script that consumes MCP tool results to use that utility. Add a static test that flags direct `json.loads(_parse_text_result(...))` patterns in MCP clients unless paired with structuredContent handling.

## Substrate Improvement Filed

This branch is the immediate substrate fix. A follow-up should generalize the helper name and add a text-only-parser scanner once the loop is green again.
