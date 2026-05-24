# MCP Host Proof Registry

Date: 2026-05-02
Owner: lead + codex-gpt5-desktop
Canonical full MCP URL: `https://tinyassets.io/mcp`
Directory/review MCP URL: `https://tinyassets.io/mcp-directory`

This registry is the source for public claims about where Workflow works. If a
host is not listed as verified here, public copy should say "compatible by
spec" or "planned", not "works".

## Verification Rules

- Public endpoint proof starts with `python scripts/mcp_public_canary.py --url https://tinyassets.io/mcp`.
- Directory endpoint proof also requires `python scripts/mcp_public_canary.py --url https://tinyassets.io/mcp-directory`.
- Hosted chatbot proof must use the real chatbot UI with the Workflow connector
  enabled, then log the trace in `output/claude_chat_trace.md` or the matching
  host trace file.
- Developer/IDE proof must include a host-specific config plus a tool-list or
  safe tool-call smoke.
- Local/self-hosted proof must include the host version, transport, config, and
  visible user result.
- Claims expire when host docs change, the endpoint flakes, or a connector/app
  submission is rejected.

## Current Gate State

| Gate | Status | Evidence | Notes |
|---|---|---|---|
| Public MCP endpoint | live-green | 2026-05-02T15:46-07:00: `mcp_public_canary.py --url https://tinyassets.io/mcp --timeout 15 --verbose` OK; `mcp_tool_canary.py --url https://tinyassets.io/mcp --timeout 20 --verbose` OK | Legacy custom connector surface remains available |
| Directory-safe MCP endpoint | live-green; strict privacy hardening deployed | 2026-05-02T15:46-07:00: `mcp_public_canary.py --url https://tinyassets.io/mcp-directory --timeout 15 --verbose` OK; `mcp_tool_canary.py --url https://tinyassets.io/mcp-directory --timeout 20 --verbose` OK; strict live status redaction probe OK; descriptor listing showed 11 expected tools at 15:27 | Use for host-directory review and ChatGPT app submission proof |
| Official MCP Registry metadata | published-live | 2026-05-01: `mcp-publisher` v1.7.6 published `io.github.Jonnyton/workflow-universe-server` 0.1.0; registry API search returned status `active` | Points clients at `https://tinyassets.io/mcp-directory` |
| OpenAI Apps domain verification | verified | 2026-05-02T14:40-07:00: PR #204 merged; deploy-site run `25262547528` passed; `https://tinyassets.io/.well-known/openai-apps-challenge` returned the OpenAI token. 2026-05-02T14:50-07:00: host approved `Verify Domain`; dashboard changed to `Domain verified`. Screenshot: `output/openai-submission-assets/openai-dashboard-domain-verified-2026-05-02.png` | Keep challenge file published while draft is under review |
| AI-readable web docs | live | `WebSite/site/static/llms.txt` live from PR #134; update in progress for registry publication | Needs periodic source freshness check |
| `/connect` customer chooser | live | PR #134 deployed; Playwright desktop/mobile smoke on 2026-05-01 | Copy separates registry live from Claude/ChatGPT directory acceptance |

## 2026-05-02 OpenAI Submission Hardening

- PR #183 (`69b93ae`) landed and deploy prod run `25260452881` passed,
  deploying image tag `69b93ae89027`.
- Branch `codex/openai-submission-hardening` added directory-only status
  redaction for raw logs, local paths, host account identifiers, session
  boundary account data, and internal hashes.
- `tests/test_directory_server.py` now verifies that
  `chatgpt-app-submission.json` matches the source directory tool set and
  annotations.
- Live production redaction proof passed at 2026-05-02T12:56-07:00:
  `get_workflow_status` returned `directory_privacy_note`, with raw
  `activity_log_tail`, raw `last_n_calls`, `policy_hash`, `session_boundary`,
  `host_id`, and storage subsystem `path` fields absent.
- PR #184 (`30363c7`) removed remaining review-noisy
  `activity_log_tail_count`, `last_n_calls_count`, and
  `evidence_caveats.last_n_calls` labels. Deploy prod run `25260784025`
  passed and deployed image tag `30363c709a28`.
- Strict live redaction proof passed at 2026-05-02T13:13-07:00:
  `evidence` only contains `activity_log_line_count` and
  `last_completed_request_llm_used`; `evidence_caveats` only contains
  `last_completed_request_llm_used`; and `activity_log_tail`, `last_n_calls`,
  `activity_log_tail_count`, `last_n_calls_count`, `policy_hash`,
  `session_boundary`, `host_id`, and storage subsystem `path` fields are
  absent.
