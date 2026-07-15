# Status

Live steering only. **Budget 4 KB / 60 lines.** Concerns/Work = one line each; landed rows are deleted; Forever rule = 24/7 uptime with zero hosts online.

**Scope (2026-05-19 reframe):** STATUS.md is for project-folder-access AIs (Claude Code, Codex CLI, Cursor sessions). Substantive work flows through the live MCP brain — wiki + dispatcher + auto-change loop. Use STATUS.md for cross-session coordination state that does not have a wiki home; check the live brain (PR-###, BUG-### in wiki) for active work.

## Concerns

- [filed:2026-04-17 verified:2026-04-28] Privacy mode: 2 of 3 host-Qs OBVIATED by community-build (per-conversation chatbot composes); Q6.3 STILL-PLATFORM (third-party providers in fallback chain — `tinyassets/providers/router.py`).
- [filed:2026-04-18 verified:2026-04-28] `add_canon_from_path` sensitivity: 3 host-Qs REFRAMED by commons-first audit F3 (self-auditing-tools structured caveats).
- [filed:2026-04-24] Task #9 host Qs: GROQ/GEMINI/XAI GH Actions secrets present + rotation e2e validated after deploy step ships.
- **[P1 filed:2026-04-30]** Castles II live run `28479d8ddfb44488` failed `provider_exhausted` at `candidate_discovery` (see BUG-038); blocks branch-run proof. Companion: BUG-039 (Echoes intake same root cause).
- [filed:2026-05-19] Wiki has shifted toward multi-agent shared scratch space — 81% of post-2026-05-01 notes (495 of 614) are Codex/Cowork/Claude agent-coordination. Volume risks drowning out chatbot discovery/remix. Worth a host conversation on whether to split coordination off the knowledge wiki.
- [filed:2026-07-14 verified:2026-07-14] Watch: anonymous-write gate LIVE + `ui-test` PASSED (Claude.ai rendered convo: reads rich, anonymous write rejected w/ actionable OAuth guidance, nothing persisted; log output/user_sim_session.md). Still pending: first organic authenticated-user write. Deploy-chown recurrence fixed (#1445).
- [filed:2026-07-13 verified:2026-07-14] Old `workflow-data` docker volume (19 GB) on droplet CONFIRMED holding unmigrated data: ~12 universes (concordance, earthos, meridian-ashes, …) + stale `.codex/auth.json`; audit before deleting. No backup timers active on droplet — backup lane needs re-install.
- [filed:2026-07-14] Wiki canary lost anonymous write-path coverage to the #1441 gate (by design); PROBE-003 now asserts gate-rejection + open read. Restoring authenticated write-roundtrip coverage needs a canary service credential — design + host decision.
## Approved Specs

Full specs: `docs/vetted-specs.md` (H2 heading per spec). Dev reads there, never wiki. On land, delete row + H2 section together.

| Spec | Status |
|---|---|
| [deferred] Daemon roster + node/gate soul policy + ledger/attribution/royalty/outcome/bounty/fair-distribution items | needs-scoping; soul-guided dispatch READ landed via open-brain v2 slice B (#900); host corrected 2026-05-01: many-daemon fleets + warning-only same-provider capacity estimates |

## Work

| Task | Files | Depends | Status |
|------|-------|---------|--------|
| Paid-market next: Track E Wave 2 transport (adapters only, assert_drained, match.best_execution, all money via market.apply_tx) as an OpenSpec change proposal; renumber migrations + schema_migrations table before applying 006–008 live | openspec/, tinyassets/paid_market/ | - (landing PR #1440 merged 07-14) | pending |
| **Codex verdict ADAPT** — in-node enqueue #1214 stays dark; before flag flip add current-universe context, queue/lineage cap, branch target validation | tinyassets/graph_compiler.py, tinyassets/branch_tasks.py, fantasy_daemon/__main__.py, tests/test_node_enqueue_*.py | verdict filed in `docs/audits/2026-05-30-in-node-enqueue-codex-review.md` | dev-ready |
| **L4 reducer law** — `_dict_merge` (graph_compiler.py ~351 + plugin mirror) is shallow right-biased, non-convergent; fix to per-key lattice join or restrict to single-writer; both-provider confirmed 2026-06-10 (basis audit L4 + codex review adaptation #5) | tinyassets/graph_compiler.py, packaging/claude-plugin mirror, tests/ | coordinate with in-node enqueue row (shared file) | dev-ready |
| External directory acceptance — PRs landed, public canaries green 2026-05-02T12:34-07:00; needs clean ChatGPT/Claude proof + first-user evidence | packaging/registry/server.json, docs/ops/mcp-* | - | host-action |
| OpenAI app submission hardening — chatgpt-app-submission.json present on disk (180 lines); submission docs/proof still pending | chatgpt-app-submission.json, docs/ops/openai-app-submission-*.md | clean ChatGPT approval/mobile proof | dev-ready |
| **#23 Arc B phase 2** — `codex/old-session-consolidation` at c967272; focused gates green | tests/, tinyassets/api/runs.py, fantasy_daemon/api.py | - | host-review |
| **#25 Arc B phase 3** — `codex/arc-b-phase3` at 1ae48ef; stacked on #23 | tinyassets/_rename_compat.py, fantasy_author/, domains/fantasy_author/ | #23 | host-review |
| **#24 Arc C** — env-var deprecation aliases (UNIVERSE_SERVER_BASE, WIKI_PATH) | tinyassets/storage/__init__.py | #25 | dev-ready |
| **Phase 6** — `.workflow.db`, `db_path()` fn, Option A migration, 30s restart, plugin minor-bump | tinyassets/storage/__init__.py + plugin mirror, tests/ | #24 | dev-ready |
| `run_branch resume_from=<run_id>` param (F2 ACCEPTED 2026-04-28) | tinyassets/api/runs.py, tests/ | #23 | dev-ready |
| Windows full-suite backup.sh path fix | tests/test_backup_script.py | #18,#23 | dev-ready |
| Clean-clone MCP config test mismatch | tests/test_mcp_server.py, .mcp.example.json | #18,#23 | dev-ready |
| Card-matcher cleanup vs legacy-connector fallback contract | scripts/claude_chat.py, tests/test_claude_chat_inline_dismiss.py | - | dev-ready |
| Mark-branch canonical decision (Task #33 phase 0) | live MCP `goals action=propose/bind/set_canonical` | host | host-decision |
| Host decision: BUG-018 canonical filename trailing-hyphen — rename canonical to drop, or `wiki action=promote` draft to overwrite? | wiki | - | host-decision |
| Fire DR drill #3 via workflow_dispatch | `.github/workflows/dr-drill.yml` | - | host or lead-with-PAT |
| Host-action: re-register `TinyAssets DEV` ChatGPT connector as workspace admin | OpenAI workspace admin | - | host-action |
| Memory-scope Stage 2c flag | - | 30d clean | monitoring |

## Live brain notes

Substantive work flows through the live MCP brain (wiki `PR-###`/`BUG-###` + dispatcher + auto-change loop), not duplicated here. Full enumeration + theme distribution: `.claude/agent-memory/navigator/wiki_sweep_cursor.md` (refresh before relying). In flight: PR-129 (branch protocols), PR-131 (Windows effect adapter), PR-139 (souled-universe, deployed); universes Meridian Ashes / Etsy Printify v2 / Markovic.

## Next

1. **Live brain is primary** for substantive work flow — wiki + dispatcher + auto-change loop. STATUS.md is the project-folder-access coordination layer; check both.
2. **Cheat-loop CI retired per 2026-06-25 host directive** — `AUTO_FIX_DISABLED=true`; remove intake/writer/checker machinery while preserving get_status, deploy lanes, MCP canaries, and live brain/dispatcher surfaces.
3. **No-shims-ever rule active** + **platform responsibility model** + **public-surface probes after DNS/tunnel/Worker/connector changes** (canonical: https://tinyassets.io/mcp).
4. **Scoping rules apply to design questions themselves** (per `feedback_design_questions_apply_scoping_rules_first.md`) — if X composes from primitives or has open-ended variations, do NOT present "platform builds it" as an option when steering.
