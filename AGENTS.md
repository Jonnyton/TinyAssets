# TinyAssets

A goal-agnostic daemon engine. Bind it to a domain and let it run. The platform supports any multi-step AI workflow — research
papers, screenplays, recipe trackers, standup trackers, novels, news
summaries, any substantive long-running work.

---

## Forever Rule (2026-04-18): Complete-System 24/7 Uptime Is Top Priority

One unified priority, not a ranked list. Every surface of the system
works 24/7 with zero hosts online:

- Tier-1 chatbot users create / browse / collaborate on nodes via a
  real chatbot UI with the TinyAssets connector installed (Claude.ai,
  ChatGPT Developer Mode, or a future equivalent surface).
- Tier-3 OSS contributors `git clone` and run cleanly.
- Tier-2 daemon hosts one-click install the tray (<5min friction).
- Node discovery, remix, converge, and live collaboration surfaces.
- Paid-market inbox + bid matching.
- Moderation + abuse response.

Target architecture:
`docs/design-notes/2026-04-18-full-platform-architecture.md`.

Work ordering: pick the task that unblocks the largest currently-broken
uptime surface. Treat any surface outage as equal severity — tiered
severity invites starvation. When multiple uptime surfaces are broken,
break ties by largest shared dependency impact, then shortest path to
verified recovery. Any uptime-track feature ships with the §14
concurrency/load-test proof or it is not done.

Subordinated work (bug sprints, rename phases, unrelated design notes)
continues but never blocks uptime work.

Everything else — bug sprints, rename phases, design notes for
unrelated concerns — is subordinated until the uptime vector is making
steady forward progress. Subordinated does not mean cancelled; it means
it doesn't top the queue.

---

## Three Living Files

All three are living documents. All three are updated immediately when
durable state changes — not batched, not deferred. After every user message,
check: does this change any of the three? Multiple sessions from different
providers may be reading these concurrently. They are the shared state.
`STATUS.md` is a live coordination board, not a backlog.

| File | What belongs here | What does NOT belong here |
|------|-------------------|--------------------------|
| **AGENTS.md** | How to work on this project. Behavior, norms, hard rules. | Architecture, design decisions, principles (→ PLAN.md) |
| **PLAN.md** | How the system works and why. Architecture, principles, design decisions, module specs. | Live state, task tracking (→ STATUS.md). Behavioral norms (→ AGENTS.md) |
| **STATUS.md** | What's happening now. Live task board, concerns, next actions. ≤60 lines canonical (~4 KB guidance). | Architecture (→ PLAN.md). How-to-work (→ AGENTS.md). Session logs (→ `activity.log`). Landing records (→ git log). Backlog parking. |

If it's about the project's architecture or design → PLAN.md.
If it's about how to work on the project → AGENTS.md.
If it's about what's happening right now → STATUS.md.

---

## How to Work

### Orient

1. Read `STATUS.md` (live coordination board, concerns, current work). **Trim check:** when reading or writing it, delete resolved concerns, landing records, entries marked DONE, duplicated host asks, and rows no provider can act on. STATUS.md has a 60-line canonical budget (~4 KB guidance); every reader is a janitor.
2. `PLAN.md` is the design reference (~50 KB). Review the relevant module(s)
   for any work you plan, build, review, or fold back. Load it based on task
   scope:
   - **Full load** when: planning or scoping a new feature, making or evaluating
     a design decision, checking alignment with project principles, working on
     module architecture or cross-cutting concerns.
   - **Section load** when: fixing a bug in a specific module, making a small
     scoped change. Use `python scripts/docview.py headings PLAN.md` to find
     the relevant section, then read only that section.
   - **Minimal check** when: routine test fixes, documentation, skill edits,
     or non-architectural code changes. Use headings/search to confirm no
     relevant design module applies, then proceed.
3. If the idea inbox is non-empty, scan `ideas/PIPELINE.md` and `ideas/INBOX.md`.
4. If your approach conflicts with a PLAN.md principle, do NOT implement it. Add the conflict to STATUS.md Concerns. PLAN.md changes require user approval.
5. **Cohit-prevention check before drafting:** before drafting a design note that proposes a new MCP action, citing an unfixed `BUG-NNN`, or pinning a sha in frontmatter / memory, run `python scripts/check_primitive_exists.py {action <verb>|bug <BUG-NNN>|sha <sha>}` from origin/main. Exits 0 (clean), 1 (warning — may be false positive), 2 (collision — investigate before drafting). Catches the "primitive already exists / already-landed work" class — see `.claude/agent-memory/dev-2/2026-05-02-check-primitive-exists-script.md` for the four 2026-05-02 cohit incidents this script is calibrated against.

### Updating the Three Files

**Tiered sync — match effort to message type:**

| Message type | STATUS.md | PLAN.md |
|---|---|---|
| Decision, priority change, new concern, task state change, reframing | **Update immediately** before responding | **Update immediately** if design-relevant |
| New idea that won't be executed now | Capture in `ideas/INBOX.md` or `ideas/PIPELINE.md` | — |
| Code change request, bug fix, feedback on output, question | Check mentally; update only if state actually changed | — |
| Greeting, clarification, small talk | — | — |

**The rule:** If the user closes the window after your next message, the files must already reflect any state change from what they said. The check is automatic. But not every message changes state — the previous "check both files on every message including 'hi'" spent ~38 KB of re-reads on turns that changed nothing.

- **Session task lists are ephemeral.** Other sessions can't see them. Use only for sub-steps.
- **If the user raises a new idea that will not be fully executed now, capture it in `ideas/INBOX.md` or `ideas/PIPELINE.md` before the turn ends.**

