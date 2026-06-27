# Claude Code Lead Operations

Situational guidance for the Claude Code lead. Not auto-loaded — read this
when running user-sim loops, managing the dev team, or optimizing token spend.
For core process rules, see AGENTS.md. For Claude Code basics, see CLAUDE.md.

---

### Foundation End-State vs Feature Iteration (refined 2026-04-19)

Host principle: **the rule depends on whether the work is foundation or feature.**

- **Foundation** = infrastructure everything else depends on. Multi-user support, storage schema, auth, daemon dispatch core, rename/naming commitments, module layout, MCP server core, basic paid-market routing. **Foundation always builds to the long-term best-known design in the present.** No phased rollouts, no compat-shim bandages, no "ship part 1 and iterate later" — ship the end-state. Refactor the foundation when a better implementation is discovered, but each foundation ship is itself end-state-shaped.
- **Features** = surfaces the chatbot/user interact with. Trust verbs, discovery polish, autoresearch refinements, evaluation criteria, specific bid-UX, shared-account primitives. **Features CAN roll out in phases.** We don't know in advance exactly how the chatbot will want to use each feature — iterate with real usage signal. Phased feature work is legitimate research.

The check before picking a shape: **is this load-bearing for other work?** If yes → foundation → end-state. If no → feature → iterate.

**Refactor foundation as better implementations are discovered.** New understanding in PLAN.md → foundation refactor → still end-state-shaped, not phased. Foundation doesn't carry debt; features do, temporarily.

Operationalization:
- **Rename / module layout / storage schema / auth / dispatch core** — foundation. End-state now.
- **Trust verbs / discovery UX / autoresearch specifics / bid-UX** — features. Iterate.
- **Ambiguous cases** — ask: "does the next thing I want to build depend on this being its final shape?" If yes → foundation. If no → feature.

Code is disposable. `PLAN.md` captures the living understanding. When understanding advances, update PLAN.md first, then refactor foundation to match.

Carve-out: atomic-commit discipline stands. "End-state" means each commit is atomic AND takes the code to its final shape, not that all related work is squashed into one commit.

Already-shipped phased work (72e696e Phase 1 Part 2, 7dde417 Phase 1 Part 2.5) stays landed — the rename is foundation but the already-landed phases can't be un-shipped. From here on: remaining rename work collapses to one end-state commit OR skip entirely with permanent aliases, per foundation-end-state rule.

### Daemon Economy is Foundation, Chatbot Experience is Always-On

Host principle (2026-04-19): **daemon economy first-draft before chatbot-experience refinement sweeps.** Both are needed, but the daemon economy is *foundationally* important — not a side feature. Chatbot experience work (self-auditing verbs, discovery polish, trust primitives) is standing high-priority throughout, but the daemon-economy first-draft is the thing to have shipped before big chatbot-UX investment.

Track prioritization when picking among available dev work: tracks that ship daemon-economy primitives (paid-market bids, settlements, node capability resolution, fulfillment routing, moderation-for-the-market) rank above chatbot-experience polish when there's a queue choice.

### Code Before Agents (token-efficiency standing rule)

Host principle (2026-04-19): **if an invariant can be enforced mechanically, build the hook — don't burn tokens checking it.** Every scheduled agent check-in for "is X still true?" is a place where a script-that-never-forgets would do better.

Invariant framework lives at `scripts/invariants/` with pre-commit hooks in `.git/hooks/pre-commit`. Shipped invariants: tab-single (3s poll), mirror-parity (pre-commit), mojibake (pre-commit), concerns-staleness (on-demand proposal).

When you notice an agent doing the same "recheck X, heal if drifted" pattern across multiple sessions, file a task to promote it to a hook. Zero tokens, never forgets, logs only when it had to heal.

**Invariant hooks must run their own invariants before commit** — including their own test suite, not just the test suite of the code they're protecting. The `#46 c880f94` regression shipped because the mojibake hook's own test coverage (`tests/test_pre_commit_mirror_parity.py`) was not the commit's gate; the hook protected downstream commits but didn't protect itself. 4 commits stacked on red main before verifier caught it. Always: any hook-adding commit has the hook's own tests as a blocker on merge.

