# TinyAssets

A goal-agnostic daemon engine. Bind it to a domain and let it run. The platform
supports any multi-step AI workflow — research papers, screenplays, recipe
trackers, novels, news summaries, any substantive long-running work.

---

## Forever Rule (2026-04-18): Complete-System 24/7 Uptime Is Top Priority

One unified priority, not a ranked list. **Every surface works 24/7 with zero
hosts online** — Tier-1 chatbot users through the live connector, Tier-2 daemon
hosts installing the tray in under 5 minutes, Tier-3 contributors cloning and
running cleanly, plus discovery, remix, converge, live collaboration, the
paid-market inbox, and moderation.

**Work ordering:** pick the task that unblocks the largest currently-broken
uptime surface, and treat every surface outage as equal severity — tiering is
what starves the quiet surfaces. Break ties by shared dependency impact, then
shortest path to verified recovery. Uptime features ship with the Hard Rule 14
proof or they are not done. Everything else continues but never blocks uptime.

Target architecture: `docs/design-notes/2026-04-18-full-platform-architecture.md`.

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
  after editing). Ten skills, named for their task — read the matching one.
  There is no router: it earned its keep at 34 skills and stopped earning it
  at 10.
- **Each remaining skill carries project knowledge you cannot infer from the
  repo.** The 24 deleted on 2026-08-25 encoded generic software practice a
  current model already has. Before adding one back, answer the question that
  removed them: *which model weakness does this encode, and does a current
  model still have it?*
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

#### Delivery flow

Full procedure: **[`docs/reference/delivery-flow.md`](docs/reference/delivery-flow.md)**.
Headline: one intent, one owner, one branch, one PR, ≤12 task checkboxes;
**finish before starting** (`python scripts/openspec_flow.py audit` prefers
complete-but-unarchived, then smallest unblocked in-flight); the change
inventory is a WIP queue, not an archive of ambitions.

### Site preview / ship loop

The site lives in `WebSite/site/`. For any non-trivial site edit read
`.agents/skills/website-editing/SKILL.md` first — it owns the preview loop,
capture conventions, and the build/ship pipeline.

---

## Working Norms

Two providers work this repo — Claude Code and Codex CLI — and they call each
other as peers via the `peer-agents` skill. Neither runs a standing team.

- **Verification is proactive and cross-family.** Every substantive change gets
  independent verification before landing. The independent path is a subprocess
  peer of the *other* family, on that subscription's budget — not a same-family
  teammate reviewing its own family's work.
- **Stuck 3+ iterations on the same error** → stop. Say what failed, what
  specific change would fix it, and whether you are repeating yourself; then
  hand it to the other family for fresh eyes. Don't loop.
- **Record what the next session needs**, in the home that fits (see § *Two
  Living Files*): a finding in `docs/concerns/`, a durable lesson in memory or a
  skill, narrative in `.agents/activity.log`. A learning left only in chat is
  lost work.

### Quality Gates

Invariants. Full procedure: **[`docs/reference/quality-gates.md`](docs/reference/quality-gates.md)**.
Which rules are executable, where they run, and which are deliberately still
judgement: **[`docs/reference/executable-gates.md`](docs/reference/executable-gates.md)**.

- **Shape before hardening** (founder, 2026-08-20). One pre-build review for
  SHAPE + APPROACH and single-user safety holes → ship the MVP live and test as
  a real user → *then* the deep hardening rounds. Do not gate a first draft
  behind a hardening gauntlet; only live users prove the shape. Split: a hole
  that leaks/exfils/bypasses for ONE founder is pre-live; an edge that only
  bites multi-tenant/concurrent/crash defers to post-live.
- **Verification is structural, and independent.** Substantive changes need
  test evidence plus a review path that is not the author. Self-review is never
  enough for public-surface, storage, auth, migration, concurrency, or
  data-loss-risk changes. Prefer the opposite model family, dispatched as a
  subprocess on its own budget (`peer-agents`).
- **A dispatched review gates landing, not your forward progress.** It runs in
  the background and re-invokes you. Pick up the next lane; fold the verdict in
  when it returns. Never idle waiting on one.
- **`main` enforces a behavioural test gate.** Required contexts: `policy`,
  `Diff scope declared`, `required-tests`, `strict` on. `required-tests` fails
  on any failure not in `.github/known-failing-tests.txt` — a one-way ratchet
  on a scope-guarded path.
- **High-risk PRs stay draft until exact-head approval**, and for auth,
  credential, and permission paths this is enforced — `pr-scope-guard`
  demands an exact-head receipt in the PR body. Any head-changing update
  invalidates it.
- **Final chatbot-surface proof is a rendered chatbot conversation** through
  the live connector at `https://tinyassets.io/mcp` (`ui-test`). Direct MCP
  calls, scripts, and canaries are supporting evidence, never final proof.
- **Then look for real-user clean use since the fix**, freshness-stamped. If
  none is visible yet, say so rather than implying it.

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
14. **Merged is not deployed.** Actions-app merges via `GITHUB_TOKEN` do not trigger workflows (five PRs landed 2026-07-21, zero deployed). Before claiming shipped, run the gate: `python scripts/deployed_sha.py --assert-contains <sha>` — it reads `release_state.git_sha` off the live surface and exits 1 if production does not contain your commit, 2 if it cannot tell. `release-reconcile.yml` self-heals drift every 15 min; the claim still needs the sha.

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

All configuration is env vars. Full catalog:
**[`docs/reference/environment-variables.md`](docs/reference/environment-variables.md)**
(pointer-loaded per [ADR-002](docs/decisions/ADR-002-static-vs-dynamic-context-budget.md)).
Load-bearing invariants stay here:

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
| `scripts/worktree_status.py` | Any AI | Worktree lane diagnostics. |
| `scripts/openspec_flow.py` | Any AI | OpenSpec WIP check + finish-first audit. |
| `.agents/skills/*/SKILL.md` | Canonical | Skill definitions (edit here first; mirror via `scripts/sync-skills.ps1`). |
| `.claude/agent-memory/<name>/` | `<name>` writes; all read | Per-agent memory. Non-owners never write here. |
| `.agents/activity.log` | Any AI | Short cross-session activity feed. |
| `ideas/*.md` | Any AI | Idea capture, triage, traceability. |
| `docs/reference/*.md` | Any AI | Pointer-loaded canonical procedure docs. |
| `docs/exec-plans/*.md`, `docs/audits/*.md` | Any AI | Execution plans; dated diagnostic audits. |

When you delete or rename a tracked file, update its row in the same change.