- ChatGPT Developer Mode proof history is preserved in
  `docs/ops/openai-app-submission-chatgpt-proof-2026-05-02.md`.
- 2026-05-02T13:37-07:00 consolidation check passed from
  `codex/onboarding-readiness-consolidation`: JSON packet validation,
  `tests/test_directory_server.py`, public canaries, tool canaries, strict live
  redaction probe, cross-provider drift check, and `git diff --check`.

## 2026-05-01 Local Verification

- `python packaging/registry/generate_server_json.py --check --validate` passed.
- `python -m pytest tests/test_directory_server.py tests/test_universe_server_directory_app.py tests/smoke/test_mcp_tools_list_non_empty.py tests/test_universe_server_metadata.py` passed.
- `node --test worker.test.js` passed in `deploy/cloudflare-worker`.
- `python packaging/claude-plugin/build_plugin.py` passed with import probe, including the new directory server module in the plugin runtime mirror.
- Local Streamable HTTP runtime smoke passed: `scripts/mcp_public_canary.py`
  initialized both `http://127.0.0.1:8017/mcp` and
  `http://127.0.0.1:8017/mcp-directory`; `scripts/mcp_probe.py` listed the
  11 directory tools from `/mcp-directory`.
- `mcp-publisher` v1.7.6 was installed to a temp tools dir, validated
  `packaging/registry/server.json`, authenticated via the local GitHub session,
  and published `io.github.Jonnyton/workflow-universe-server` version `0.1.0`.
- Registry API verification passed:
  `https://registry.modelcontextprotocol.io/v0.1/servers?search=io.github.Jonnyton/workflow-universe-server`
  returned one active latest server pointing at `https://tinyassets.io/mcp-directory`.
- Public MCP diagnostics after one local HTTP 502: 5 consecutive
  `python scripts/mcp_public_canary.py --url https://tinyassets.io/mcp --timeout 15 --verbose`
  probes passed; GitHub Actions uptime run `25231089323` passed; direct
  `https://mcp.tinyassets.io/mcp` stayed Access-gated at HTTP 403 as expected.
- Production rollout proof after PR #123/#124/#125:
  - Deploy prod run `25233226847` passed for merge `d6a44eb`.
  - Manual Worker deploy run `25233386849` passed for main `e8e0fd0`.
  - `python scripts/mcp_public_canary.py --url https://tinyassets.io/mcp --timeout 15 --verbose` returned OK.
  - `python scripts/mcp_public_canary.py --url https://tinyassets.io/mcp-directory --timeout 15 --verbose` returned OK.
  - `python scripts/mcp_probe.py --url https://tinyassets.io/mcp-directory tools` returned exactly the 11 directory tools.
  - `python scripts/mcp_probe.py --url https://tinyassets.io/mcp tools` still returned the 7 legacy custom-connector tools.
- `npm run check` in `WebSite/site` passed with 0 errors and 0 warnings.
- `npm run build` in `WebSite/site` passed and emitted `build/connect.html`
  plus `build/llms.txt`.
- Playwright production-preview smoke passed on desktop 1440x1100 and mobile
  390x900: 0 console/page errors, no horizontal overflow, 6 customer path
  cards, 3 gate rows, canonical URL value present, mobile host table stacks to
  one column, `/llms.txt` includes Workflow and ChatGPT guest caveats.
- Screenshots: `output/connect-desktop-2026-05-01.png`,
  `output/connect-mobile-2026-05-01.png`.

## Host Matrix

