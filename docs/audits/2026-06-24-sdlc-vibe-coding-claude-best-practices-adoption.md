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
| Staleness / residue | HALF-DONE → **fixed below** | infra-ops references named deleted skills (`godaddy-ops`/`cloudflare-ops`); `SKILLS_AUDIT.md` left at root. |
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

All landed on branch `worktree-sdlc-best-practices-adoption`, ruff-clean, verified.

1. **Unblocked the test suite** — fixed the stale `_resolve_bugs_canonical` import in `tests/test_wiki_alias_corner_cases.py` (renamed to `_resolve_filed_page_canonical(..., category="bugs")`, no compat shim). Full suite now collects **8287 tests, 0 errors** (was 1 fatal error); the file's own 13 tests pass (10 pass / 3 skip on Windows NTFS).
2. **Context-budget guard** — `scripts/check_context_budget.py` measures the always-loaded set (CLAUDE.md+AGENTS.md+STATUS.md): HARD budget for STATUS.md (its own declared 4 KB/60 ln) exits 2 under `--strict`; soft advisory targets for AGENTS.md/CLAUDE.md warn only. Wired as the committed **`context-budget` invariant** (`scripts/invariants/context_budget.py`, propose-only, not commit-blocking — same stance as `concerns-staleness`) so the "AGENTS.md tripled unaudited" drift class is now caught automatically. This is the durable home (committed) vs the gitignored settings.json.
3. **provider_context_feed timing** — widened the hook's inner subprocess timeout 8→9 s and switched to `sys.executable`, so a slow feed fails safe instead of timing out the whole hook. (Deeper fix — caching the git porcelain/merge-base calls — routed below.)
4. **Skill residue** — rewrote infra-ops references that named the deleted `godaddy-ops`/`cloudflare-ops` skills to point within infra-ops; skills still validate.
5. **Wove Codex-via-MCP into Claude behavior** — `CLAUDE.md §"Calling Codex via MCP"` documents that `mcp__codex__codex` is a second model family in the harness (opposite-provider review, adversarial/second-opinion, diverse judging, fresh-eyes-when-stuck) with discipline. Demonstrated it by running the **R1 opposite-provider review through Codex** — which caught a real factual error in the design note (wrong wiring point) and returned ADAPT. That is the SDLC research's harness/orchestration + diverse-verification practice, live.
6. **provider_context_feed O(N)→O(1) (R10)** — replaced the per-branch `merge-base --is-ancestor` loop with one `git branch --merged` (`_merged_branch_set`). Measured **~6 s → 0.88 s**; 20 tests pass. The deeper fix behind the interim timeout-widen.
7. **Skills sync-target clarity (R9.2)** — documented in `scripts/sync-skills.ps1` that `.claude` is the sole mirror target (Codex reads `.agents/` directly), so no future session re-introduces a `.codex` mirror.
8. **Shared-config mechanism (R5, opt-in)** — `.claude/settings.shared.json` (committed: env + Read deny-list for generated/vendored paths) + `scripts/setup_claude_settings.py` (deep-merge `--apply` / drift `--check`, backs up, never clobbers local keys; 6 tests). Closes the blog's "version-control your exclusions" gap that the gitignored settings.json created. Host opts in with one command; hooks-registration propagation left as a host/DRI cross-platform call.

---

## Routed to 100% (decision / gate / host required)

Tracker for the remaining items. None are autonomous-only; each names its blocker.

| ID | Item | Owner | Note |
|---|---|---|---|
| R1 | **Coding-loop eval gate** (output + trajectory). Codex opposite-provider review DONE — **ADAPT** (2026-06-24, via `mcp__codex__codex`): 3 adaptations gate the build (S2 wiring is `auto_ship.validate_ship_request`, not a `release_safety_gate`; S1 must stay CI-local; S3 needs its own trajectory schema) | navigator (incorporate the 3 adaptations) | Design note + §Codex review: `docs/design-notes/2026-06-24-coding-loop-eval-gate-wiring.md`. Highest leverage. |
| R2 | **STATUS.md** — correct the 2 false claims + trim to ≤60 ln/4 KB | host (STATUS is host-managed) | Not edited from this branch (fast-moving coordination file). |
| R3 | **AGENTS.md lean/layer** — move the ~248-ln worktree manual into `git-workflow-and-versioning`; delete the duplicate "Where new conventions live" block; set a byte budget | navigator (cross-provider canonical) | Budget number = host call; mechanical move = autonomous once approved. |
| R4 | **Static/dynamic context ADR** — declare the always-loaded vs on-demand boundary as a reviewed decision; tune `check_context_budget.py` CONFIG numbers | navigator + host (the numbers) | Guard now exists; the ceiling is the host's to set. |
| R5 | Shared Claude-config home — **mechanism shipped (opt-in).** `.claude/settings.shared.json` (env + Read deny-list) + `scripts/setup_claude_settings.py` (`--apply` merge / `--check` drift; backs up; preserves local allow/mode/hooks; tested). Host adopts by running `--apply`. | host (run `--apply`) | Exclusions + env now propagate (blog's "version-control exclusions"). **Hooks-registration propagation deferred** — the commands are PowerShell-shaped; a cross-platform strategy is a host/DRI call. |
| R6 | **Reflection Stop/SessionEnd hook** — automate the continuous-learning norm | host-decision (what/where it writes) | Depends on R5 for shared registration. |
| R7 | **PostToolUse ruff hook** — deterministic format/lint on edit instead of CI-only | host-decision | Depends on R5. |
| R8 | **ui-test re-run** — fresh live-connector proof; promote to a scored scenario (ties to R1) | host (needs live tunnel + human-driven chatbot) | ~36 days stale. |
| R9 | `.codex` sync-target — **DONE** (documented why `.claude` is sole target; AGENTS.md says Codex reads `.agents/` directly). `ui-test/SKILL.md` split + `SKILLS_AUDIT.md` disposition still open. | navigator / owner | `ui-test` split is **riskier than first rated** — 30+ sections are `## CRITICAL` always-visible operational rules; moving them to load-on-demand refs would hide critical rules. Needs a careful owner-aware pass, not a blind split. |
| R10 | provider_context_feed git-call cost — **DONE**. Replaced the per-branch `merge-base --is-ancestor` loop (O(N) subprocess spawns) with one `git branch --merged`. Measured **~6 s → 0.88 s**; 20 feed tests pass. Silent-degradation risk resolved. | — | Landed (`_merged_branch_set`). |

### Confirmed non-goals (won't-do unless a norm is reopened)
- **Cost-based model routing** — conflicts with the ratified, hook-enforced always-latest-model norm. Would require relaxing `latest_model_guard.py` / `roster_model_audit.py` first.
- **Machine-readable path-scoped skills** — needs Claude Code loader support for a `paths:` frontmatter field; cannot be fixed in-repo.

---

## What the repo already does that both sources only recommend
Harness-as-product, 33 progressive-disclosure skills with mechanically-enforced mirror parity, read-only explorer subagents that return findings before editing, a real (prose-lane) gating LLM-judge + trajectory eval, MCP servers, ADRs, the idea→spec→build→review→ship skill chain, cross-provider claim coordination, a committed mechanical-invariants framework. The adoption surface is small because the foundation is strong — but the gaps above are real and now tracked.
