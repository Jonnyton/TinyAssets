# Status

Live steering only. **Budget 4 KB / 60 lines.** Concerns/Work = one line each; landed rows are deleted; Forever rule = 24/7 uptime with zero hosts online.

**Scope (2026-05-19 reframe):** STATUS.md is for project-folder-access AIs (Claude Code, Codex CLI, Cursor sessions). Substantive work flows through the live MCP brain — wiki + dispatcher + auto-change loop. Use STATUS.md for cross-session coordination state that does not have a wiki home; check the live brain (PR-###, BUG-### in wiki) for active work.

## Concerns

- [filed:2026-04-17 verified:2026-04-28] Privacy mode: 2 of 3 host-Qs OBVIATED by community-build (per-conversation chatbot composes); Q6.3 STILL-PLATFORM (third-party providers in fallback chain — `workflow/providers/router.py`).
- [filed:2026-04-18 verified:2026-04-28] `add_canon_from_path` sensitivity: 3 host-Qs REFRAMED by commons-first audit F3 (self-auditing-tools structured caveats).
- [filed:2026-04-24] Task #9 host Qs: GROQ/GEMINI/XAI GH Actions secrets present + rotation e2e validated after deploy step ships.
- **[P1 filed:2026-04-30]** Castles II live run `28479d8ddfb44488` failed `provider_exhausted` at `candidate_discovery` (see BUG-038); blocks branch-run proof. Companion: BUG-039 (Echoes intake same root cause).
- [filed:2026-04-30 reframed:2026-05-19] Classic-game v0 desktop shortcut concern: now PR-131 in dispatcher queue (`bc6ed9df-e764-495a-b466-c5c86d7e0e2e`); user-canary packet `tiberian_sun_host_local_effect_packet_v1` built with correct idempotency_key + asset policy. First consumer of #914 external-write design.
- [filed:2026-05-19] Wiki has shifted toward multi-agent shared scratch space — 81% of post-2026-05-01 notes (495 of 614) are Codex/Cowork/Claude agent-coordination. Volume risks drowning out chatbot discovery/remix. Worth a host conversation on whether to split coordination off the knowledge wiki.

## Approved Specs

Full specs: `docs/vetted-specs.md` (H2 heading per spec). Dev reads there, never wiki. On land, delete row + H2 section together.

| Spec | Status |
|---|---|
| [deferred] Daemon roster + node/gate soul policy + ledger/attribution/royalty/outcome/bounty/fair-distribution items | needs-scoping; soul-guided dispatch READ landed via open-brain v2 slice B (#900); host corrected 2026-05-01: many-daemon fleets + warning-only same-provider capacity estimates |

## Work

universe_server.py: 14012 → 972 LOC live in main. PLAN.md restructured 30→11 modules (#915, 41569b5) — Brain Module + skills tie-in + plan_module_audit script LANDED 2026-05-19. External-write authority design locked + on main (#914, e2c20f4).

**Multi-provider note:** any provider runs `python scripts/claim_check.py --provider <yourname>` to discover what's safe to claim. AGENTS.md §"Parallel Dispatch" has the full ritual.

| Task | Files | Depends | Status |
|------|-------|---------|--------|
| **#906 host merge key** — Open-brain v2 slice C cost-ledger READ surface; Claude checker APPROVED 2026-05-19 | workflow/daemon_brain.py, workflow/api/status.py + plugin mirrors | - | host-action |
| **#907 host merge key** — Bounded autonomous spend CI writer-prompt guardrail; Claude checker APPROVED 2026-05-19 | .github/workflows/auto-fix-bug.yml, docs/ops/auto-fix-runbook.md | - | host-action |
| External directory acceptance — PRs landed, public canaries green 2026-05-02T12:34-07:00; needs clean ChatGPT/Claude proof + first-user evidence | packaging/registry/server.json, docs/ops/mcp-* | - | host-action |
| OpenAI app submission hardening — docs/code never landed; chatgpt-app-submission.json absent on disk | chatgpt-app-submission.json, docs/ops/openai-app-submission-*.md | clean ChatGPT approval/mobile proof | dev-ready |
| **#23 Arc B phase 2** — `codex/old-session-consolidation` at c967272; focused gates green | tests/, workflow/api/runs.py, fantasy_daemon/api.py | - | host-review |
| **#25 Arc B phase 3** — `codex/arc-b-phase3` at 1ae48ef; stacked on #23 | workflow/_rename_compat.py, fantasy_author/, domains/fantasy_author/ | #23 | host-review |
| **#24 Arc C** — env-var deprecation aliases (UNIVERSE_SERVER_BASE, WIKI_PATH) | workflow/storage/__init__.py | #25 | dev-ready |
| **Phase 6** — `.workflow.db`, `db_path()` fn, Option A migration, 30s restart, plugin minor-bump | workflow/storage/__init__.py + plugin mirror, tests/ | #24 | dev-ready |
| `run_branch resume_from=<run_id>` param (F2 ACCEPTED 2026-04-28) | workflow/api/runs.py, tests/ | #23 | dev-ready |
| Windows full-suite backup.sh path fix | tests/test_backup_script.py | #18,#23 | dev-ready |
| Clean-clone MCP config test mismatch | tests/test_mcp_server.py, .mcp.example.json | #18,#23 | dev-ready |
| Card-matcher cleanup vs legacy-connector fallback contract | scripts/claude_chat.py, tests/test_claude_chat_inline_dismiss.py | - | dev-ready |
| Mark-branch canonical decision (Task #33 phase 0) | live MCP `goals action=propose/bind/set_canonical` | host | host-decision |
| Host decision: BUG-018 canonical filename trailing-hyphen — rename canonical to drop, or `wiki action=promote` draft to overwrite? | wiki | - | host-decision |
| Fire DR drill #3 via workflow_dispatch | `.github/workflows/dr-drill.yml` | - | host or lead-with-PAT |
| Host-action: re-register `Workflow DEV` ChatGPT connector as workspace admin | OpenAI workspace admin | - | host-action |
| Memory-scope Stage 2c flag | - | 30d clean | monitoring |
| Remove provider+DO keys from persistent uptime surfaces | `deploy/*` | host Qs answered | host->e2e |

## Live brain notes (informational; not work rows)

Substantive work flowing through the live MCP brain — not duplicated here. Currently active:

- **PR-129** (filed 2026-05-19) — Goal-bound branch protocols / ordered branch family runbook with typed artifact handoffs. Real community-build case (chatbot already composed manually via wiki prose; needs first-class durability). Dispatcher `ec15c952-aefa-42ab-b50b-eee1524d3ef9` queued.
- **PR-131** (filed 2026-05-19) — Host-local Windows desktop effect adapter; closes BUG-043 generalized. First consumer of #914 external-write design. Dispatcher `bc6ed9df-e764-495a-b466-c5c86d7e0e2e` queued.
- **PR-130** (Markovic) — peer-reviewed simulation-biology publication strategy.
- **PR-139 / GH #1090** — souled-universe consolidation; slices #1089/#1091/#1092 landed; slice 4 permission lane in flight.
- **New universes in flight:** Meridian Ashes (fantasy prose-lab), Etsy Printify v2 (commerce via effect packets), Markovic (scientific publication).

For full live-brain enumeration see `.claude/agent-memory/navigator/wiki_sweep_cursor.md` (refreshed 2026-05-19: 890 promoted + 134 drafts + theme distribution).

## Next

1. **Live brain is primary** for substantive work flow — wiki + dispatcher + auto-change loop. STATUS.md is the project-folder-access coordination layer; check both.
2. **PRs in your queue:** #906 + #907 (Claude APPROVED 2026-05-19, awaiting host merge key).
3. **Auto-change loop is landing slice work** — ExperiencePool/AcceptanceScenario/PrivateTraceCommons Slices 1-3 merged (#936/#937/#938/#954/#956) without the Claude review-gate audits the prior STATUS rows referenced. Treat live brain as the substantive build surface; review gates re-enter only if a slice trips a real concern.
4. **No-shims-ever rule active** + **platform responsibility model** + **public-surface probes after DNS/tunnel/Worker/connector changes** (canonical: https://tinyassets.io/mcp).
5. **Scoping rules apply to design questions themselves** (per `feedback_design_questions_apply_scoping_rules_first.md`) — if X composes from primitives or has open-ended variations, do NOT present "platform builds it" as an option when steering.
