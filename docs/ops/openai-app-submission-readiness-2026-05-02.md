# OpenAI App Submission Readiness - 2026-05-02

Purpose: one checklist for deciding whether Workflow is ready to click
`Submit for Review` in the OpenAI Apps dashboard.

## Acceptance Inputs From Official Docs

Official OpenAI docs checked 2026-05-02 say the submission must satisfy these
practical gates:

- Public app submissions are for public distribution; private/workspace use
  should stay in developer mode.
- Publisher identity must be verified as the individual or business name used
  for publication.
- The MCP server must be on a publicly accessible HTTPS domain, not a local or
  testing endpoint.
- Submission form fields include app name, logo, description, company and
  privacy policy URLs, MCP/tool information, screenshots, test prompts and
  responses, and localization information.
- Common rejection causes include unreachable MCP URLs, failing test cases,
  outputs that contain irrelevant personal/internal identifiers, missing
  privacy disclosures, and inaccurate tool annotations.
- Test cases should pass in ChatGPT web and mobile, with direct,
  outcome-oriented, and negative prompts represented.
- Metadata should be precise enough to call Workflow only for relevant prompts
  and avoid negative prompts.
- Tool inputs and outputs should minimize data collection and avoid restricted
  or credential-like fields.

Sources:

- `https://developers.openai.com/apps-sdk/deploy/submission`
- `https://developers.openai.com/apps-sdk/app-submission-guidelines`
- `https://developers.openai.com/apps-sdk/guides/security-privacy`
- `https://developers.openai.com/apps-sdk/plan/tools`
- `https://developers.openai.com/apps-sdk/guides/optimize-metadata`
- `https://developers.openai.com/apps-sdk/deploy/testing`
- `https://developers.openai.com/apps-sdk/deploy`

## Current Readiness Verdict

Verdict: not ready for final submit yet.

Source packet is review-aligned and deployed, direct `/mcp-directory` proof is
clean, and the repo-side legal/asset closeout has landed. A fresh
2026-05-02T15:37-07:00 browser audit reopened the ChatGPT user-testing
boundary: the enabled ChatGPT `Workflow DEV` app is still registered to
`https://tinyassets.io/mcp`, while the OpenAI dashboard draft is correctly
configured to `https://tinyassets.io/mcp-directory`. Final submission should
wait for the OpenAI-specific blockers below:

1. ChatGPT Developer Mode must be re-registered/refreshed to
   `https://tinyassets.io/mcp-directory`, then the web golden prompt set must
   pass in a fresh chat.
2. ChatGPT mobile must complete the main read/write flows against the same
   directory-safe app registration.
3. Logo/screenshots or demo asset choices, release notes, mature-content
   answer, publisher selector, verification assertion, and compliance/legal
   checkboxes need host review and action-time approval before dashboard edits.
4. Host must approve final `Submit for Review` at action time.

Parallel onboarding gaps that are not OpenAI-submit blockers:

- Claude Connectors Directory form submit still needs contact/org field and
  final-submit approval.

Post-submit monitoring:

- First-user clean-use evidence beyond controlled tests cannot be proven before
  public distribution without a real external user. Keep it as a watch item
  after OpenAI/Claude submission rather than a blocker for clicking OpenAI
  review.

Closed 2026-05-02T12:56-07:00:

- PR #183 merged to `main` at `69b93ae`.
- Deploy prod run `25260452881` passed and deployed image tag
  `69b93ae89027`.
- Public canaries passed for both `https://tinyassets.io/mcp` and
  `https://tinyassets.io/mcp-directory`.
- `python scripts/mcp_tool_canary.py --url https://tinyassets.io/mcp-directory --timeout 20 --verbose`
  passed from the updated worktree and invoked `get_workflow_status`.
- Live `/mcp-directory` `get_workflow_status` no longer returns raw
  `activity_log_tail`, raw `last_n_calls`, `policy_hash`,
  `session_boundary`, `host_id`, or storage subsystem `path` fields. It
  returns `directory_privacy_note`.
- PR #184 later removed remaining review-noisy `activity_log_tail_count`,
  `last_n_calls_count`, and `evidence_caveats.last_n_calls` labels before
  final OpenAI submit proof.

Closed 2026-05-02T13:13-07:00:

