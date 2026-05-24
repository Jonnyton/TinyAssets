# OpenAI App ChatGPT Proof - 2026-05-02

Purpose: preserve the live ChatGPT Developer Mode evidence that informed the
OpenAI submission prep packet.

## Environment

- Surface: ChatGPT web Developer Mode.
- App shown as: `Workflow Dev`.
- Historical expectation: `https://tinyassets.io/mcp-directory`.
- Current verified setting, 2026-05-02T15:37-07:00: the enabled ChatGPT
  `Workflow DEV` app is still connected to `https://tinyassets.io/mcp`, not
  `/mcp-directory`.
- Related prep doc: `docs/ops/openai-app-submission-prep-2026-05-02.md`.

Do not use this ChatGPT web proof as final directory-safe proof until the
ChatGPT Developer Mode app is re-registered or refreshed to
`https://tinyassets.io/mcp-directory` and the golden prompt set is rerun in a
fresh chat.

## Read-Only Positive Proof

Earlier 2026-05-02 Developer Mode checks showed these read flows working:

1. Prompt: `Use Workflow to check the current daemon status and tell me any caveats before I start.`
   - Result: Workflow status tool invoked and ChatGPT returned daemon status
     plus caveats.
2. Prompt: `Use Workflow to search for goals related to onboarding and show the best matches.`
   - Result: `search_workflow_goals` invoked. No onboarding matches were
     returned; the OpenAI form and JSON expected output were corrected to allow
     a clear empty state.
3. Prompt: `Use Workflow to list available universes, then inspect the active one.`
   - Result: universe list and active-universe inspection returned
     successfully.
4. Prompt: `Use Workflow to search the wiki for current launch risks, then read the most relevant page.`
   - Result: wiki search/read tools invoked and response summarized launch
     risks while preserving the truncation caveat.

Negative prompt checked:

- Prompt: `What is the weather in San Francisco tomorrow?`
- Result: ChatGPT used the native weather surface; no new Workflow tool call
  was observed between prompt and response.

## Write-Path History

Initial write prompt:

`Use Workflow to propose a public goal named "Onboard new MCP hosts" with tags discovery,onboarding, then submit a request asking the daemon to summarize today's discoverability blockers.`

Observed result before backend fixes:

- ChatGPT rendered a `Propose new public workflow goal?` approval card.
- After approval, the tool call did not complete.
- Direct public `/mcp-directory` probe reproduced
  `cannot import name '_ensure_author_server_db' from 'workflow.api.branches'`.

After PR #149 deployment (`2a1651f`, deploy run `25245035290`):

- Direct `/mcp-directory` `propose_workflow_goal` succeeded and created goal
  `35f70887461e` (`Onboard new MCP hosts`).
- Direct `/mcp` `goals action=propose` succeeded and created goal
  `975e8fbdead0` (`Workflow legacy propose probe 2026-05-02`).
- ChatGPT Developer Mode read proof found `35f70887461e` by exact title.
- ChatGPT Developer Mode `submit_workflow_request` returned
  `req_1777701087_d215c1fa` in `echoes-of-the-cosmos`.
- ChatGPT Developer Mode goal-propose approval still stalled after clicking
  `Propose Goal`.

After Platform MCP Server `Scan Tools` and `Continue` on 2026-05-02:

- Platform draft remained configured to `https://tinyassets.io/mcp-directory`.
- The Platform MCP Server section showed the narrow tool set, including
  `propose_workflow_goal` and `submit_workflow_request`; no legacy `Goals` tool
  appeared there.
- Fresh ChatGPT Developer Mode before clicking Platform `Continue` rendered a
  `propose_workflow_goal` approval card, but the opened call detail showed
  Workflow -> `Goals` with request `{ action: "propose_workflow_goal", ... }`.
- Response returned `Unknown action 'propose_workflow_goal'` with available
  legacy actions `bind`, `common_nodes`, `get`, `leaderboard`, `list`,
  `propose`, `search`, `set_canonical`, and `update`.
- After clicking Platform `Continue` into Testing, a second fresh Developer
  Mode chat again rendered the `propose_workflow_goal` approval card. After
  approval, the tool detail still showed Workflow -> `Goals` with
  `action: "propose_workflow_goal"` and remained stuck at `Access granted for
  Workflow` / `Thinking`; no response body appeared before browser automation
  timeout.

## PR #161 Follow-Up

PR #161 added explicit legacy `Goals` aliases:

- `propose_workflow_goal` -> `propose`
- `search_workflow_goals` -> `search`
- `list_workflow_goals` -> `list`
- `get_workflow_goal` -> `get`

Post-deploy public probes after PR #161 initially passed, and a direct legacy
wrapper proof showed:

