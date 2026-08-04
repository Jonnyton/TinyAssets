# TinyAssets

A goal-agnostic daemon engine. Bind it to a domain and let it run. The platform
supports any multi-step AI workflow — research papers, screenplays, recipe
trackers, novels, news summaries, any substantive long-running work.

---

## Forever Rule (2026-04-18): Complete-System 24/7 Uptime Is Top Priority

One unified priority, not a ranked list. Every surface works 24/7 with zero
hosts online:

- Tier-1 chatbot users create / browse / collaborate on nodes via a real
  chatbot UI with the TinyAssets connector (Claude.ai, ChatGPT Developer Mode,
  or equivalent).
- Tier-3 OSS contributors `git clone` and run cleanly.
- Tier-2 daemon hosts one-click install the tray (<5min friction).
- Node discovery, remix, converge, live collaboration, paid-market inbox +
  bid matching, moderation + abuse response.

Target architecture: `docs/design-notes/2026-04-18-full-platform-architecture.md`.

Work ordering: pick the task that unblocks the largest currently-broken uptime
surface; treat any surface outage as equal severity. Break ties by largest
shared dependency impact, then shortest path to verified recovery. Uptime-track
features ship with the §14 concurrency/load-test proof or they are not done.
Everything else (bug sprints, renames, unrelated design notes) continues but
never blocks uptime work.

---

## Three Living Files

Updated immediately when durable state changes — they are the shared state
across concurrent multi-provider sessions. `STATUS.md` is a live coordination
board, not a backlog.

| File | What belongs here | What does NOT belong here |
|------|-------------------|--------------------------|
| **AGENTS.md** | How to work on this project. Behavior, norms, hard rules. | Architecture, design decisions, principles (→ PLAN.md) |
| **PLAN.md** | How the system works and why. Architecture, principles, design decisions, module specs. | Live state, task tracking (→ STATUS.md). Behavioral norms (→ AGENTS.md) |
| **STATUS.md** | What's happening now. Live task board, concerns, next actions. ≤60 lines canonical (~4 KB guidance). | Architecture (→ PLAN.md). How-to-work (→ AGENTS.md). Session logs (→ `activity.log`). Landing records (→ git log). Backlog parking. |

---

## How to Work

### Orient

1. Read `STATUS.md`. **Trim check:** when reading or writing it, delete
   resolved concerns, landed rows, duplicated host asks, and rows no provider
   can act on. Every reader is a janitor.
2. `PLAN.md` is the design reference (~50 KB). Full load for feature
   planning / design decisions / cross-cutting work; section load
   (`python scripts/docview.py headings PLAN.md`, then the section) for scoped
   module fixes; minimal check for routine test/doc/skill edits.
3. If the idea inbox is non-empty, scan `ideas/PIPELINE.md` and `ideas/INBOX.md`.
4. If your approach conflicts with a PLAN.md principle, do NOT implement it.
   Add the conflict to STATUS.md Concerns. PLAN.md changes require user approval.
5. Before drafting a design note that proposes a new MCP action, cites an
   unfixed `BUG-NNN`, or pins a sha, run
   `python scripts/check_primitive_exists.py {action <verb>|bug <BUG-NNN>|sha <sha>}`
   from origin/main (exit 2 = collision, investigate first).

### Updating the Three Files

| Message type | STATUS.md | PLAN.md |
|---|---|---|
| Decision, priority change, new concern, task state change, reframing | **Update immediately** before responding | **Update immediately** if design-relevant |
| New idea that won't be executed now | Capture in `ideas/INBOX.md` or `ideas/PIPELINE.md` | — |
| Code change request, bug fix, feedback, question | Update only if state actually changed | — |
| Greeting, clarification, small talk | — | — |

The rule: if the user closes the window after your next message, the files
already reflect any state change from what they said. Session task lists are
ephemeral — other sessions can't see them.

**Deletion is as important as addition.** On every STATUS.md write: resolved
concern → delete the line; landed row → delete (the commit is the record);
accepted design decision → move to PLAN.md; narrative → `activity.log`; detail
→ link a commit/spec/audit, entries stay ≤150 chars.

### Where new conventions live (provider-agnostic by default)