- PR #184 merged to `main` at `30363c7`.
- Deploy prod run `25260784025` passed and deployed image tag
  `30363c709a28`.
- Public canaries passed for both `https://tinyassets.io/mcp` and
  `https://tinyassets.io/mcp-directory`.
- `python scripts/mcp_tool_canary.py --url https://tinyassets.io/mcp-directory --timeout 20 --verbose`
  passed and invoked `get_workflow_status`.
- Strict live redaction probe passed: `evidence` only contains
  `activity_log_line_count` and `last_completed_request_llm_used`;
  `evidence_caveats` only contains `last_completed_request_llm_used`; and
  `activity_log_tail`, `last_n_calls`, `activity_log_tail_count`,
  `last_n_calls_count`, `policy_hash`, `session_boundary`, `host_id`, and
  storage subsystem `path` fields are absent.

Closed 2026-05-02T13:23-07:00:

- ChatGPT web Developer Mode read prompt completed using Workflow status with
  no `Unknown action`, hang, or 5xx.
- ChatGPT web rendered the `Propose a public workflow goal?` approval card for
  `propose_workflow_goal`.
- Host approved the public write at action time.
- ChatGPT completed and returned goal id `20e2339c82e3` with
  `Called tool was propose_workflow_goal: yes`.
- Direct `/mcp-directory` verification via `search_workflow_goals` and
  `get_workflow_goal` confirmed goal `20e2339c82e3` exists, is public, and has
  tags `submission, smoke`.

Historical ChatGPT Developer Mode proof and BUG-034 boundaries are preserved in
`docs/ops/openai-app-submission-chatgpt-proof-2026-05-02.md`.
Current final-review packet is
`docs/ops/openai-app-submission-final-review-2026-05-02.md`.

Closed repo-side in `codex/onboarding-close-gaps` on
2026-05-02T14:08-07:00 to 2026-05-02T14:12-07:00:

- `WebSite/site/src/routes/legal/+page.svelte` now discloses ChatGPT, Claude,
  and other MCP connector data categories and retention boundaries.
- `WebSite/site/src/routes/connect/+page.svelte` keeps the full
  `https://tinyassets.io/mcp-directory` URL visible in the mobile copy field.
- Local asset pack refreshed under `output/openai-submission-assets/`, with
  ambiguous historical failed goal screenshots removed.
- ChatGPT web goal-success screenshot captured for goal `20e2339c82e3`.
- `tests/test_directory_server.py` now asserts directory tool titles in
  addition to explicit annotation hints.
- `python -m json.tool chatgpt-app-submission.json` passed.
- `python -m pytest tests/test_directory_server.py -q` passed: 7 tests.
- Public and tool canaries passed for `https://tinyassets.io/mcp` and
  `https://tinyassets.io/mcp-directory`.
- Strict live `/mcp-directory` redaction probe passed with no raw logs, recent
  call arrays, count labels, policy hash, session boundary, host id, or storage
  `path` keys.
- `npm run check` and `npm run build` passed in `WebSite/site`.

Discovered 2026-05-02T14:35-07:00 during in-app browser dashboard review:

- OpenAI Apps draft still showed `Domain not verified` for `tinyassets.io`.
- Required challenge URL:
  `https://tinyassets.io/.well-known/openai-apps-challenge`.
- Branch `codex/openai-domain-verification` publishes the challenge file.
- Dashboard `Verify Domain` remains blocked on action-time host approval after
  the challenge URL is live.

Closed 2026-05-02T14:40-07:00:

- PR #204 merged to `main` at `361357b`.
- Deploy-site run `25262547528` passed.
- `https://tinyassets.io/.well-known/openai-apps-challenge` returned the
  OpenAI token.
- Dashboard `Verify Domain` still requires action-time host approval.
- In-app browser inspection confirmed the Submit section still needs release
  notes, publisher selector, compliance checkboxes, mature-content answer, and
  final `Submit for Review`.

Closed 2026-05-02T14:50-07:00:

- Host approved clicking OpenAI dashboard `Verify Domain`.
- OpenAI dashboard changed to `Domain verified` for `tinyassets.io`.
- Screenshot:
  `output/openai-submission-assets/openai-dashboard-domain-verified-2026-05-02.png`.

Parallel Claude gap narrowed 2026-05-02T14:44-07:00:

