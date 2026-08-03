# Agent-Teams-on-Workflow — Research + Thinking Notes

**Date:** 2026-04-20
**Author:** navigator
**Status:** Strategic research note. Not a dispatch. Inbox entry: `ideas/INBOX.md` [2026-04-20] "Agent-teams-on-Workflow." Pre-reading for future triage when uptime-track closes.
**Lens:** 3-layer. Does this make the user's chatbot better at serving the user's real goals? The user's "real goal" here is: compose multi-agent workflows for themselves, on Claude.ai, WITHOUT installing anything beyond the MCP connector. We provide the primitives; user authors the team.

---

## 1. The two load-bearing URLs

**1.1 Claude Code Agent Teams doc** — `https://code.claude.com/docs/en/agent-teams`

This is the **team primitive we want to echo**. Not the harness. The *team-over-harness* layer. Load-bearing design shapes from the doc:

- **One lead + N teammates, each a full Claude Code session** with its own context window.
- **Shared task list** (file-based at `~/.claude/tasks/{team-name}/`) with pending / in-progress / completed states + dependency edges. Teammates claim tasks with file locking.
- **Direct teammate-to-teammate messaging** via mailbox (`SendMessage` + broadcast). Not lead-routed; peer-to-peer.
- **Subagent-definition reuse:** a teammate role can reference a `subagent` definition by name → the teammate loads that definition's `tools` allowlist + model + body-as-system-prompt.
- **Plan-approval gate:** a teammate can be required to produce a plan in read-only mode; lead approves/rejects; on reject, teammate revises + resubmits.
- **Hooks as quality gates:** `TeammateIdle` / `TaskCreated` / `TaskCompleted` hooks fire at lifecycle events and can reject with feedback.
- **Each teammate loads its own CLAUDE.md + MCP servers + skills** from its working directory. Leader's conversation history does NOT carry.
- **In-process vs split-pane display modes.** `tmux`-backed split panes require local install; in-process is the always-works fallback.

**Limitations the doc flags (relevant to our design):**
- No session resumption for in-process teammates.
- One team per lead session; no nested teams; lead is fixed for session lifetime.
- Split-pane mode requires local tmux/iTerm2 — doesn't work in VS Code integrated terminal, Windows Terminal, or Ghostty.

**1.2 The OSS Python rewrite** — the "opensource python code one on github" host named.

Two candidate repos emerged from the March 31, 2026 Claude Code npm `.npmignore`-miss leak (~512K LoC of unobfuscated TypeScript):

| Repo | Author | Language | Shape | Why relevant |
|---|---|---|---|---|
| **claw-code** (`github.com/instructkr/claw-code`) | Sigrid Jin (@instructkr) | Python v1 → now Rust-primary 96.4% | Single-session harness; 40+ tools; subagent spawn; worktree isolation | Record-holder repo (100K stars in ~hours). Originally Python, rewritten to Rust for perf. The "fastest-growing repo in GitHub history" the user referenced. |
| **nano-claude-code** (`github.com/SafeRL-Lab/nano-claude-code`) | SafeRL-Lab | Pure Python, ~40K LoC, ~85 files | Typed-event-generator loop, pluggable LLM providers (8+), runtime tool registration, multi-agent orchestration via `Agent` tool, memory persistence, background-daemon bridges | More Python-idiomatic + more readable architecture study. Better "source to work from" candidate than claw-code's now-Rust codebase. |

**Recommendation: treat `nano-claude-code` as the primary architecture reference for user-built Workflow-on-top projects.** Reasons:
- **Python alignment with our Workflow engine.** Our daemon is Python; interop is native. Claw-code's Rust majority requires FFI or IPC — more moving parts for user projects.
- **Read-ability + hackability.** ~40K LoC / ~85 files vs. Claude Code's opaque TS (~283K LoC). Users can understand + modify.
- **Explicit architectural seams** (see below §3) that map cleanly onto Workflow's daemon-request + node primitives.
- **Runtime tool registration + MCP auto-wiring.** Our tools are MCP verbs; slots in with zero glue.

