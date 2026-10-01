# Design: a lean, self-improving agent harness for every universe

Status: proposed for founder approval (2026-10-01). This document is the design
and contains no code. Measurements were taken read-only on production on
2026-10-01, through `ssh workflow-droplet` → `docker exec tinyassets-daemon`,
against `/data/.tinyassets.db` and `/data/u-01kxm1vszd8hwp7em418asq8h9/`.

## 1. Research: the four reference harnesses (sources fetched 2026-10-01)

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

The founder's memory note says pi has "exactly four tools". Current pi still
defaults to those four, but it now ships `grep`/`find`/`ls` and built-in MCP
behind codemode and deferred exposure.

**Synthesis.**
- Every reference keeps the **session** as the unit of continuity and compacts
  it, rather than rebuilding context per message.
- All four use **Agent Skills** files the agent can write.
- None puts per-action consent inside the agent's own workspace. Containment or
  a classifier carries safety.
- The three that learn (OpenClaw, Hermes, Claude Code) let the agent edit its
  own instructions, and the stronger two version or rollback-capture what it
  writes.

## 2. Current-state audit: tiny's harness

### 2.1 Code paths (origin/main 2ffb29ae)

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
- **Background self.** Agent nodes (`shared_self.py`) run the same converse
  harness through `background_served_provider.py:815-852`. Each wake is
  likewise a fresh, ephemeral turn.

### 2.2 Production numbers (agent_turns, 2026-09-15 → 2026-10-01; 1,644 tiny turns)

Turns were classified by the actual message after the memory block. 1,393 are
background wakes ("I am tiny, continuing my background work …") and 251 are
founder chat.

| Measure | Chat (251) | Wake (1,393) |
|---|---|---|
| Median input tokens per turn | 61,862 (p90 510,368) | 126,055 (p90 200,891) |
| Total input tokens | 53.7M | **226.9M** |
| Median reply length | 637 chars | 363 chars |
| Replies containing an ask | 26% | 0% |
| Replies with blocked / can't / unavailable language | 54% | 65% |
| Replies with "I haven't verified / unverified / can't confirm" disclaimers | 29% (66) | 17% (231) |
| Replies claiming any effect (merged, posted, PR, sent …) | 33 (15%) | 50 (3.7%) |
| … of which not negated in the same reply | **7** | **2** |
| Input tokens per effect-claiming reply | 1.6M | **4.5M** |
| Turns ending indeterminate (`held_native_unknown`) or abandoned | 26 (10.4%) | 24 (1.7%) |

**The 2026-09-30 wake storm.** There were 1,294 wakes between 03:14Z and 23:59Z,
a median of **38 s apart**, totalling **186.6M input tokens**. 770 of the 1,280
replies said, in effect, "no new evidence / no product progress". Typical
examples:
- "I read my handoff and found no new signal … I left continuation under the
  host's control."
- "I checked my handoff to choose useful work, but repeated an already-failing
  inventory check; its output was truncated. I made no product progress."

The founder said it on 2026-10-01 05:35Z: "each wake it does nothing 3 wakes now
and soon to be 4 each time nothing done".

**Corrections.** 46 of 262 founder messages (18%) are corrections ("your still
not understanding the general shape", "it could have easily by now made the
village fully functional"), and 8 of the last 40 are. 13 universe replies open
with "You're right" or "Sorry".

**Asks.** 85 app requests were raised between 2026-08-28 and 2026-10-01. The
founder dismissed 15 and muted 8 more request kinds.

**What tiny itself says blocks it** (`notes/continuation.md`, 2026-10-01 05:43Z):
"Local FastMCP/pytest/Ruff/browser capabilities remain absent", and a
`read_graph` result "truncates before its result can be compacted". In chat it
said: "My background turn currently has a 15-minute maximum". That was its own
900 s interval trigger, which it believed was a limit.

**Workspace.** The universe root has 422 entries, 362 of them platform
`.worker_supervisor.*.json` files. tiny's real work lives in `notes/` (about
880 KB of scripts, JSON probes and plans), including a 4.4 KB
`prompts/background-operating.md` and an 18 KB `notes/goals-and-outcomes.md`
that it must re-read on every wake, because no session carries them.

**Tool observability.** `agent_turn_tools` holds 109 rows, all from the
HTTP-loop universe and **none for tiny's 1,644 native turns**. Nobody, including
the founder and tiny, can see after the fact which tools a turn called.

### 2.3 Top drag findings

1. **No session.** Every message and every wake rebuilds context from scratch
   and forgets its own tool work. Median wake: 126k input tokens. 2 of 1,369
   wakes delivered an un-negated effect.