- Claude.ai in-app browser read-only proof succeeded in chat
  `3959f3de-0244-4488-aa24-87a396e465c2`.
- Prompt used naive connector language and Claude returned Workflow daemon
  status after loading tools.
- This closes the fresh rendered Claude read proof; Claude directory form
  contact/org fields and final submit remain action-time host gates.

Fresh final-readiness validation 2026-05-02T15:27-07:00 from
`codex/openai-final-readiness`:

- `git diff --check` passed.
- `python -m json.tool chatgpt-app-submission.json > $null` passed.
- `python -m pytest tests/test_directory_server.py -q` passed: 8 tests.
- The new eighth test covers `submit_workflow_request` against a temporary
  Workflow data directory, proving the reviewed request-write path queues
  state without touching production.
- Public canaries passed for both `https://tinyassets.io/mcp` and
  `https://tinyassets.io/mcp-directory`.
- Tool canaries passed for both endpoints; `/mcp-directory` listed the 11
  directory tools and invoked `get_workflow_status`.
- Live `/mcp-directory` tool descriptors expose all 11 expected tools, clear
  `Use this when...` descriptions, explicit schemas, and explicit
  read/open-world/destructive annotations.
- Strict live redaction probe passed: `evidence` only contained
  `last_completed_request_llm_used` and `activity_log_line_count`;
  `evidence_caveats` only contained `last_completed_request_llm_used`; and
  raw logs, recent-call arrays, count labels, policy hash, session boundary,
  host id, and storage `path` keys were absent.
- Direct `/mcp-directory` read probes passed for status, goals, wiki search,
  and run listing; direct search/get verified public goal `20e2339c82e3` still
  exists with tags `submission, smoke`.
- Post-rebase 2026-05-02T15:46-07:00 public canaries, tool canaries, and the
  strict `/mcp-directory` redaction assertion still passed.

ChatGPT web caveat discovered 2026-05-02T15:37-07:00:

- ChatGPT Settings -> Apps -> `Workflow DEV` currently shows URL
  `https://tinyassets.io/mcp` and legacy actions including `get_status`.
- A fresh ChatGPT web prompt in a new chat invoked legacy `get_status` and
  returned raw `activity_log_tail`, `last_n_calls`, `policy_hash`,
  `session_boundary`, and storage `path` values.
- This does not contradict the direct `/mcp-directory` proof. It means the
  current ChatGPT user-testing app registration is stale and must be
  re-registered to `/mcp-directory` before final web/mobile proof.
- Creating a new custom MCP app in ChatGPT displays an elevated-risk warning;
  accepting that warning and creating the persistent app should remain an
  action-time host approval step.

OpenAI dashboard audit 2026-05-02T15:05-07:00:

- App Info still exposes the logo upload control, so the logo is not yet
  proven uploaded in the dashboard.
- MCP Server section shows `https://tinyassets.io/mcp-directory`, `No Auth`,
  and 11 complete tool-justification rows.
- Testing section shows 5 positive and 3 negative dashboard test cases. The
  repo packet remains fuller at 10 positive and 4 negative cases; no dashboard
  add-control was visible during audit.
- Submit section remains incomplete: release notes empty; publisher unset; 7
  legal/compliance boxes unchecked; mature/adult-content answer unset; final
  `Submit for Review` not clicked.

OpenAI dashboard re-audit 2026-05-02T15:35-07:00:

- App Info values are populated: `Workflow`, `Build durable workflows`,
  `Productivity`, developer `TinyAssets`, website/support/privacy/terms URLs,
  and no commerce/purchase checkbox selected.
- Logo upload control is still visible; logo not uploaded.
- MCP Server values are populated with `https://tinyassets.io/mcp-directory`,
  `No Auth`, 11 tool rows, complete justifications, and `Domain verified`.
- Testing contains 5 positive and 3 negative dashboard cases. The source JSON
  still carries 10 positive and 4 negative cases for audit depth.
- Screenshots page says screenshots are optional for non-UI apps. If the host
  chooses to upload optional screenshots, that is an outbound file upload and
  should be handled at final review.
- Global localization/country page shows English (US) text and `Allow all`
  countries.
- Submit page remains incomplete: release notes empty, publisher selector
  unset, legal/compliance boxes unchecked, mature/adult-content answer unset,
  and `Submit for Review` untouched.

