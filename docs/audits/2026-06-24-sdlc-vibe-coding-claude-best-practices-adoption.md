# Adoption audit + tracker: "New SDLC with Vibe Coding" + "Claude Code in large codebases"

**Filed:** 2026-06-24 · **Living record** — update grades as items land.
**Sources:**
- Kaggle/Google whitepaper *The New SDLC With Vibe Coding* (Addy Osmani, Shubham Saboo et al.) — https://www.kaggle.com/whitepaper-the-new-SDLC-with-vibe-coding (writeup: https://addyosmani.com/blog/new-sdlc-vibe-coding/)
- Anthropic *How Claude Code works in large codebases* — https://claude.com/blog/how-claude-code-works-in-large-codebases-best-practices-and-where-to-start

**Method note:** A first pass rated most items "already have" from surface evidence (files exist, hooks registered). That was wrong to trust — this repo's own truth-drift ledger shows docs routinely overstate reality. So every grade below was **re-verified against actual code/runtime by five read-only audits on 2026-06-24** (grades: SOLID / HALF-DONE / ASPIRATIONAL / BROKEN / GAP). Several first-pass "HAVE" ratings were corrected. The repo is a genuinely mature agentic-engineering harness, but "mature" ≠ "100%."

---

## Verified scorecard (2026-06-24)

### Instruction files
| Item | Grade | Reality |
|---|---|---|
| Lean & layered (root=pointers, subdirs=local) | **BROKEN** | AGENTS.md 689 ln / 56 KB (was ~17.6 KB on 2026-04-28 — **3×, unaudited**); zero subdirectory layering; pure root monolith. |
| Internal consistency / no dup | HALF-DONE | Duplicate "Where new conventions live" block in AGENTS.md; the drift guard is blind to self-duplication. |
| Claims match reality | HALF-DONE | Spot-check 6 TRUE / 2 FALSE: STATUS.md says `universe_server.py` 972 LOC (actually **1891**); says `chatgpt-app-submission.json` "absent on disk" (**present**). |
| Expertise in skills not instruction files | ASPIRATIONAL | ~248 ln of worktree/git how-to inlined in AGENTS.md duplicating the `git-workflow-and-versioning` skill; FUSE recipes in CLAUDE.md duplicate `loop-uptime-maintenance`. |
| STATUS.md within its own 4 KB/60-ln budget | **BROKEN** | 72 ln / 9 KB (220% of budget); the header asserts the budget it violates. |

### Skills
| Item | Grade | Reality |
|---|---|---|
| Mirror parity (.agents↔.claude↔.codex) | SOLID | Mechanically enforced (pre-commit re-syncs + `skills_valid` invariant). `.codex` is local-only/untracked. |
| Progressive disclosure | SOLID (1 outlier) | 33/33 valid frontmatter, heavy content in subfiles. Outlier: `ui-test/SKILL.md` 419 ln / 34 KB monolith. |
| Trigger quality | SOLID | All 33 descriptions are discovery-shaped "use when…". |
| Staleness / residue | **fixed** | infra-ops references named deleted skills (`godaddy-ops`/`cloudflare-ops`) — fixed; `SKILLS_AUDIT.md` root residue → moved to `docs/audits/2026-06-23-skills-refactor-audit.md`. |
| Path-scoped activation | GAP (by design) | No machine-readable path scoping — needs loader `paths:` support; editorial scoping only. |

### Hooks
| Item | Grade | Reality |
|---|---|---|
| Liveness | SOLID | 10 hooks all real. (`dev_idle_guard.py` is **not** dead — wired via `.claude/agents/developer.md`; first-pass false positive.) |
| Correctness | SOLID | Exit codes / PowerShell `$env:` / `python` all OK; minor stale "Opus 4.7" comment. |
| Deterministic lint/format as a hook | GAP | No PostToolUse ruff/format hook; ruff is CI-only. |
| Reflection (Stop/SessionEnd) hook | GAP | None — continuous-learning is a manual norm that lapses. |
| Shareable registration | GAP | `.claude/settings.json` gitignored → hook *files* propagate, *wiring* does not. |

### Verification & eval
| Item | Grade | Reality |
|---|---|---|
| Tests pass / surface | SOLID → **fixed below** | 8287 collected; had 1 fatal collection error (`test_wiki_alias_corner_cases.py` stale import) that aborted bare `pytest`. |
| Output-eval for non-deterministic output | HALF-DONE | Prose lane: real, gating LLM-judge. Coding lane: rubric + AcceptanceScenario exist but **unwired** (no registered dispatcher, no golden scenarios). |
| Trajectory-eval | HALF-DONE | `process.py` scores trajectory and runs — but result is logged, not enforced in the verdict. |
| ui-test live-connector proof | ASPIRATIONAL | Was a living practice; last run 2026-05-19 (~36 days stale). Artifacts unversioned. |
| Bar at eval not demo | HALF-DONE | True for prose; coding lane is demo-gated. |

