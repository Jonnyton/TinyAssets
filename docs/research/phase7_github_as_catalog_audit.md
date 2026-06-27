# Phase 7 Pre-work: GitHub-as-Catalog Audit

Pivot from "multi-tenant hosted runtime" to "git-native open-source
platform." Each user clones, runs locally, PRs to share. The question
this audit answers: **which storage surfaces become git-tracked files,
which stay local SQLite/disk?**

Source of ground truth: live `tinyassets/author_server.py` (24 tables)
and `tinyassets/runs.py` (6 tables) as of post-cluster #67.

## Storage Surface Classification

| Surface | Today | Phase 7 split | Migration shape |
|---------|-------|---------------|-----------------|
| `branch_definitions` | SQLite row, 1 per workflow | **git-tracked** as `branches/<slug>.yaml` | Serialize to YAML on save; load on demand. Drop the row, keep the cache for query indexes. |
| `goals` | SQLite row | **git-tracked** as `goals/<slug>.yaml` | Same shape as branches. Goal name = slug, description in body. |
| `node_defs` (embedded JSON in branch row today) | SQLite | **git-tracked** as `nodes/<branch_slug>/<node_id>.yaml` OR inlined in branch YAML | Inline keeps related state together; per-file makes node-level diffs/reuse cleaner. **Recommend per-file** because node reuse across branches is a Phase 5 design goal (#62). |
| `state_schema` | SQLite (JSON in branch row) | **git-tracked** inline in branch YAML | Schema is small, tightly coupled to branch identity. Inline. |
| `branches` (Phase 4 multiplayer table — branch heads, snapshots) | SQLite | **git-tracked**: lives in git refs naturally | The Phase 4 "branches" table replicates what git already does. Retire it; map onto git refs/branches/tags. |
| `branch_heads`, `universe_snapshots` | SQLite | **subsumed by git** | Same — git ref + commit hash supersedes. |
| `action_records` (ledger) | SQLite append-log | **subsumed by git commit history** | Every public mutation is already a commit; commit message + author + timestamp IS the ledger entry. Retire the table. |
| `user_accounts`, `user_sessions`, `capability_grants` | SQLite | **stays local** | Auth is per-machine in git-native model. GitHub identity replaces remote auth. |
| `author_definitions`, `author_forks`, `author_runtime_instances` | SQLite | **mixed**: definitions git-tracked (`authors/<slug>.yaml`), runtime instances stay local | A "daemon identity" is a public artifact; "I'm running it on my laptop right now" is local state. |
| `universe_rules` | SQLite | **git-tracked** as `<universe>/rules.yaml` | Universe-scoped governance is a public document. |
| `universe_notes`, `universe_work_targets`, `universe_hard_priorities` | SQLite | **git-tracked** as `<universe>/notes/`, `targets.yaml`, `priorities.yaml` | All steering/feedback content. Notes are the established public-feedback surface (PLAN.md). |
| `runs` (run_id, status, started_at, output_json) | SQLite | **stays LOCAL** | Runs are user-specific execution traces. Sharing a single run is a separate publish action, not auto. |
| `run_events`, `run_cancels` | SQLite | **stays LOCAL** | Per-run telemetry; ephemeral by nature. |
| `run_judgments` | SQLite | **publish-on-demand** | A judgment is a free-text critique. Stays local by default; user can promote individual judgments to a `judgments/<slug>.md` file (mirror of how wiki drafts → promoted pages already work). |
| `run_lineage` | SQLite | **mostly LOCAL, parent pointers public** | The "this run's parent was that run" pointer can stay local — runs are local. The "this branch was forked from that branch" pointer becomes a YAML field `parent_def: <slug>`. |
| `node_edit_audit` | SQLite | **subsumed by git history** | Already what git tracks per file. Retire. |
| `vote_windows`, `vote_ballots`, `user_requests` | SQLite | **subsumed by GitHub Issues/Discussions** | Voting on a daemon fork = thumbs-up on an issue. User requests = issues. Don't reinvent. |
| `.langgraph_runs.db` (SqliteSaver) | SQLite | **stays LOCAL** | LangGraph checkpointer for run resumption. Pure runtime state. |
| LanceDB vectors | local dir | **stays LOCAL** | Retrieval cache, derived from canon. Rebuilt from canon on demand; not worth syncing. Add a `make rebuild-index` target. |
| `knowledge.db` (KG) | SQLite | **stays LOCAL, source artifacts public** | KG is derived from prose + canon (which ARE git-tracked). Rebuild on clone, like the vector cache. |
| Canon (`<universe>/canon/`) | filesystem | **already git-friendly** | Already directory-structured markdown. Drop in repo as-is. |
| Prose (`<universe>/output/...`) | filesystem | **already git-friendly** | Same. |
| Scene packets (`*.packet.json`) | filesystem | **git-tracked** | Already JSON files alongside prose. Drop in repo as-is. |

## MCP Action Git-Bridging Requirements

Current writes that need a git seam:

- **`extensions action=build_branch` / `patch_branch` / `update_node` / `patch_nodes` / `rollback_node`** — write SQLite row today. Phase 7: write YAML file → `git add` → optionally `git commit -m "..."` with the action summary. Two-phase commit pattern fits naturally: stage on each MCP write, batch-commit on user's "publish" action.
- **`goals action=propose / update / bind / delete`** — same pattern. YAML files in `goals/`, bind = a field on the branch YAML, not a separate row.
- **`extensions action=judge_run`** — stays local-only by default; new action `publish_judgment` writes the markdown and stages it.
- **`universe action=write_note / give_direction / submit_request`** — notes are public, write directly to `<universe>/notes/<timestamp>.md` and stage.
- **READS** (`get_branch`, `list_branches`, `goals action=get / list / search / leaderboard / common_nodes`) — load from YAML cache, not SQLite. Indexing layer (an in-memory SQLite scratch DB rebuilt on clone or file-watcher tick) preserves the existing query shape without duplicating durable state.

## Test-Suite Impact

- **Most affected**: tests in `test_community_branches_phase{2,3,4,5}.py`, `test_composite_branch_actions.py`, `test_patch_nodes.py`, `test_text_channel_id_redaction.py` — all build branches via the dispatcher and assert SQLite shape via `get_branch_definition`. Migration: tests load YAML → assertions stay structurally similar.
- **Unaffected**: `test_node_timeout.py`, `test_progress_events.py`, `test_wait_for_run.py`, `test_graph_compiler_literal_braces.py` — exercise the runner/compiler. Run state is local-only by design; nothing changes.
- **Subtle**: `test_universe_server_ledger.py`, `test_text_channel_id_redaction.py` assert ledger rows. Once the ledger maps to git commits, those tests rewrite to assert commit shape (or skip if the seam stubs out git in test mode).

## Recommended Phase 7 Sequencing

1. YAML schema + serializer/deserializer for `branch_definitions`, `goals`. Round-trip tests: SQLite → YAML → SQLite produces the same row.
2. Git seam: a thin `GitWriter` that takes a path + content + commit message and stages/commits via `subprocess.run(["git", ...])`. Stub for tests.
3. Cutover: `save_branch_definition` writes YAML AND SQLite (cache). `get_branch_definition` reads SQLite (cache). On clone, build cache from YAML.
4. Retire `action_records` (ledger) — git log replaces it.
5. Retire `branches`/`branch_heads`/`universe_snapshots` Phase 4 multiplayer tables — git refs supersede.
6. PR/Issue bridges (Phase 7.5): `submit_request` opens an issue, judgments can be promoted to PR comments, etc.

The good news: **most local-runtime surfaces stay exactly as they are**. Phase 7 isn't a rewrite — it's adding a YAML-emit + git-stage seam to the ~12 mutation handlers in `author_server.py` and retiring three tables that git already does better.