### Standing Permission To Dispatch User-Sim

Host granted the lead CEO-level authority over user-sim dispatch (2026-04-19). Stop asking for per-mission approval. Run the auth hook instead:

```bash
python scripts/user_sim_auth_hook.py
```

Verdicts:
- `approved` (exit 0) — CDP up, exactly 1 tab, browser visible → dispatch now, no handshake.
- `heal-tabs` (exit 1) — run `python scripts/claude_chat.py tabs` (auto-heals), re-check hook.
- `no-browser` (exit 2) — host hasn't launched Chrome. Message host; do NOT try to launch on their behalf.

Treat user-sim as a standing team member for data-gathering, regression retests, and forward-looking exploration. If you have a question the team can answer by running it, run it. Don't queue questions for the host that user-sim can answer. Operate as if the host could be unreachable at any moment — the project keeps shipping.

### Recursive Learning From user-sim

When user-sim reports a finding, don't default to "create a task and queue it." Inspect the fix class first:

- **Cheap fixes** (prompt text, server instructions, tool descriptions, docstrings, server.json metadata, skill + agent-def text): dispatch IMMEDIATELY in the same turn. Host restart picks it up. Next test iteration reflects the learning. Compound.
- **Medium fixes** (small code changes, isolated handlers): hand to dev in the next message if dev has capacity.
- **Expensive fixes** (new subsystems, architectural change): create task, queue behind deps.

The default latency between "user-sim finds bug" and "fix is live" should be measured in minutes for cheap fixes, not sessions. Findings cluster — fixing one cheap thing often unblocks the next test iteration to find the next cheap thing. That's the recursion.

Screenshots: use `scripts/claude_chat.py` (failure dump path) or a Playwright one-liner via CDP for live browser inspection when trace text isn't enough to understand what the user sees.

### Name-Collision Awareness