Claw-code remains worth tracking as the cultural-moment repo, but nano-claude-code is the *technical* base. User's framing "use it as a base to build something like Claude Code agent teams" → we document nano-claude-code as the anchor; user can swap if they prefer claw-code's runtime when they start building.

---

## 2. The user story, precisely

Reading host's message through the 3-layer lens:

**User:** wants agent-teams-style multi-agent workflows on Claude.ai (tier-1 chatbot path). Not a developer running Claude Code locally — a chatbot user composing teammates through the connector.

**Chatbot:** needs primitives to (a) spawn teammates as workflow nodes, (b) distribute work across teammates, (c) collect teammate messages back, (d) coordinate via a shared task surface.

**System (us):** provides the primitives. Specifically:
- Teammates = **nodes in a branch**. One branch per team. Each teammate = one node in that branch with a soul-file.
- Teammate spawn = **daemon-request** against that teammate-node. Existing Track D host_pool + Track E paid-market primitives already cover this transaction shape.
- Shared task list = **workflow state** on the team branch. Task-claim = standard branch-write.
- Inter-teammate messaging = **additional daemon-request with `target_teammate_id`** field, OR a free-queue fan-out via the paid-market bid surface.
- Lead's orchestration role = **the user's chatbot itself.** Not a daemon; the chatbot IS the lead.

The last bullet is the load-bearing insight. **Lead = the chatbot.** Teammates = daemon-executed nodes on branches. This maps cleanly onto existing Workflow primitives; no new orchestration layer is needed.

**Critical observation:** Claude Code's agent-teams is "one lead session + N teammate sessions all running in the user's terminal." Ours is "one chatbot + N teammate-node daemon-invocations." Same abstract shape; different execution surface. The user's chatbot composes the team over MCP; each teammate-invocation is a node-execution daemon-request; the task list lives in branch state the chatbot reads/writes via existing verbs.

**This means we probably don't need a new MCP verb set for teammate orchestration.** We compose from existing primitives — a user at Claude.ai says "spawn a researcher teammate on branch `team-alpha`," chatbot calls `submit_request` against a researcher-typed node on that branch. Open question for triage-time: does the chatbot need a `list_teammates(branch)` shortcut verb for readable UX, or does `list_pending_requests(branch=...)` suffice? Likely shortcut for UX, but it's feature-layer not foundation-layer.

---

## 3. Architectural seams to watch — borrowed from nano-claude-code + Agent Teams doc

These are the places where user's project-on-top and our platform meet. Each is a potential contract to design carefully at triage-time.

| Seam | Claude-Code/nano shape | Workflow primitive we offer | Gap check |
|---|---|---|---|
| **Agent loop** | Typed event generator (`TextChunk` / `ToolStart` / `ToolEnd` / `TurnDone`) | MCP streamable-http responses; chatbot IS the loop | None — chatbot does the loop. |
| **Subagent/teammate spawn** | `Agent` tool with isolated worktree | `submit_request` against a teammate-typed node; branch = worktree analog | None — primitive exists post-Track-E. |
| **Shared task list** | File-based (`~/.claude/tasks/`) with file locking | Branch state + existing write verbs | Maybe need a typed `team_tasks` node-type for convention, but not required. |
| **Inter-teammate messaging** | Direct `SendMessage` via mailbox, peer-to-peer | Not yet natively supported. Options: (a) free-queue fan-out via paid-market; (b) a `teammate_message` node-type that any teammate can write + any teammate can poll. | **GAP.** Worth a design note at triage-time. |
| **Plan-approval gate** | Teammate in read-only plan mode; lead approves/rejects | Not yet natively supported. Maps to "dry-inspect-node" from Devin Session 2 §4 — already a self-auditing-tools follow-up. Could unify. | Partial coverage. Unify with self-auditing-tools pattern at triage. |
| **Subagent-definition reuse** | Named subagent type → tools/model/prompt loaded | Teammate node-type could encode tools/model/prompt. Maps to node-type taxonomy per `project_node_software_capabilities.md`. | Partial — need confirmation that node-type taxonomy can encode LLM choice + soul-file + tool-allowlist as a reusable bundle. |
| **Hooks (TeammateIdle / TaskCreated / TaskCompleted)** | Lifecycle event hooks with reject/feedback capability | Maps to existing verifier + evaluator layer per `project_evaluation_layers_unifying_frame.md`. | None — unify evaluator primitive with teammate-lifecycle hooks when project lands. |
| **Tool registration** | nano-claude-code: `register_tool(ToolDef(...))` at runtime, MCP auto-wired | Our tools ARE MCP verbs; user's teammates can discover + call any verb we expose | None — best-in-class alignment already. |
| **Memory backend** | nano-claude-code: dual-scope (user/project) JSON, recency-weighted | Our memory-scope is tiered (node/branch/goal/user/universe) per `project_memory_scope_mental_model.md`. Different shape, compatible goals. | Need a memory-scope-to-teammate-scope mapping at triage; likely additive. |
| **Background daemons + bridges** | nano-claude-code: Telegram/WeChat/Slack bridges; remote-control job queues | Our daemon-economy IS this; paid-market + free-queue IS the job queue | None. |
| **Worktree isolation** | Git worktree per teammate | Workflow branch per teammate | Map is clean. |