Next dashboard action should be one explicit approval bundle, not piecemeal
guessing:

- Fill release notes with: `Initial public alpha of Workflow. This app connects ChatGPT to the directory-safe Workflow MCP surface for daemon status, shared goals, project wiki lookup, run browsing, and bounded request submission.`
- Re-register ChatGPT Developer Mode to `https://tinyassets.io/mcp-directory`
  and rerun web/mobile golden prompts before treating ChatGPT user proof as
  clean.
- Select publisher type `Business` only if host confirms TinyAssets may publish
  on behalf of that business.
- Select mature/adult content `No` only after host confirms Workflow is
  suitable for under-18 users and contains no mature/adult content.
- Check the seven legal/compliance boxes only after host confirms each
  assertion.
- Upload `assets/brand/workflow-logo-icon.png` only after host approves the
  file upload.
- Do not click `Submit for Review` until host gives separate final-submit
  approval at action time.

Fresh command/live validation 2026-05-02T15:07-07:00 from
`codex/openai-submission-closeout`:

- `git diff --check` passed.
- `python -m json.tool chatgpt-app-submission.json > $null` passed.
- `python -m pytest tests/test_directory_server.py -q` passed: 7 tests.
- Public canaries passed for both `https://tinyassets.io/mcp` and
  `https://tinyassets.io/mcp-directory`.
- Tool canaries passed for both endpoints; `/mcp-directory` listed the 11
  directory tools and invoked `get_workflow_status`.

## Tool Hint Audit

Source audited: `workflow/directory_server.py`.

Result: 11 source tools match `chatgpt-app-submission.json` exactly for
`readOnlyHint`, `openWorldHint`, and `destructiveHint`.
All 11 source tools also have tool titles and annotation titles, matching
Claude's current directory-review checklist.

ChatGPT Apps submission packet audit on 2026-05-02:

- 11 source tools, 11 JSON tools, no missing or extra packet tools.
- 10 positive test cases after adding two outcome-oriented discovery/write
  prompts.
- 4 negative test cases.
- No widget/resource templates are exposed from this directory surface, so no
  widget CSP domains are required for this submission packet.

Fresh validation on 2026-05-02T13:37-07:00 from
`codex/onboarding-readiness-consolidation`:

- `python -m json.tool chatgpt-app-submission.json` passed.
- `python -m pytest tests/test_directory_server.py -q` passed: 7 tests.
- Public canaries passed for both `https://tinyassets.io/mcp` and
  `https://tinyassets.io/mcp-directory`.
- Tool canaries passed for both endpoints; `/mcp-directory` listed the 11
  directory tools and invoked `get_workflow_status`.
- Strict live redaction probe passed with `directory_privacy_note`; no raw
  logs, recent call arrays, count labels, policy hash, session boundary,
  host id, or storage `path` keys appeared.
- `python scripts/check_cross_provider_drift.py` and `git diff --check`
  passed.

Write tools:

- `propose_workflow_goal`: `readOnlyHint=false`,
  `openWorldHint=true`, `destructiveHint=false`. It creates a shared Workflow
  goal proposal and can be public.
- `submit_workflow_request`: `readOnlyHint=false`,
  `openWorldHint=false`, `destructiveHint=false`. It queues a bounded request
  inside Workflow and does not itself publish to third-party systems.

Read tools:

- `get_workflow_status`
- `list_workflow_universes`
- `inspect_workflow_universe`
- `list_workflow_goals`
- `search_workflow_goals`
- `get_workflow_goal`
- `search_workflow_wiki`
- `read_workflow_wiki_page`
- `list_workflow_runs`

All are annotated read-only, non-destructive, and non-open-world.

## Privacy/Data Review

OpenAI docs flag unnecessary logs, telemetry, internal identifiers, timestamps,
request IDs, and personal identifiers as rejection risks.

Branch hardening:

- Directory `get_workflow_status` redacts raw activity logs.
- Directory `get_workflow_status` redacts host account identifiers.
- Directory `get_workflow_status` redacts internal policy hashes.
- Directory `get_workflow_status` removes local/storage paths from subsystem
  storage details.
- Directory `get_workflow_status` removes session-boundary account data.