**`AGENTS.md` is the cross-provider standard** — every major coding agent
reads it. Project-level conventions go here first; provider-specific files
(`CLAUDE.md`, `.cursor/rules/*`, `.codex/*`) hold only genuine harness quirks
and should reduce to pointers at `AGENTS.md`. Self-check: *"Would a Codex or
Cursor session need this?"* If yes → here. When in doubt → here.

Drift guard: `python scripts/check_cross_provider_drift.py` (auto-fires as a
Claude Code PostToolUse hook; other providers run it manually after editing a
provider-specific file). Exit 2 = move the content here or tag the heading
`[<provider> only]`.

### Truth And Freshness

- Truth is typed: `AGENTS.md` owns process truth, `PLAN.md` design truth,
  `STATUS.md` live-state truth. Audits are diagnostic, never a fourth source.
- Verification claims carry a freshness stamp: date, environment, command.
- Concern rows: `[filed:YYYY-MM-DD]`, add `verified:YYYY-MM-DD` on re-check;
  severity prefix outside the bracket. Server-bug concerns cross-reference
  their wiki `BUG-NNN`.
- Contradictions are downgraded immediately — rewrite the stale claim or file
  a Concern before responding; labels `current:`/`historical:`/`contradicted:`.
- Audit docs decay: freshness-check before dispatching prescriptions from an
  audit older than ~24h.

### Client Conversations Are Bug Reports

When the user pastes a chat conversation from any MCP client, extract the
issues and fix them immediately.

### Large Docs And Artifacts

Use `python scripts/docview.py` (stat → headings/section/lines/search/json)
instead of raw whole-file reads for `PLAN.md`, `output/*/notes.json`, large
review artifacts, and any text/JSON file over ~10 KiB or 200 lines. Codex
truncates large raw reads.

### Project Skills

- Canonical skills live in `.agents/skills/`, mirrored to `.claude/skills/`
  for Claude Code (`powershell -ExecutionPolicy Bypass -File scripts/sync-skills.ps1`
  after editing). Unsure which skill? Start with `using-agent-skills`; if
  there is even a ~1% chance a skill applies, invoke it before acting.
  Core dev loop: `idea-refine` → `planning-and-task-breakdown` →
  `test-driven-development` / `debugging-and-error-recovery` →
  `code-review-and-quality` → `git-workflow-and-versioning` →
  `shipping-and-launch`.
- Outside project/paper/repo to learn from → `external-research-implications`.
- **Research-derived concepts need opposite-provider review before
  implementation** (Codex finding → Claude reviews; Claude finding → Codex
  reviews; other provider → name the reviewer in STATUS.md). The review
  re-checks sources + TinyAssets context, leaves a durable artifact, and gates
  build/push/rollout/acceptance. Hard provider limits activate the
  review-provider fallback under Quality Gates.

### Spec-driven development — OpenSpec is the standard [all providers]

Host directive 2026-07-19; process-budget calibration 2026-08-02.

- `openspec/specs/<capability>/spec.md` is as-built requirement truth;
  `openspec/changes/<name>/` holds in-flight change proposals. Lifecycle:
  explore → propose → apply → sync-specs → archive (`openspec` skill /
  `opsx:*`).
- **Every substantive change starts as an OpenSpec change** (behavior, MCP/API
  surface, storage shapes, capabilities, security posture), with its
  `applyRequires` artifacts done before implementation. **Skip-threshold:**
  trivial mechanical work — typos, formatting, comment/doc edits, test-only
  fixes changing no behavior, coordination-file edits — needs NO change. Do
  not spec the act of coordinating; specs describe product behavior.
- **Touch it → spec it:** still-unspecced capabilities get their spec written
  before or alongside their next substantive change
  (`spec-out-existing-platform` baseline).
- **Sync and archive on land, in the same lane.** A landed change with
  unsynced deltas is spec drift — a failing gate. Target-only/aspirational
  changes must never sync to `openspec/specs/` (as-built truth).
- Truth split: `PLAN.md` owns why (architecture/principles); `openspec/specs/`
  owns what (behavioral requirements).

#### Delivery flow (WIP discipline, review 2026-08-11)

- **Delta-first, never vision conversion.** One intent, one owner, one branch,
  one PR, explicit acceptance, ≤12 task checkboxes. Vision belongs in
  PLAN/design docs; park incidental findings in the idea feed.
