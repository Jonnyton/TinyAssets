# OpenAI App Final Submit Runbook - 2026-05-02

Purpose: give the final dashboard operator one truthful packet for submitting
Workflow to OpenAI review, without mixing repo-side evidence with host-only
legal/publisher assertions.

## Action-Time Boundary

Do not click `Submit for Review`, check legal/compliance boxes, assert
publisher verification, or transmit final dashboard fields until the host says
to submit at action time.

The prepared app is for public ChatGPT Apps Directory review. It uses the
directory-safe MCP endpoint:

`https://tinyassets.io/mcp-directory`

Do not swap to the full custom connector endpoint `https://tinyassets.io/mcp`
without regenerating `chatgpt-app-submission.json` and re-running the tool
audit, because `/mcp` exposes the broader legacy surface.

2026-05-02T15:37-07:00: ChatGPT Settings -> Apps -> `Workflow DEV` still
points to `https://tinyassets.io/mcp`. That enabled developer app is stale for
submission testing and returned raw legacy diagnostics in a fresh ChatGPT web
prompt. Re-register or create the ChatGPT Developer Mode test app against
`https://tinyassets.io/mcp-directory` before final web/mobile proof.

## Official Docs Checked

Checked 2026-05-02:

- `https://developers.openai.com/apps-sdk/deploy/submission`
- `https://developers.openai.com/apps-sdk/deploy/testing`
- `https://developers.openai.com/apps-sdk/app-submission-guidelines`
- `https://developers.openai.com/apps-sdk/guides/security-privacy`
- `https://developers.openai.com/apps-sdk/guides/optimize-metadata`

Submission implications:

- App review uses the dashboard flow after Developer Mode testing.
- The app must use a public HTTPS MCP server, not a local/test endpoint.
- The form needs app name, logo, description, company and privacy URLs,
  MCP/tool info, screenshots, test prompts/responses, and localization info.
- OpenAI calls out ChatGPT iOS/Android testing as part of Developer Mode
  validation.
- Tool metadata should minimize accidental activation and include direct,
  indirect/outcome-oriented, and negative prompts.
- Security/privacy review expects least privilege, explicit consent for write
  actions, validation, auditability, redaction, and published retention policy.

## Dashboard Values

- Display name: `Workflow`
- Subtitle: `Build durable workflows`
- Category: `PRODUCTIVITY`
- Developer/publisher: `TinyAssets` (host must confirm verified publisher)
- Website: `https://tinyassets.io`
- Support: `https://tinyassets.io/legal#contact` or `ops@tinyassets.io`
- Privacy policy: `https://tinyassets.io/legal#privacy`
- Terms: `https://tinyassets.io/legal#terms`
- Domain verification: `Domain verified` in the OpenAI dashboard on
  2026-05-02T14:50-07:00; keep
  `https://tinyassets.io/.well-known/openai-apps-challenge` live while under
  review.
- MCP Server URL: `https://tinyassets.io/mcp-directory`
- Authentication: `No Auth`
- Logo: `assets/brand/workflow-logo-icon.png` (1024x1024 PNG)

Description:

`Workflow connects ChatGPT to a durable open-source work graph. Users can check daemon status, browse shared goals and project wiki knowledge, and submit bounded requests that continue through the Workflow loop beyond a single chat.`

Release notes:

`Initial public alpha of Workflow. This app connects ChatGPT to the directory-safe Workflow MCP surface for daemon status, shared goals, project wiki lookup, run browsing, and bounded request submission.`

## Submission Packet

Use `chatgpt-app-submission.json`.

- 11 directory tools covered.
- 10 positive test cases.
- 4 negative test cases.
- No widget/resource templates are exposed from the directory surface, so no
  widget CSP domains are required for this submission packet.
- Source regression coverage verifies packet tools match the directory source
  tool set and hints.
- 2026-05-02T15:27-07:00 regression coverage added a direct
  `submit_workflow_request` temp-data-dir write-path test; the directory test
  suite now passes with 8 tests.

Review-facing write boundaries:

- `propose_workflow_goal`: creates a Workflow goal proposal and can create
  public Workflow state after ChatGPT approval. It is non-destructive but
  open-world.
- `submit_workflow_request`: queues a bounded Workflow request inside Workflow
  after ChatGPT approval. It is non-destructive and not open-world by itself.

## Asset Pack

Current local assets in `output/openai-submission-assets/`:

- `chatgpt-web-workflow-proof-2026-05-02.png`
- `chatgpt-web-goal-success-2026-05-02.png`
- `workflow-connect-desktop-2026-05-02.png`
- `workflow-connect-mobile-2026-05-02.png`
- `workflow-legal-privacy-desktop-2026-05-02.png`
- `workflow-legal-privacy-mobile-2026-05-02.png`

The older failed goal screenshots were removed from this asset folder so they
cannot be mistaken for positive proof. The historical failure record remains in
`docs/ops/openai-app-submission-chatgpt-proof-2026-05-02.md`.

Current proof caveat: the ChatGPT web screenshots are historical and should not
be used as final directory-safe proof until the Developer Mode app is
re-registered to `/mcp-directory` and the web golden prompts are rerun in a
fresh chat.

## Final Gate

Run immediately before final submit, from deployed `main` or the exact branch
being submitted:

```powershell
python -m json.tool chatgpt-app-submission.json > $null
python -m pytest tests/test_directory_server.py -q
python scripts/mcp_public_canary.py --url https://tinyassets.io/mcp --timeout 15 --verbose
python scripts/mcp_public_canary.py --url https://tinyassets.io/mcp-directory --timeout 15 --verbose
python scripts/mcp_tool_canary.py --url https://tinyassets.io/mcp --timeout 20 --verbose
python scripts/mcp_tool_canary.py --url https://tinyassets.io/mcp-directory --timeout 20 --verbose
```

If the legal or connect pages changed, also run:

```powershell
cd WebSite/site
npm run check
npm run build
```

Confirm live `get_workflow_status` from `/mcp-directory` still includes
`directory_privacy_note` and does not expose raw activity logs, recent-call
arrays, local filesystem paths, host account identifiers, session-boundary
account data, or internal policy hashes.

Confirm ChatGPT Settings -> Apps -> the enabled developer app for testing shows
URL `https://tinyassets.io/mcp-directory`. If it still shows
`https://tinyassets.io/mcp`, do not use ChatGPT web/mobile results as OpenAI
submission proof.

Confirm the OpenAI Apps domain challenge is still live:

```powershell
Invoke-WebRequest https://tinyassets.io/.well-known/openai-apps-challenge
```

Dashboard domain verification is already complete as of
2026-05-02T14:50-07:00; do not rotate or remove the challenge before final
review.

## Host-Only Answers

These remain blocked until action-time host approval:

- ChatGPT mobile iOS or Android golden prompt proof.
- ChatGPT Developer Mode re-registration to `/mcp-directory`, including the
  custom MCP elevated-risk warning, followed by fresh ChatGPT web proof.
- Mature/adult-content answer.
- Publisher selector and verification assertion.
- Compliance/legal checkboxes.
- Any business/legal identity/contact assertion in the dashboard.
- Final `Submit for Review`.

Suggested mature/adult-content answer if the host confirms it: `No`.

Suggested sensitive-data disclosure if the host confirms it: the public
directory connector does not request passwords, API keys, MFA codes, payment
card data, government IDs, biometrics, SSNs, PHI, or PCI data. It receives only
tool inputs needed for Workflow actions and returns redacted Workflow
status/goal/wiki/run/request metadata.