The 2026-05-02 closeout branch updates the legal page source to disclose the
OpenAI app path categories below. Final submit should wait until that source is
landed and live:

- User-submitted goal names, descriptions, tags, and visibility.
- User-submitted Workflow request text and optional target universe/branch.
- Workflow goal, branch, wiki, run, queue, and daemon status metadata returned
  to answer user prompts.
- Generated Workflow identifiers that are necessary for follow-up actions
  (`goal_id`, `run_id`, `request_id`, `branch_task_id`, `universe_id`).
- Operational status/routing/sandbox/storage-pressure metadata in redacted
  form.

The directory surface does not request passwords, API keys, MFA codes, payment
data, government IDs, biometrics, SSNs, PHI, or PCI data.

## Golden Prompt Set

Use these for ChatGPT web and mobile. For write prompts, confirm at action-time
before approving the write. The set intentionally includes direct Workflow
prompts plus outcome-oriented prompts that should still map to Workflow because
they ask for durable workflow goals.

Positive:

1. `Use Workflow to check the current daemon status and tell me any caveats before I start.`
2. `Use Workflow to search for goals related to onboarding and show the best matches.`
3. `I'm planning onboarding for new MCP hosts. Search durable workflow goals about onboarding and summarize the best matches.`
4. `Use Workflow to list shared goals, then inspect the first relevant goal you find.`
5. `Use Workflow to list available universes, then inspect the active one.`
6. `Use Workflow to search the wiki for current launch risks, then read the most relevant page.`
7. `Use Workflow to list recent runs and tell me whether anything is currently active or blocked.`
8. `Use Workflow to propose a public goal named 'Onboard new MCP hosts' with tags discovery,onboarding.`
9. `Create a shared durable workflow goal named 'Reduce MCP onboarding friction' with tags onboarding,hosts.`
10. `Use Workflow to submit a request asking the daemon to summarize today's discoverability blockers.`

Negative:

1. `What is the weather in San Francisco tomorrow?`
2. `Use Workflow to send an email to my team about the launch.`
3. `Use Workflow to delete every universe and wipe all stored data.`
4. `Use Workflow to save my API key and password for later.`

Pass criteria:

- The expected tool is selected for positive prompts.
- No Workflow tool is selected for negative prompts.
- Write actions show approval UX and complete after explicit approval.
- Outputs are relevant and do not include raw logs, local filesystem paths,
  host account identifiers, or irrelevant internal IDs.

## Pre-Submit Command Gate

Run from the branch that will be submitted:

```powershell
python -m json.tool chatgpt-app-submission.json > $null
python -m pytest tests/test_directory_server.py -q
python scripts/mcp_public_canary.py --url https://tinyassets.io/mcp --timeout 15 --verbose
python scripts/mcp_public_canary.py --url https://tinyassets.io/mcp-directory --timeout 15 --verbose
python scripts/mcp_tool_canary.py --url https://tinyassets.io/mcp --timeout 20 --verbose
python scripts/mcp_tool_canary.py --url https://tinyassets.io/mcp-directory --timeout 20 --verbose
python scripts/mcp_probe.py --url https://tinyassets.io/mcp-directory --tool get_workflow_status --args "{}" --raw
cd WebSite/site
npm run check
npm run build
```

For the final probe, parse the tool result text as JSON and verify these
diagnostic keys are absent:

- `activity_log_tail`
- `last_n_calls`
- `activity_log_tail_count`
- `last_n_calls_count`
- `policy_hash`
- `session_boundary`
- `host_id`
- storage subsystem `path` fields

## Final Submit Checklist

- Branch landed and deployed.
- Legal/connect closeout source landed and live.
- Public canaries green after deploy.
- Live status redaction proof captured.
- ChatGPT web golden prompts captured.
- ChatGPT mobile golden prompts captured.
- ChatGPT Developer Mode app URL verified as `https://tinyassets.io/mcp-directory`,
  not legacy `https://tinyassets.io/mcp`.
- OpenAI dashboard shows `tinyassets.io` domain verified.
- Logo and any chosen screenshots/demo assets uploaded.
- Privacy policy categories reviewed.
- Release notes reviewed.
- Publisher selector and verification assertion approved.
- Compliance/legal boxes approved.
- Mature/adult-content answer approved.
- Host says "submit now" at action-time.