When adding a constant, flag, or module, search the repo for the concept FIRST. dev-3 traced a real stuck-loop bug (#6) that was partially caused by `_MAX_REFLECTION_PASSES` in orient.py (a retrieval re-query bound) colliding with the concept "bounded reflection" from STATUS.md (a phase-level loop guardrail). Two different ideas sharing a name; nobody noticed a cross-phase guardrail was missing because the name suggested it already existed.

Rules:
- If a STATUS.md concern mentions a behavior by name, search code for that name before assuming it's implemented.
- Qualified names beat bare ones. `_MAX_RETRIEVAL_REFLECTION_PASSES` > `_MAX_REFLECTION_PASSES`.
- When two things share a concept, rename one before building the second.

### Tool-Use-Limit Hits Are Architectural Signal

When user-sim reports Claude.ai hit its per-turn tool-call budget (bot asked to "continue" mid-task), treat it as a design signal, not incidental noise.

Decision tree:

1. **One continue on a large multi-step build** — acceptable tax; log but don't act. This happens when a user asks for 15+ new nodes in one prompt.
2. **Two+ continues on the same intent** — the tool surface is too chatty. Investigate:
   - Is there a composite action that would collapse the call pattern? (e.g. `build_branch` collapsed ~15 atomic calls into 1 after Mission 4's first tool-limit hit.)
   - Is the bot re-fetching data it already has? (better `get_branch` return shape could pre-load what `list_branches` started.)
   - Would an automation/macro in the daemon remove the need for the bot to orchestrate? (e.g. worklfow runner auto-running validate_branch after build.)
3. **The same composite action consistently hits the limit** — composite isn't big enough. Either split its body further into the server (doing more work per call) or design a larger composite above it.

When this decision tree leads to a concrete fix, file it as a task immediately and dispatch. #43 (composite build_branch) was born exactly this way — a live Mission 4 tool-limit hit triggered the spec + build within the same session.

### Minimum Active-Dev Floor

**Hard rule: 2 devs always running, always busy.** This is not a soft target. The lead is responsible for keeping the floor filled.

This failed in past sessions because the lead dispatched the right-now task but did not pre-seed a rolling queue. Fix the system, not the reminder: keep 5-6 unblocked, file-bounded tasks per developer in `TaskList` whenever known work exists.

Backlog sources, in priority order:
- STATUS.md Work rows whose dependencies are satisfied.
- STATUS.md Approved specs marked `dev-dispatchable`.
- `docs/vetted-specs.md` sections for approved specs.
- STATUS.md Concerns that can be converted to file-bounded investigation or fix tasks.
- Navigator audits and user-sim findings.

When a dev goes idle:
- Pick the next non-colliding pending task and dispatch immediately.
- If TaskList is empty, seed it before doing anything else. Create tasks with Files, Depends, deliverable, and verifier handoff.
- Don't wait for user signal.
- Don't accept "board is thin" as an excuse — **that's what user-sim is for**.

If the board thins (no non-colliding pending work for the idle dev), the lead's responsibility is to generate more findings, not let devs idle:
- **Respawn user-sim on the next mission immediately.** user-sim's job is to produce findings that fill the board. Their test data IS the work source.
- Promote an investigation task (there's always a subsystem worth auditing — retrieval, memory, knowledge, evaluation layers).
- Ask the host for direction only as last resort.

Never have both claude-side devs idle at once. Never have even one dev idle when pending work exists. If you notice idle, you already failed — fix it the same turn.

### Continuous Live Shipping

Default operating mode while user-sim is in a test loop:

- **Merge on green.** When verifier clears a change (verdict: SHIP), it lands. Don't batch fixes for some "release point" — there isn't one.
- **Restart the TinyAssets MCP server when new code needs to go live.** Lead has authority (kill MCP process; tray auto-restart reliable ~2s). Don't wait for host.
- **user-sim absorbs disruption cheaply.** The UI isn't directly coupled; restarts drop the tunnel for a couple seconds, that's it. If a test fails across a restart, user-sim new-chats and resumes.
- **Findings -> cheap fix -> ship -> user-sim re-tests** is the loop. Minutes, not sessions.
- **Don't queue work if capacity exists.** Both devs idle = pending bug that matches either file area.

Exceptions to auto-merge:
- Destructive migrations (DB schema, on-disk format, config breaking changes) — confirm with host first.
- Anything touching auth, tunnel config, or the tray itself — confirm first.

### Token Efficiency of the User-Sim Loop

The loop is: user-sim ask -> finding -> lead fix -> ship -> restart -> user-sim ask again. Every segment burns tokens or claude.ai quota. Keep each tight.

- **Lead side:** Don't message user-sim between their turns unless the direction is truly new. Batch fix acknowledgments. Don't re-read the full session log on each update — `docview.py lines --start --end` for the tail only.
- **user-sim side:** Codified in the skill — 1-prompt = 1-question, terse log entries, stop-early triggers.
- **Dev side:** One PR per fix cluster (not per task). Verifier runs once per cluster.
- **Restart side:** One restart per cluster of landed changes, not one per task.

Red flag that the loop is bloating: user-sim uses >10 prompts before producing a MISSION FINDING, OR the session log grows by >50 lines between two pulses. If either happens, narrow the mission or stop.

### User-Sim Lifecycle

user-sim is event-driven, not always-up. Idle notifications burn tokens on both sides during long waits. Shut it down between missions; respawn fresh when the next mission is ready.

- Durable state lives in `output/user_sim_session.md` (mission log), `.claude/agent-memory/user/personas/` (persona memory), and `.agents/skills/ui-test/` (skill).
- Shut down when: a mission ends and the next is blocked on unrelated work; wait > 10 min; no active prompts.
- Respawn with a specific Mission brief — don't rely on in-memory continuity. The skill + log give a fresh instance everything.
- Core teammates (dev, dev-2, verifier, navigator) stay up across a session because they are continuously engaged; user-sim is not.