### Context engineering & automation
| Item | Grade | Reality |
|---|---|---|
| provider_context_feed | SOLID (timing risk) → **mitigated below** | Real, defensive, fail-safe; but ~6 s vs an 8 s inner timeout → silently degrades as worktrees grow. |
| Static/dynamic context split | HALF-DONE | ~71 KB (~18K tokens) loads every session (AGENTS.md dominates); split is emergent, not a reviewed decision; no budget guard (until now). |
| agent-memory health | SOLID | 204 files actively maintained; user auto-memory updated today. |
| Plugin packaging | SOLID | `build_plugin.py` real (stages runtime + import probe + marketplace). Hooks not bundled (maybe intentional). |
| Model routing for cost | GAP / **deliberate non-goal** | Provider chain routes for availability, not cost. Cost-tiering conflicts with the hook-enforced always-latest norm. |
| LSP symbol precision | GAP (low priority) | Not configured; Grep/Glob suffice for this Python+md repo. |

---

## What shipped this session (verified durable fixes)

All landed on branch `worktree-sdlc-best-practices-adoption`, ruff-clean, verified. The shipped code additionally passed an **independent Codex read-only correctness review via `mcp__codex__codex` — verdict SHIP** (2026-06-24, thread `019efd64`): `_merged_branch_set` semantically equivalent + fail-safe; the settings merge tool can't clobber local config; the budget invariant is correctly non-blocking; the test import matches the current API.

