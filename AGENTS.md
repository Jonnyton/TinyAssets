# TinyAssets

A goal-agnostic daemon engine: bind it to a domain and let it run. Architecture:
`PLAN.md` and `docs/design-notes/2026-04-18-full-platform-architecture.md`.

---

## The rulebook only shrinks

**The rulebook only shrinks: a new rule must displace an old one; the ratchet
enforces it.** `python scripts/check_context_budget.py --strict` pins this file,
`CLAUDE.md`, and the `docs/reference/` and `.agents/skills/` sets, so moving a
rule somewhere unpinned is not a way out. Lowering a pin is free; raising is not.

Keep a rule only if it encodes project knowledge unavailable from the repo,
prevents irreversible or cross-user harm, or states a founder principle.

---

## Forever Rule: 24/7 uptime, zero hosts online

**Every surface works with no host online** — `PLAN.md` § *24/7 uptime*
inventories them. Take the task unblocking the largest currently-broken surface;
treat every outage as equal severity, because tiering starves the quiet ones.

**Personal-desktop prohibition (founder, 2026-09-21).** `DESKTOP-KCPMGP3` is the
founder's home PC, not infrastructure: never enroll it, route platform work to
it, or use it as a fallback. Platform service dependencies are cloud-only. An
existing local registration, tunnel, provider login or heartbeat is not
permission.

---

## Two Living Files

**AGENTS.md** (here) is how to work: behaviour, norms, hard rules. **PLAN.md** is
how the system works and why. Architecture never goes here; norms never go there.
Both update immediately when durable state changes.

**Live state has no living file.** It has homes by kind:

| Kind | Home |
|---|---|
| Queued / in-flight work | `openspec/changes/` -- `python scripts/openspec_flow.py audit` |
| Unresolved findings | `docs/concerns/` -- one file each, deleted when resolved |
| Founder-only work | `docs/host-actions.md` |
| Who is working on what | git branches and open PRs |
| Narrative / landings | `.agents/activity.log` / the git log |

---

## How to Work

### Orient

1. `PLAN.md` is the design reference: `python scripts/docview.py headings
   PLAN.md`, then one section. Skip for routine edits.
2. `python scripts/openspec_flow.py audit` is the work queue; skim
   `docs/concerns/README.md` for known findings in the area.
3. An approach conflicting with a `PLAN.md` principle does not get implemented --
   file it in `docs/concerns/`. PLAN.md changes need user approval.
4. Before a design note proposing a new MCP action, citing an unfixed `BUG-NNN`,
   or pinning a sha: `python scripts/check_primitive_exists.py` (exit 2 =
   collision).

### Keeping state current

If the user closed the window after your next message, durable state must already
reflect anything they said: decisions, priority changes and new findings go to
their home above *before* you respond, design-relevant ones also to `PLAN.md`.
Ideas not being executed now go to `ideas/INBOX.md`; greetings change nothing.
**Deletion matters as much as addition** — resolve a concern by deleting its file,
archive a landed change rather than annotating it.

### Where new conventions live

A convention any provider would need goes in `AGENTS.md`. Provider-specific
files (`CLAUDE.md`, `CODEX.md`) hold only harness quirks. In doubt, `AGENTS.md` —
broader visibility is the safer error. Enforced by `cross-provider-drift`.

### Truth and freshness

Truth is typed: `AGENTS.md` owns process, `PLAN.md` design, `openspec/specs/`
behaviour. Audits are diagnostic, never a source. Verification claims carry date,
environment and the command that produced them. **Re-verify a premise before
acting on it, and correct the citation in place** — paths and line numbers rot
faster than findings do. A contradicted claim gets fixed or filed before you
respond.

A pasted client chat is a bug report: extract the issues and fix them.

`python scripts/docview.py` (`stat`, `headings`, `section`, `lines`, `search`,
`json`) reads large files — `PLAN.md`, `output/*/notes.json`, review artifacts.

### Project Skills

Canonical in `.agents/skills/`, mirrored to `.claude/skills/` (`powershell
-ExecutionPolicy Bypass -File scripts/sync-skills.ps1` after editing). Seven,
named for their task -- read the matching one; there is no router. Before adding
one: **which model weakness does this encode, and does a current model still have
it?** Per-agent memory in `.claude/agent-memory/<name>/` (owner writes, everyone
reads). **Delete or rename a tracked file -> update every reference in the same
change.**

### Spec-driven development -- OpenSpec is the standard