- **One delivery change per exact session identity.** Before claiming/building
  a scaffolded change: `python scripts/openspec_flow.py check-change <name>
  --provider <session-specific-provider>`. Minting a new provider suffix to
  evade the limit is a review violation. A P0/security exception must name
  the exception and the WIP it displaces.
- **Finish before starting.** At dispatch/triage: `python
  scripts/openspec_flow.py audit` — prefer complete-but-unarchived, then
  smallest unblocked in-flight, then smallest P0/uptime dependency-removal
  slice, before admitting new work.
- **Backlog is bounded.** The live `openspec/changes/` inventory is a WIP
  queue, not an archive of ambitions: when it exceeds what active sessions are
  actually building, triage it (premise-verify → archive dead/landed changes)
  before proposing new ones. Legacy oversized changes are grandfathered for
  visibility, not blessed — pick concrete slices, don't fan out child changes.

#### OpenSpec drain [temporary bridge until cloud cutover]

The host restored the local autonomous drain after the 2026-08-02 de-bloat
test and directed on 2026-08-03 that it stay green and productive until the
cloud drain is accepted as running 24/7. Keep exactly the canonical tray and
guard tasks active; test-created scheduled tasks are leaks and must be removed.
At single-active cutover, stop and disable the local drain before activating
the cloud epoch so tray and cloud never claim concurrently. Historical rollback
evidence remains in `docs/audits/2026-08-02-process-debloat-rollback-test.md`;
the operational reference is
`docs/ops/2026-07-28-openspec-drain-supervisor.md`.

### Multi-Session Steering

Durable coordination belongs in files (`STATUS.md`, `ideas/*.md`,
`.agents/activity.log`), never in private chat memory. If two sessions may
converge on one idea, narrow the file boundary and record the split. A useful
idea left only in chat is lost work.

### Site preview / ship loop

The site lives in `WebSite/site/`. For any non-trivial site edit read
`.agents/skills/website-editing/SKILL.md` first — it owns the preview loop,
capture conventions, build/ship pipeline, and FUSE quirks.

---

## Team Norms

- **Claim before working.** Claiming communicates intent; file locking only
  handles races.
- **Verification is proactive.** Every substantive change gets independent
  verification before landing (persistent verifier teammate in Claude Code;
  focused tests + independent diff/subagent review elsewhere).
- **Scope-message before implementing self-found tasks** — one line to the
  lead, wait for approval; the step catches silent divergence.
