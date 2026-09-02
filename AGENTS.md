# TinyAssets

A goal-agnostic daemon engine. Bind it to a domain and let it run. The platform
supports any multi-step AI workflow — research papers, screenplays, recipe
trackers, novels, news summaries, any substantive long-running work.

---

## Forever Rule: 24/7 uptime, zero hosts online

One unified priority, not a ranked list. **Every surface works with no host
online** -- chatbot users through the live connector, daemon hosts installing
the tray in under 5 minutes, contributors cloning and running cleanly, plus
discovery, remix, converge, the paid-market inbox, and moderation.

**Work ordering:** take the task unblocking the largest currently-broken uptime
surface, and treat every outage as equal severity -- tiering is what starves the
quiet surfaces. Break ties by shared dependency impact, then shortest path to
verified recovery. Everything else continues but never blocks uptime.

Architecture: `docs/design-notes/2026-04-18-full-platform-architecture.md`.

---

## Two Living Files

**AGENTS.md** (here) is how to work: behaviour, norms, hard rules.
**PLAN.md** is how the system works and why: architecture, principles, design.
Architecture never goes here; norms never go there. Both update immediately when
durable state changes.

**Live state has no living file.** It has homes by kind:

| Kind | Home |
|---|---|
| Queued / in-flight work | `openspec/changes/` -- `python scripts/openspec_flow.py audit` |
| Unresolved findings | `docs/concerns/` -- one file each, deleted when resolved |
| Founder-only work | `docs/host-actions.md` |
| Who is working on what | git branches and open PRs |
| Narrative / landings | `.agents/activity.log` / the git log |

> **Do not recreate `STATUS.md`** (retired 2026-08-25: 5.2x over its own declared
> ceiling, touched by 46% of its last 90 days of commits). One always-loaded file
> absorbing every kind of live state is the failure mode, not the format.

---

## How to Work

### Orient

1. `PLAN.md` is the design reference. Full load for feature planning or design
   decisions; `python scripts/docview.py headings PLAN.md` then one section for
   scoped work; skip for routine test/doc edits.
2. `python scripts/openspec_flow.py audit` is the work queue. Skim
   `docs/concerns/README.md` when the area has known-unresolved findings.
3. An approach conflicting with a `PLAN.md` principle does not get implemented --
   file it in `docs/concerns/`. PLAN.md changes need user approval.
4. Before a design note proposing a new MCP action, citing an unfixed `BUG-NNN`,
   or pinning a sha: `python scripts/check_primitive_exists.py` (exit 2 =
   collision).

### Keeping state current

If the user closed the window after your next message, durable state must
already reflect anything they said. Decisions, priority changes, and new
findings get written to their home (above) before you respond; design-relevant
ones also update `PLAN.md`. Ideas that will not be executed now go to
`ideas/INBOX.md`. Greetings and questions change nothing — do not write.

**Deletion matters as much as addition.** Resolve a concern by deleting its
file; archive a landed change rather than annotating it. The commit is the record.

### Where new conventions live

A convention any provider would need goes in `AGENTS.md`. Provider-specific
files (`CLAUDE.md`, `CODEX.md`) hold only harness quirks. In doubt, `AGENTS.md` —
broader visibility is the safer error. Enforced by `cross-provider-drift`.

### Truth And Freshness

- Truth is typed: `AGENTS.md` owns process, `PLAN.md` design, `openspec/specs/`
  behaviour. Audits are diagnostic, never a source.
- Verification claims carry date, environment, and the command that produced them.
- **Re-verify a premise before acting on it, and correct the citation in place.**
  Paths and line numbers rot faster than findings do. A stale pointer misleads
  worse than no pointer.
- Contradicted claim → fix it or file `docs/concerns/` before responding.

### Client Conversations Are Bug Reports

A pasted chat from any client is a bug report. Extract the issues and fix them.

### Large Docs And Artifacts

Use `python scripts/docview.py` (`stat`, `headings`, `section`, `lines`,
`search`, `json`) instead of whole-file reads for anything large -- `PLAN.md`,
`output/*/notes.json`, big review artifacts. Narrow the query rather than
falling back to a raw read.

### Project Skills

Canonical in `.agents/skills/`, mirrored to `.claude/skills/`
(`powershell -ExecutionPolicy Bypass -File scripts/sync-skills.ps1` after
editing). Seven skills named for their task -- read the matching one; there is no
router. Each carries project knowledge you cannot infer from the repo. The 24
deleted on 2026-08-25 encoded generic practice a current model already has;
before adding one back, answer the question that removed them: **which model
weakness does this encode, and does a current model still have it?**

Research-derived concepts need opposite-provider review before implementation
(Codex finding -> Claude reviews, and vice versa), leaving a durable artifact
that gates build/push/rollout.