`openspec/specs/<capability>/spec.md` is as-built requirement truth;
`openspec/changes/<name>/` holds in-flight proposals (`openspec` skill).

- **Spec what is hard to reverse, build the rest.** Public MCP/API surface,
  storage shape, authority/permissions, migrations and money get a proposal and
  design before code. Everything else — fixes, refactors, UI, docs, tests,
  single-surface behaviour — gets built, proven live, and specced from what
  shipped, which is more accurate than what was predicted.
- **Sync and archive on land, same lane.** A landed change with unsynced deltas
  is spec drift -- treat it as a failing gate.
- **Finish or archive.** A change idle 14 days is not in flight; archiving is free
  and reversible, because git holds it. Procedure:
  [`docs/reference/delivery-flow.md`](docs/reference/delivery-flow.md).

### Site preview / ship loop

The site lives in `WebSite/site-react/`; `.agents/skills/website-editing/SKILL.md`
owns the preview loop and the build/ship pipeline. Read it first.

---

## Working Norms

Claude Code and Codex CLI work this repo, calling each other as peers via
`peer-agents`. Neither runs a standing team.

- **Review is cross-family and narrow.** One round, dispatched in parallel once
  the PR is open, on the peer's own budget, for a floor-class change (below) or a
  gate-defining file (`executable-gates.md`). Everything else ships without a review. It gates landing,
  not your progress: take the next lane. Findings off the floor become
  `docs/concerns/` files, never extra rounds. Backstop: three rounds, then the
  founder.
- **Work in parallel, about four lanes,** in isolated worktrees; serialize merges
  and live-account operations. Parallelism never relaxes tests.
- **Stuck 3+ iterations on the same error -> stop.** Say what failed, what
  specific change would fix it, and whether you are repeating yourself; then
  hand it to the other family. `scripts/supervisor.py` watches for this.

### Quality Gates

Procedure: **[`docs/reference/quality-gates.md`](docs/reference/quality-gates.md)**.
Enforced vs judgement: **[`docs/reference/executable-gates.md`](docs/reference/executable-gates.md)**.

- **Shape -> live MVP -> user-test -> then harden** (founder, 2026-08-20). Never
  gate a first draft behind a hardening gauntlet; only live users reveal whether
  the shape is right.
- **The floor, and only the floor, blocks a deploy:** cross-user read or effect;
  auth or credential exposure; unrecoverable loss of user data; wrong money; an
  irreversible external act without consent; public connector down. Everything
  else is tracked and re-judged after live use.
- **Carry each item to verified completion** (founder, 2026-09-24). Done =
  deployed, working through the real app, relevant regressions green, spec synced.
- **If you know the next step, take it** (founder, 2026-09-17/24), approvals
  inside the agreed work included; ask only about new spending, irreversible or
  outward-facing acts outside it, and PLAN.md changes.
- **Test through the app agent as a user would** (founder, 2026-09-24): never
  feed it an answer it is supposed to work out, and never build users' workflows
  yourself — enable the agent to do it.
- **Scope is the basic capability set, not the current user's needs** (founder,
  2026-09-24): a basic capability stays listed until cleared, even with nobody
  blocked on it.

## Hard Rules

