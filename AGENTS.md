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

## Two Living Files

Updated immediately when durable state changes.

| File | What belongs here | What does NOT belong here |
|------|-------------------|--------------------------|
| **AGENTS.md** | How to work on this project. Behavior, norms, hard rules. | Architecture, design decisions, principles (-> PLAN.md) |
| **PLAN.md** | How the system works and why. Architecture, principles, design decisions, module specs. | Behavioral norms (-> AGENTS.md). Live state (-> the homes below) |

Live state has no living file. It has typed homes:

| Kind of state | Home |
|---|---|
| Queued and in-flight work | `openspec/changes/` — `python scripts/openspec_flow.py audit` |
| Unresolved findings | `docs/concerns/` — one file each, deleted when resolved |
| Work only the founder can do | `docs/host-actions.md` |
| Who is working on what | git branches and open PRs |
| Session narrative | `.agents/activity.log` |
| Landing records | the git log |

> **`STATUS.md` was retired 2026-08-25.** It was a prose blob 5.2x over the
> ceiling it declared for itself, touched by 46% of commits in its last 90 days
> and by 17% that changed nothing else. Its contents went to the homes above.
> Do not recreate it: a single always-loaded file that absorbs every kind of
> live state is the failure mode, not the format.

---

## How to Work

### Orient

1. `PLAN.md` is the design reference (~50 KB). Full load for feature planning /
   design decisions / cross-cutting work; section load
   (`python scripts/docview.py headings PLAN.md`, then the section) for scoped
   module fixes; minimal check for routine test/doc/skill edits.
2. `python scripts/openspec_flow.py audit` is the work queue. Skim
   `docs/concerns/README.md` when the task touches a known-unresolved area.
3. If the idea inbox is non-empty, scan `ideas/PIPELINE.md` and `ideas/INBOX.md`.
4. If your approach conflicts with a PLAN.md principle, do NOT implement it.
   File it in `docs/concerns/`. PLAN.md changes require user approval.
5. Before drafting a design note that proposes a new MCP action, cites an
   unfixed `BUG-NNN`, or pins a sha, run
   `python scripts/check_primitive_exists.py {action <verb>|bug <BUG-NNN>|sha <sha>}`
   from origin/main (exit 2 = collision, investigate first).

### Keeping state current

If the user closes the window after your next message, durable state must
already reflect anything they said. Match effort to the message:

| Message type | Do this |
|---|---|
| Decision, priority change, new finding, reframing | Write it to its home (above) before responding; update `PLAN.md` if design-relevant |
| New idea that will not be executed now | `ideas/INBOX.md` or `ideas/PIPELINE.md` |
| Code change, bug fix, question | Check mentally; write only if state actually changed |
| Greeting, clarification, small talk | Nothing |

**Deletion is as important as addition.** A resolved concern gets its file
deleted, not marked DONE. A landed change gets archived, not annotated. The
commit is the record.

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
  `openspec/specs/` behavioural truth. Audits are diagnostic, never a source.
- Verification claims carry a freshness stamp: date, environment, command.
- Concern files carry `**Filed:**` / `**Verified:**` / `**Re-verified:**` and a
  severity. Re-verify a premise before acting on it and correct the citation in
  place — paths and line numbers rot faster than findings do. Server-bug
  concerns cross-reference
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
  reviews; other provider → name the reviewer in the change). The review
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
- **Reviews pipeline; never idle on one [all sessions, host 2026-08-24].** A
  dispatched cross-family/peer review (or any background agent) runs on the
  peer's budget and re-invokes you when it returns, so it gates LANDING
  (merge/deploy/flip-on), NOT your forward progress. The standard build pipeline
  for every session: build slice A → dispatch its review in the **background**
  (`peer_agent.py` / `codex_review.py`, `run_in_background`) → **immediately pick
  up the next lane** → fold each verdict in when it lands (fix findings →
  re-review → land). A pending review is a wait state, not a stopping point: do
  NOT stop, sit idle, or ask the host "should I wait?" while one runs. This
  complements *Finish before starting* — the review IS part of finishing the
  slice, so you advance the pipeline while it runs rather than blocking on it.
  (Only genuine external blockers — a host-only secret/decision, a broken
  harness, an unresolved review verdict on THE lane you'd advance into — stop a
  lane; pick a different lane instead of idling.)

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

**Review sequencing — shape before hardening (founder directive 2026-08-20).**
Reviews run in a fixed order, and the order is load-bearing:
1. **Pre-first-build / first-draft review = SHAPE + APPROACH.** One pass, not a
   gauntlet. It catches architecture/approach problems (fail-closed vs fail-open,
   one general primitive vs per-channel spaghetti, the right authority/ownership
   model) and basic-safety holes that leak/exfil/bypass even for a single user.
   Architectural reviews and rebuilds belong here.
2. **Ship LIVE as MVP** — flip the dark flags on, deploy — and **test as a real
   user** through Slack / the app / the chatbot connector. The live user path is
   the shape oracle: it is the only thing that proves the shape + UX flow are
   right.
3. **THEN the deep security-hardening rounds** — concurrency, TOCTOU,
   durability/crash, timing side-channels, migrations of hypothetical prior
   state, abuse-at-scale. These run AFTER live-MVP user testing.
Do NOT gate a first-draft MVP behind multiple hardening rounds — that is
"endless hardening of the wrong shape," and only live users reveal whether the
shape is right. The split: a hole that leaks/exfils/bypasses for ONE founder =
fix pre-live (basic-safety); an edge that only bites multi-tenant / concurrent /
crash = defer to post-live hardening, tracked in the change's `REVIEW.md`.

**Verification is structural.** Substantive changes need test/check evidence
plus an independent review path before they count as landed. The PRE-live review
is the shape/approach pass above (one round); the multi-round adversarial
hardening is post-live-MVP. Self-review alone is never enough for public-surface,
storage, auth, migration, concurrency, or data-loss-risk changes — but for a
first-draft MVP the pre-live bar is shape + basic-safety, and deep hardening
follows live user testing.

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
converts back to draft until fresh exact-head approval. For a first-draft MVP
that approval is the SHAPE + basic-safety pass (§ Review sequencing) — not a
completed hardening gauntlet; the deep hardening rounds re-run post-live.

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
| `docs/concerns/` | Any AI, any tool | Unresolved findings, one file each. |
| `docs/host-actions.md` | Any AI, any tool | Work only the founder can do. |
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
