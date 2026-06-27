# Phase 7 Reconciliation Plan

**Author:** planner
**Date:** 2026-04-13
**Status:** recommendation for lead approval

## TL;DR

The two efforts are not two competing Phase 7 designs. They are two
incompatible project states. **Uncommitted main is the real Phase 7 work,
executing against the approved spec at `docs/specs/phase7_github_as_catalog.md`
and the PLAN.md design decision "GitHub as the canonical shared state"
(already landed on main with user approval).** The `claude/inspiring-newton`
worktree is a pre-Community-Branches branch that reverts c85efa1 entirely,
pivots back to a Custom GPT thesis, and does STATUS.md housekeeping. Its
"Phase 7" label in the scoping message is a misread — that branch has no
Phase 7 content.

**Recommendation: keep all of main. Cherry-pick STATUS.md structural
discipline wording from the worktree only. Abandon the rest of
inspiring-newton.**

---

## What each effort actually is

### Effort A — uncommitted main (the real Phase 7.1)

**Branch state:** on top of c85efa1 (Community Branches Phases 2-5 already
landed). Eight modified tracked files, ten new untracked test files, seven
research docs, one executable spec, one new module tree.

**Scope of change:**

- **New module `tinyassets/storage/`** (688 lines): Phase 7.1 storage surface
  per spec. Three files:
  - `layout.py` — pure-path `YamlRepoLayout` + `slugify`. Resolves
    `branches/<slug>.yaml`, `goals/<slug>.yaml`,
    `nodes/<branch_slug>/<node_id>.yaml`, `<universe>/rules.yaml`,
    `<universe>/notes/<ts>.md`, etc. No I/O.
  - `serializer.py` — `branch_to_yaml_payload` / `_from_`,
    `goal_to_yaml_payload` / `_from_`, `node_to_yaml_payload` / `_from_`.
    Round-trip identity contract for the SQLite ↔ YAML cache migration.
    Externalized-nodes default; inline fallback for smaller branches.
  - `backend.py` — `StorageBackend` Protocol with `SqliteOnlyBackend`
    (zero behavior change wrapper over `author_server`) and
    `SqliteCachedBackend` (SQLite-first write + YAML mirror + deferred
    `_stage_hook` for Phase 7.2's git bridge).
- **New spec** `docs/specs/phase7_github_as_catalog.md` (125 lines).
  Executable, seven sub-phases (7.1 layout → 7.7 draft workflow), nine
  explicit acceptance criteria.
- **Research docs** (7 files, 1001 lines) covering: GitHub-as-catalog
  audit per-table (dev-2), local-only chokepoint audit (dev-2), directory
  layout proposals (dev-3), always-on hosting / federation framing,
  multi-tenant-hosted-runtime framing (discarded), claude.ai rendering
  behaviors. These are the reasoning trail behind the spec.
- **Test coverage** for the new module (3 files) plus unrelated test files
  addressing earlier in-flight Phase 2-5 work:
  - Phase 7.1 coverage: `test_storage_phase7_layout.py`,
    `test_storage_phase7_serializer.py`, `test_storage_phase7_backend.py`.
  - Out-of-scope-for-Phase-7 coverage (arrived in same working tree):
    `test_goals_discoverability.py`, `test_node_ref_reuse.py`,
    `test_node_reuse_discovery.py`, `test_node_timeout.py`,
    `test_patch_branch_metadata.py`, `test_patch_nodes.py`,
    `test_progress_events.py`, `test_wait_for_run.py`. These were added
    alongside the +1,237 line expansions in `universe_server.py`,
    `runs.py`, `graph_compiler.py`, `branches.py` — i.e. the in-flight
    cluster the devs were already running (patch_nodes, node_ref reuse,
    progress events, wait_for_run, node timeout). Not Phase 7 work;
    adjacent in time.
- **Edits** to `PLAN.md` (codifies "GitHub as the canonical shared state"
  + "Local-first execution, git-native sync" Design Decisions — already
  in place), `STATUS.md` (concerns + work rows reflecting this session's
  strategic pivot), `scripts/claude_chat.py` (+189), and the four runtime
  files that host the pre-existing in-flight cluster.

**What it does NOT yet do:** no git bridge (`tinyassets/git_bridge.py`) yet,
no MCP action cutover (build_branch/patch_branch still only write SQLite),
no export script, no GitHub Actions. That's Phases 7.2–7.5. The landed
code is strictly Phase 7.1 "storage layout + serializer, no git yet" per
the spec's own rollout.

### Effort B — worktree `claude/inspiring-newton` @ b5e75a9

**Branch state:** single commit on top of **36f097a (initial commit)**.
Branched BEFORE c85efa1. Never saw Community Branches Phases 2-5 land.
One commit titled "Refactor STATUS.md into active/watch/archive sections;
tighten staleness rules".

**What the single commit actually does** (the title massively undersells
it — 466 files, +38K/-65K):

- **Reverts c85efa1 in its entirety.** Deletes `tinyassets/universe_server.py`
  (-6,692 lines), `tinyassets/runs.py` (-1,333), `tinyassets/graph_compiler.py`
  (-481), plus `tinyassets/node_eval.py`, `tinyassets/node_sandbox.py`,
  `tinyassets/packets.py`, `tinyassets/preferences.py`, `tinyassets/utils/json_parsing.py`.
  `tinyassets/branches.py` also not present.
- **Reintroduces the Custom GPT path.** Adds `custom_gpt/` with
  `actions_schema.yaml` (926 lines), `instructions.md`, `README.md`.
  PLAN.md on the worktree says "Custom GPT / MCP-compatible chatbots",
  contradicting main's PLAN.md "MCP is primary; Custom GPT is legacy."
- **Adds `tinyassets/testing/gpt_builder.py` (+508) and `gpt_harness.py`
  (+471).** New test surface for Custom-GPT-driven builds.
- **Adds `.claude/skills/gpt-test/` and `gpt-update/` skills** (+299 each
  mirrored into `.agents/skills/`). Deletes `ui-test/` skill.
- **Housekeeping:** STATUS.md reshape into active/watch/archive sections
  with stronger staleness rules (+297/-???), AGENTS.md tightening, agent
  def edits, quarantine of `archive/stale-cross-universe-content/` (which
  on main is the successful resolution of task #4's cross-universe
  cluster; the worktree deletes those files outright instead of archiving
  — different disposition of the same cleanup).
- **Removes the Community Branches specs** (`docs/specs/community_branches_phase{2,3,4,5}.md`,
  `composite_branch_actions.md`, `tool_return_shapes.md`,
  `multi-provider-tray-runtime.md`).

**What it does NOT do:** no Phase 7 content. No storage backend, no
YAML layout, no git bridge, no GitHub-as-catalog spec, no PLAN.md
GitHub-canonical decision. The commit title references STATUS.md
discipline, which it does do — but 99% of the file-count and line-count
is the rollback of Community Branches.

---

## Agreements, conflicts, orthogonality

### Agreements (small)

- **STATUS.md structural discipline.** Worktree introduces an explicit
  active/watch/archive section split, tighter staleness rules ("under ~20
  Concerns", "under ~12 Work rows", mandatory `current:`/`historical:`
  labels, same-session archival discipline). Main has evolved its STATUS.md
  in the same direction but without a clean header block. The *wording*
  of that discipline section is worth lifting.
- **Both want AGENTS.md to tighten** process norms. Overlap is small
  (~23 lines on worktree's side); main has already absorbed most of
  that content in-place.

### Conflicts (structural, unreconcilable)

- **The entire c85efa1 Community Branches Phase 2-5 ship.** Worktree
  deletes `universe_server.py`, `runs.py`, `graph_compiler.py`,
  `branches.py`. Main not only keeps them, it extends them (+1,237 lines
  across them plus Phase 7 layering on top). Merging the worktree would
  wipe out seven landed capabilities (build_branch/patch_branch/runner/
  async/judge/compare/rollback/goals) that user-sim Mission 4-5 already
  depend on.
- **PLAN.md identity.** Worktree PLAN.md frames the project as "Custom
  GPT / MCP-compatible chatbots" with gpt_harness as the testing surface.
  Main's PLAN.md locks in "MCP is primary; Custom GPT is legacy" (user
  memory also confirms this: `MCP is primary interface`) and establishes
  the "GitHub as the canonical shared state" design decision.
- **Spec corpus.** Worktree deletes community_branches_phase{2,3,4,5}.md,
  composite_branch_actions.md, tool_return_shapes.md,
  multi-provider-tray-runtime.md. These are the design record for
  shipped-and-working functionality. Main keeps them.
- **STATUS.md content.** Worktree's STATUS.md has no concerns newer than
  2026-04-12 and no rows for any Phase 2-5 landing. Main's STATUS.md is
  deep into 2026-04-13 with Phase 4/5 green rows, the GitHub-canonical
  concern, and Phase 7 scoping.

### Orthogonal (neither depends on the other)

- **gpt_builder.py / gpt_harness.py.** These are a testing approach the
  worktree proposes that doesn't exist on main. They are not incompatible
  with Phase 7 per se; they just target a Custom-GPT driver surface that
  the project has moved away from. Keep them available in git history
  via the worktree branch if ever revived; do not merge.
- **archive/stale-cross-universe-content/ disposition.** Main keeps the
  files in `archive/` (the chosen disposition in task #4). Worktree
  deletes them. Main's disposition is correct and already landed.

---

## Merge path

### Chosen path: **keep-all-from-main, narrow cherry-pick of STATUS.md discipline wording only**

**Why not rework one onto the other?** The worktree pre-dates c85efa1
and builds on a Custom-GPT thesis the user and STATUS.md have both
repudiated. Re-landing it on main would mean re-deleting Phase 2-5
(losing live functionality user-sim depends on) then re-adding the
deleted pieces, then layering Phase 7 on top. Net zero for Phase 7,
negative for Phase 2-5.

**Why not drop the worktree entirely?** The STATUS.md section-header
discipline wording ("Concerns stay under ~20 items", "Work stays under
~12 rows", "Archive immediately", explicit active/watch/archive
headers) is a real improvement. Worth lifting.

### Concrete steps for dev

1. **Commit uncommitted main as-is, in one commit, once the reviewer
   audit clears** (Task #5 — reviewer audit of uncommitted scaffolding
   is already in flight). The 1,352-line delta + new module + 10 new
   tests + 7 research docs + 1 spec + PLAN/STATUS edits are one logical
   Phase 7.1 + adjacent-cluster landing.
2. **Cherry-pick STATUS.md *wording* only from b5e75a9** — specifically
   the "Session discipline — read this every session" block and the
   active/Concerns/Work/Watch/Archive section headers. Do NOT take
   the actual concerns/rows from the worktree (they are stale and
   describe a different project state). Reviewer should confirm the
   wording can be applied cleanly on top of main's current STATUS.md
   without content loss.
3. **Retire the worktree.** `git worktree remove .claude/worktrees/inspiring-newton`
   after the cherry-pick lands. The branch stays in refs for history.
4. **Capture `gpt_builder.py` / `gpt_harness.py` as an ideas/INBOX.md
   entry** before retiring the branch — if the Custom-GPT driver
   testing approach ever earns a second look, the code exists in git
   history at b5e75a9:tinyassets/testing/gpt_builder.py.

### Phase 7 roadmap after this reconciliation

Phase 7.1 is the uncommitted landing (storage module + tests + spec +
research). Next concrete steps per the spec are:

- **7.2** Implement `tinyassets/git_bridge.py` (thin `subprocess.run(["git",
  ...])` wrapper: `stage`, `commit`, `pull`, `open_pr`). Replace
  `SqliteCachedBackend._stage_hook` noop with `git_bridge.stage`.
- **7.3** Wire ~12 MCP write handlers through `StorageBackend`. Start
  with the three highest-traffic writes: `build_branch`, `patch_branch`,
  `update_node`. Add `sync_latest` and `publish_to_remote` actions.
- **7.4** Identity wiring: `TINYASSETS_GITHUB_USERNAME` env; `_current_actor`
  threads through FastMCP request context; existing `OAuthProvider`
  lights up for self-hosted installs.
- **7.5** GitHub Actions: BranchDefinition validation on PR + mermaid
  preview comment.
- **7.6** Outcome gates YAML seam (forward-compat #56).
- **7.7** `draft/` convention + `save_draft`/`publish` split.

These are all sequential — no parallelism opportunity between 7.2 and
7.3 because 7.3 depends on 7.2. 7.5 can run in parallel with 7.4 once
7.3 ships.

---

## Risks

- **Risk: the uncommitted delta on main is big enough that reviewer
  audit uncovers issues.** Task #5 is in flight; wait for it. Size is
  justified: new module + tests + docs + spec + PLAN.md pivot is one
  coherent landing, not a kitchen-sink commit. If reviewer flags
  specific concerns, address them in-place rather than splitting the
  landing (splitting would leave the spec in main without the module
  backing it, which is worse).
- **Risk: the "adjacent-cluster" test files (patch_nodes, node_ref_reuse,
  progress_events, wait_for_run, node_timeout) actually test functionality
  that hasn't fully landed in `universe_server.py` / `runs.py`.** Task
  #4 (baseline test run) will surface any such gap. Planner does NOT
  recommend trying to disentangle these from the Phase 7.1 landing —
  they arrived together and the test suite's green/red state is the
  single integration signal.
- **Risk: retiring the worktree feels like throwing away work.** It is
  not — the STATUS.md discipline wording gets preserved, and the
  Custom-GPT direction has already been rejected in PLAN.md + user
  memory. The code is git-addressable at b5e75a9 forever.
- **Risk: Phase 7.2's git-bridge work hits pull-conflict UX rough
  edges.** Spec acknowledges this as "the unavoidable rough edge" and
  defers `resolve_conflict` to 7.x. Surface conflicts + bail is good
  enough for v1.

---

## Next concrete dev task

**Task:** finalize Phase 7.1 landing.

**Prerequisites in flight:**

- Task #4 baseline test run — confirms the uncommitted delta is green.
- Task #5 reviewer audit of uncommitted scaffolding — confirms the
  storage module + spec + research docs are sound.

**Dev actions (sequential, one dev):**

1. Once #4 and #5 clear, commit the uncommitted delta as a single
   commit: "Phase 7.1: storage layout + serializer + spec + adjacent
   cluster". Include the 8 modified + 10 new test + 7 research doc +
   1 spec + 1 new `tinyassets/storage/` module.
2. Cherry-pick STATUS.md *discipline wording only* from b5e75a9 (the
   "Session discipline — read this every session" block + the section
   header schema). Do not pull any of its actual Concerns or Work
   rows.
3. `git worktree remove .claude/worktrees/inspiring-newton`. Branch
   stays in refs.
4. Open a follow-up task for **Phase 7.2 git bridge**
   (`tinyassets/git_bridge.py`). Spec §7.2 has the executable surface.

**Parallel-safe next (different dev):**

- Capture `tinyassets/testing/gpt_builder.py` / `gpt_harness.py` from
  b5e75a9 as an ideas/INBOX.md pointer entry in case Custom-GPT
  driver testing is ever revived.

No work is blocked between dev #1 and dev #2 — they touch different
files.