1. **SqliteSaver only** -- not AsyncSqliteSaver (not production-safe).
2. **LanceDB singleton** -- reuse connection objects, never recreate.
3. **No vendor-specific compute or connection code** (founder, 2026-09-24). Any LLM or platform connects through vendor-neutral connectors the user's agent configures; a new vendor never needs a patch. Existing vendor paths are migration debt (`PLAN.md` Providers). Dev tooling is exempt.
4. **Executable gates need autonomous defaults** -- never block a workflow gate on human input when a safe default exists. True host-only authority only as a concrete `host-decision`/`host-action` row with the smallest ask, and it must not block unrelated work.
5. **TypedDict + Annotated reducers** -- `Annotated[list, operator.add]` for accumulating fields.
6. **FactWithContext with truth-value typing** -- every extracted fact needs source_type, reliability, temporal_bounds, language_type.
7. **Python 3.11+** required.
8. **Fail loudly, never silently.** Mock fallbacks that look like real output are worse than crashes.
9. **User uploads are authoritative.** Preserved verbatim — never summarize, truncate, or reformat.
10. **Contributor attribution uses `CONTRIBUTORS.md`.** When `attribution_credit` rows exist on ship, map each `actor_id` to a GitHub handle and emit `Co-Authored-By:` lines; unknown actor_id → skip silently, never block a commit.
11. **Public-surface changes verify post-change.** After any edit to DNS, the Cloudflare tunnel, or any surface affecting `tinyassets.io`: export `TINYASSETS_WIKI_CANARY_TOKEN` (there is no anonymous read, so every probe is the `canary` principal and exits 2 without it), then `python scripts/mcp_public_canary.py --url https://tinyassets.io/mcp` must go green; tool-surface changes add `--assert-handles` (canonical set: `openspec/specs/live-mcp-connector-surface/spec.md`). Required evidence, not final chatbot proof. `https://tinyassets.io/mcp` is the only canonical public endpoint; `mcp.tinyassets.io` is an Access-gated internal origin — never document it user-facing. Why: `docs/audits/2026-04-20-public-mcp-outage-postmortem.md`; probes: `docs/ops/acceptance-probe-catalog.md`.
12. ~~Portfolio graph~~ — **CUT 2026-08-27.** Number kept so "Hard Rule 13/14" citations elsewhere stay correct.
13. **Inventory before you destroy; approval is not diligence.** No `git reset --hard`, `git checkout --`, `git restore`, `git clean`, force-push, or stash/drop as cleanup unless the host explicitly asks — and even then, **first prove what is unique**: for every path in scope, is it on a remote, or reachable in history? If neither, preserve it first. Approval settles *whether* to discard, never *what* (a 2026-08-26 "stale cruft" checkout held 4,711 lines of research existing nowhere else). Never switch a dirty worktree to `main`.
14. **Merged is not deployed.** Actions-app merges via `GITHUB_TOKEN` raise no workflow events, so a merge can land without deploying. Before claiming shipped, export the canary credential and run `python scripts/deployed_sha.py --assert-contains <sha>`, which reads `git_sha` from bearer-protected `GET /mcp/pulse`. `release-reconcile.yml` self-heals drift every 15 min; the claim still needs the sha.
15. **The platform has no LLM** (founder, 2026-09-24). Only a powered universe calls an LLM, with its owner's own connected credentials, for that universe alone. The platform never makes, needs or brokers an LLM call to run: no platform model, no shared/host/maintainer credential, no fallback. The founder's subscription is the founder universe's only.

---

## Testing

- `pytest` for the suite, `ruff check` before committing; nodes never crash.
  **Run the relevant tests locally, heavy ones included:** required PR CI excludes
  `.github/heavy-test-files.txt` and `heavy-tests` skips PRs. `actionlint` on
  workflow edits.
- **No mandatory mutation tables.** Mutation-check only a guard against data loss
  or a cross-user leak: break what it guards, confirm red, restore. A gate that
  cannot fail is decoration.
- **Never point a temp root inside the repo** (`--basetemp`/`TMPDIR`/`TEMP`/`TMP`;
  `tests/conftest.py` refuses to start). A sandbox-created dir there gets a
  Windows ACL nothing can remove without an elevated
  `scripts/clear_sandbox_temp_dirs.ps1 -Apply`.
- After canonical `tinyassets/*` edits affecting the plugin runtime:
  `python packaging/claude-plugin/build_plugin.py` (`mirror-parity` gates it).
- **A local Windows run is not an oracle on its own.** Before pushing anything
  touching the sandbox, the filesystem helpers, process limits or the workspace:
  `python scripts/linux_oracle.py -- -q tests/<file>.py` runs the working tree in
  a container with CI's Python 3.11 and bubblewrap — a real jail and POSIX
  descriptor semantics being what this host cannot supply. A green Windows suite
  that skipped 40 tests is not green; `python scripts/skip_census.py` says what a
  run did not cover.
- **Hot-path rewrites keep the original in the suite as executable spec** and
  differential-test against it (`tests/test_match_scale.py`).

## Configuration -- environment variables

All configuration is env vars. Catalog:
**[`docs/reference/environment-variables.md`](docs/reference/environment-variables.md)**.
Load-bearing invariants:

- **CWD-independent resolvers only** -- `tinyassets.storage.data_dir()`,
  `wiki_path()`. Never `Path.cwd()` logic or a re-implemented precedence.
- **Containers:** `TINYASSETS_DATA_DIR=/data` + bind-mount (`deploy/README.md`).
- **Secrets are vault-first:** `set -a; source scripts/load_secrets.sh; set +a`.
  Never a committed plaintext file.