| Host surface | Customer path | Status | Proof / blocker |
|---|---|---|---|
| Official MCP Registry | Registry-aware MCP hosts | published-live | 2026-05-01 proof: `mcp-publisher publish packaging/registry/server.json`; API search returned `io.github.Jonnyton/workflow-universe-server` active/latest |
| Claude.ai custom connector | verified: read-only UI | 2026-05-02T14:44-07:00 in-app browser Claude.ai chat `3959f3de-0244-4488-aa24-87a396e465c2`: naive connector prompt loaded Workflow tools and returned daemon status; screenshot `output/openai-submission-assets/claude-ai-workflow-connector-status-2026-05-02.png` | Read-only proof only; directory form submit still separate |
| Claude Connectors Directory | Logged-in Claude users/admins | form-reached; submit blocked on contact/final-submit approval | 2026-05-02: in-app browser reached Google Form page 2 from official Claude submission docs; stopped before entering required contact/org fields because submission records Google identity and transmits contact data. Closeout packet: `docs/ops/claude-directory-submission-closeout-2026-05-02.md` |
| ChatGPT custom MCP / developer mode | Logged-in eligible ChatGPT user/workspace | stale app registration | 2026-05-02T15:37-07:00 settings audit: enabled `Workflow DEV` points to legacy `https://tinyassets.io/mcp`; fresh ChatGPT web prompt called legacy `get_status` and returned raw diagnostics. Re-register to `/mcp-directory` before final web/mobile proof |
| ChatGPT App Directory | app draft; submit blocked | `chatgpt-app-submission.json` covers the 11 directory tools with 10 positive and 4 negative tests; 2026-05-02 dashboard draft uses `/mcp-directory`, `No Auth`, 11 complete justification rows, `Domain verified`, 5+3 dashboard tests, optional screenshots for non-UI app; direct `/mcp-directory` proof is green; final submit remains blocked on ChatGPT DEV re-register + web/mobile proof, legal/publisher assertions, optional uploads, and action-time host approval |
| ChatGPT guest | No logged-in chatbot account | unsupported by ChatGPT path | Route to local/self-hosted/no-chatbot-login options |
| Mistral Le Chat MCP connector | Logged-in Mistral user/admin | planned | Need connector config proof and directory/submission research |
| Open WebUI | No hosted chatbot login if self-hosted | verified: local Docker 0.9.2 | 2026-05-01 proof: `docs/ops/open-webui-runtime-proof-2026-05-01.md`; Streamable HTTP MCP to `https://tinyassets.io/mcp-directory`, auth `None`, chat invoked `workflow_get_workflow_status` |
| LibreChat | No hosted chatbot login if self-hosted | verified: local Docker v0.8.5 | 2026-05-01 proof: `docs/ops/librechat-runtime-proof-2026-05-01.md`; Streamable HTTP MCP to `https://tinyassets.io/mcp-directory`, auth `None`, chat invoked `get_workflow_status_mcp_workflow` |
| LM Studio / Jan | Local model user | planned | Verify native MCP support or document bridge/fallback truthfully |
| OpenClaw / channel gateway | Channel user | planned | Need direct support proof before claiming |
| VS Code / GitHub Copilot | Developer/IDE user | planned | Verify `.vscode/mcp.json` or user MCP config with Copilot Chat |
| Codex CLI/IDE | Developer/IDE user | verified: Codex CLI 0.104.0 | 2026-05-02 proofs: `docs/ops/mcp-codex-registration-proof-2026-05-02.md` and `docs/ops/mcp-codex-runtime-proof-2026-05-02.md`; Codex CLI listed directory tools from `https://tinyassets.io/mcp-directory` and called `get_workflow_status`, returning `"schema_version": 1`; CLI 0.104.0 needed `-m gpt-5.2` because the configured default `gpt-5.5` requires a newer CLI |
| Cursor | Developer/IDE user | registration-path verified; tool-call pending | 2026-05-01 proof: `docs/ops/mcp-cursor-registration-proof-2026-05-01.md`; Cursor 3.2.16 CLI wrote isolated Streamable HTTP config for `https://tinyassets.io/mcp-directory`; needs UI/agent tool-list plus read call before public verified copy |
| Gemini CLI | Developer/CLI user | planned | Verify `settings.json`/command path and a safe tool call |
| Microsoft Copilot Studio | Enterprise maker/admin | planned | Build custom MCP connector/Power Platform package or OpenAPI fallback |
| Custom MCP host | Builder | compatible-by-spec | Provide minimal integration contract and smoke command |

## First Prompts To Verify

Use host-specific wording, but each host should prove at least one of these:

- "Use Workflow to list available goals."
- "Use Workflow to browse the live wiki and summarize the current launch risks."
- "Use Workflow to inspect universes and tell me what durable state exists."
- "Use Workflow to create or propose a node for a simple workflow." Only use
  this once write permissions and approval UX are verified in that host.

## Open Follow-Ups

Detailed execution queue: `docs/ops/mcp-directory-rollout-action-queue.md`.

- Monitor the official MCP Registry listing and add registry-aware client proof
  as clients consume `io.github.Jonnyton/workflow-universe-server`.
- Submit the Claude directory packet through Anthropic's review flow after the
  live Claude.ai proof and host approval gates in
  `docs/ops/claude-directory-submission-closeout-2026-05-02.md`.
- Submit `chatgpt-app-submission.json` through OpenAI's app submission flow
  only after the final-submit runbook gates in
  `docs/ops/openai-app-submission-final-submit-runbook-2026-05-02.md`.
- Verify the next no-chatbot-login host after Open WebUI + LibreChat: LM
  Studio/Jan, OpenClaw/channel gateway, or custom hosts. Proof traces:
  `docs/ops/open-webui-runtime-proof-2026-05-01.md` and
  `docs/ops/librechat-runtime-proof-2026-05-01.md`.
- Add host-specific proof traces as they land.
