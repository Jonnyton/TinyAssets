# Design: every universe is an always-on dot

Status: **revised 2026-10-01 to the founder's dots direction. Needs founder
approval again.** The first version (approved 2026-10-01, sessions, tone, tools
and self-improvement) is kept wherever this revision does not replace it. §5
lists what is kept and what changed. This document is the design and contains
no code. Production measurements in §3 were taken read-only on 2026-10-01,
through `ssh workflow-droplet` → `docker exec tinyassets-daemon`, against
`/data/.tinyassets.db` and `/data/u-01kxm1vszd8hwp7em418asq8h9/`.

## 1. Founder direction and the product it names

### 1.1 Direction (verbatim, 2026-10-01)

> "a new users universe should act like an always on dot agent from chatgpt.
> but with the customization of openclaw and the clean powerfull tool list of
> pi.dev and user design shareabliaty for harness and on ui interface command
> center designs for agent management"

> "it should work how ever dots work for chatgpt. dont get past background self
> work that was a user project anyways and i dont want you matching or thinking
> about that shape, i want you building what ever it is that a chatgpt dot agent
> expereance is like. pi's 4 tools, users should have full customization of the
> harness layer for any configeration of agents"

The second message rules out a source of design. The always-on behaviour here
copies what dots do. It is **not** derived from, and is not measured by, the
background agent tiny built for itself or any user-built heartbeat graph. Those
remain user projects built from graph primitives, and this design neither
reuses nor changes their shape.

### 1.2 ChatGPT dots as shipped (OpenAI DevDay, 2026-09-29)

`openai.com` and `help.openai.com` answer 403 to automated fetches, so OpenAI's
wording below comes from search excerpts of its pages and from press that quotes
them. The full research brief, with every citation, is
`ta-scratch-lead/dots-research.md`. It is outside the repo.