**Summary: out of 11 seams, only 2 are clear gaps** (inter-teammate messaging; partially, plan-approval). Everything else is native-or-adjacent to existing Workflow primitives. This is the strong form of the thesis: **the agent-teams shape is already 80% composable from our primitive set once daemon-economy Wave 2+3 lands.**

---

## 4. What to build for the user (when triage lands)

Ranked by load-bearing:

### 4.1 Foundation (required before user can compose agent-teams on Workflow)

- **Daemon-economy Wave 2+3** — claim + settle + tray UX. Without these, teammate invocation isn't end-to-end.
- **Inter-teammate messaging primitive.** Per §3 gap. Recommend a typed `teammate_message` node-type + a poll/subscribe verb on the MCP side. ~2-3 dev-days for spec + ship.
- **Node-type taxonomy supports teammate bundles.** Confirm at triage: can a node-type declaration encode (LLM model, tool-allowlist, soul-file, default prompt template)? If not, extend. ~1-2 dev-days depending on current shape.

### 4.2 UX primitives (improve the chatbot's orchestration ergonomics)

- **`list_teammates(branch)` convenience verb** — readable UX on top of `list_pending_requests`. ~0.25 dev-day.
- **`spawn_teammate(branch, role, ...)`** — sugar wrapper over `submit_request` against a teammate-typed node. Naming alignment with Claude Code's Agent Teams doc helps user recognition. ~0.5 dev-day.
- **Plan-approval hook on submit_request** — optional `require_plan=True` flag; teammate outputs a plan; user's chatbot (as lead) approves via a second verb. Maps to self-auditing-tools `dry_inspect_node` pattern. ~1-2 dev-days; pairs with self-auditing-tools exec plan.

### 4.3 Convergent-commons (makes teammate-definitions viral)

Per `project_convergent_design_commons.md`: teammate definitions (role + tools + prompt) are exactly the kind of artifact that wants wiki-shared + forkable + autoresearch-optimizable. Hook teammate-node-types into the convergent-commons discovery surface. User defines a "senior-reviewer teammate" once; everyone else can fork it.

This is the **feature that makes Workflow-for-agent-teams compounding** rather than one-user-one-team. Without it, every user reinvents teammate-roles. With it, the commons carries the growth.

---

## 5. What we do NOT build

- **We do not build the agent-teams orchestrator.** That's the user's project. Our job is primitives.
- **We do not fork claw-code or nano-claude-code.** We document them as reference architectures so users can pattern-match.
- **We do not replicate Claude Code's Agent Teams UX on Claude.ai.** The chatbot IS the lead; the UX is chat. Users who want split-pane multi-window multi-teammate experiences can run Claude Code itself; users who want to compose teams via chatbot compose via our MCP verbs.
- **We do not build tmux integration or local-machine split-panes.** Out of scope for a zero-install platform.

---

## 6. Timing + dependencies

**Do not dispatch now.** Uptime-track + daemon-economy first-draft must land first. Triage this idea post-acceptance of §6 of `docs/exec-plans/active/2026-04-20-selfhost-uptime-migration.md`.