2. **Empty-wake busy loop.** There were 1,294 wakes in one day, 38 s apart, and
   60% of them said nothing changed. Because there is no session, "continue the
   work" is expressed as "start a new run", and every run pays the rebuild.
3. **Guidance teaches asking and hedging.** 26% of chat replies ask, and 29%
   carry verification disclaimers. The persona prompt instructs warmth,
   curiosity, asking to clarify, and per-turn consent.
4. **Tools are walled where the work is.** There is no network in bash, no
   browser, and no toolchain, and `read_graph` results truncate. Those are the
   blockers tiny lists itself, and they became 85 requests.
5. **Heavy per-round context.** About 8k characters of persona, 7k of history
   text and about 28.5k of tool descriptions are re-sent each round. Tool calls
   are invisible for native turns, and 10.4% of chat turns end indeterminate.

## 3. Target design

### 3.1 Principle

The universe is the agent's computer. Inside it the agent behaves like Claude
Code in auto mode: it works until the job is done, verifies, reports briefly,
and remembers. The platform supplies a few things:
- a session that persists and compacts;
- a jail that makes full power safe;
- credential-blind access to connections;
- durable events.

Everything else, including tone, habits, wake strategy, skills and goals, is a
file the user and agent own and edit. This is PLAN.md Scoping Rule 1 taken
seriously, and the cross-user floor (`the-floor-is-cross-user-only`) is the
only fixed boundary.

### 3.2 Sessions (biggest felt change)

- **Unit.** A *session* is a durable, append-only log of messages, tool calls,
  tool results, compactions and events. It has an id and belongs to one
  universe. There is one per conversation thread: the founder's main thread is
  one session across app, phone, desktop and connector. There is also one per
  agent node, keyed by `(branch_def_id, node_id)`. The background self is an
  agent node, so it has its own session. It shares the same files (brain,
  `MEMORY.md`, notes) with chat, but not the same context window. That is how
  Claude Code sessions in one project share CLAUDE.md and memory.
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

### 3.3 Wakes are events into an existing session

- A wake is an event appended to a session:
  - a message;
  - `run_completed`;
  - `pending_request_answered`;
  - `app_event`;
  - `owner_message` (#4171);
  - a schedule firing (a schedule is just a timed event);
  - a webhook.
- If the session is idle, the event starts a turn. If a turn is live, the event
  is steered in, as for messages.
- The event message is mechanical and short, for example "since your last
  turn: 2 new messages, run 7f3… completed (failed: …), request req_… answered".
  It is computed by the platform and never authored by an LLM.
- Continuing to work no longer means "schedule another run". The session is
  still there, and the turn simply keeps going. A self-retriggering loop keeps
  working (it is user-built), but each wake now costs only the event plus the
  delta, not a 126k-token rebuild.
- The platform adds no wake policy. How often to wake, and whether to run a
  goal judge (Hermes `/goal`), are seed-harness defaults in `AGENTS.md` and a
  seed workflow, which the user can edit (`enabling-primitives-not-prebuilt-complexity`).

### 3.4 Tools

| Layer | What | Source |
|---|---|---|
| Core | `read`, `write`, `edit`, `bash` in the jail at `/u`. `grep`/`find`/`ls` are reached through bash. | pi defaults. They exist today (`universe_tools.py`). |
| Workspace | The whole user root is writable. Platform-owned state (vault, consent, usage and receipt DBs, `.worker_supervisor.*`, run DBs) moves under `.runtime/`, which is masked. `soul.md` authority and `config.yaml` become user files or move to `.runtime/` by owner. | The pending #3972 follow-up (storage proposal in that slice). |
| Network | Bash gets **public egress** through a filtered network namespace that refuses loopback, RFC 1918, link-local and metadata addresses. `pip`/`npm`/`git clone`/`curl` work into `/u`. | Old design S3. Floor-safe: nothing cross-user is reachable. |
| Toolchain | Python 3, node, git, ripgrep, a headless Chromium with a `browse` CLI (Playwright) in the jail image. Packages install into `/u`, counted to the user's storage. | OpenClaw `browser`, Hermes browser tools. |
| Web | `web_fetch` and `web_search` are skills over bash plus egress. A search API needing a key uses the user's connection through `ta connect call`. | Vendor-neutral, no platform key. |
| Skills | `skills/<name>/SKILL.md`, Agent Skills spec. The index sits in the prompt and the body is read on demand. Skills import directly from the pi, Claude Code, Hermes and OpenClaw ecosystems and from the commons. | Exists (`skill_index`). |
| Extensions | `extensions/<name>/extension.yaml` declares `bin/` commands and hooks (`turn_start`, `tool_result`, `turn_end`, `pre_compact`). Hooks run as jailed processes that take JSON on stdin and whose stdout may add context. | Old design §3. pi and Claude Code hooks. |
| Platform | **One extension.** The existing engine handlers (graphs, runs, automations, requests, commons, connections) are reachable as the `ta` CLI in the jail over a per-universe socket, with `ta --help` for progressive disclosure, and as **deferred** MCP tools for adapters that load schemas on demand. The resident tool block shrinks from about 28.5k characters to the core four plus one line naming `ta`. The handbook chapters become skills. | pi codemode and deferred exposure, OpenClaw `tool_search`. Same handlers, no new handle. |
| Subagents | `ta session spawn <prompt>` starts a child session with its own context in the same universe and returns its result. Long parallel work is an agent node (`run_graph`). | Claude Code subagents, Hermes `delegate_task`. Composed from agent nodes. |

### 3.5 Authority: broad inside, ask outside

The **default grant** of a primary agent in its own universe is everything
inside it, with no ask:
- read, write and delete its files (git makes this reversible);
- shell, egress and the browser;
- create, edit, run and schedule its workflows and agents;
- edit its own harness and brain;
- use every connection already granted, within that grant's scope;
- spend its own seats and compute.

Users may narrow any agent (`node_tool_grant`, `agent-access-controls`).
Narrowing is opt-in and never per surface (`primary-agent-has-all-powers-by-default`).

**The agent asks** only for:
1. a credential it does not hold, or a wider scope on one it holds;
2. acting toward other people or other people's property where no standing
   grant covers the destination (posting, messaging, emailing, opening a PR on a
   repo it was not granted, publishing to the commons);
3. spending money beyond a budget the user set.

An ask is an app request (`write_graph target=pending_request`, later
`ta connect ask`). It batches the job's needs into one request and never
appears as prose in chat.

**An approval is a standing grant** on that destination or scope, revocable in
the app. It is not consent for one action. The effectors already work this way:
`_check_consent` (`effectors/authenticated_external_call.py:643`) checks a
standing grant by destination, sink and revocation, with no turn identity
(`storage/effector_consents.py:250`), and those guards stay as they are. What
is wrong is the guidance. The conversation-memory footer still tells the model
that "a costly action still needs consent recorded THIS turn"
(`conversation_memory.py:158`), so it asks again for things it already holds.
That line and similar prompt text are deleted (Codex review finding 3).

**Unchanged floor:** other users' data, the host, credential blindness (the
vault and the credential-blind proxy), per-tenant quota, and jail resource
limits.