1. **Unblocked the test suite** — fixed the stale `_resolve_bugs_canonical` import in `tests/test_wiki_alias_corner_cases.py` (renamed to `_resolve_filed_page_canonical(..., category="bugs")`, no compat shim). Full suite now collects **8287 tests, 0 errors** (was 1 fatal error); the file's own 13 tests pass (10 pass / 3 skip on Windows NTFS).
2. **Context-budget guard** — `scripts/check_context_budget.py` measures the always-loaded set (CLAUDE.md+AGENTS.md+STATUS.md): HARD budget for STATUS.md (its own declared 4 KB/60 ln) exits 2 under `--strict`; soft advisory targets for AGENTS.md/CLAUDE.md warn only. Wired as the committed **`context-budget` invariant** (`scripts/invariants/context_budget.py`, propose-only, not commit-blocking — same stance as `concerns-staleness`) so the "AGENTS.md tripled unaudited" drift class is now caught automatically. This is the durable home (committed) vs the gitignored settings.json.
3. **provider_context_feed timing** — widened the hook's inner subprocess timeout 8→9 s and switched to `sys.executable`, so a slow feed fails safe instead of timing out the whole hook. (Deeper fix — caching the git porcelain/merge-base calls — routed below.)
4. **Skill residue** — rewrote infra-ops references that named the deleted `godaddy-ops`/`cloudflare-ops` skills to point within infra-ops; skills still validate.
5. **Wove Codex-via-MCP into Claude behavior** — `CLAUDE.md §"Calling Codex via MCP"` documents that `mcp__codex__codex` is a second model family in the harness (opposite-provider review, adversarial/second-opinion, diverse judging, fresh-eyes-when-stuck) with discipline. Demonstrated it by running the **R1 opposite-provider review through Codex** — which caught a real factual error in the design note (wrong wiring point) and returned ADAPT. That is the SDLC research's harness/orchestration + diverse-verification practice, live.
6. **provider_context_feed O(N)→O(1) (R10)** — replaced the per-branch `merge-base --is-ancestor` loop with one `git branch --merged` (`_merged_branch_set`). Measured **~6 s → 0.88 s**; 20 tests pass. The deeper fix behind the interim timeout-widen.
7. **Skills sync-target clarity (R9.2)** — documented in `scripts/sync-skills.ps1` that `.claude` is the sole mirror target (Codex reads `.agents/` directly), so no future session re-introduces a `.codex` mirror.
8. **Shared-config mechanism (R5, opt-in)** — `.claude/settings.shared.json` (committed: env + Read deny-list for generated/vendored paths) + `scripts/setup_claude_settings.py` (deep-merge `--apply` / drift `--check`, backs up, never clobbers local keys; 6 tests). Closes the blog's "version-control your exclusions" gap that the gitignored settings.json created. Host opts in with one command; hooks-registration propagation left as a host/DRI cross-platform call.
9. **Deep re-read of the primary whitepaper (51 pp) + two refinements.** Read the full source, not summaries. Adoption holds up against the primary text — it validates the context-budget guard ("treat the static/dynamic boundary as a first-class, versioned decision"), hooks-as-guardrails ("the place for things the agent should never forget but often does"), and Codex-via-MCP ("orchestration: sub-agent spawning, model routing, hand-offs between specialists"; A2A). Refinements: (a) **grounded R1's eval rubric in the whitepaper's 5 explicit dimensions** — task success, tool-use quality, trajectory compliance, hallucination, response quality; (b) added an **AI-generated-code review** section to the `code-review-and-quality` skill (hallucinated/slopsquatted deps, "looks-right-but-wrong" conceptual errors, skipped-verification trajectory, skepticism of clever code) — directly from the whitepaper's "re-shape code review for AI-generated code."
10. **Two opt-in hooks (R6 + R7), the first real consumers of R5.** `session_reflection_nudge.py` (SessionEnd — nudges to commit + capture learning only when uncommitted durable changes remain) and `ruff_autofix_on_write.py` (PostToolUse — silent `ruff --fix` on edited `.py`, non-blocking). Both wired into `settings.shared.json` as opt-in (host flips via `setup_claude_settings.py --apply`); both tested with synthetic payloads, and the merge tool unions them without clobbering local hooks. Directly from the whitepaper's "wire deterministic checks as hooks" + "stop hooks that reflect and propose CLAUDE.md/memory updates."
11. **"Finish-all" wave (2026-06-25).** R1/S1 — the eval-gate beachhead (`tests/test_acceptance_suite_ci.py`: rubric'd, CI-gated, blocks a malformed call, zero production-behavior change, Codex SHIP after a `sqlite_only` fix). R2 — STATUS.md's 2 false claims corrected. R3 — AGENTS.md duplicate-section dedup. R4 — `ADR-002` for the static/dynamic context budget. R9.1 — conservative `ui-test` split (419→391 ln; all CRITICAL rules retained). What's genuinely left is not solo-buildable: R1 S2/S3 (production accept-behavior → navigator + watched rollout), R3's lean/layer move + AGENTS budget number (host), and R8 (live ui-test proof — needs a live connector + human-driven browser, impossible from a background session).

---

## Routed to 100% (decision / gate / host required)

Tracker for the remaining items. None are autonomous-only; each names its blocker.

| ID | Item | Owner | Note |
|---|---|---|---|
| R1 | **Coding-loop eval gate** — **S1 DONE.** `tests/test_acceptance_suite_ci.py` is a rubric'd, *gating* output-eval (min_score 0.9, min-aggregation, named task-success dimensions) run as a normal pytest → CI-gated with no `.yml` change and **zero production-behavior change** (suite-local dispatcher registration). Verified: 3 passed (passes a good call, *blocks* a malformed one), Codex-reviewed SHIP after one fix (`sqlite_only`). **S2 warn-only LANDED** (2026-06-25): rubric wired into `auto_ship.validate_ship_request` behind `WORKFLOW_AUTO_SHIP_RUBRIC_MODE` (default `warn` — annotates `rubric_warnings`, never blocks; fail-open; Codex SHIP; mirror rebuilt; zero block-behavior change). **S3 LANDED** (2026-06-25): pure trajectory scorer + warn-only wiring + ledger, then the **enforce PATH** (`WORKFLOW_AUTO_SHIP_TRAJECTORY_MODE=enforce` promotes a conclusive path-quality FAIL to one `trajectory_path_unsound` block on its own axis; default `warn`; Codex SHIP thread `019f00f9`). **Both S2 + S3 at off/warn/enforce parity.** **ENFORCE FLIP LIVE + verified 2026-06-25** (host-approved, overriding the warn-period gate): the running droplet daemon has `WORKFLOW_AUTO_SHIP_{RUBRIC,TRAJECTORY}_MODE=enforce` (confirmed via `docker exec ... printenv`), durable in systemd's `/opt/workflow/compose.yml`, daemon `healthy`, loopback + public `tinyassets.io/mcp` canary green. Repo config flipped to match (`deploy/compose.yml` + `workflow-env.template`, 3836d073). Low-risk: the gate is the on-demand `validate_ship_packet` MCP action, not an autonomous-loop gate, so it cannot wedge the loop. | **DONE** (engineering + live flip + verified) | Design note + §Codex review: `docs/design-notes/2026-06-24-coding-loop-eval-gate-wiring.md`. |
| R2 | **STATUS.md false claims — DONE.** Corrected the 2 demonstrably-false facts (`universe_server.py` 972→**1927** LOC; `chatgpt-app-submission.json` "absent"→**present, 180 lines**). Budget trim (≤60 ln) left to host curation. | host (trim) | Evidence-based correction (allowed); the `context-budget` invariant surfaces the over-budget state. |
| R3 | **DONE.** Dedup + the lean/layer move both landed. Applied ADR-002's pointer-load lever: env-var catalog → `docs/reference/environment-variables.md`; worktree-discipline full procedure → `docs/reference/worktree-discipline.md`; `git-workflow-and-versioning` skill re-pointed to the doc (resolves the AGENTS↔skill dup). AGENTS.md 699→540 ln / 55.7→44.1 KB (−22%). Codex ADAPT→SHIP (thread 019f00a6); drift clean. | — | Landed 92575e6e. Still over the 30 KB SOFT target *by design* — further shrink would move genuinely-behavioral content (session-start ritual etc.), a separate judgment. |
| R4 | **Static/dynamic context ADR — DONE.** `docs/decisions/ADR-002-static-vs-dynamic-context-budget.md` declares the always-loaded vs on-demand boundary + budgets; enforced by `check_context_budget.py` + the `context-budget` invariant. | host (tune SOFT numbers) | HARD STATUS budget is the file's own contract; SOFT numbers are host-tunable in `CONFIG`. |
| R5 | Shared Claude-config home — **mechanism shipped (opt-in).** `.claude/settings.shared.json` (env + Read deny-list) + `scripts/setup_claude_settings.py` (`--apply` merge / `--check` drift; backs up; preserves local allow/mode/hooks; tested). Host adopts by running `--apply`. | ENABLED 2026-06-25 (host-authorized) | Exclusions + env now propagate (blog's "version-control exclusions"). **Hooks-registration propagation deferred** — the commands are PowerShell-shaped; a cross-platform strategy is a host/DRI call. |
| R6 | Session-reflection hook — **DONE (opt-in).** `.claude/hooks/session_reflection_nudge.py` (SessionEnd; nudges only when uncommitted *durable* changes remain, else silent; non-blocking, exit 2). Wired into `settings.shared.json`; host enables via `setup_claude_settings.py --apply`. Tested: dirty→nudge, clean→silent. | ENABLED 2026-06-25 (host-authorized) | First real consumer of R5 beyond the deny-list. |
| R7 | ruff-on-write hook — **DONE (opt-in).** `.claude/hooks/ruff_autofix_on_write.py` (PostToolUse Write\|Edit\|MultiEdit; silent `ruff --fix` on edited `.py`, always exit 0, best-effort). Wired into `settings.shared.json`; host enables via `--apply`. Tested: auto-fixes native-path edits. | ENABLED 2026-06-25 (host-authorized) | The whitepaper's "wire deterministic checks as hooks". |
| R8 | **DONE 2026-06-25 — live-connector proof produced by this session.** Self-spawned the visible Chrome (CDP profile; user-sim norm, not a host action), confirmed live `tinyassets.io/mcp` canary green, drove a real Claude.ai conversation through the installed connector: 2 multi-tool exchanges (`get_status`, universe inspect, `goals`, runs detail) rendered accurate LIVE state (12 universes, patch-loop-live active, 303–308s timeout cluster, `account_user=anonymous`) — matches known live state, not hallucinated. Trace `output/claude_chat_trace.md`; log `output/user_sim_session.md`. | — | Landed. The "needs a human" framing was wrong (host corrected). Watch item filed in STATUS (run-transcript persistence gap surfaced during the proof). |
| R9 | `.codex` sync-target DONE. **`ui-test/SKILL.md` split — DONE** (conservative, Codex-blessed: 3 one-time preflight/host-setup sections → `references/preflight-and-setup.md`; 419→391 ln; all 9 `## CRITICAL` rules + the post-fix-evidence + CDP-down-stop nuggets retained in body). `SKILLS_AUDIT.md` → `docs/audits/2026-06-23-skills-refactor-audit.md` (root residue cleared 2026-06-25). | — | Landed. |
| R10 | provider_context_feed git-call cost — **DONE**. Replaced the per-branch `merge-base --is-ancestor` loop (O(N) subprocess spawns) with one `git branch --merged`. Measured **~6 s → 0.88 s**; 20 feed tests pass. Silent-degradation risk resolved. | — | Landed (`_merged_branch_set`). |

### Confirmed non-goals (won't-do unless a norm is reopened)
- **Cost-based model routing** — conflicts with the ratified, hook-enforced always-latest-model norm. Would require relaxing `latest_model_guard.py` / `roster_model_audit.py` first.
- **Machine-readable path-scoped skills** — needs Claude Code loader support for a `paths:` frontmatter field; cannot be fixed in-repo.

---

## What the repo already does that both sources only recommend
Harness-as-product, 33 progressive-disclosure skills with mechanically-enforced mirror parity, read-only explorer subagents that return findings before editing, a real (prose-lane) gating LLM-judge + trajectory eval, MCP servers, ADRs, the idea→spec→build→review→ship skill chain, cross-provider claim coordination, a committed mechanical-invariants framework. The adoption surface is small because the foundation is strong — but the gaps above are real and now tracked.
