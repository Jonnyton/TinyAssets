# Agent user path map — what a user should be able to do with their agent

**Source model:** `https://github.com/vercel/ai` via
`docs/audits/2026-08-07-vercel-ai-sdk-agent-and-ux-implications.md` (the SDK's
capability model: loop control, typed tools, streaming tool states, approval
states, workflow patterns). **Surface:** the 28 tools of
`tinyassets/universe_agent_server.py` as deployed (prod hash-verified against
`claude/slack-socket-mode` 2026-08-08, 5/5 files match).
**Method:** every path is walked in Slack as a real user (DM `D0BMPBUBBSB`,
universe `u-tiny`); no MCP bypass. Failures get an ENABLING PRIMITIVE — the
thing that lets a user build the custom version themselves — never a bundled
feature (AGENTS.md: enabling primitives, not pre-built complexity).

**Status legend:** `PROVEN` = walked live in Slack with rendered evidence ·
`BUILT?` = code exists, never walked as a user · `PARTIAL` = some of the path
proven · `MISSING` = no primitive exists yet.

## A. Talk to it

| # | Path — the user can… | SDK grounding | Status | Evidence / gap |
|---|---|---|---|---|
| A1 | DM their agent and get an answer in its own voice | HarnessAgent | PROVEN | 2026-08-07 rounds; founder recognition live |
| A2 | Be recognised as founder; strangers get no founder powers | — (authority ≠ approval) | PROVEN | `founder-mapping-proven-live-slack` |
| A3 | Teach it a durable fact it recalls in a LATER conversation | — | PARTIAL | canon path reads requests correctly; post-hoc extractor overwrote identity once (`extractor-overwrites-identity-from-a-request`) |
| A4 | Ask "what can you do?" and get an accurate user-level map | typed tool catalog | BUILT? | tools carry user-facing docstrings; never asked live |

## B. See what it's doing (SDK #6/#8 — the top UX gap)

| # | Path | SDK grounding | Status | Evidence / gap |
|---|---|---|---|---|
| B1 | See progress notes WHILE a multi-step job runs, not silence-then-answer | tool parts stream through states | BUILT? | `report_progress` posts to the turn's channel via `TINYASSETS_AGENT_CHANNEL_ID`; never observed live mid-job |
| B2 | Know explicitly whether the job finished or stopped blocked | `done` tool + `toolChoice:'required'` | PROVEN | `finish` seen live in both states (`done —` / `stopping —…Blocked:`) |
| B3 | Be protected from a runaway loop | `stopWhen` / `isStepCount` | PROVEN | guard fires at call 40, correct message (probed) |

## C. Build workflows (SDK #9/#5)

| # | Path | SDK grounding | Status | Evidence / gap |
|---|---|---|---|---|
| C1 | Start from a remixable pattern template | 5 workflow patterns as commons content | BUILT? | `sequential/routing/parallel/orchestrator/evaluator_starter` seeded, build+run fixed (state_schema derivation); never instantiated by a live user ask |
| C2 | Describe a custom workflow and have the agent compose it from scratch | branches = nodes+edges substrate | PROVEN | `topic_bullets` (2 nodes) built to spec live |
| C3 | A wrong spec comes back as ONE problem with an actionable fix, and the agent repairs | typed errors + `repairToolCall` | PROVEN | live: 1 problem + `proposed_fix` (was 4 errors naming nothing) |
| C4 | Change an existing workflow afterwards ("make it 5 bullets, not 3") | — | BUILT? | rebuild via `build_branch` + versions exist; iterate-as-a-user never walked |

## D. Run it and get the result

| # | Path | SDK grounding | Status | Evidence / gap |
|---|---|---|---|---|
| D1 | Run a workflow now and receive the actual produced text in the DM | — | PROVEN | 3 bullets delivered; run `20d2c209ad4f47c9` |
| D2 | A run missing inputs is refused at the call site naming what's missing | `InvalidToolInputError` | BUILT? | preflight exists; never triggered by a live user ask |
| D3 | Read back what a past run produced | — | PROVEN | `read_run` returned produced text (was a mermaid diagram) |

## E. Consent for spending (SDK #7)

| # | Path | SDK grounding | Status | Evidence / gap |
|---|---|---|---|---|
| E1 | A costly action asks FIRST; a typed "yes" resumes it | `approval-requested/-responded` | PROVEN | one-word "yes" → approval recorded → run → delivery |
| E2 | Say NO and the agent stops honestly, no spend | `output-denied` | BUILT? | deny branch of `record_approval`; never walked live |
| E3 | Say "don't ask again for this" — standing consent | — | BUILT? | `standing=True` exists; never walked live |
| E4 | Answer with a BUTTON click, not typed text | approval UI states | MISSING | STATUS row; needs `interactive` envelope + founder check through the EXISTING resolver — deferred, own lane |

## F. Automate (recurring work — the product)

| # | Path | SDK grounding | Status | Evidence / gap |
|---|---|---|---|---|
| F1 | Turn a workflow into a scheduled automation by asking | — | BUILT? | `build_automation` (any kind, created PAUSED, `deliver_to` defaults to the asking DM); never walked live |
| F2 | Start it, stop it, trigger it now, list what they have | — | BUILT? | `start/stop_automation`, `run_automation_now`, `list_my_automations`; never walked live |
| F3 | Change a running automation's inputs | `prepareStep` (per-step control) | BUILT? | `update_automation_inputs` + revision CAS; never walked live |
| F4 | A scheduled tick delivers to the DM WITHOUT the user asking | — | BUILT? | cadence + `deliver_to`; never observed live |
| F5 | Declare what an automation may spend (operation scopes) | capabilities are user-declared | BUILT? | `list/define_operation_scope`; never walked live |

## G. Reach and delegation

| # | Path | SDK grounding | Status | Evidence / gap |
|---|---|---|---|---|
| G1 | Connect a destination and have results delivered there | — | BUILT? | `connect_destination`/`list_connections`; never walked live |
| G2 | Enroll their own compute so the universe runs on THEIR subscription | — | BUILT? | `enroll_compute` (works once env set — `unavailable-often-means-unconfigured`); never walked from Slack |
| G3 | Cloud automation against their repository | — | BUILT? | `create_automation`/`control_automation`; cloud-drain lanes own the backend; not this lane's proof to make |
| G4 | Ask what files the agent keeps in its workspace | — | BUILT? | `workspace_list/read/write/delete`; never walked live |

## H. Meta — agents building agents

| # | Path | SDK grounding | Status | Evidence / gap |
|---|---|---|---|---|
| H1 | Ask their agent to create + activate ANOTHER custom agent and wire it to a chat surface | dynamicTool/MCP composition | BUILT? | `create_agent`/`activate_agent`/`connect_agent_to_chat`; V1 demo row monitors the whole-core route |

## Walk order (this session)

1. **B1** progress visibility during a real multi-step job — the audit's #1.
2. **F1→F2→F4** automation lifecycle: build from C1 template remix, start,
   run-now, observe an unasked scheduled delivery, stop.
3. **E2/E3** deny + standing consent (E1's siblings — cheap while in-channel).
4. **C4** iterate an existing branch by asking.
5. **A4** discoverability; **G4** workspace; **D2** missing-inputs refusal.
6. Note-only: E4 (buttons, own lane), G3 (cloud drain lanes), H1 (V1 demo row).

Results log: `output/user_sim_session.md`. Failures → enabling primitive →
re-walk the same path live before flipping its status.
