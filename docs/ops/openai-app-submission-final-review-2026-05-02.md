# OpenAI App Submission Final Review Packet - 2026-05-02

Purpose: one current review packet for deciding when Workflow is ready to
submit to OpenAI Apps review.

## Current Verdict

Not ready to click `Submit for Review`.

Repo-side and production MCP evidence is green. The remaining blockers are
external action-time gates:

1. Re-register or create the ChatGPT Developer Mode test app at
   `https://tinyassets.io/mcp-directory`, then rerun web golden prompts.
2. Run the same golden prompts on ChatGPT iOS or Android.
3. Decide whether to leave optional screenshots blank for this non-UI app or
   upload approved screenshots.
4. Host confirms publisher, mature-content, and legal/compliance assertions.
5. Claude directory form contact/org/final submit remains separate.
6. Host gives final action-time approval to click OpenAI `Submit for Review`.

## Official Docs Rechecked

Checked 2026-05-02 against current official OpenAI docs:

- `https://developers.openai.com/apps-sdk/deploy/submission`
- `https://developers.openai.com/apps-sdk/deploy/testing`
- `https://developers.openai.com/apps-sdk/app-submission-guidelines`

Implications applied:

- Public app submission requires dashboard review flow, verified publisher
  identity, public HTTPS MCP server, non-local endpoint, and completed
  dashboard fields.
- Testing should cover direct, indirect, and negative prompts, including
  ChatGPT iOS or Android.
- Tool names, descriptions, inputs, and annotations must match behavior; write
  and open-world behavior must be explicit.

## Green Evidence

2026-05-02T15:27-07:00 from `codex/openai-final-readiness`:

- `git diff --check` passed.
- `python -m json.tool chatgpt-app-submission.json > $null` passed.
- `python -m pytest tests/test_directory_server.py -q` passed: 8 tests.
- Public canaries passed for `https://tinyassets.io/mcp` and
  `https://tinyassets.io/mcp-directory`.
- Tool canaries passed for both endpoints.
- `/mcp-directory` live descriptor listing showed 11 expected tools with
  explicit titles, schemas, descriptions, and annotations.
- Strict `/mcp-directory` redaction assertion passed with no raw logs,
  recent-call arrays, count labels, policy hash, session boundary, host id, or
  storage `path` keys.
- Direct read probes verified status, goal search/get, wiki search, and run
  listing. Public goal `20e2339c82e3` remains visible with tags
  `submission, smoke`.

Post-rebase freshness check 2026-05-02T15:46-07:00:

- `python scripts/mcp_public_canary.py --url https://tinyassets.io/mcp --timeout 15 --verbose`
  passed.
- `python scripts/mcp_public_canary.py --url https://tinyassets.io/mcp-directory --timeout 15 --verbose`
  passed.
- `python scripts/mcp_tool_canary.py --url https://tinyassets.io/mcp --timeout 20 --verbose`
  passed.
- `python scripts/mcp_tool_canary.py --url https://tinyassets.io/mcp-directory --timeout 20 --verbose`
  passed.
- Strict `/mcp-directory` redaction assertion still passed.

## Dashboard State

2026-05-02T15:35-07:00 in-app browser audit:

- App Info populated: `Workflow`, `Build durable workflows`, `Productivity`,
  developer `TinyAssets`, website/support/privacy/terms URLs.
- Logo upload control still visible; no logo uploaded.
- MCP Server populated: `https://tinyassets.io/mcp-directory`, `No Auth`, 11
  tool rows, complete justifications, `Domain verified`.
- Testing populated: 5 positive and 3 negative cases. Source packet remains
  fuller at 10 positive and 4 negative cases.
- Screenshots page says screenshots are optional for non-UI apps.
- Global page shows English (US) and `Allow all` countries.
- Submit page incomplete: release notes empty, publisher unset, seven legal
  boxes unchecked, mature/adult-content answer unset, submit untouched.

## User-Testing Blocker

2026-05-02T15:37-07:00 ChatGPT Settings audit:

- Enabled `Workflow DEV` is connected to `https://tinyassets.io/mcp`.
- It exposes legacy actions including `get_status`.
- A fresh ChatGPT web prompt invoked legacy `get_status` and returned raw
  diagnostics.

This is a registration mismatch, not a production `/mcp-directory` regression.
Do not use current ChatGPT web output as final directory-safe proof.

## Final Approval Bundle

Recommended release notes:

`Initial public alpha of Workflow. This app connects ChatGPT to the directory-safe Workflow MCP surface for daemon status, shared goals, project wiki lookup, run browsing, and bounded request submission.`

Recommended final choices, pending host review:

- Publisher selector: `Business` only if TinyAssets publisher verification is
  confirmed.
- Mature/adult content: `No` only if host confirms Workflow is suitable for
  users under 18 and has no mature/adult content.
- Screenshots: leave blank unless host wants optional evidence uploaded.
- Legal checkboxes: check only after host confirms each assertion.
- Submit: click only after separate final action-time approval.