| Dots behaviour | Source |
|---|---|
| An always-on agent with **its own cloud computer and browser** (Linux plus Chrome). It keeps working after the chat closes and can "keep several projects moving simultaneously, accept new work without forcing users into separate conversational threads." | [VentureBeat 09-29](https://venturebeat.com/technology/openai-launches-dots-always-on-ai-agent-coworkers-and-chatgpt-space-where-they-can-collaborate-with-human-teams), [Anima 09-30](https://animaapp.com/blog/agentic/openai-dots/) |
| **Onboarding:** give it a name and a clear responsibility, meaning what it owns, where it learns, its quality bar, what needs approval, and how often it reports. Connect apps and set rules. | Anima; [Codersera 09-30](https://codersera.com/blog/openai-chatgpt-dots-guide-2026/) |
| **Proactive research.** When you are not working with it, it "looks for ways to help in the background … using read-only tools restricted in code, so they cannot send messages, change content in connected apps, or control a browser or computer, and any follow-up action must pass the usual rules and checks." | help.openai.com excerpt; [Unite.AI 09-29](https://www.unite.ai/openai-rolls-out-dots-agents-powered-by-gpt-6-astra-in-chatgpt/) |
| **Custom Rules:** each action gets one of four behaviours: *Take action without asking*, *Take action if pre-approved* (only the exact action the user asked for), *Ask before taking action*, or *Hand off to you*. | help.openai.com excerpt; Codersera |
| **Auto-review** "checks potentially consequential actions against the user's instructions, Custom Rules and OpenAI's built-in safety requirements before determining whether the work can proceed autonomously or requires approval." It cannot be turned off. | VentureBeat; Codersera |
| **Reserved actions.** Changing a password or moving money "must be handed back to the user". Permanently deleting data or installing unrecognised software "requires confirmation each time". | Unite.AI |
| **Profile and Activity:** *In progress / Scheduled / Completed*, the live computer with **Take over / Return control**, and **Pause** from the ••• menu. "Activity View lets users inspect background work and intervene." | VentureBeat; Anima; help.openai.com excerpt |
| **Notification:** a phone push when a task is done. Reachable in ChatGPT on web, desktop and phone, in Slack and Teams, and by voice. | help.openai.com excerpt; Unite.AI |
| **Memory:** it learns preferences from feedback. Individual memories "cannot currently be viewed or edited". The only way to clear them is to delete the dot. | Unite.AI |
| **Limits:** one dot per plan, OpenAI's model, and setup only on desktop. | Codersera; [MediaNama 10-01](https://www.medianama.com/2026/10/223-openai-launches-dots-devday-2026/) |

**What we copy as-is:** everything in the table except the last two rows.
**What we change:** memory is viewable and editable item by item, the number of
agents is unlimited and configured by the user, and every model call runs on
the user's own compute because the platform never supplies an LLM. **What we
add from the founder's other references:** OpenClaw-level customization of the
harness, pi's four tools, and harness and command-center designs that users
can share.

### 1.3 pi's tool list (the "clean powerful tool list")

pi's defaults are `read`, `write`, `edit` and `bash`. Its prompt plus tool
definitions come to under 1k tokens
([pi.dev](https://pi.dev)). pi 0.99 (v0.99.2 of 2026-09-30) added MCP without
adding resident schemas: servers are reached through one programmable layer
(`codemode`, with `searchTools()` / `describeNamespace()`) and are not listed
in the tool description
([release](https://github.com/earendil-works/pi/releases/tag/v0.99.2)). This
design keeps exactly the four tools. Bash is the programmable layer, and `ta
search` is the discovery call (§4.6).

## 2. Research: the four reference harnesses (sources fetched 2026-10-01)

| | pi (pi.dev, earendil-works/pi, v0.99.2 of 2026-09-30) | OpenClaw (openclaw/openclaw, v2026.9.7 of 2026-09-30) | Claude Code (code.claude.com/docs, auto mode default from v2.1.283) | Hermes Agent (NousResearch/hermes-agent, v2026.9.24 of 2026-09-24) |
|---|---|---|---|---|
| **Loop / session length** | A run continues while tool results or queued messages need another model call, then ends. Sessions are persistent JSONL trees with resume, fork and branch. | Serialized per-session runs. The default runtime budget is **48 h** (`timeoutSeconds` 172800, `0` = unlimited). Progress does not reset it, and a separate idle watchdog (120 s cloud) catches a hung model. | Gather, act, verify, repeat until done. Sessions persist as JSONL and support `--continue`, `--resume` and fork. | Persistent sessions. `/goal` adds a judge model after every turn that feeds "continue" back into the same session until the goal is met (the Ralph loop). |
| **Context** | Auto-compaction when `tokens > window − reserve` (reserve 16k, keep the latest 20k). It writes a structured iterative summary as a tree entry, and the originals stay on disk. | Auto-compaction keeps tool call/result pairs intact. Before compacting it runs a silent **memory flush** turn so the agent saves durable notes. A safeguard mode audits summary quality. | Auto-compaction plus `/compact`. CLAUDE.md is always loaded. **Auto memory** loads `MEMORY.md` (first 200 lines or 25 KB) every session. | `MEMORY.md` (2,200 chars) and `USER.md` (1,375 chars) are a frozen snapshot in the system prompt. A full store is an error the agent must consolidate. `/compress`. FTS5 search over past sessions. |
| **Tools** | Defaults are `read`, `bash`, `edit`, `write`, with optional `grep`, `find`, `ls`. MCP servers default to **codemode** (scripts call tools found by `searchTools()`) or **deferred** (`tool_search`), so their schemas are never resident. | `exec`, `process`, `read`/`write`/`edit`/`apply_patch`, web search and fetch, `browser`, `message`, `sessions_*`/subagents, `cron`, `tool_search`/`tool_call` for large catalogs, plugins. | File ops, search, shell, web search and fetch, subagents, MCP with deferred tool loading, Claude in Chrome. | 40+ tools: terminal, files, browser, `web_search`, `execute_code` (scripts call tools over RPC), `delegate_task`, `memory`, `session_search`, `cronjob`, MCP. Seven terminal backends (local, Docker, SSH, Modal, Daytona …). |
| **Extensions / skills** | Agent Skills spec (agentskills.io). Only name, description and path sit in the prompt, and the body loads on demand. TypeScript extensions add tools, hooks and providers. Packages ship via npm or git. "Ask Pi to create the … skills, extensions … you need." | Skills plus **Skill Workshop**. Plugins and ClawHub. | Skills (Agent Skills standard; commands merged into skills), hooks, plugins, subagents. | Skills (agentskills.io) in `~/.hermes/skills/`. The agent can create, modify or delete any skill through `skill_manage`. Skills Hub. |
| **Authority** | **No permission system.** It runs with the process's OS permissions. Containment (container or micro-VM) is the boundary. | `tools.exec.mode`, with `auto` recommended. Main-session tools run on the host unless sandboxed, and inbound senders are untrusted until paired. | Permission modes. **Auto mode** (a classifier approves or denies) is the default starting mode. `bypassPermissions`, plus a sandbox for defense in depth. | `approvals.mode: smart`: an auxiliary model auto-approves low risk, auto-denies dangerous commands and prompts only when uncertain. `off` = yolo. Unattended cron defaults to deny for dangerous commands. |
| **Self-improvement** | The agent writes its own skills, prompt templates and extensions. | **Self-learning, default `auto`**. Immediate repair of a skill the turn used, plus a detached experience review after substantial work. Proposals are hash-bound, security-scanned and **captured for rollback**. "Dreaming" consolidates memory in the background. | Auto memory learns from corrections. The user or agent edits CLAUDE.md and skills. | Agent-curated memory with periodic **nudges**. **Autonomous skill creation** after complex tasks. Skills self-improve during use. A **curator** moves unused skills from active to stale to archived. |
| **Background** | None built in. pi-chat bridges chat channels into sandboxed sessions. | Automations (cron), a heartbeat monitor, hooks, webhooks, standing orders. | `/loop` (session-scoped), Desktop scheduled tasks, cloud **Routines**. | Built-in cron delivering to any platform, `/goal`, kanban worker lanes. |
| **Steering mid-run** | `Enter` steers after the current tool batch and `Alt+Enter` queues a follow-up. Esc aborts and returns queued messages. | A **steering queue** checks at every tool launch. Unstarted tools get a synthetic "Skipped to process an incoming message" result and the message enters before the next model call. | Interrupt, then redirect. | A new message interrupts. `/stop`. |
| **Best at** | Minimal resident surface (<1k tokens), self-extension, containment over prompts. | Long budgets, a steering queue at tool boundaries, memory flush before compaction, rollback-captured self-learning. | Verify-as-you-go loop, terse result-first tone, auto memory, auto mode. | A closed learning loop (skills plus memory nudges plus curator), goal continuation, cron. |

Sources:
- [pi docs](https://github.com/earendil-works/pi/tree/main/packages/coding-agent/docs): `how-pi-works.md`, `compaction.md`, `skills.md`, `mcp.md`, `settings.md`, `security.md`, `usage.md`
- [pi-chat](https://github.com/earendil-works/pi-chat)
- [OpenClaw docs](https://github.com/openclaw/openclaw/tree/main/docs): `concepts/agent-loop.md`, `concepts/compaction.md`, `concepts/queue-steering.md`, `concepts/agent-workspace.md`, `concepts/soul.md`, `tools/index.md`, `tools/self-learning.md`, `tools/permission-modes.md`, `automation/index.md`
- [Claude Code docs](https://code.claude.com/docs/en/how-claude-code-works): `memory`, `skills`, `permission-modes`, `scheduled-tasks`
- [Hermes Agent README](https://github.com/NousResearch/hermes-agent) and docs: `user-guide/features/{memory,skills,curator,goals,tools}`, `user-guide/security`

Current pi defaults to the four tools, and it now also ships `grep`/`find`/`ls`
and built-in MCP behind codemode and deferred exposure. This design keeps the
four and puts breadth behind `ta` in bash (§4.6).

**Synthesis.**
- Every reference keeps the **session** as the unit of continuity and compacts
  it, rather than rebuilding context per message.
- All four use **Agent Skills** files the agent can write.
- None puts per-action consent inside the agent's own workspace. Containment or
  a classifier carries safety.
- The three that learn (OpenClaw, Hermes, Claude Code) let the agent edit its
  own instructions, and the stronger two version or rollback-capture what it
  writes.

## 3. Current-state audit: tiny's harness

### 3.1 Code paths (origin/main 2ffb29ae)

- **Persona prompt.** `universe_intelligence._build_persona_system_prompt`
  (`:433-672`) opens "You are a personified intelligence the founder is
  raising, and right now you are getting to know the founder". It then says
  "Speak warmly", "stay genuinely curious and ask about them", and "If
  something is ambiguous … I ask to clarify". About 2.4k characters of "How I
  ask for what I need" grant-shape instructions follow (`:613-650`).
  `_CROSS_SURFACE_CONTINUITY` (`:1202`) says "Greet them warmly", and
  `_turn_input_method_context` (`:1218`) and `_UNRECORDED_LESSON` (`:1186`) add
  more. Measured median system prompt: 7,963 characters.
- **Turn loop.** `converse` (`:1241`) is one stateless turn. Memory is
  `conversation_memory.format_history`: `DEFAULT_LIMIT = 20` messages and
  `DEFAULT_CHAR_CAP = 7000` (`conversation_memory.py:34-41`), text only, so the
  turn never sees its own earlier tool calls or results. That block ends with
  "a costly action still needs consent recorded THIS turn" (`:158`). Codex
  launches with `--ephemeral` (`providers/codex_provider.py:871`), so there is
  no native session to resume either. For converse, Codex gets an empty scratch
  `/workspace` "so it answers as a chat model rather than acting as a code
  agent" (`:876-880`), which is the opposite of the directive. After the reply,
  a separate learning-extraction model call still runs whenever the turn did not
  call `write_brain` (`:1484-1494`).
- **Served tools.** `served_tools.SERVED_ENGINE_MCP_TOOLS` lists 14 handles:
  `read_graph`, `get_status`, `run_graph`, `write_graph`, `browse_commons`,
  `read_commons_shape`, `read_brain`, `write_brain`, `connect_compute`,
  `source_channel`, `read`, `write`, `edit`, `bash`. Their descriptions are
  resident on every round, ratcheted at 30,000 characters (about 28.5k actual,
  roughly 7k tokens) in `tests/test_converse_turn_cost.py:79`. pi's whole
  prompt plus tools fits under 1k tokens.
- **Jail.** `universe_tools.py` runs `read`/`write`/`edit`/`bash` inside
  bubblewrap. It has **no network** (`:1069-1082`: "a shell in /u with no
  network"), a read-only root, and writes limited to ten brain files and six
  harness dirs (`AGENT_BRAIN_FILES`, `AGENT_HARNESS_DIRS`, `:129-135`). The
  `.runtime/` move for platform state is still pending.
- **Skills.** `skill_index` and `harness_prompt` exist (`:1036-1108`). The
  founder's `skills/` directory is **empty**.
- **Agents it builds.** Agent nodes in the universe's own graphs
  (`shared_self.py`) run the same converse harness through
  `background_served_provider.py:815-852`, so the agents it builds inherit
  every harness limit above. They are measured as the universe's own creations,
  not as the harness.

### 3.2 Production numbers (agent_turns, 2026-09-15 → 2026-10-01: tiny's chat turns)

The harness is the universe's own agent talking with its owner, so it is
measured on chat turns only. Turns were classified by the actual message after
the memory block. Of 1,644 tiny turns, 251 are chat with the founder. The other
1,393 are wakes of a background agent tiny built for itself, which is a
user-built graph and not part of the harness. They are excluded here (founder,
2026-10-01: "dont conflate the two things").

| Measure (251 chat turns) | Value |
|---|---|
| Median input tokens per turn | 61,862 (p90 510,368) |
| Total input tokens | 53.7M |
| Median reply length | 637 chars |
| Replies containing an ask | 26% |
| Replies with blocked / can't / unavailable language | 54% |
| Replies with "I haven't verified / unverified / can't confirm" disclaimers | 29% (66 of 225) |
| Replies claiming any effect (merged, posted, PR, sent …) | 33 (15%) |
| … of which not negated in the same reply | **7** |
| Input tokens per effect-claiming reply | 1.6M |
| Turns ending indeterminate (`held_native_unknown`) or abandoned | 26 (10.4%) |

**Corrections.** 46 of 262 founder messages (18%) are corrections ("your still
not understanding the general shape", "it could have easily by now made the
village fully functional"), and 8 of the last 40 are. 13 universe replies open
with "You're right" or "Sorry".

**Asks.** 85 app requests were raised between 2026-08-28 and 2026-10-01. The
founder dismissed 15 and muted 8 more request kinds.

**What tiny itself says blocks it** (`notes/continuation.md`, 2026-10-01 05:43Z):
"Local FastMCP/pytest/Ruff/browser capabilities remain absent", and a
`read_graph` result "truncates before its result can be compacted". In chat it
said that a background turn "has a 15-minute maximum". That was its own
900 s interval trigger, which it believed was a limit.

**Workspace.** The universe root has 422 entries, 362 of them platform
`.worker_supervisor.*.json` files. tiny's real work lives in `notes/` (about
880 KB of scripts, JSON probes and plans), including a 4.4 KB
`prompts/background-operating.md` and an 18 KB `notes/goals-and-outcomes.md`
that it re-reads every turn, because no session carries what it already read.

**Tool observability.** `agent_turn_tools` holds 109 rows, all from the
HTTP-loop universe and **none for tiny's native turns**. Nobody, including
the founder and tiny, can see after the fact which tools a turn called.

### 3.3 Top drag findings (chat turns)

1. **No session.** Every chat message rebuilds context from scratch and forgets
   the agent's own earlier tool calls and results. The median turn is 61,862
   input tokens, and 7 of 225 replies report an un-negated effect.
2. **Guidance teaches asking and hedging.** 26% of chat replies ask, and 29%
   carry verification disclaimers. The persona prompt instructs warmth,
   curiosity, asking to clarify, and per-turn consent.
3. **Tools are walled where the work is.** There is no network in bash, no
   browser, and no toolchain, and `read_graph` results truncate. Those are the
   blockers tiny lists itself, and they became 85 requests.
4. **Heavy per-round context.** About 8k characters of persona, 7k of history
   text and about 28.5k of tool descriptions are re-sent each round.
5. **Invisible, unreliable turns.** Native turns journal no tool calls, so
   neither the founder nor tiny can see what a turn did, and 10.4% of chat turns
   end indeterminate or abandoned.

## 4. Target design: the dot experience, element by element

### 4.1 Principle

A new user's universe **is** a dot. It is one always-on agent with its own
computer and a responsibility. It does its own work, watches for things to do
while idle, and acts under rules the user sets. It runs on the user's own
compute.

- **Platform supplies:** a persisted session, a jailed computer, rule
  enforcement and review, activity tracking, and a profile page.
- **User owns:** everything else, including the instructions, memory,
  skills, rules, model and the number of agents.
- **Fixed boundaries:** the only platform-wide invariant is cross-user isolation
  (`the-floor-is-cross-user-only`). Within a universe, the boundaries are the
  user's own rules, plus the reserved actions of §4.9.

| Element | Section |
|---|---|
| Name plus one responsibility at onboarding | 4.2 |
| Own computer and browser, with live view and take-over | 4.3 |
| Always on, several projects at once (Activity) | 4.4 |
| Read-only proactive research while idle, proposals only | 4.5 |
| Exactly pi's four tools | 4.6 |
| Custom Rules with four behaviours | 4.7 |
| Auto-review | 4.8 |
| Reserved hand-back actions | 4.9 |
| Profile page, Pause, push | 4.10 |
| Reachable from the app, `converse` and chat apps | 4.11 |
| Memory editable item by item | 4.12 |
| Harness layer and roster, any configuration | 4.13 |
| Shareable harness bundles and command-center layouts | 4.14 |

### 4.2 Onboarding: a name and one responsibility

On a new universe's first conversation, from any surface, the agent asks for
two things: a name, and a responsibility. The responsibility has the five parts
dots asks for:
- what it owns;
- where it learns from (connections and sources);
- the quality bar;
- what needs approval;
- how often it reports.

The platform supplies the onboarding questions as part of the seed template
(§4.13). They are not code paths. The agent writes the answers into its own
files:
- the name goes to `identity.md`, as the personification spec already requires;
- the responsibility goes to a `## Responsibility` section of `AGENTS.md`;
- each "needs approval" item becomes an *Ask before taking action* rule. The
  agent cannot write rules, so it proposes them in one request the owner
  confirms (§4.7).
- the report cadence becomes a scheduled activity (§4.4).

If no compute is connected, onboarding says so plainly and links to connecting
compute. Nothing pretends to run (Hard Rule 8). The responsibility can be
changed at any time, by telling the agent or in the profile's Harness tab.

### 4.3 Its own computer

- **Workspace.** The jailed universe folder `/u`, with the whole user root
  writable once S3c has moved platform state to `.runtime/`.
- **Shell network.** `bash` has public egress through the checking proxy (S3a,
  #4174).
- **Browser.** A Chromium dedicated to the agent. It runs in its **own**
  sandbox, separate from the tool jail.
  - The agent drives it through a `browse` command in bash, which talks to the
    browser over a per-universe socket.
  - The browser profile (cookies, saved logins) lives under
    `.runtime/browser/` and is never mounted into the tool jail. The agent can
    use a session the owner logged into, but cannot read the cookie or password
    store. This keeps credential blindness: dots stores credentials "without
    model exposure", and so do we.
- **Live view.** The profile's Computer tab streams the browser's screen
  (CDP screencast frames over the owner door) and the tail of the running bash
  command.
- **Take over / Return control.** *Take over* hands the browser's input to the
  owner, and the agent's `browse` calls block with `owner has control`.
  - The owner logs in or decides, then presses *Return control*.
  - The agent's session receives the mechanical line `owner returned control at
    <url>`.
  - Anything typed during take-over goes to the browser only. It never enters
    the session log or the model.

### 4.4 Always on, several projects at once: Activity

- **Main thread.** The dot's main session is the owner thread that S1 already
  keeps (`thread:principal:<owner>`, one session across app, phone, desktop and
  connector). It stays responsive.
- **Activities.** Work the dot takes on becomes an **activity**: a child
  session keyed `activity:<id>`, with these fields:
  - title;
  - origin: an owner ask, an approved proposal, or a schedule;
  - status: `in_progress`, `waiting_on_you`, `scheduled`, `paused`, `completed`
    or `failed`;
  - a result summary;
  - receipts: the effects it caused, the approvals it used, and its tool
    journal.
- **Parallelism.** The dot starts activities with `ta activity start`, and
  several run at once. Each takes an agent seat (#4154). When seats are full
  the new activity waits visibly and is never refused (`usage-limits-are-
  storage-and-seats`).
- **Status reaches the main thread** as the S2 event line, for example
  `activity "Invoice Acme" completed: invoice sent (receipt r_…)`.
- **No client needed.** Activities do not need a connected client. They run
  until done (`turn-runs-until-finished-not-wall-clock`) and survive deploys,
  because the session log persists.
- **Scheduled activities.** A scheduled activity is a user-owned automation
  whose target is "start this activity on agent X". The existing
  `user-owned-automations` rows and firing are reused, and the Scheduled tab
  lists them with their next run.
- **Storage.** Activity records are a new storage shape. Slice D2 opens its own
  storage proposal before code. Records live under `.runtime/` and count to the
  account storage pool.

### 4.5 Proactive research while idle (read-only, enforced in code)

As in dots, the dot itself looks for ways to help while the owner is not
working with it. This is a behaviour of the harness. It is not a graph the user
must build, and it does not reuse the shape of any user-built wake loop.

- **When it runs.** A research turn starts only when all of these hold:
  - the agent is not paused;
  - it has no `in_progress` activity;
  - the owner has not messaged for the idle period;
  - the time is inside active hours.

  It then runs at most at the cadence in the agent's `settings.yaml`, and also
  when a connected read source reports new items. Defaults: idle period 30 min,
  cadence 4 h, active hours 08:00–22:00 in the owner's clock (open question 3).
  Setting the cadence to `off` disables it.
- **Read-only profile, enforced in code, not by prompt:**
  - `read` works. `write` and `edit` are refused by the tool layer.
  - `bash` runs with `/u` mounted read-only and **no egress socket bound**, so
    no network.
  - The `ta` socket opened for a research turn carries a read-only capability.
    Every mutating handler refuses it, and only read verbs answer.
  - Connected-app access goes through the credential-blind effectors. Only
    operations declared as reads run.
  - `browse` is not available.
- **Output is proposals only.** The turn may raise zero or more requests of
  kind `proposal`. Each names one concrete planned action and why, for example
  "Invoice for the Acme article is not sent; draft and send it?".
  - Approving a proposal starts an activity in which that exact action counts
    as pre-approved (§4.7). The action still goes through auto-review.
  - A turn that finds nothing sends nothing.
- **Cost.** Research runs on the user's compute and seats like any turn, and
  the profile shows its share of usage. Pause stops it.

### 4.6 Tools: exactly pi's four

- **Resident tools.** Every agent gets `read`, `write`, `edit` and `bash`
  over `/u`, and no other resident tool. The tool definitions sent each round
  are those four schemas plus one base-prompt line naming `ta`.
- **Native built-ins off.** Adapters that bring native tools run with them
  disabled. Only the four reach the model. Today each adapter restricts its
  native tools in its own way (`claude_provider.py`, `codex_provider.py`), and D6
  makes that uniform.
- **Breadth goes behind one searchable command in bash.** This is pi's codemode
  idea, with bash as the interpreter:
  - `ta search <words>` lists the matching capabilities across platform verbs
    (graphs, runs, automations, activities, requests, commons), the user's
    connected-app operations, user extensions, and any MCP servers the user
    attached.
  - `ta describe <name>` prints one capability's arguments.
  - `ta <name> --json '<args>'` calls it, and a script can chain many calls in
    one `bash` command.
- **Same handlers as the connector.** `ta` uses the same handlers as the public
  connector, over the per-universe socket. The deferred-MCP route that the first
  version planned for the agent is dropped. The public connector's six verbs
  for chatbots are unchanged.

### 4.7 Custom Rules (authority)

**Shape.** A rule has two parts:
- **an action matcher:** a plain-language description plus a structured match
  on an *action class* and optional fields such as destination or operation;
- **a behaviour:** `do` (take action without asking), `do_if_preapproved`,
  `ask_first`, or `hand_off`.

The most specific matching rule wins. When two rules are equally specific, the
stricter wins.

**Action classes the platform can see and enforce:**

| Class | Enforcement point |
|---|---|
| `universe.files`, `universe.shell`, `universe.workflows` (inside the universe) | tool layer, `ta` handlers |
| `shell.egress` (public network from bash) | egress proxy, as one coarse class |
| `app.read:<connection>` / `app.write:<connection>[:<op>]` | credential-blind effector call site |
| `people.message:<channel>` (sending to people) | effector or channel send |
| `commons.publish` / `share` (publishing, granting others access) | commons and visibility handlers |
| `spend` (paid operations over a set budget) | effector cost declaration |
| `browser.submit` (form submit or purchase click through `browse`) | browse socket |
| `delete.external` (permanent deletion in a connected app) | effector op declaration |

**Honest limit.** Bash egress tunnels HTTPS, so the platform cannot see what an
anonymous shell request does. `shell.egress` is one class, governed as a
whole. Every credentialed action goes through the effectors, so rules bind
there precisely.

**Who edits rules.** Rules are the one part of the harness the agent cannot
write.
- They live in owner-only platform state (`.runtime/state/rules`, after S3c).
- The owner edits them in the profile's Rules tab, or through the owner door.
- The agent reads them through a read-only view, and may propose a rule change
  as a request.
- Reason: an agent that edits its own harness must never be able to loosen
  its own authority.

**Seed rules** at onboarding reproduce the first version's "act inside, ask
outside" default, now as rules the user can see and change:

| Class | Seed behaviour |
|---|---|
| `universe.*`, `shell.egress`, `app.read:*` | `do` |
| `app.write` to a destination with an existing standing grant | `do` (existing grants are honoured) |
| `app.write` to a new destination, `people.message`, `commons.publish`, `share`, `spend` over budget, `browser.submit` | `ask_first` |
| Each "needs approval" item from onboarding | `ask_first` |
| Reserved classes (§4.9) | `hand_off`, not editable |

**One decision point.** Every enforcement point calls
`rules.decide(action, context)` before it executes:
- `do`: proceed. A consequential action goes through auto-review first (§4.8).
- `do_if_preapproved`: proceed only when the owner's own message in this
  session, or an approved proposal, names exactly this action. Auto-review
  judges the match. Otherwise the call is treated as `ask_first`.
- `ask_first`: raise one app request with the planned action. The activity goes
  to `waiting_on_you`, and the agent continues other work. An approval may tick
  "always allow this", which writes a `do` rule.
- `hand_off`: raise a request asking the owner to do it, offering *Take over*
  when it is a browser step. The agent never executes it, even after approval.

**Existing grants are kept.** The standing destination grants
(`effector_consents`, the `_check_consent` path) and their call-time checks are
unchanged. They become the data the `app.write` rules consult.

### 4.8 Auto-review

- **What triggers it.** Before any **consequential** action whose rule is `do`
  or `do_if_preapproved`, the platform runs a review. Consequential means every
  class outside `universe.*` and `app.read`.
- **What runs it.** One structured call on **the universe's own model and
  credentials**, through its seat. There is no platform model.
- **Inputs:**
  - the planned action, in structured form;
  - the `## Responsibility` section and the owner's recent messages;
  - the matching rules;
  - the built-in safety requirements (a short fixed text in the base prompt);
  - for `do_if_preapproved`, the message or proposal claimed as the
    pre-approval.
- **Output.** Either `proceed`, or `needs_approval: <one-line reason>`.
  `needs_approval` converts the action to `ask_first`.
- **Fails closed and loud.** If the review cannot run (no compute, an error, a
  timeout), the action becomes a request that names the cause. It never
  proceeds silently.
- **Inside the universe it never runs.** Universe file history makes those
  actions undoable, and reviewing them would recreate the drag measured in §3.
- **Off switch.** Dots does not allow one. The founder asked for full harness
  customization. Recommendation: on by default, and the owner may switch it off
  per class in the Rules tab, except for the reserved classes (open question 2).

### 4.9 Reserved actions

These classes are always `hand_off`. The owner does them, in take-over or in
the connected app:
- changing a password, credential or security setting on an external account;
- moving money or making a payment;
- granting another person access to the owner's accounts or data.

They are enforced in code at the decision point. No rule, import or agent edit
can change them.

Dots' "permanent deletion" and "unrecognised software" confirmations map as
follows. `delete.external` is `ask_first`, and the owner may set it to
`hand_off`. Installing software **inside the jail** is not reserved, because the
jail is the containment and file history covers it.

These protect the owner's own accounts from their own agent, which is a
product choice beyond the cross-user floor (open question 1).

### 4.10 The profile page and the command center

**One agent's profile:**
- **Header:** name, responsibility, status (working / idle / paused / waiting
  on you), model, usage this period.
- **Activity tab:** *Waiting on you* first, then *In progress*, *Scheduled* and
  *Completed*. Completed items carry receipts. Each item can be steered (a
  message into its session), paused or stopped. A stopped activity keeps its
  partial result.
- **Computer tab:** live browser view, Take over / Return control, and the
  current bash tail.
- **Memory tab:** §4.12.
- **Rules tab:** the four-behaviour editor, with proposed rule changes
  awaiting approval.
- **Harness tab:** the agent's files (`AGENTS.md`, skills, extensions,
  `settings.yaml`), the history, and Undo.

**Pause** (••• menu) stops the agent's new turns, proactive research and
scheduled activities. The running turn stops at its next tool boundary
(#4152). Resume continues where it left off.

**Push** is sent on *completed*, *waiting on you* and *new proposal*, through
the existing phone, desktop and browser notifications (#4140, #4138), with a
toggle per kind.

**The roster view is the command center.** It has one row per agent, showing:
- status;
- the waiting-on-you count;
- the current activity and the next scheduled run;
- usage.

From it the owner can reply or approve inline, pause, and open a profile.

**Layouts are the user's own.** Both pages are built on the custom-UI layer
(`app-ui-library`, #4160 and #4165), so users redesign them and share the
design (§4.14).

### 4.11 Reachable everywhere

- **App and connector.** The app (web, desktop, phone) and `converse` already
  reach one main session per owner (S1).
- **Chat apps** (Slack, Telegram, Teams and others) connect through **channel
  extensions** that relay into the same session.
  - Channels stay user-built (`channels-must-be-user-built-not-hardcoded-
    effectors`).
  - The published starter template ships ready-made channel extensions, so a
    new user gets dots' "reach it in Slack" in one connect step, without
    platform channel code.
- **One session.** A message from any of these steers the same session (S2).

### 4.12 Memory, item by item

- **One item per bullet.** `MEMORY.md` holds one item per bullet, each with a
  short stable id (`- [m_7f3a] Prefers invoices on the 1st`). The agent adds
  and edits items as it learns from feedback, which is how a dot "learns over
  time".
- **Memory tab.** The profile's Memory tab lists the items, and the owner can
  edit or delete any one.
- **History and Undo.** Every change is recorded in the universe file history,
  with Undo.
- **Deleting an item does not delete the agent.** That is the dots limitation
  we drop.

### 4.13 The harness layer: fully user-configurable, any roster

**Per-agent harness files.** The main agent's files stay where S1 put them, at
the universe root. Each further agent in the roster has the same layout under
`agents/<id>/`:
- `AGENTS.md`: instructions and `## Responsibility`;
- `identity.md`;
- `MEMORY.md`;
- `skills/` and `extensions/`: a skill or extension in `agents/<id>/` overrides
  the root one of the same name;
- `settings.yaml`: model, research cadence, idle period, active hours,
  compaction thresholds, channels and seat priority;
- rules, which are owner-edited and held in `.runtime/` (§4.7).

**Any configuration.** The user can configure:
- one dot or many;
- specialists with narrow rules;
- a lead dot that hands activities to others (`ta activity start --agent
  <id>`).

Each agent has its own sessions, activities, rules and profile, and all of them
draw seats from the account pool. Graph agent nodes stay workflow primitives,
and a graph can start an activity on a roster agent.

**The seed template.** A new universe is seeded from an explicitly published,
reviewed starter template, never the founder's live private files. The
template holds the base `AGENTS.md`, the onboarding questions, the seed rules,
starter skills and channel extensions. The user may replace any part of it.

### 4.14 Sharing harness bundles and command-center layouts

- **What a bundle holds.** A bundle is one agent's or a whole roster's harness
  (instructions, skills, extensions, settings, a rules *suggestion*),
  optionally with the command-center and profile layouts.
- **Reuse.** Bundles use the existing `universe-custom-agents` public-definition
  shape, which is already immutable, bounded, secret-free and
  provenance-tracked, with verified portable interchange.
- **Export is explicit, and private by default.**
  - Never included: memory (unless the owner opts in item by item), session
    logs, credentials and browser state.
  - A scrub pass removes the owner's email addresses, phone numbers, names and
    connection identifiers from text.
  - The owner confirms a preview of the scrubbed bundle before publishing.
- **Import lands in quarantine.** It is copied to `imports/<id>/` and stays
  inert: no rules apply, no extensions run, no schedules register and no
  channels connect until the owner reviews and activates it in the app.
  - Imported rule suggestions can be activated only as written or stricter.
    Loosening one requires an explicit owner edit.
  - Imported text reaches the agent inside the existing untrusted-content
    envelope.

### 4.15 Kept from the first version, unchanged

The full text is in Appendix A.

Everything below is unchanged from the first version:
- sessions and compaction, with the pre-compaction flush;
- the turn running until done;
- owner steering at tool boundaries;
- truthful tool results and the full journal (which feeds Activity receipts and
  the live view);
- the result-first tone and seed `AGENTS.md`;
- self-improvement with a jailed history store and Undo;
- the egress safety floor;
- the delete list of the first version. The resident handbook moves to skills
  read through `ta`.

## 5. What already shipped, mapped onto the dot

| Shipped or in flight | Kept | Changed |
|---|---|---|
| **S1, #4173 (merged):** a native session per thread or agent node, resume as a declared capability, persona warmth and per-turn-consent text removed, seeded `AGENTS.md` | Sessions, which become the dot's main thread. Activities reuse the same keying (`activity:<id>`). The tone removal. Claude resume (S1b). | The seeded `AGENTS.md` text "act without asking inside, one request outside, an approval stands" becomes a **description** of the user's seed rules. Enforcement moves to `rules.decide` (D1). |
| **S3a, #4174 (in review):** bash egress through the checking proxy socket | All of it. | Egress becomes the `shell.egress` rule class. The socket is not bound for read-only research turns (D3). |
| **S3c, #4175 (proposal, harness-s3 building):** platform state leaves the universe root for `.runtime/` | All of it, and it is now a prerequisite. | Rules, activities, proposals and the browser profile are new `.runtime/` residents. The S3c resolver is where they register. |
| **First version S2:** owner messages steer the live turn | All of it. | It also carries activity status lines. |
| **First version S4:** journal, session log, spill to file | All of it. | It also feeds Activity receipts and the live view. |
| **First version S5:** the platform as one extension (`ta` plus deferred MCP) | `ta` over the socket, and the resident block cut. | **Exactly four tools.** The deferred-MCP route for the agent is dropped, and `ta search` / `describe` is the single discovery layer (D6). |
| **First version S6:** self-improvement and versioning | All of it. | Memory items get stable ids and the Memory tab (D7). Rules are excluded from what the agent can write. |
| **First version S7:** outward actions through standing grants | The effectors and the standing-grant checks. | **Replaced** by Custom Rules, auto-review and reserved actions (D1). |
| **First version S8:** every universe gets the harness | The starter template and deleting the old surface. | Onboarding and the profile join it (D4, D10). |
| Spec requirement "inside acts without asking; outside asks once" | Its default effect, reproduced by the seed rules. | **Replaced** by the Custom Rules, auto-review and reserved-actions requirements. |

## 6. Slices

Each slice is its own PR, proven live in the founder's app before the next one
lands, with at most 12 tasks. A slice that adds a storage shape opens its own
storage proposal first. D1 is authority, and its proposal, design and spec
deltas are this change (§4.7–4.9, spec delta). Order: substrate first, then the
dot's felt pieces.

**S2: Owner steering** (unchanged from the first version)
1. Queue owner messages per session.
2. Append them to the next tool result with the unread count.
3. Write the idle-session opening line.
4. Add activity status lines.
5. Live proof: a mid-turn steer.

**S3 remainder: Toolchain and the writable root** (S3a and S3c are in flight)
1. Add python, node, git and ripgrep to the jail image.
2. Land the S3c migration.
3. Make the root writable for migrated universes.
4. Write a jail-proof test per refused address class.
5. Live proof: pip install, pytest and git clone.

**S4: Journal and spill** (unchanged)
1. Journal native tool events.
2. Add the HTTP-loop session log and compaction.
3. Spill oversized output to a file.
4. Report one-line causes.
5. Show live tool activity.
6. Live proof: an oversized `read_graph` read in full.

**D1: Custom Rules, auto-review, reserved actions**
1. Define the action classes and the matcher.
2. Add the owner-only rules store under `.runtime/`, registered with S3c.
3. Add `rules.decide` at the tool layer, `ta`, the effectors, the egress proxy
   and `browse`.
4. Seed rules from the template, with honoured standing grants.
5. Raise `ask_first` and `hand_off` as app requests with the activity status.
6. Make "always allow" write a `do` rule.
7. Write the auto-review call on the universe's own model, failing closed.
8. Enforce the reserved classes in code.
9. Make the agent's rule edits refused and proposal-only.
10. Build the Rules tab.
11. Change the S1 `AGENTS.md` authority text to describe the rules.
12. Live proof: approve once, then reuse, plus a reserved action refused with
    take-over offered.

**D2: Activities** (storage proposal first)
1. Write the activity storage proposal.
2. Add activity records under `.runtime/`.
3. Add `ta activity start/list/stop`.
4. Make activities child sessions keyed `activity:<id>`.
5. Have them take seats and wait visibly.
6. Make scheduled activities automation targets.
7. Report status lines into the main thread.
8. Keep partial results on stop.
9. Build the Activity tab with *Waiting on you*, *In progress*, *Scheduled*
   and *Completed*.
10. Add Pause and Resume per agent.
11. Live proof: two activities in parallel after the chat is closed.

**D3: Proactive research**
1. Write the idle and cadence scheduler from `settings.yaml`.
2. Run the read-only tool profile: refuse write and edit, mount bash read-only,
   bind no egress socket.
3. Add a read-only capability on the `ta` socket.
4. Gate effector calls to reads only.
5. Make `browse` absent.
6. Add the `proposal` request kind.
7. Make an approved proposal start a pre-approved activity.
8. Send nothing when there is nothing to propose.
9. Show the usage share on the profile.
10. Write a jail test that each write path is refused in research.
11. Live proof: a real proposal from a connected source.

**D4: Onboarding, profile and push**
1. Write the template onboarding questions.
2. Write name and responsibility into the files.
3. Propose the approval items as rules.
4. Create the report cadence as a scheduled activity.
5. Show the no-compute notice.
6. Build the profile page header and tabs shell.
7. Add push kinds for completed, waiting and proposal.
8. Live proof: a fresh account onboarded end to end.

**D5: The computer**
1. Run the browser sandbox separate from the tool jail.
2. Add the `browse` CLI over a socket.
3. Keep the profile in `.runtime/browser/`, unmounted from the jail.
4. Stream the CDP screencast to the Computer tab.
5. Add Take over / Return control with input forwarding.
6. Write the `owner returned control` line.
7. Keep take-over input out of the session log.
8. Show the bash tail.
9. Live proof: the owner logs in during take-over and the agent continues.

**D6: Exactly four tools**
1. Add `ta search` and `ta describe` across platform verbs, connections,
   extensions and attached MCP servers.
2. Cut the resident block to four schemas plus the `ta` line.
3. Disable native built-ins on every adapter.
4. Drop the deferred-MCP plan for the agent.
5. Move handbook chapters to skills.
6. Lower the token ratchet.
7. Live proof: tokens per round before and after, with every capability still
   reachable.

**D7: Memory and harness editing**
1. Give memory items stable ids.
2. Build the Memory tab with edit and delete.
3. Add the jailed history store and Undo.
4. Add `settings.yaml`.
5. Build the Harness tab.
6. Add seed curator and review skills.
7. Delete `read_brain`, `write_brain`, `soul_edit` and the learning call.
8. Live proof: delete one memory item, and Undo an `AGENTS.md` change.

**D8: Roster and command center**
1. Add the `agents/<id>/` layout and its override rules.
2. Add create, rename and remove agent.
3. Make `ta activity start --agent`.
4. Give each agent its own rules, sessions and profile.
5. Build the roster view with inline approve and pause.
6. Build both pages on the custom-UI layer.
7. Live proof: a lead dot hands work to a specialist.

**D9: Sharing**
1. Export through the custom-agents definition shape.
2. Write the scrub pass with an owner-confirmed preview.
3. Exclude memory, sessions, credentials and browser state.
4. Include layouts.
5. Import into an inert `imports/<id>/`.
6. Allow activation only as written or stricter.
7. Wrap imported text in the untrusted envelope.
8. Live proof: a second account imports and activates the founder's bundle.

**D10: Everywhere, and delete the old surface**
1. Seed every new universe from the published starter template.
2. Add starter channel extensions for Slack and Telegram.
3. Delete the replaced handles and resident guidance.
4. Run `ui-test` on a fresh account.
5. Run the canary with `--assert-handles`.

D1, D2 and D4 are the felt dot: rules, parallel work and a profile. D3 is the
proactivity. D5 completes "its own computer". D6 is the pi surface. D8 and D9
deliver "any configuration" and sharing.

## 7. Open questions for the founder

1. **Reserved actions.** Dots always hands back password and credential
   changes, moving money, and granting others access. Here these would be
   fixed in code, even though the only platform invariant is cross-user
   isolation. *Recommendation:* fix them, as dots does. The agent can still
   prepare everything, and the owner finishes the step in take-over.
2. **Auto-review off switch.** Dots does not allow one, and you asked for full
   customization. *Recommendation:* on by default for every action outside the
   universe, and the owner may turn it off per class, except the reserved
   classes.
3. **Proactive research default.** It spends the user's own compute. *Default
   proposed:* after 30 min idle, at most every 4 h, 08:00–22:00 in the owner's
   clock, and on new items from connected read sources. On for a new user and
   easy to set to `off`. On free models this cadence costs a few turns a day.
4. **Brain safety (carried over).** Rollback through file history, instead of
   refusing a write, remains the guard against a weak model blanking a file.

**Review record.**
- gpt-6-astra refute review of 04983ba2 (first version), 2026-10-01: ADAPT,
  folded in.
- The dots revision is reviewed below (see the PR comment).

## Appendix A: first-version detail that is kept

These sections are from the approved first version, renumbered. §4 overrides
them where the two differ. In particular:
- §4.7–4.9 replace the first version's authority section (3.5), which is
  omitted here.
- §4.6 replaces its tool table (3.4), which is omitted here.
- The "Platform: one extension … deferred MCP" route is dropped.

### A.2 Sessions (biggest felt change)

- **Unit.** A *session* is a durable, append-only log of messages, tool calls,
  tool results, compactions and events. It has an id and belongs to one
  universe. There is one agent and one session per conversation thread: the
  owner's main thread is one session across app, phone, desktop and connector.
  Agents the universe builds for itself (agent nodes in its graphs) are its own
  creations. The harness gives them the same primitive (an agent node may keep
  a session keyed by its node) so it can build good agents, but their behaviour
  is theirs, not the harness's.
- **Storage.** The session log lives under `.runtime/agent-sessions/`, which
  only the platform can write. The agent sees it read-only, through a
  read-only mount at `/u/sessions` in the tool jail, never as a writable root
  path (Codex review finding 6). So it can read and grep its own history but
  cannot forge it. It is the
  successor to `AgentTurnJournal` rows, which become keyed by session. Its
  bytes count to the account storage pool (`account-storage-quota`).
- **Model context** is the last compaction summary plus every entry after it.
  The platform assembles it mechanically:
  1. base prompt (≤600 tokens);
  2. `AGENTS.md`;
  3. `MEMORY.md` (the first 200 lines or 25 KB);
  4. the skill index;
  5. the session.

  There is no persona Python, no 7,000-character text block, and no
  re-description of files.
- **Compaction.** The defaults follow pi:
  - The trigger is `projected_tokens > window − reserve`, with a 16k reserve
    and the latest 20k kept verbatim.
  - The summary is structured (goal, decisions, files touched, open threads,
    pending requests, exact ids) and made by the session's own model. Tool
    call/result pairs are never split, as in OpenClaw.
  - Before compacting, one silent *flush* round lets the agent write what must
    survive to its files, as in OpenClaw's memory flush.
  - Thresholds live in `settings.yaml`, which the agent and user edit.
  - The flush and summary calls are made by the universe's own model, on its
    own credentials, through the same seat and accounting as any other turn.
    There is no platform fallback model (Hard Rule 15).
- **Native adapters.** An adapter MAY declare a `resume` capability with an
  opaque handle, which the platform stores on the session (a CLI session id,
  for example). With `resume`, the adapter continues its own native session and
  `--ephemeral` goes. An adapter that `self_compacts` compacts itself, and the
  platform records the event. Without `resume`, or after a model switch, the
  platform seeds a new native session from the summary plus the tail. The
  platform log stays the truth either way. No vendor name appears in this
  contract (Hard Rule 3). The existing adapters are migration debt that
  implements it.
- **The turn runs until done.** The founder's rule already holds in
  practice, though the code expresses "no cap" as a 30-day sentinel
  (`universe_intelligence.py:272`). The coordinator enforces that sentinel
  (`agent_turn_coordinator.py:416`), and it becomes a truly absent deadline.
  Real turns stop only on idle, Stop, run-owner proof, or a budget the user
  set (`turn-runs-until-finished-not-wall-clock`). A "turn" ends when the model
  stops calling tools.
- **Steering.** A message arriving mid-turn is queued. At the next tool
  boundary the platform appends the queued messages to that tool's result as a
  delimited "new messages from your founder" block, and adds the unread counter
  from #4170. This is OpenClaw's steering queue, expressed in a way any adapter
  can carry, because every adapter returns tool results. Stop and "send all
  queued" is #4152.

### A.3 Owner messages and events reach the live session

- A message the owner sends while a turn is running is steered into that turn
  at the next tool boundary, appended to that tool's result together with the
  unread count (#4170). The owner never waits for a long turn to end before
  being heard. Stop, then send everything queued, is #4152.
- Events that concern the owner's session reach it the same way when a turn is
  live, or as the opening line of the next turn when it is idle. Those events
  are a run it started finishing, a request it raised being answered, or an
  owner message from another surface. The line is short and mechanical, for
  example "since your last turn: run 7f3… completed (failed: …), request req_…
  answered". It is computed by the platform and never authored by an LLM.
- How any agent the universe builds wakes, loops or schedules itself is that
  agent's own design. The platform supplies the event and trigger primitives
  (`automation_events`, #4171) and adds no wake policy.

### A.6 Tone and the seed `AGENTS.md`

The persona Python is replaced by a short seed `AGENTS.md`. It belongs to the
user and is edited by the agent. Its core, about 300 tokens:

> I am {name}, my founder's agent, working in my universe at /u. I work like a
> senior engineer with my own computer. I do the work, check that it worked,
> and report in a few lines: what changed, where, how I verified it, and what
> is next if anything. Result first, no preamble, no apologies, no restating the
> question. I mention what I could not verify only when it changes what my
> founder should do. Inside my universe I act without asking. I ask, through one
> app request, only for credentials, reaching other people, or spending beyond
> my budget. When blocked I try another route, then move to other work. I keep
> MEMORY.md current, save a skill when I solve something new or get corrected,
> and edit this file when my founder tells me how to work.

Identity stays in `identity.md`: the persona name still comes from the
learned self-model, as the existing personification spec requires. Only the
platform-authored tone and behaviour text moves into `AGENTS.md`. `voice.md`
keeps working until S6 folds it in. The untrusted-envelope rule stays in
the base prompt, because it is a cross-user boundary.

### A.7 Feedback loop

- **Truthful, fast results.** A tool error returns the real cause in one line
  plus the remedy where one is known. There are no generic "unavailable"
  messages (`a-blanket-except-makes-one-message-for-every-cause`). Results over
  the model budget are written to `sessions/<id>/tool-output/<call>.txt` and
  returned as a head plus the path, never as a truncation marker with nothing
  behind it.
- **Every adapter journals every tool call** into the session log. For native
  adapters this comes from their streamed tool events, which the Codex adapter
  already parses (`codex_provider.py:397`). The app shows the turn's tool
  activity live. That is the "see it work" half of Claude Code.
- **Verify is a habit, not a gate.** The seed `AGENTS.md` asks the agent to
  check each effect by reading it back (run status, file diff, PR state). The
  platform adds no checklist (founder 2026-10-01: "No gates, review checklists or
  cooldowns").

### A.8 Self-improvement with versioning and rollback

- **Harness files.** These are user-owned and agent-editable:
  - `AGENTS.md`
  - `MEMORY.md` (index, always loaded, bounded)
  - `skills/`, `prompts/`, `extensions/`
  - `settings.yaml` (model preference, compaction thresholds, reserve,
    session defaults)
  - the brain files (OKF kept)
- **Versioning.** At turn end the platform snapshots the changed tracked paths
  into a history store under `.runtime/harness-history/`. The commit message
  carries the session and turn id. The store is a bare git repository that the
  agent cannot write or delete.
  - Git never runs on the host against agent-written content. The commit runs
    as a process inside a credential-free tool jail, with `/u` read-only and
    only the history store writable, and with hooks, filters, `core.*` and
    attributes all disabled.
  - An agent-written `.git/hooks` or a filter config therefore never executes
    outside the jail (Codex review finding 5; `workspace_git.py:3` forbids
    host git on user-controlled repos for this reason).
  - The agent may keep its own git repository in `/u` for its own use, which
    is separate from the history store.
  - Package caches are not tracked. Rollback
  uses `git` from bash, `ta harness rollback <rev>`, or an **Undo** in the app.
  This is the code-level guard against a weak model blanking a file (see open
  question 2): any loss is one revert away. A turn that empties or more than
  halves a loaded file (`AGENTS.md`, `MEMORY.md`, a brain file) gets an Undo
  notice in the app and a line in its next event message.
- **Learning loop.** The agent learns the way Hermes and OpenClaw do, by
  default and through files:
  - it saves a skill after novel multi-step success or a correction;
  - it patches a skill it used that was wrong;
  - it updates `MEMORY.md` at the pre-compaction flush.

  A curator (stale, then archived) and a nightly experience review ship as
  editable seed workflows, not platform code.
- **Deleted:** `read_brain`/`write_brain`, the separate learning-extraction call
  (`extract_learning`, `commit_learning`, `_LEARNING_SYSTEM`,
  `_UNRECORDED_LESSON`), the `soul.edit` whitelist and `soul_versions/` for
  owner turns. Git replaces versioning. The founder-only write boundary is
  enforced by the jail: a visitor turn has no write view.

### A.9 Map to existing primitives (reuse, do not rebuild)

| Need | Existing primitive |
|---|---|
| Session log | `AgentTurnJournal` / `agent_turn_rounds` / `agent_turn_tools`, rekeyed by session. `conversation_store` (custody, failure history) stays as the owner-door projection. |
| Turn loop and adapters | `agent_turn_coordinator.py`, `providers/call.make_interactive_agent_turn`, native adapters |
| Stop and queued messages | `turn_interrupt.py` (#4152) |
| Unread counter | #4170 |
| Event wakes | `automation_events.py`, `owner_message` (#4171), `pending_request_answered`, `app_event`, schedules, webhooks |
| Agent nodes (agents the universe builds) | `shared_self.py`, `served_tools.node_tool_grant` |
| Jail and tools | `universe_tools.py`, `providers/provider_jail.py`, `universe_files.py` |
| Skills | `universe_tools.skill_index` |
| Asks | `pending_requests` and the request rail with phone/desktop/browser notifications (#4140, #4138) |
| Credential-blind calls | `effectors/authenticated_external_call.py`, `connect_http`/`extend_http` grants |
| Concurrency and usage | `universe_seats` (#4154), account storage quota (#4158, #4166) |
| Platform verbs | `engine_mcp_server.py` handlers, re-exposed (not rewritten) as `ta` and as deferred MCP |

### A.10 Delete list (each lands in the slice that replaces it)

- `universe_intelligence.py`:
  - persona assembly `_build_persona_system_prompt` with its brain, ask and
    clock sections (the clock becomes one base-prompt line);
  - `_GROUNDING_IS_CURRENT`, `_CROSS_SURFACE_CONTINUITY`,
    `_turn_input_method_context`, `_UNRECORDED_LESSON`;
  - the learning path (`extract_learning`, `commit_learning`,
    `_learn_from_turn`, `_LEARNING_SYSTEM`, `_parse_learning_json`,
    `_brain_recording_tools`, `_wrote_its_brain`);
  - the WebFetch denylist tuples, once every adapter runs tools only in the
    platform jail.
- `conversation_memory.format_history` as model context (it stays only as an
  owner-door transcript renderer, if one is still needed).
- Codex `--ephemeral` and the empty-`/workspace` converse mode
  (`codex_provider.py:871-880`).
- Engine handles `read_brain`, `write_brain`, `connect_compute`, `source_channel`
  as resident tools (folded into `ta`). The resident handbook guidance moves
  to skills, and the 30,000-character ratchet in `test_converse_turn_cost.py`
  drops to the new budget.
- `soul_edit` governance and `soul_versions/` for owner turns, and the
  `voice.md` special case.
- The prompt text that teaches per-turn consent: the `conversation_memory.py:158`
  footer, and any similar handbook text. The effectors' standing-grant checks
  stay.
- The 362 `.worker_supervisor.*.json` files at the universe root move to
  `.runtime/`. Leftover epoch-1 supervisor files with no live owner are
  deleted.

### A.11 Risks

1. **Weak free models with full power.** Mistakes stay inside the universe and
   git reverts them. The founder's 09-26 rule (a code guard, not obedience)
   is answered by git rather than refusal. Measure per model family in each
   slice's live test.
2. **Egress safety and abuse** (Codex review finding 7).
   - The filter is enforced at packet level, inside the jail's own network
     namespace. It covers every protocol and both address families, and checks
     each translated destination (NAT64/DNS64, as `storage/outbound_connections.py:1649`
     already documents), not only the address the agent named.
   - The host's own services and other universes' engine ports are never
     routable.
   - Per-tenant connection-rate and bandwidth limits protect the shared IP and
     the box. These are host-protection floors, not usage quotas.
   - S3 cannot land without a jail-proof test for each refused class.
3. **Session logs hold sensitive tool output.** They are owner-only and never
   published. A commons publish refuses `sessions/` (old design §4).
4. **Two authorities.** `conversation_store` and the session log must not both
   be model context. The session log is the model's, and the store is the
   owner door's projection of it. Delete the old path in the same slice.
5. **Writable root before trusted readers move** (Codex review finding 6). If
   the agent could create a legacy `.effector_consents.db` at the root, the
   daemon would read forged grants from it.
   - S3 moves every trusted reader to `.runtime/` and removes each legacy
     root-path fallback before the root becomes writable, in one change.
   - Provider-launch and tool-jail views stay separate, and hidden-settings
     masking stays (`provider_jail.py:251`).
6. **Deploys kill live turns** (`deploy-kills-in-flight-turns`). A session
   survives, and the next event resumes it from the log, so a deploy loses at
   most one round, not the thread.