### Spec-driven development -- OpenSpec is the standard

Host directive 2026-07-19.

- `openspec/specs/<capability>/spec.md` is as-built requirement truth;
  `openspec/changes/<name>/` holds in-flight proposals. Lifecycle: explore ->
  propose -> apply -> sync -> archive (`openspec` skill).
- **Spec what is hard to reverse, build the rest.** A change directory is
  required for the things a wrong guess makes expensive: **public MCP/API
  surface, storage shape, authority/permissions, migrations, money**. Those get
  proposal + design before code.
- **Everything else: build it, prove it live, then write the spec from what
  shipped.** Bug fixes, internal refactors, UI, docs, tests, and single-surface
  behaviour changes do not wait on a proposal. Writing the spec after the fact
  is not a shortcut -- it is more accurate, because it describes what actually
  works rather than what was predicted.
- **Rationale (measured 2026-08-26).** 67 active changes, median 23 days idle,
  50 of 67 untouched in a fortnight. A mandatory pre-build proposal is the step
  a fresh project folder does not have, and it is where idea-to-deployed stalls.
  The founder's comparison was explicit: an empty folder iterated dramatically
  faster than this repo.
- **Sync and archive on land, same lane.** A landed change with unsynced deltas
  is spec drift -- treat it as a failing gate.
- Truth split: `PLAN.md` owns *why*; `openspec/specs/` owns *what*.

#### Delivery flow

**A WIP limit you cannot satisfy is a wall, not a limit.** With 67 changes open
and three quarters idle, "finish before starting" blocked new work without
draining old. Prefer: finish or **archive**. A change idle 14 days is not
in flight -- archive it and re-propose when it is real. Archiving is free and
reversible; git holds it.


Full procedure: **[`docs/reference/delivery-flow.md`](docs/reference/delivery-flow.md)**.
Headline: one intent, one owner, one branch, one PR, ≤12 task checkboxes;
**finish before starting** (`python scripts/openspec_flow.py audit` prefers
complete-but-unarchived, then smallest unblocked in-flight); the change
inventory is a WIP queue, not an archive of ambitions.

### Site preview / ship loop

The site lives in `WebSite/site-react/`. For any non-trivial site edit read
`.agents/skills/website-editing/SKILL.md` first — it owns the preview loop,
capture conventions, and the build/ship pipeline.

---

## Working Norms

Two providers work this repo -- Claude Code and Codex CLI -- calling each other
as peers via `peer-agents`. Neither runs a standing team.

- **Verification is cross-family**, on the peer's own budget: not a same-family
  teammate reviewing its own family's work.
- **Stuck 3+ iterations on the same error -> stop.** Say what failed, what
  specific change would fix it, and whether you are repeating yourself; then
  hand it to the other family. `scripts/supervisor.py` watches for this.
- **Record what the next session needs** in the home that fits. A learning left
  only in chat is lost work.

### Quality Gates

Procedure: **[`docs/reference/quality-gates.md`](docs/reference/quality-gates.md)**.
Enforced vs judgement: **[`docs/reference/executable-gates.md`](docs/reference/executable-gates.md)**.

- **Shape before hardening** (founder, 2026-08-20). One pre-build review for
  shape, approach, and single-user safety holes -> ship the MVP live and test as
  a real user -> *then* deep hardening. Gating a first draft behind a hardening
  gauntlet hardens a shape live users may change.
- **Verification is independent and cross-family.** Test evidence plus a
  reviewer who is not the author: a subprocess peer of the *other* model family
  (`peer-agents`), on its own budget. Self-review never suffices for
  public-surface, storage, auth, migration, concurrency, or data-loss changes.
- **A dispatched review gates landing, not your progress.** It re-invokes you;
  take the next lane and fold the verdict in. Never idle on one.
- **Three rounds, then escalate.** A review round that returns findings is not a
  reason to run another one. Published evidence: defect counts across repeated
  audit rounds are *non-monotonic* (15, 8, 12, 2, 8, 1, 4, 1, 0 over nine
  rounds), a second independent reviewer adds ~nothing over the first, and three
  well-structured agents beat five. There is no published convergence rule, so
  the cap is the rule. After the third round, take the remaining findings to the
  founder with what you fixed and what you did not -- do not open a fourth.
  Fixing round N's findings often *creates* round N+1's, which is a loop, not
  progress. (PR #2561 ran six rounds; rounds 4 and 5 each found weaknesses in
  tests written one round earlier.)
- **Ask the reviewer to disagree in a structured way** -- `AGREE` /
  `DISAGREE_EVIDENCE` with a code citation / `DISAGREE_CONCERN`. Structured
  disagreement measurably beat adding more reviewers, and it makes a finding you
  should act on separable from one you should note.