**STATUS.md deletion is as important as addition.** Every time you write to STATUS.md, also check for content that should leave:
- Concern resolved? Delete the line (don't mark DONE — just delete).
- Work row landed? Delete the row. The commit is the record.
- A concern became a Work row? Delete the concern — the task IS the resolution.
- Accepted design decision? Move to PLAN.md, delete from STATUS.md.
- Duplicate host ask? Coalesce to one smallest concrete ask.
- No provider-actionable next step? Move detail to an artifact, or rewrite as a concrete `host-decision` / `host-action` row.
- Session summary or landing narrative? Put it in `activity.log`, not STATUS.md.
- Need detail on a concern? Link to the commit, spec, or `docs/concerns/` — STATUS.md entries stay ≤150 chars.

### Where new conventions live (provider-agnostic by default)

This project is multi-provider: the user steers Codex, Cursor, Aider, Claude Code, and Cowork sessions against the same repo. **`AGENTS.md` is the cross-provider standard** — every major coding agent reads it as canonical project context.

**Rule:** when adding a project-level convention (anything a teammate in any provider would need to know — preview loops, ship rituals, file layouts, naming, gates), it goes in `AGENTS.md` first. Provider-specific files (`CLAUDE.md`, `.cursor/rules/*`, `.codex/*`, agent memory) exist only for genuinely provider-specific rules — harness behavior, harness quirks, harness-specific bootstrapping. Those files should reduce to *pointers at `AGENTS.md`* plus a thin layer of harness-specific notes.

**Self-check before saving any rule:** *"Would a Codex session or a Cursor session need to know this?"* If yes → `AGENTS.md`. If "no, this is purely about how my harness works" → the provider-specific file. When in doubt, default to `AGENTS.md` — broader visibility is the safer error.

| Convention type                                | Lives in                                            |
|------------------------------------------------|-----------------------------------------------------|
| Cross-provider (any agent needs it)            | `AGENTS.md`                                         |
| Claude Code harness behavior                   | `CLAUDE.md` (which `@AGENTS.md` imports)            |
| Cursor-specific                                | `.cursor/rules/*.mdc` or `.cursorrules`             |
| Cowork-quirk (e.g., FUSE truncation)           | Cowork agent memory + pointer in a project doc      |
| Codex-specific                                 | `AGENTS.md` (Codex's canonical file already)        |

**This rule is itself self-correcting.** If a future session adds a project-level convention to `CLAUDE.md` or memory without also putting it in `AGENTS.md`, that session has drifted. Catch the drift on review and pull the convention up to `AGENTS.md`. Provider-specific files should de-duplicate by replacing the duplicated content with a pointer.

**Auto-heal hook (apply the `auto-iterate` skill when fixing recurring behavioral failures).** Run `python scripts/check_cross_provider_drift.py` from any provider. It scans `CLAUDE.md`, `.cursorrules`, `.cursor/rules/*`, `.codex/*` for substantive sections that don't appear in `AGENTS.md`. Exits 2 with a fix prescription on drift (move to `AGENTS.md`, or tag `[harness-specific]` / `[Claude Code only]` / `[Cursor only]` / etc. on the heading). In Claude Code it fires automatically as a `PostToolUse` hook on Write/Edit of any watched provider-specific file (see `.claude/hooks/cross_provider_drift_guard.py`). Cowork / Codex / Cursor sessions should run the script manually after editing one of those files. Each drift recurrence ratchets the prevention layer, same auto-iterate pattern as the FUSE-truncation guard (`WebSite/HOOKS_FUSE_QUIRKS.md`).

### Truth And Freshness

- **Truth is typed, not singular.** `AGENTS.md` owns process truth, `PLAN.md` owns design truth, and `STATUS.md` owns live-state truth. Do not silently treat one file as global truth when evidence disagrees.
- **Reality audits are diagnostic, not a fourth living source of truth.** Use them to reconstruct confidence when trust is damaged, then push stable conclusions back into `AGENTS.md`, `PLAN.md`, and `STATUS.md`.
- **Landed items leave STATUS.md.** Don't mark concerns DONE — delete them. If trust in a claim matters, use labels `current:`, `historical:`, `contradicted:`, `unknown:` with date + environment.
- **Verification claims must be freshness-stamped.** If a claim depends on tests, lint, runtime behavior, or environment state, include the date, environment, and evidence/command.
- **STATUS.md Concern row date-stamp format.** Every Concern row begins with `[filed:YYYY-MM-DD]` (when added) and gains `verified:YYYY-MM-DD` once someone re-checks the concern is still valid: `[filed:2026-04-23 verified:2026-04-28]`. Severity prefix optional and goes outside the bracket: `**[P1 filed:... verified:...]**`. Rationale: per `docs/audits/2026-04-28-status-md-coordination-gap.md` Rule 1, single-date stamps decay into stale state without explicit re-verification semantics.
- **Server-bug Concerns cross-reference their wiki BUG.** When a STATUS Concern row maps to a wiki `BUG-NNN` page, append `(see BUG-NNN)` inline. When a wiki BUG-NNN page is severity P0/P1, its header should reference the STATUS row. Rationale: per audit Rule 3, BUG-034 + duplicate Concern rows drifted as 3 separate items for 4 days because no cross-reference convention existed.
- **Contradictions must be downgraded immediately.** If current code, runtime artifacts, or verification output contradict an older claim, rewrite the `STATUS.md` claim or add a Concern before responding. Do not leave stale certainty in place.
- **Revalidate `PLAN.md` section by section when trust is damaged.** Treat the plan as candidate design intent until the relevant sections are confirmed against code and runtime evidence.
- **Audit docs decay too.** Before dispatching prescriptions from an audit older than ~24h, run a freshness check (git log, search, spot-read) and stamp any claim that still matters.

### Client Conversations Are Bug Reports

When the user pastes a chat conversation (from any MCP client or interface), extract issues and fix them immediately.

### Large Docs And Artifacts

Codex may truncate large local-file and tool output. This repo therefore has a
scoped reader at `python scripts/docview.py`.

- Use `python scripts/docview.py` instead of raw whole-file reads for large
  Markdown, text, or JSON artifacts.
- This is required for `PLAN.md`, `output/*/notes.json`, large review
  artifacts, and any text/JSON file likely to exceed roughly 10 KiB or 200
  lines.
- Start with `stat`, then narrow with `headings`, `section`, `lines`,
  `search`, `json-keys`, or `json`.
- If `docview.py` says the result is too large, narrow the query again. Do not
  fall back to raw whole-file reads.
- Raw full-file reads are only acceptable after a scoped query shows the file
  is small enough to fit safely.

### Project Skills

- Project engineering skills live canonically in `.agents/skills/` and are mirrored into `.claude/skills/` for Claude Code's harness discovery.
- Codex and project-visible agents read from `.agents/skills/` directly — there is no separate Codex mirror.
- Claude Code reads from `.claude/skills/`.
- When the right workflow skill is not obvious, start with `using-agent-skills` and then read the matching skill.
- After editing shared skills, run `powershell -ExecutionPolicy Bypass -File scripts/sync-skills.ps1` to refresh the Claude Code mirror.
- When the user points at an outside project, repo, paper, benchmark, article, or codebase and asks what TinyAssets should learn or integrate, use `external-research-implications`. That process must canonicalize the source, research current context, compare module-by-module against TinyAssets, write durable implications, and self-update the skill when the process itself improves.
- Research-derived concepts need opposite-provider review before implementation. If Codex makes the initial finding, Claude researches/reviews it; if Claude makes the initial finding, Codex researches/reviews it. If another provider makes the initial finding, name a different reviewer provider explicitly in `STATUS.md`, preferring the Codex/Claude pair when available. The review must re-check sources and TinyAssets context, leave a durable artifact, and gate any build, git push, live rollout, or acceptance test based on the finding.

### Skill methodology [all providers]

The project skills bake in a complete, self-enforcing development methodology
(merged from obra/superpowers, DietrichGebert/ponytail, and Fission-AI/OpenSpec
into the native skills). The governing discipline lives in `using-agent-skills`:
**if there is even a ~1% chance a skill applies, invoke it before responding or
acting** — including before clarifying questions; user instructions in
`AGENTS.md` / `CLAUDE.md` always override a skill where they conflict. Core dev
loop: `idea-refine` (design-approval gate) -> `planning-and-task-breakdown` ->
`test-driven-development` / `debugging-and-error-recovery` ->
`code-review-and-quality` (evidence-before-completion gate) ->
`git-workflow-and-versioning` -> `shipping-and-launch`;
`subagent-driven-development` runs it via fresh per-task subagents.
`code-simplification` carries the write-the-least-code ladder. All skills mirror
into `.claude/skills/` and `.codex/skills/`.

### Spec-driven development — OpenSpec is the standard [all providers]

Host directive 2026-07-19: this project is spec-driven from here on.

- **OpenSpec (`openspec/`) is the canonical spec system.**
  `openspec/specs/<capability>/spec.md` is the as-built requirement truth for
  each capability; `openspec/changes/<name>/` holds in-flight change proposals
  (proposal / design / delta specs / tasks). The `openspec` skill drives the
  lifecycle: explore → propose → apply → sync-specs → archive.
- **Every substantive change starts as an OpenSpec change.** Behavior changes,
  MCP/API surface, storage shapes, new capabilities, security posture — all get
  a change with its `applyRequires` artifacts done before implementation.
  `opsx:propose` fronts the core dev loop; `idea-refine` and
  `spec-driven-development` remain the dependency-free fallback only where the
  CLI is unavailable. Trivial mechanical work (typos, comment/doc formatting,
  test-only fixes that change no behavior) needs no change.
- **Touch it → spec it (backfill obligation).** Capabilities that predate
  OpenSpec get their main spec backfilled by the
  `spec-out-existing-platform` baseline; anything still unspecced gets its
  spec written before or alongside its next substantive change.
- **Sync and archive on land.** When a change's implementation lands, sync its
  delta specs into `openspec/specs/` and archive the change in the same lane.
  A landed change with unsynced deltas is spec drift — treat it like a failing
  gate.
- **Truth split stays.** `PLAN.md` owns architecture and principles (why the
  system is shaped this way); `openspec/specs/` owns behavioral requirements
  (what each capability does). Specs complement PLAN.md, never replace it.

### Multi-Session Steering

- The user may steer multiple live sessions across different providers at once.
- Durable coordination belongs in files, not private chat memory.
- Use `STATUS.md`, `ideas/*.md`, and `.agents/activity.log` as the shared coordination surface.
- If two sessions may converge on the same idea, narrow the file boundary and record the split in `STATUS.md` or `ideas/PIPELINE.md`.
- A useful idea left only in chat is lost work.

### GitHub/Worktree Coordination Spine

- Treat GitHub branches plus local `../wf-<slug>` worktrees as the execution
  spine for buildable work. `STATUS.md` still owns cross-provider file claims;
  `scripts/worktree_status.py` owns persistent local worktree visibility.
- Before building from any `STATUS.md` row, idea, spec, exec plan, audit, or
  memory, refactor it into current project state: exact `STATUS.md` Files and
  Depends, branch name, worktree path, PR or draft-PR/live-push expectation,
  prior-provider memory refs, and related implication refs.
- Each active worktree should have a local `_PURPOSE.md` with the lane source,
  claim boundary, branch, worktree path, review gate, expected publish route,
  memory refs, and implication refs. This file is local worktree metadata, not
  product source, and is ignored by git.
- Review-blocked work should still have a visible pending worktree lane, but
  must not advance beyond planning/scaffolding until the required
  opposite-provider review returns approve/adapt.

### Site preview / ship loop

The TinyAssets site lives in `WebSite/site/`. Keep website-specific rules in
`.agents/skills/website-editing/SKILL.md`, not expanded here. For any
non-trivial website edit, read that skill first; it owns the preview loop,
UX affordance conventions, transparent-capture rules, build/ship pipeline,
FUSE quirks, and website-specific auto-iteration.

---

## Team Norms

- **Teammates communicate directly where the harness supports it.** Claude Code devs message verifier after finishing work. Use SendMessage by name, not broadcast.
- **Verification is proactive.** Every substantive change gets independent verification before landing. Claude's persistent verifier is the background teammate implementation; other providers use focused tests plus independent diff/subagent review when available.
- **Persistent teams stay ready.** Where the harness supports teammates, they stay up, idle when not needed. "Standing by" is a valid state.
- **Iterate agent behavior.** If a teammate isn't performing well, refine its `.claude/agents/` definition and respawn.
- **Broadcast sparingly.** Token cost scales with team size. Use direct messages for targeted coordination, broadcast only for team-wide state changes.
- **Claim before working.** When self-claiming from the task list, claim first to prevent collisions. File locking handles races but claiming communicates intent.
- **Shutdown is graceful.** Teammates can reject shutdown if mid-task. Lead shuts down all teammates before running cleanup. Never force-kill without checking.
- **Despawn discipline.** Floater swaps use Escape-then-`shutdown_request` (Protocol A in `LAUNCH_PROMPT.md`). Verifier and dev despawns wait for in-flight tool calls — no Escape unless the teammate is genuinely idle. Hung teammates require filesystem cleanup of `~/.claude/teams/<team>/`; no force-kill verb exists. Spawn the replacement only AFTER `shutdown_approved` lands — never overlap, since the 3+1 floater roster is sized to the rate-limit budget. See `docs/audits/2026-04-25-despawn-chain-protocol.md`.

### Quality Gates

Three patterns keep agent output trustworthy:

**Verification is structural.** Every substantive change needs test/check evidence and an independent review path before it is treated as landed. Claude Code's `TaskCompleted` -> verifier loop is the preferred team implementation. Codex/Cowork satisfy the same invariant with focused tests plus independent diff/subagent review where available. Self-review alone is not enough for public-surface, storage, auth, migration, concurrency, or data-loss-risk changes.

**Confirmed findings become mutation-proven regression tests.** Once the host accepts a concrete finding for implementation, write the regression test first and preserve RED evidence against the vulnerable code (or against a scratch mutation that removes an already-present protection), then fix and preserve GREEN evidence. A test that cannot be made RED is vacuous and must be reported as such. When the host explicitly designates these tests as the final gate, do not create another adversarial review-document round; the permanent fast regression suite is the gate.

**Final chatbot-surface verification is a rendered chatbot conversation through the live connector.** For changes affecting public MCP behavior, chatbot UX, connector tool descriptions, user-visible node/workflow state, or `tinyassets.io`, final acceptance must use a real browser-rendered chatbot conversation with the installed TinyAssets MCP connector at `https://tinyassets.io/mcp`, following `ui-test`. Claude.ai and ChatGPT Developer Mode both satisfy this when the TinyAssets connector is visible/installed and the tester types user-like prompts in the browser. The proof requirement is not host-login Claude.ai access; it is a real user path through the live MCP service. Direct MCP calls, local scripts, tests, DOM-only checks, and canaries are supporting evidence, not final user-surface proof. Log the rendered prompt/result in `output/user_sim_session.md` and include a trace or screenshot path when available.

**Post-fix clean-use evidence.** After the fix and `ui-test`, final verification must also look for evidence that actual users have used the affected feature cleanly since the fix landed. Use available production traces, connector/server logs, support reports, user-visible history, or other real-user evidence. Freshness-stamp the evidence. If no post-fix real-user use is visible yet, say that explicitly and, for public-surface or high-risk changes, leave a short watch item in `STATUS.md` instead of claiming proven clean use.

**Agent team loop guardrails with forced reflection.** If a teammate is stuck retrying the same approach, it must pause and reflect before the next attempt: "What failed? What specific change would fix it? Am I repeating the same approach?" If stuck for 3+ iterations on the same error, message the lead for reassignment or a fresh perspective. Don't loop forever. (Note: this is about dev agent stuck-loops, not daemon-level bounded reflection — see STATUS.md #6 for the daemon concern.)

**REFLECTION.md for compound learning.** After completing a significant task, the teammate writes a short reflection: what surprised me, one pattern worth capturing, one thing I'd do differently. Save to `REFLECTION.md` in the working directory. The lead reviews and merges approved learnings into AGENTS.md or the agent's memory. This is how sessions make future sessions better — systematically, not ad hoc.

**Scope-message before implementing self-found tasks.** Even when scope feels obvious, send the lead a one-line scope message and wait for approval before editing. The scope step exists to catch silent divergence from lead intent.

### Two Task Systems

The project uses two coordination layers that serve different purposes:

| System | Scope | Lifetime | Who sees it |
|--------|-------|----------|-------------|
| **Agent team task list** | Intra-session. Tasks the lead creates for teammates. | Ephemeral — dies with the session. | Lead + all teammates in this session. |
| **STATUS.md Work table** | Cross-provider. Tasks any provider can claim. | Durable — survives across sessions and providers. | Any AI, any tool, any provider. |

**Rule:** Work items that matter beyond the current session go in STATUS.md. The agent team task list is for sub-steps and intra-session coordination only. When a teammate completes a STATUS.md item, the lead updates STATUS.md — don't rely on the ephemeral task list as the record.

---

## Parallel Dispatch

**Multi-provider concurrent execution is the default operating mode.**
Multiple providers (Claude Code, Codex, Cursor, Cowork, future) work on
this project at the same time. The host does not announce when a new
provider is started; coordination flows through STATUS.md, not through
chat. Treat any session-start as "the team is already running; what's
safe to claim?"

The complete coordination contract is: **STATUS.md Work table is the
authoritative claim surface.** No external locks. No runtime signaling.
A provider with a fresh checkout, no chat history, and no announcement
should be able to start working productively in under a minute.

### Provider session-start ritual

Every provider, every session, in this order:

0. **Run `python scripts/session_sync_gate.py`.** Fetches with `--prune` and
   warns if the primary checkout is off `main` or behind origin/main — the
   "1,209 behind / stale refs" trap. Advisory; never mutates the tree. Claude
   Code fires it automatically via the `SessionStart` hook.
1. **Read STATUS.md.** Concerns + Work table + Next.
2. **Run `python scripts/worktree_status.py`.** This shows dirty current
   checkouts, worktrees that need `_PURPOSE.md`, orphaned or missing paths,
   lanes that need PR/STATUS promotion, and parked draft lanes. Do not switch
   a dirty checkout to `main`; start a clean main-based worktree for new
   live-ready work.
3. **Run `python scripts/claim_check.py --provider <yourname>`.**
   Output classifies every Work row into CLAIMABLE / BLOCKED / IN-FLIGHT
   / HOST-OWNED / STALE-CLAIM. The CLAIMABLE list is what's safe to
   start on right now; BLOCKED tells you why something isn't; IN-FLIGHT
   shows files off-limits.
4. **Run `python scripts/provider_context_feed.py --provider <yourname> --phase claim`.**
   This scans provider memories/configs, shared ideas, recent research
   artifacts, worktree handoffs, and provider automation notes. It is a
   context feed, not a backlog writer. Relevant candidates must be promoted
   into a current STATUS/worktree/PR lane before they become build authority.
   Claim phase deliberately includes durable memory/brain notes authored by
   other AI families, not only your own provider. Search the feed for the
   issue/request slug and related domain terms before assuming no prior
   Claude/Codex/Cursor/Cowork context exists.
5. **Claim by editing STATUS.md.** Change the chosen row's Status cell
   to `claimed:<yourname>`. Use a session-specific provider name when
   more than one session from the same tool may be active (for example
   `codex-gpt5-desktop`, `codex-cli-2`, `cursor-gpt55`). Commit that
   edit on your branch (or directly to main if you're operating without
   a worktree). The edit IS the claim — no other notification required.
6. **Scan cross-implications before building.** Before implementation,
   compare your claimed task against active `STATUS.md` rows,
   `ideas/PIPELINE.md` Active Promotions, and recent research/design
   artifacts for matching domain terms, files, primitives, or user surfaces.
   If a research-derived finding may affect your design, read its artifact
   before coding and either add a `Depends` edge / note to your row or record
   why it does not apply. Do not bypass an opposite-provider review gate just
   because your task is named differently.
7. **Work in a worktree or branch.** `git worktree add ../wf-<task>` or
   feature branch. Do not write outside your row's Files write-set
   without first updating STATUS.md to reflect the new write-set. A branch is
   isolation, not memory; make sure the lane has `_PURPOSE.md`,
   `.agents/worktrees.md`, STATUS row, or draft PR metadata before leaving it.
8. **On land**, change Status -> `done` and delete the row in the same
   commit. The commit is the audit trail.

### Provider-context feed checkpoints

`provider_context_feed.py` is a lifecycle gate, not a session-start-only
ritual. Run it whenever a provider is about to narrow or advance durable work:

- `--phase claim` before claiming or adding a STATUS row.
- `--phase plan` before writing a plan, design note, exec plan, or
  `_PURPOSE.md`.
- `--phase build` before implementation starts and again before broadening a
  Files cell.
- `--phase review` before reviewing another provider's work.
- `--phase foldback` before pushing, opening/updating a PR, merging, or
  retiring a STATUS row.
- `--phase memory-write` after writing provider memory, idea-feed entries,
  research artifacts, reflections, or `_PURPOSE.md` so related candidates can
  be folded into the current lane immediately.

If a harness supports automatic hooks or automations, wire those checkpoints
there too, but the shared contract remains the script + STATUS/worktree/PR
promotion. The scanner may produce noisy candidates; the agent must read the
relevant ones and then either promote them into the lane or explicitly note why
they do not apply. `ideas/INBOX.md` remains a loose idea feed at the bottom of
lanes, never design truth or permission to build.
The phase filters are coarse triage, not proof that unrelated context is
absent. Bare CLI use should start with the default limit for a broad sweep,
use `--limit 10` for compact hook-like triage, and use `--limit 200` when
auditing whether a category is absent.

### Work-table row schema

Every row must have:

- **Files** — specific files or directories this task will write.
  This is the collision boundary. Be concrete: `tinyassets/api/wiki.py, tinyassets/storage/__init__.py`
  not `backend`. Read-only dependencies go in Depends, not Files. Use
  comma or semicolon between atoms.
- **Depends** — which tasks must merge first. Include both task
  dependencies (`#18, #23`) and file-read dependencies. If your task
  needs to read `api.py` after another task rewrites it, that is a
  dependency.
- **Status** — one of: `pending`, `claimed:<provider>`, `in-flight`,
  `dev-ready`, `host-action`, `host-decision`, `host-review`,
  `monitoring`, `done`. Provider is the tool/session name: `codex`,
  `claude-code`, `cursor`, `cowork`, or a more specific label such as
  `codex-gpt5-desktop` / `cursor-gpt55` when generic names would be
  ambiguous. `claimed:*` and `in-flight` mean the row's Files are
  off-limits to others until status flips.

### Stale-claim reaping

A claim is stale if its Files have seen no commits in 24h and the row
has no fresh active-date heartbeat. `claim_check.py` flags these as
STALE-CLAIM CANDIDATES. Any provider may reap a stale claim by editing
the row Status to `reaped:<yourname>:no-activity-24h`, then re-claiming
as their own (`claimed:<yourname>`). No daemon, no permission needed;
the convention is the policy. If a provider is actively building or
testing before a commit lands, add `ACTIVE YYYY-MM-DD` to the Work row
task text or status note. That heartbeat keeps the claim live for the
date shown and prevents uncommitted active work from being reaped just
because it has not landed yet.

### Pre-claim collision guard

Before adding a new row or broadening a Files cell, run
`python scripts/claim_check.py --provider <yourname> --check-files "path/a.py, docs/foo.md"`.
It warns if your prospective claim's Files overlap any in-flight row's
Files. Substring match either direction. If overlap fires, EITHER add a
Depends edge (the overlap is real coordination) OR refine your row's
Files to be narrower (the overlap was a hint, not a real write).

### GitHub-Aligned Worktree Discipline

GitHub is the integration model: a worktree is the local checkout for one
branch, the branch folds back through a PR, and `STATUS.md` is the claim surface
— not a replacement for GitHub history. **A branch is not durable memory** (it
remembers commits, not why it exists, whether it is live-safe, what blocks it,
or who owns it); the durable layer is `_PURPOSE.md`, `.agents/worktrees.md`,
`STATUS.md`, idea files, and draft-PR bodies.

**Full procedure → [`docs/reference/worktree-discipline.md`](docs/reference/worktree-discipline.md)**
(the `_PURPOSE.md` template, numbered creation steps, `worktree_status.py`
diagnostic states, and the branch-lifecycle automation layers). Read it before
creating, taking over, or sweeping a worktree. Invariants you must honor without
opening it:

- **Four lane states**, exactly one per branch/worktree: **Active** (actionable
  now; STATUS row + worktree + branch + `_PURPOSE.md`), **Parked draft** (pushed
  branch + draft PR recording ship/abandon conditions + review gates),
  **Idea/reference only** (no build authority; lives in `ideas/*.md` or a
  `_PURPOSE.md` "Idea feed refs" section; promote to `STATUS.md` + check
  `PLAN.md` before building), **Abandoned/swept** (removed or logged in
  `.agents/worktrees.md` with a reason; extract useful ideas first).
- **Dirty-main safety.** A non-main branch is isolated from the live deploy
  chain until merged; merging to `main` is production-impacting. Never switch a
  dirty checkout to `main` — start a clean main-based worktree for live-ready
  work.
- **Lifecycle via tooling, not by hand.** Use `python scripts/wt.py new|done|list`
  (creates off `origin/main` + scaffolds `_PURPOSE.md`; `done` refuses an
  unmerged branch) instead of raw `git worktree add`/`remove`, so teardown stops
  being optional. Run `python scripts/worktree_status.py` at session start to
  surface stale / orphaned / dirty / incomplete lanes.
- **Memory refs are required for inherited work.** When continuing or reviewing
  another provider's work, `_PURPOSE.md` / `.agents/worktrees.md` / the STATUS
  row / PR body must reference the prior provider's memory/artifact paths; read
  them before coding. If none are listed, search `.claude/agent-memory/`,
  `.agents/activity.log`, and recent audits by task slug before assuming absence.
- **Review-blocked work still gets a lane.** Create the review row claimable and
  the implementation row `pending` with `Depends` naming the review artifact +
  required verdict; the branch may exist, but runtime implementation, push, live
  rollout, and acceptance-test advancement stay blocked until review returns
  `approve` / `adapt`.
- **Legacy docs/ideas/memories are context, not build queues.** Promote into a
  current `STATUS.md`/`PLAN.md` lane (re-check PLAN modules, add the Work row,
  run `claim_check.py --check-files`) before building from them.

### Staying unblocked

If `claim_check.py` shows zero CLAIMABLE rows, look for cross-cutting
work that doesn't appear in the Work table: docs hygiene, skill audits,
test surface, design-note classifications, audit follow-ups. Add a new
Work row for the task you pick up rather than working off-table — that
keeps the next provider's `claim_check.py` accurate.

---

## Hard Rules

1. **SqliteSaver only** -- not AsyncSqliteSaver (not production-safe).
2. **LanceDB singleton** -- reuse connection objects, never recreate.
3. **No API SDKs for primary writer** -- Claude/Codex use `claude -p` and `codex exec` subprocesses.
4. **Executable gates need autonomous defaults** -- never block a workflow gate on human input when a safe default exists. True host-only authority is allowed only as a concrete `host-decision` or `host-action` row with the smallest possible ask; it must not block unrelated autonomous work. If no safe default exists, route around it or pick another non-overlapping uptime task.
5. **TypedDict + Annotated reducers** -- `Annotated[list, operator.add]` for accumulating fields.
6. **FactWithContext with truth-value typing** -- every extracted fact needs source_type, reliability, temporal_bounds, language_type. Domain skills may extend these fields.
7. **Python 3.11+** required.
8. **Fail loudly, never silently.** Mock fallbacks that look like real output are worse than crashes.
9. **User uploads are authoritative.** Preserved verbatim. Never summarize, truncate, or reformat.
10. **Contributor attribution uses `CONTRIBUTORS.md`.** When a branch or node ships and `attribution_credit` rows exist, read `CONTRIBUTORS.md` to map each `actor_id` to a GitHub handle and emit `Co-Authored-By:` lines in the commit message. Format: `Co-Authored-By: Display Name <handle@users.noreply.github.com>`. If an actor_id is not in the table, skip silently — never block a commit on missing attribution.
11. **Public-surface changes verify post-change.** After any edit to DNS records, Cloudflare tunnel config, GoDaddy Website Builder config, or any surface affecting `tinyassets.io`, run `python scripts/mcp_public_canary.py --url https://tinyassets.io/mcp` (or `scripts/uptime_canary.py --once` when Layer-1 is wired) and confirm a green probe. For any change to the MCP tool surface or connector tool catalog, additionally run `python scripts/mcp_public_canary.py --url https://tinyassets.io/mcp --assert-handles` to confirm the live `/mcp` advertises exactly the canonical handle set (`read_graph`/`write_graph`/`run_graph`/`read_page`/`write_page`/`converse`, plus optional `get_status` — as-built truth: `openspec/specs/live-mcp-connector-surface/spec.md`, asserted by `CANONICAL_HANDLES` in the canary) — the PR-178 drift guard, so the user surface can never silently regress to the legacy fat tools. This canary is required evidence, not final chatbot-surface proof; MCP/chatbot-facing changes also require the rendered chatbot `ui-test` check above before final acceptance. Canonical public endpoint is `https://tinyassets.io/mcp` only. `mcp.tinyassets.io` is an Access-gated internal tunnel origin (host directive 2026-04-20) — it exists in DNS but is not user-facing; direct requests without the Worker's CF Access service-token headers return 401/403. Do not document or share `mcp.tinyassets.io` in user-facing contexts. The 2026-04-19 P0 outage (`docs/audits/2026-04-20-public-mcp-outage-postmortem.md`) landed when a tunnel reshuffle silently dropped a route — no commit touched the broken surface, so only a post-change out-of-band probe can catch this class. Named reference probes (including PROBE-001, the validated full-stack smoke): `docs/ops/acceptance-probe-catalog.md`.
12. **Portfolio graph stays current.** Before changing public-facing docs, project status, repo structure, or lineage, inspect `PROJECT_GRAPH.yml` where present and the standards in `docs/portfolio/`. If the change affects how a project appears publicly, update the relevant manifest, `docs/project-lineage.md`, or portfolio index notes. Default stance is public-draft unless explicitly private, but public publishing remains gated by scan/review.
13. **No destructive git ops without explicit approval.** Do not use `git reset --hard`, `git checkout --`, `git restore`, `git clean`, force-push, or stash/drop as cleanup or diagnostics unless the host explicitly asks for that operation. Do not switch a dirty worktree to `main`; create a clean main-based worktree/session for live-ready work.

---

## Testing

- `pytest` for the full suite. `ruff check` before committing.
- Every module must have tests. Nodes must never crash.
- After canonical `tinyassets/*` edits that affect the Claude plugin runtime, rebuild/check the mirror with `python packaging/claude-plugin/build_plugin.py`; pre-commit mirror parity is the guardrail. See `packaging/INDEX.md`.
- `actionlint` for GH Actions workflow edits. Install: `choco install actionlint -y` (Windows) / `brew install actionlint` (macOS) / `go install github.com/rhysd/actionlint/cmd/actionlint@latest` (Go). Pre-commit invariant #7 runs it on staged `.github/workflows/*.yml`; CI (`.github/workflows/actionlint.yml`) is the authoritative gate.
- **Hot-path rewrites use differential testing [all providers].** When rewriting a validated implementation for performance, keep the original verbatim in the test suite as the executable spec and differential-test the rewrite against it (randomized tie-heavy trials + a scale gate). Founder-adopted 2026-07-13; reference implementation: `tests/test_match_scale.py`.
- **Sandbox test-temp hygiene [all providers].** Some agent sandboxes (notably Codex; also some Cursor/Cowork runs) redirect pytest's `--basetemp`/`TMPDIR` *into* the checkout (`.pytest-tmp/`, `.codex-test-tmp/`, `.workflow-test-data/`) and create those dirs under a restricted sandbox token. On Windows the resulting dirs carry ACLs the normal interactive user can't read or delete, so they survive `git worktree remove` / `wt.py done` and need an elevated `takeown` + `icacls` + `rmdir` to clear (a reboot does **not** help — it's an ACL, not a held handle). Prevention: point your sandbox's `--basetemp`/`TMPDIR` *outside* the repo (system temp). These patterns are gitignored so they don't pollute `git status` or block worktree teardown. Diagnosed 2026-06-25 during de-fantasy worktree cleanup (no process held the dirs — every candidate's CWD was the main checkout; the block was an unreadable ACL on the sandbox-created temp subdir).

---

## Configuration — environment variables

The daemon reads **all** configuration from env vars — data paths, auth/identity,
feature flags, LLM/provider routing, observability, and local secrets. The full
catalog (every var, its purpose, and default) is pointer-loaded per
[ADR-002](docs/decisions/ADR-002-static-vs-dynamic-context-budget.md):

> **Canonical reference → `docs/reference/environment-variables.md`.**

Load-bearing invariants stay inline (don't make a reader open the catalog to
honor these):

- **Canonical, CWD-independent resolvers.** Path/data defaults must be
  CWD-independent and go through the resolver APIs — `tinyassets.storage.data_dir()`
  for `TINYASSETS_DATA_DIR`, `wiki_path()` for the wiki root — never `Path.cwd()`
  logic or a re-implemented precedence.
- **Container deploys.** Set `TINYASSETS_DATA_DIR=/data` + bind-mount the host path
  to `/data` (`deploy/README.md`).
- **Subscription-only by default.** API-key provider env vars (`OPENAI_API_KEY`,
  `GEMINI_API_KEY`, `GROQ_API_KEY`, `XAI_API_KEY`, …) are ignored unless
  `TINYASSETS_ALLOW_API_KEY_PROVIDERS` is truthy.
- **Local secrets are vault-first.** Load via
  `set -a; source scripts/load_secrets.sh; set +a` (`TINYASSETS_SECRETS_VENDOR` =
  `1password` default / `bitwarden` / `plaintext`), never a committed plaintext
  file. Canonical keys: `scripts/secrets_keys.txt`.

---

## Project Files

| File | Audience | Purpose |
|------|----------|---------|
| `AGENTS.md` | Any AI, any tool | How to work, team norms, hard rules. |
| `STATUS.md` | Any AI, any tool | Live state: task board, concerns, watch, archive. |
| `PLAN.md` | Any AI, any tool | Architecture, principles, design decisions. |
| `README.md` | Any human or AI | Fast project orientation. |
| `INDEX.md` | Any human or AI | Repo map and Obsidian hub. |
| `CODEX.md` | Codex | Thin routing layer. |
| `notes.json` | Daemon + sessions | Per-universe unified notes (user, editor, structural, system). |
| `scripts/docview.py` | Any AI, any tool | Scoped reader for large Markdown/text/JSON artifacts that should not be read raw. |
| `scripts/capture_idea.py` | Any AI, any tool | Fast append helper for the idea inbox. |
| `scripts/claim_check.py` | Any AI, any tool | Multi-provider session-start helper. Classifies STATUS.md Work rows as CLAIMABLE / BLOCKED / IN-FLIGHT / HOST-OWNED / STALE. Run with `--provider <yourname>` before claiming work. |
| `scripts/worktree_status.py` | Any AI, any tool | Worktree cold-start helper. Shows dirty current checkouts, missing or incomplete `_PURPOSE.md`, orphaned/missing paths, active lanes, parked drafts, and PR/STATUS promotion gaps. |
| `scripts/provider_context_feed.py` | Any AI, any tool | Lifecycle checkpoint feed for provider memories/configs, ideas, research artifacts, automation notes, and worktree handoffs. Run at claim/plan/build/review/foldback/memory-write checkpoints. |
| `scripts/sync-skills.ps1` | Repo maintenance | Re-sync `.agents/skills/` into `.claude/skills/`. |
| `CLAUDE.md` | Claude Code only | Thin routing layer. |
| `CLAUDE_LEAD_OPS.md` | Claude Code lead | Situational: user-sim loops, dev team management, token efficiency. Not auto-loaded. |
| `LAUNCH_PROMPT.md` | Claude Code lead | Team spawn, session protocol, lead norms. |
| `.claude/agents/*.md` | Claude Code only | Individual agent definitions. |
| `.claude/agent-memory/<name>/` | Claude Code teammate `<name>` only (write); any AI (read) | Per-teammate persistent memory. **Owned by the named teammate; other agents and other providers must NOT write here.** Read-only access is fine when context is needed. If a non-owner has a useful observation for another teammate, route it via SendMessage / activity log / a docs note, not by writing into the memory directory. |
| `.agents/skills/*/SKILL.md` | Codex + project agents (canonical source) | Canonical skill definitions. Edit here first. |
| `.claude/skills/*/SKILL.md` | Claude Code only | Mirror of `.agents/skills/` refreshed by `scripts/sync-skills.ps1`. |
| `.agents/activity.log` | Any AI, any tool | Short cross-session activity feed for coordination. |
| `ideas/*.md` | Any AI, any tool | Idea capture, triage, and shipped traceability. |
| `knowledge/*.md` | Any human or AI | Human-readable compiled knowledge companion to `knowledge.db`. |
| `docs/exec-plans/*.md` | Any AI, any tool | Multi-step execution plans and landing history. |
| `docs/conventions.md` | Any AI, any tool | Stable documentation and linking patterns. |
| `docs/reference/environment-variables.md` | Any AI, any tool | Canonical env-var catalog (pointer-loaded per ADR-002; AGENTS.md keeps the invariants + pointer). |
| `docs/reference/worktree-discipline.md` | Any AI, any tool | Canonical worktree/branch lane procedure (pointer-loaded per ADR-002; AGENTS.md keeps the invariants + pointer). |
| `docs/decisions/INDEX.md` | Any AI, any tool | ADR directory surface. |
| `docs/specs/INDEX.md` | Any AI, any tool | Feature/change spec directory surface. |