- **Stuck 3+ iterations on the same error** → pause, reflect ("what failed,
  what specific change would fix it, am I repeating myself?"), then hand off
  for fresh perspective. Don't loop forever.
- **REFLECTION.md:** after a significant task, write what surprised you, one
  pattern worth capturing, one thing you'd do differently; the lead folds
  approved learnings into AGENTS.md or agent memory.
- Harness-specific team mechanics (SendMessage, despawn protocol, floater
  roster) live in `CLAUDE.md` / `LAUNCH_PROMPT.md` [Claude Code only].

### Quality Gates

**Verification is structural.** Substantive changes need test/check evidence
plus an independent review path before they count as landed. Self-review alone
is never enough for public-surface, storage, auth, migration, concurrency, or
data-loss-risk changes.

**`main` enforces a behavioural test gate (live 2026-08-03).** Required contexts
are `policy`, `Diff scope declared`, and `required-tests`, with `strict` on. So:
a PR merges only if `required-tests` is green, and only while up to date with
`main`. `required-tests` fails on any test failure not already listed in
`.github/known-failing-tests.txt` — that ledger is a one-way ratchet, so adding
a line to excuse a test you broke is a visible, reviewable edit on a
scope-guarded path. It runs a ~5-minute subset; the excluded heavy files run in
the non-required `full-tests` job on a best-effort schedule. Two consequences
worth knowing before you plan work: falling behind `main` costs a re-run, and
updating a drain PR's branch invalidates any exact-head review receipt.
Details and rollback: `docs/decisions/ADR-003-required-test-aggregator.md`.

**Review-provider limit fallback.** Opposite-provider review is first choice.
If that provider hits a hard account/subscription/usage limit, record dated
evidence, then dispatch a fresh-context independent reviewer from the
available provider against the exact commit. The reviewer is never the
author; blocking findings must be resolved before landing/rollout.
Inconvenience or disagreement does not activate this fallback.

**High-risk PRs stay draft until exact-head approval.** Auth, storage,
migration, concurrency, public-surface, and data-loss-risk PRs open as drafts
so auto-enrollment cannot merge them ahead of review. Ready only after an
approval artifact names the unchanged head SHA; any head-changing update
converts back to draft until fresh exact-head approval.

**Final chatbot-surface verification is a rendered chatbot conversation**
through the live connector at `https://tinyassets.io/mcp` (`ui-test` skill)
for any change affecting public MCP behavior, chatbot UX, connector tool
descriptions, user-visible node/workflow state, or `tinyassets.io`.
Host-visible rendered chatbot use is the
invariant; the automation transport is provider-specific. Direct MCP calls,
scripts, and canaries are supporting evidence, not final proof. Log rendered
prompt/result in `output/user_sim_session.md`.

**Post-fix clean-use evidence.** After fix + `ui-test`, look for real-user
clean use since the fix (production traces, logs, user-visible history),
freshness-stamped. None visible yet? Say so and leave a STATUS watch item
for public-surface/high-risk changes.

### Two Task Systems

Ephemeral in-session task lists are for sub-steps only. Anything that matters
beyond the session goes in the STATUS.md Work table — the durable,
cross-provider record.

---

## Parallel Dispatch

Multiple providers work concurrently; the host does not announce new sessions.
**STATUS.md Work table is the authoritative claim surface** — no external
locks, no runtime signaling. A fresh checkout with no chat history should be
productive in under a minute.

### Provider session-start ritual

0. `python scripts/session_sync_gate.py` — warns if the primary checkout is
   off `main` or behind origin/main. Advisory; auto-fires in Claude Code.
1. Read `STATUS.md` (Concerns + Work + Next).
2. `python scripts/worktree_status.py` — dirty checkouts, incomplete lanes,
   promotion gaps. Never switch a dirty checkout to `main`.
3. `python scripts/claim_check.py --provider <yourname>` — classifies rows
   CLAIMABLE / BLOCKED / IN-FLIGHT / HOST-OWNED / STALE-CLAIM.
4. `python scripts/provider_context_feed.py --provider <yourname> --phase claim`
   — context feed of provider memories, ideas, research artifacts, handoffs.
   Candidates must be promoted into a STATUS/worktree/PR lane before they
   become build authority; it is a feed, not a backlog writer.
5. **Claim by editing STATUS.md** — set the row's Status to
   `claimed:<yourname>` (session-specific name when ambiguous, e.g.
   `codex-gpt5-desktop`). Commit the edit; the edit IS the claim.
6. **Scan cross-implications before building** — compare your task against
   active rows, `ideas/PIPELINE.md`, and recent research/design artifacts; add
   a `Depends` edge or record why not applicable. Never bypass an
   opposite-provider review gate because your task is named differently.
7. **Work in a worktree or branch.** Do not write outside your row's Files
   without updating STATUS.md first.
8. **On land**, delete the row in the same commit. The commit is the audit
   trail.

Run `provider_context_feed.py` again at later checkpoints (`--phase
plan|build|review|foldback|memory-write`) when narrowing or advancing durable
work; read the relevant candidates and promote or note why they don't apply.

### Work-table row schema

- **Files** — what this task will WRITE; the collision boundary. Concrete
  paths, not areas. Read-only deps go in Depends. Row-lifecycle edits to
  STATUS.md itself are implicit (`claim_check.py` ignores an exact `STATUS.md`
  atom).
- **Depends** — tasks that must merge first + file-read dependencies.
- **Status** — `pending`, `claimed:<provider>`, `in-flight`, `dev-ready`,
  `host-action`, `host-decision`, `host-review`, `monitoring`, `done`.
  `claimed:*`/`in-flight` = Files off-limits to others.

### Stale-claim reaping

A claim with no commits on its Files in 24h and no `ACTIVE YYYY-MM-DD`
heartbeat is stale. Any provider may reap: set
`reaped:<yourname>:no-activity-24h`, then re-claim. The convention is the
policy. A heartbeat in the row text keeps uncommitted active work alive.

### Pre-claim collision guard

Before adding a row or broadening Files:
`python scripts/claim_check.py --provider <yourname> --check-files "<paths>"`.
On overlap: add a Depends edge, or narrow your Files.

### GitHub-Aligned Worktree Discipline

A worktree is the local checkout for one branch; the branch folds back through
a PR. **A branch is not durable memory** — the durable layer is `_PURPOSE.md`,
`.agents/worktrees.md`, STATUS.md, idea files, and draft-PR bodies.

**Full procedure → [`docs/reference/worktree-discipline.md`](docs/reference/worktree-discipline.md).**
Invariants:

- Four lane states, exactly one per branch: Active (STATUS row + worktree +
  `_PURPOSE.md`), Parked draft (pushed branch + draft PR with ship/abandon
  conditions), Idea/reference only (no build authority), Abandoned/swept
  (removed or logged in `.agents/worktrees.md`; extract ideas first).
- Lifecycle via tooling: `python scripts/wt.py new|done|list` (creates off
  `origin/main`, scaffolds `_PURPOSE.md`; `done` refuses unmerged branches).
- Never switch a dirty checkout to `main`; merging to `main` is
  production-impacting.
- Inherited work requires memory refs: read the prior provider's
  memory/artifact paths (from `_PURPOSE.md` / STATUS row / PR body) before
  coding; if none listed, search `.claude/agent-memory/`,
  `.agents/activity.log`, recent audits by slug first.
- Review-blocked work gets a visible lane but stays at planning/scaffolding
  until the required review returns approve/adapt.
- Legacy docs/ideas/memories are context, not build queues — promote into a
  current STATUS/PLAN lane before building from them.

### Staying unblocked

Zero CLAIMABLE rows? Pick cross-cutting work (docs hygiene, skill audits,
test surface, audit follow-ups) and ADD a Work row for it — keep the next
provider's `claim_check.py` accurate.

---

## Hard Rules

1. **SqliteSaver only** -- not AsyncSqliteSaver (not production-safe).
2. **LanceDB singleton** -- reuse connection objects, never recreate.
3. **No API SDKs for primary writer** -- Claude/Codex use `claude -p` and `codex exec` subprocesses.
4. **Executable gates need autonomous defaults** -- never block a workflow gate on human input when a safe default exists. True host-only authority only as a concrete `host-decision`/`host-action` row with the smallest ask; it must not block unrelated autonomous work.
5. **TypedDict + Annotated reducers** -- `Annotated[list, operator.add]` for accumulating fields.
6. **FactWithContext with truth-value typing** -- every extracted fact needs source_type, reliability, temporal_bounds, language_type.
7. **Python 3.11+** required.
8. **Fail loudly, never silently.** Mock fallbacks that look like real output are worse than crashes.
9. **User uploads are authoritative.** Preserved verbatim — never summarize, truncate, or reformat.
10. **Contributor attribution uses `CONTRIBUTORS.md`.** When `attribution_credit` rows exist on ship, map each `actor_id` to a GitHub handle and emit `Co-Authored-By:` lines; unknown actor_id → skip silently, never block a commit.
11. **Public-surface changes verify post-change.** After any edit to DNS, Cloudflare tunnel, or any surface affecting `tinyassets.io`: `python scripts/mcp_public_canary.py --url https://tinyassets.io/mcp` must go green; MCP tool-surface changes additionally need `--assert-handles` (canonical set: `read_graph`/`write_graph`/`run_graph`/`read_page`/`write_page`/`converse` + optional `get_status`; as-built truth `openspec/specs/live-mcp-connector-surface/spec.md`). The canary is required evidence, not final chatbot-surface proof (see Quality Gates). Canonical public endpoint is `https://tinyassets.io/mcp` only; `mcp.tinyassets.io` is an Access-gated internal origin — never document it user-facing. Rationale: the 2026-04-19 P0 outage had no commit touching the broken surface (`docs/audits/2026-04-20-public-mcp-outage-postmortem.md`); probe catalog: `docs/ops/acceptance-probe-catalog.md`.
12. **Portfolio graph stays current.** Before changing public-facing docs/status/structure/lineage, check `PROJECT_GRAPH.yml` + `docs/portfolio/` standards and update the affected manifest/lineage notes. Public-draft by default; publishing stays gated by scan/review.
13. **No destructive git ops without explicit approval.** No `git reset --hard`, `git checkout --`, `git restore`, `git clean`, force-push, or stash/drop as cleanup or diagnostics unless the host explicitly asks. Never switch a dirty worktree to `main`.
14. **Merged is not deployed.** Actions-app merges via `GITHUB_TOKEN` do not trigger workflows (five PRs landed 2026-07-21, zero deployed). Before claiming shipped: `get_status` → `release_state.git_sha` must contain your commit. `release-reconcile.yml` self-heals drift every 15 min; the claim still needs the sha.

---

## Testing

- `pytest` for the full suite; `ruff check` before committing. Every module
  has tests; nodes must never crash.
- After canonical `tinyassets/*` edits affecting the Claude plugin runtime:
  `python packaging/claude-plugin/build_plugin.py` (pre-commit mirror parity
  is the guardrail; see `packaging/INDEX.md`).
- `actionlint` on GH Actions edits (pre-commit runs it on staged workflow
  files; CI is the authoritative gate).
- **Hot-path rewrites use differential testing:** keep the original verbatim
  in the suite as executable spec; differential-test the rewrite (randomized
  tie-heavy trials + scale gate). Reference: `tests/test_match_scale.py`.
- **Sandbox test-temp hygiene:** point sandbox `--basetemp`/`TMPDIR` OUTSIDE
  the repo. Sandbox-created in-repo temp dirs on Windows carry ACLs that
  survive teardown and need elevated `takeown`+`icacls` to clear.

---

## Configuration — environment variables

All configuration is env vars. Full catalog (pointer-loaded per
[ADR-002](docs/decisions/ADR-002-static-vs-dynamic-context-budget.md)):

> **Canonical reference → `docs/reference/environment-variables.md`.**

Inline invariants:

- **CWD-independent resolvers only:** `tinyassets.storage.data_dir()` for
  `TINYASSETS_DATA_DIR`, `wiki_path()` for the wiki root — never `Path.cwd()`
  logic or re-implemented precedence.
- **Container deploys:** `TINYASSETS_DATA_DIR=/data` + bind-mount
  (`deploy/README.md`).
- **Subscription-only by default:** API-key provider env vars are ignored
  unless `TINYASSETS_ALLOW_API_KEY_PROVIDERS` is truthy.
- **Local secrets are vault-first:** `set -a; source scripts/load_secrets.sh;
  set +a` (`TINYASSETS_SECRETS_VENDOR`), never a committed plaintext file.
  Canonical keys: `scripts/secrets_keys.txt`.

---

## Project Files

| File | Audience | Purpose |
|------|----------|---------|
| `AGENTS.md` | Any AI, any tool | How to work, team norms, hard rules. |
| `STATUS.md` | Any AI, any tool | Live state: task board, concerns, next. |
| `PLAN.md` | Any AI, any tool | Architecture, principles, design decisions. |
| `README.md` / `INDEX.md` | Any human or AI | Orientation / repo map. |
| `CLAUDE.md` / `CODEX.md` | One harness | Thin routing layers over AGENTS.md. |
| `scripts/docview.py` | Any AI | Scoped reader for large artifacts. |
| `scripts/claim_check.py` | Any AI | Work-row classifier + collision guard. |
| `scripts/worktree_status.py` | Any AI | Worktree lane diagnostics. |
| `scripts/provider_context_feed.py` | Any AI | Lifecycle context-feed checkpoints. |
| `scripts/openspec_flow.py` | Any AI | OpenSpec WIP check + finish-first audit. |
| `.agents/skills/*/SKILL.md` | Canonical | Skill definitions (edit here first; mirror via `scripts/sync-skills.ps1`). |
| `.claude/agent-memory/<name>/` | Teammate `<name>` writes; all read | Per-teammate memory. Non-owners never write here. |
| `.agents/activity.log` | Any AI | Short cross-session activity feed. |
| `ideas/*.md` | Any AI | Idea capture, triage, traceability. |
| `docs/reference/*.md` | Any AI | Pointer-loaded canonical procedure docs. |
| `docs/exec-plans/*.md`, `docs/audits/*.md` | Any AI | Execution plans; dated diagnostic audits. |