- `goals action=propose_workflow_goal` returned validation
  `name is required for propose`, not `Unknown action`.
- `goals action=search_workflow_goals query="Onboard new MCP hosts"` worked.

Later ChatGPT approval-card proof reached Workflow but returned a tool 502
while the public endpoint was temporarily unhealthy.

2026-05-02T12:34-07:00 refresh:

- `python scripts/mcp_public_canary.py --url https://tinyassets.io/mcp --timeout 15 --verbose` passed.
- `python scripts/mcp_public_canary.py --url https://tinyassets.io/mcp-directory --timeout 15 --verbose` passed.
- `python scripts/mcp_tool_canary.py --url https://tinyassets.io/mcp --timeout 20 --verbose` passed.
- `python scripts/mcp_tool_canary.py --url https://tinyassets.io/mcp-directory --timeout 20 --verbose` passed.

## Clean ChatGPT Web Proof After PR #184

2026-05-02T13:23-07:00, ChatGPT web Developer Mode conversation:
`https://chatgpt.com/c/69f59b6c-45b0-83e8-93e2-6b3800852202`.

Read-only prompt:

`Use Workflow to check the current daemon status and tell me any caveats before I start.`

Observed result:

- ChatGPT invoked Workflow and completed normally.
- No `Unknown action`, hang, or 5xx occurred.
- Response summarized daemon status and caveats.

Approved public write prompt:

`Use Workflow to propose a public workflow goal named "Workflow directory post-redaction approval 2026-05-02T13-18" with tags "submission,smoke". After the tool result, reply with the exact goal id and whether the called tool was propose_workflow_goal. Do not call any other tool.`

Observed result:

- ChatGPT rendered a `Propose a public workflow goal?` approval card.
- Host approved the public write at action time.
- ChatGPT completed normally and returned goal id `20e2339c82e3`.
- ChatGPT response stated: `Called tool was propose_workflow_goal: yes`.
- No `Unknown action`, hang, or 5xx occurred.

Direct public MCP verification:

- `python scripts/mcp_probe.py --url https://tinyassets.io/mcp-directory --tool search_workflow_goals --args '{"query":"Workflow directory post-redaction approval 2026-05-02T13-18","limit":5}' --raw`
  returned `20e2339c82e3` as a public goal with tags `submission, smoke`.
- `python scripts/mcp_probe.py --url https://tinyassets.io/mcp-directory --tool get_workflow_goal --args '{"goal_id":"20e2339c82e3"}' --raw`
  returned goal `20e2339c82e3`, visibility `public`, tags
  `submission, smoke`, and `is_deleted=false`.

Current proof boundary:

- BUG-034 `Unknown action` is fixed at the direct legacy-wrapper layer.
- Public MCP endpoints are reachable as of 2026-05-02T13:13-07:00.
- The approved public write proof for goal `20e2339c82e3` remains useful as a
  ChatGPT-rendered approval-card proof, and direct `/mcp-directory` search/get
  still verifies the created goal.
- This is not final directory-safe ChatGPT web proof because a later settings
  audit found the enabled `Workflow DEV` app is connected to the legacy
  `/mcp` endpoint.
- Remaining OpenAI submission proof gaps are directory-safe ChatGPT web,
  ChatGPT mobile, final submission form/legal/publisher approval, and post-fix
  first-user evidence beyond this controlled proof.

## 2026-05-02T15:37-07:00 Settings Audit

In-app browser inspected ChatGPT Settings -> Apps -> `Workflow DEV`.

Observed:

- Connected on: Apr 24, 2026.
- URL: `https://tinyassets.io/mcp`.
- Actions included legacy `get_status`, `goals`, `universe`, `wiki`, `gates`,
  and `extensions`.
- A fresh new ChatGPT web prompt invoked legacy `get_status` and returned raw
  `activity_log_tail`, `last_n_calls`, `policy_hash`, `session_boundary`, and
  local storage `path` values.

Direct production `/mcp-directory` probes at the same time remained clean:

- `get_workflow_status` returned `directory_privacy_note`.
- Strict redaction assertion found no `activity_log_tail`, `last_n_calls`,
  count labels, `policy_hash`, `session_boundary`, `host_id`, or storage
  `path` keys.

Action required before final ChatGPT user proof:

1. Re-register or create a ChatGPT Developer Mode app pointed at
   `https://tinyassets.io/mcp-directory`.
2. Accept the custom MCP warning only with action-time approval because
   ChatGPT warns that unverified MCP servers can modify or erase data.
3. Rerun the web golden prompt set in a fresh chat.
4. Rerun the same prompt set in ChatGPT iOS or Android.