- **Final chatbot-surface proof is a rendered conversation** through the live
  connector (`ui-test`). Scripts and canaries are supporting evidence, never
  proof. Then look for real-user clean use since the fix, freshness-stamped; if
  none is visible, say so.

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
12. ~~Portfolio graph~~ — **CUT 2026-08-27.** It required consulting `PROJECT_GRAPH.yml`, which has never existed in this repo; 328 public-surface commits since June, 4 touched `docs/portfolio/`. Number kept so "Hard Rule 13/14" citations elsewhere stay correct.

13. **Inventory before you destroy; approval is not diligence.** No `git reset --hard`, `git checkout --`, `git restore`, `git clean`, force-push, or stash/drop as cleanup unless the host explicitly asks — and even then, **first prove what is unique.** For every path in scope: is it on a remote, or reachable in history? If neither, preserve it before acting. Approval settles *whether* to discard, never *what*. On 2026-08-26 a dirty checkout that looked like stale cruft held 4,711 lines of research existing nowhere else, two reference docs `AGENTS.md` had been citing for months, and — because this repo is PUBLIC — an unignored data room. A plain "yes, clean it" would have destroyed all three. Never switch a dirty worktree to `main`.
14. **Merged is not deployed.** Actions-app merges via `GITHUB_TOKEN` do not trigger workflows (five PRs landed 2026-07-21, zero deployed). Before claiming shipped, run the gate: `python scripts/deployed_sha.py --assert-contains <sha>` — it reads `release_state.git_sha` off the live surface and exits 1 if production does not contain your commit, 2 if it cannot tell. `release-reconcile.yml` self-heals drift every 15 min; the claim still needs the sha.

---

## Testing

- `pytest` for the suite, `ruff check` before committing. Every module has
  tests; nodes never crash.
- **Never point a temp root inside the repo.** `tests/conftest.py` refuses to
  start if `--basetemp`/`TMPDIR`/`TEMP`/`TMP` resolves under it. Sandbox agents
  create those dirs under a restricted token, and the resulting Windows ACL
  locks you out entirely -- you cannot delete, list, or even read it, and a
  reboot does not help. Cleanup needs an elevated
  `scripts/clear_sandbox_temp_dirs.ps1 -Apply`.
- After canonical `tinyassets/*` edits affecting the plugin runtime:
  `python packaging/claude-plugin/build_plugin.py` (`mirror-parity` gates it).
- `actionlint` on workflow edits; CI is authoritative.
- **Hot-path rewrites use differential testing:** keep the original in the suite
  as executable spec and differential-test the rewrite
  (`tests/test_match_scale.py`).
- **A local Windows run is not an oracle on its own.** Pin the tree and
  set-compare against the same suite at base before calling anything a
  regression. **Run the Linux oracle before pushing anything that touches the
  sandbox, the filesystem helpers, process limits or the workspace:**
  `python scripts/linux_oracle.py -- -q tests/<file>.py` runs the WORKING TREE
  (uncommitted changes included) in a container with CI's Python 3.11, git 2.47
  and bubblewrap — the two things this host cannot supply at all being a real
  jail and POSIX descriptor semantics. It is not a CI replacement; CI stays
  authoritative. It exists because six CI rounds on `workspace-node` were spent
  on failures of one shape: the behaviour changed, Windows went green, and a
  test encoding the OLD contract survived because its assertion only runs on
  POSIX. A green Windows suite that skipped 40 tests is not a green suite —
  `python scripts/skip_census.py` says what a run did not cover.

## Configuration -- environment variables

All configuration is env vars. Catalog:
**[`docs/reference/environment-variables.md`](docs/reference/environment-variables.md)**.
Load-bearing invariants:

- **CWD-independent resolvers only** -- `tinyassets.storage.data_dir()`,
  `wiki_path()`. Never `Path.cwd()` logic or a re-implemented precedence.
- **Containers:** `TINYASSETS_DATA_DIR=/data` + bind-mount (`deploy/README.md`).
- **Subscription-only by default:** API-key provider vars are ignored unless
  `TINYASSETS_ALLOW_API_KEY_PROVIDERS` is truthy.
- **Secrets are vault-first:** `set -a; source scripts/load_secrets.sh; set +a`.
  Never a committed plaintext file.

## Project Files

`README.md` orients. `AGENTS.md` (here) is how to work; `PLAN.md` is how the
system works; live state lives in the typed homes above. Canonical skills in
`.agents/skills/`, per-agent memory in `.claude/agent-memory/<name>/` (owner
writes, everyone reads). **Delete or rename a tracked file -> update every
reference to it in the same change.**