### 3.6 Tone and the seed `AGENTS.md`

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

### 3.7 Feedback loop

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

### 3.8 Self-improvement with versioning and rollback

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

### 3.9 Map to existing primitives (reuse, do not rebuild)

| Need | Existing primitive |
|---|---|
| Session log | `AgentTurnJournal` / `agent_turn_rounds` / `agent_turn_tools`, rekeyed by session. `conversation_store` (custody, failure history) stays as the owner-door projection. |
| Turn loop and adapters | `agent_turn_coordinator.py`, `providers/call.make_interactive_agent_turn`, native adapters |
| Stop and queued messages | `turn_interrupt.py` (#4152) |
| Unread counter | #4170 |
| Event wakes | `automation_events.py`, `owner_message` (#4171), `pending_request_answered`, `app_event`, schedules, webhooks |
| Agent nodes / background self | `shared_self.py`, `served_tools.node_tool_grant` |
| Jail and tools | `universe_tools.py`, `providers/provider_jail.py`, `universe_files.py` |
| Skills | `universe_tools.skill_index` |
| Asks | `pending_requests` and the request rail with phone/desktop/browser notifications (#4140, #4138) |
| Credential-blind calls | `effectors/authenticated_external_call.py`, `connect_http`/`extend_http` grants |
| Concurrency and usage | `universe_seats` (#4154), account storage quota (#4158, #4166) |
| Platform verbs | `engine_mcp_server.py` handlers, re-exposed (not rewritten) as `ta` and as deferred MCP |

### 3.10 Delete list (each lands in the slice that replaces it)

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

### 3.11 Risks

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

## 4. Slices (each independently shippable and proven live in the founder's app)

1. **S1: Sessions, tone, authority.**
   - Build:
     - Every resume-capable adapter continues its native session, keyed by
       thread or agent node. The native session state, which includes the
       adapter's own tool calls and results, persists under `.runtime/`
       instead of tmpfs, and `--ephemeral` goes.
     - A resumed turn sends only the new message, plus any messages from
       other surfaces the session has not seen.
     - An editable `AGENTS.md`, seeded on first use and writable in the tool
       jail, carries tone and authority. The persona's warmth, curiosity,
       ask-to-clarify and per-turn-consent text goes.
     - Native adapters compact themselves. Platform compaction for the HTTP
       loop and `settings.yaml` land with S4 and S6.
   - Founder sees: tiny remembers what it did and saw three messages ago,
     replies in a few lines result-first, and acts without asking inside its
     universe.
   - Proof: a multi-message thread with tool work, plus the before/after ask
     rate, disclaimer rate and tokens per turn.
2. **S2: Wakes are events into the session, with steering.**
   - Build: agent-node sessions are resumed by events (#4171), steering at tool
     boundaries, the unread counter (#4170), and mechanical "since your last
     turn" messages.
   - Founder sees: a message sent while the background self works changes what
     it does within one tool call.
   - Hypothesis to measure: wakes and tokens per day fall. A self-retriggering
     loop is the user's own design, so the platform makes each wake cheap and
     informative but does not cap wakes (Codex review finding 9).
   - Proof: measured wakes and tokens per day before and after, plus one live
     mid-run steer.
3. **S3: Network, browser, toolchain, writable root.**
   - Build:
     - Packet-level filtered egress for both address families (risk 2).
     - Chromium with a `browse` CLI, and python/node/git in the jail.
     - The `.runtime/` move: trusted readers first, then the writable root, in
       one change with its own storage proposal (risk 5).
     - A MODIFIED delta of the `universe-harness` jail requirement, once
       `universe-harness-four-tools` has synced.
   - Founder sees: tiny can `pip install`, run pytest, clone a repo, read a web
     page and drive a site.
   - Proof: a live task that needs all four, plus a jail-proof refusal for
     every blocked address class.
4. **S4: Truthful tools, full journal, platform session log.**
   - Build:
     - Native tool events journaled.
     - A platform session log with compaction for the HTTP loop, run on the
       universe's own model.
     - Oversized output spilled to a file.
     - One-line real causes.
     - Live tool activity in the app.
   - Founder sees: every tool call tiny made, live and afterwards. No
     "truncated" dead ends.
   - Proof: a `read_graph` larger than the budget is read in full from its file
     path.
5. **S5: The platform is one extension.**
   - Build: `ta` CLI over the per-universe socket and deferred MCP. The resident
     block shrinks to the four core tools, and handbook chapters become skills.
   - Founder sees: faster turns.
   - Proof: input tokens per round before and after, and every engine
     capability still reachable.
6. **S6: Self-improvement with versioning.**
   - Build:
     - A jailed history store with Undo in the app.
     - `MEMORY.md` and `settings.yaml`.
     - The skill-save habit, and seed curator and review workflows the
       universe can edit.
     - Delete `read_brain`/`write_brain`/`soul_edit` and the separate
       learning call for owner turns.
   - Founder sees: tiny writes skills from its own work, and a bad self-edit is
     one tap to undo.
   - Proof: tiny saves a skill and reuses it in a new session, and an Undo
     restores `AGENTS.md`.
7. **S7: Outward actions without friction.**
   - Build:
     - `ta connect` (`call`, `ask`) on the existing credential-blind effectors
       and standing destination grants, whose checks stay unchanged.
     - Batched asks in the request rail.
     - Removal of any remaining guidance that implies per-action consent.
   - Founder sees: one approval, then it keeps posting and opening PRs to that
     destination without asking again.
   - Proof: a granted repo PR from a background wake with the founder signed out.
8. **S8: Every universe gets the harness. Delete the old surface.**
   - Build:
     - New universes are seeded from an explicitly published, reviewed
       starter template, never the founder's live private subtree (Codex
       review finding 8).
     - The replaced engine handles and resident guidance are removed.
   - Founder sees: a second account's agent behaves the same way.
   - Proof: `ui-test` on a fresh account and the public canary with
     `--assert-handles`.

S1 and S2 are where the felt drag is. S3 removes tiny's own listed blockers.
S5 and S8 are the efficiency payoff.

**Review record.** gpt-6-astra refute review of 04983ba2, 2026-10-01: ADAPT.
Findings 2–10 are folded in above. The production numbers in §2 are
measurements and were not re-run by the reviewer.

## 5. Open questions for the founder

1. **One session or two for chat and the background self?** The recommendation
   is two sessions sharing the same files: chat stays responsive while the
   background works, and each window holds only its own work. That is how Claude
   Code sessions share CLAUDE.md and memory. The alternative is one session that
   chat interrupts, as OpenClaw's main session does.
2. **Brain safety: git rollback instead of a write refusal.** On 2026-09-26 you
   asked for a code-level guard, not obedience, against a weak model blanking a
   brain file. This design makes the guard "every change is a git commit, a big
   shrink shows an Undo" instead of refusing the write. Is that acceptable?