**Dependency chain:**

1. Self-host migration §6 acceptance (rows A-N complete + 48h offline trial green). [**Current focus.**]
2. Daemon-economy first-draft Waves 1-3 (Track A schema + Track D host_pool + Track E paid-market CRUD+claim+settle+tray). Wave 1 dispatch-ready today; Wave 2+3 ship post-uptime.
3. Self-auditing-tools exec plan (currently drafted at `docs/design-notes/2026-04-19-self-auditing-tools.md`) — ships `dry_inspect_node` which plan-approval would build on.
4. **Triage this idea** (promote from `ideas/INBOX.md` to `ideas/PIPELINE.md` + draft an exec plan for the 3 foundation items in §4.1).
5. **Dispatch the 3 foundation items** (inter-teammate messaging, node-type teammate bundles, possibly plan-approval hook).
6. **Announce to the user community** that Workflow now composes agent-teams. Pair with a reference tutorial using nano-claude-code as the recognizable base.

**Realistic timing:** 2-4 weeks post-uptime acceptance. The pieces are mostly already on the roadmap; this project reframes + sequences them around a concrete user story.

---

## 7. Viral-angle considerations (worth naming)

The user framed this as "could ride the OSS-Claude-Code wave." Worth taking seriously:

- **Claw-code hit 100K stars in hours because the audience exists and is urgent.** Users want Claude-Code-style orchestration without the cost / vendor-lock / local-install friction.
- **Workflow positions as the zero-install team orchestrator.** Claude.ai connector + our primitives = agent-teams via chat, no install, no terminal, no tmux. This is a real wedge.
- **The viral moment has a half-life.** If we triage this in 2-4 weeks the audience is still hot; in 6 months the moment has cooled and we're competing on features rather than novelty. Host + lead should calibrate.
- **Don't over-promise at platform level.** Platform provides primitives; user builds their team. If we say "we do Claude-Code agent-teams," we own the bug surface. If we say "Workflow primitives let you compose agent-teams, like this reference project does," we ride the wave without owning the UX debt.

**Recommendation:** frame any future public announcement as reference-project-driven, not feature-driven. "User X built a Claude-Code-style team on Workflow in N hours" is stronger than "Workflow has agent-teams." The former scales; the latter makes us the single support vendor.

---

## 8. What to ask host at triage-time (NOT now)

Placeholder questions — capture for when this surfaces to triage:

- Which repo should be named as the reference base: nano-claude-code (recommended) or claw-code? Host may have preference we don't see.
- Is inter-teammate messaging truly a gap, or should we defer? (Test: can a small reference-project demo 2-teammate message handoff without it? If yes, defer; if no, foundation.)
- Plan-approval hook: ship in this project, or unify with self-auditing-tools when that ships? (Leaning: unify.)
- Convergent-commons integration: day-one of this project or deferred? (Leaning: day-one if possible — that's what makes this compound.)
- Community announcement timing: shortly after self-host 48h trial closes, or wait for daemon-economy to prove out?

---

## 9. Sources

- [Claude Code Agent Teams documentation](https://code.claude.com/docs/en/agent-teams)
- [instructkr/claw-code (now Rust-primary)](https://github.com/instructkr/claw-code)
- [SafeRL-Lab/nano-claude-code (Python reference)](https://github.com/SafeRL-Lab/nano-claude-code)
- [Cybernews: Leaked Claude Code source spawns fastest growing repository in GitHub's history](https://cybernews.com/tech/claude-code-leak-spawns-fastest-github-repo/)
- [WaveSpeedAI Blog: What Is Claw Code?](https://wavespeed.ai/blog/posts/what-is-claw-code/)
- [36kr: Python Version of Claude Code After Major Overhaul](https://eu.36kr.com/en/p/3749018747699717)
- `ideas/INBOX.md` — the seed entry this note expands.
- `project_convergent_design_commons.md` — the compounding-angle memory.
- `project_daemon_default_behavior.md` — relevant to multi-spawn policy.
- `docs/design-notes/2026-04-19-self-auditing-tools.md` — the plan-approval unification candidate.
