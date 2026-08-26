# Harness reset — baseline audit

**Date:** 2026-08-25 · **Base:** `origin/main` @ `8cbf9769` · **Worktree:** `wf-harness-reset`
**Purpose:** the measured "before" for the AVO/NOOA-guided harness reset, and the **rollback map** —
what each scaffold slated for deletion encodes, and where its content goes.

Nothing was deleted to produce this document. Every number below is reproducible from the
commands in § *Reproduce*.

---

## 1. Always-loaded context

`python scripts/check_context_budget.py` — **HARD FAIL today**, on `origin/main`, before any change:

| File | Lines / max | Bytes / max | Status |
|---|---|---|---|
| `STATUS.md` | 56 / 60 | **21,170 / 4,096** | **OVER-HARD (5.2×)** |
| `AGENTS.md` | 493 / 450 | 28,524 / 30,000 | OVER-soft (lines) |
| `CLAUDE.md` | 223 / 200 | 12,388 / 12,000 | OVER-soft |
| **COMBINED** | — | **62,082 / 40,000** | **1.55× over** |

`CLAUDE_LEAD_OPS.md` adds a further 13,131 B when the lead path loads it. `PLAN.md` is 90,671 B
(pointer-loaded, not always-on — correctly so).

AGENTS.md history: **17.6 KB (2026-04-28) → 571 → 439 → 479 → 493 lines.** It has never
ratcheted down.

## 2. The measuring instrument exists, is registered, and is set to never block

This is the sharpest finding, and it corrects the plan's own claim that the budget check is
"wired to nothing." It is wired — and deliberately defanged.

`scripts/invariants/context_budget.py:40-42`:

```python
pre_commit_scope = False  # host-managed content; surface, don't block (cf. concerns-staleness)
poll_interval_s = None    # on-demand
auto_heal = False         # propose-only; splitting content is editorial
```

`python scripts/invariants_run.py --check-all` right now:

```
[OK      ] cross-provider-drift   cross-provider drift check clean
[OK      ] mirror-parity          all 364 canonical file(s) mirror-matched
[OK      ] mojibake               3513 text file(s) scanned clean
[OK      ] skills-valid           skill validation passed
[SKIPPED ] tab-single             CDP unreachable (Chrome not launched)
[VIOLATED] concerns-staleness     1 concern(s) machine-flagged as stale
[VIOLATED] context-budget         STATUS.md over declared HARD budget; always-loaded total 62082 bytes
```

Both VIOLATED invariants are `pre_commit_scope=False`, `auto_heal=False`, `poll_interval_s=None` —
they run only when a human types `--check-all`, which nothing does. The tracked pre-commit hook
(`scripts/git-hooks/pre-commit`, 446 lines) invokes `invariants_run.py` for exactly two checks,
`cross-provider-drift` and `skills-valid`. Neither VIOLATED invariant is among them.

**The ratchet has a measuring rod and no pawl.** That is the mechanism behind 17.6 KB → 62 KB.

Branch protection required checks are `["policy", "Diff scope declared", "required-tests"]` —
no context or coordination gate among them.

## 3. Coordination churn

Measured over `origin/main`:

| Metric | Value |
|---|---|
| Commits touching `STATUS.md`, last 90 days | **541 of 1,181 (46%)** |
| Commits changing **nothing but** `STATUS.md`, last 500 | **83 (17%)** |
| Commits with **zero product-code churn**, last 500 | **223 (44%)** |
| Tracked files referencing `STATUS.md` | **296** (160 in `docs/`, 39 in `openspec/`, 8 skills) |
| `../wf-*` worktree directories on disk | **101** |
| Registered git worktrees | **26** |

"Zero product-code churn" = the commit touches no path under `tinyassets/`, `WebSite/`, `deploy/`,
`packaging/`, or `tests/`. Nearly half of all commits move only harness, board, and docs.

Commit-subject prefixes, last 500: `fix` 96, `feat` 49, `chore` 47, `docs` 46, **`coord` 39**,
`test` 13, `ops` 13, `app` 12, **`status` 11**, `spec` 11.

## 4. Hook layer — 15 hooks, 1,728 lines

| Hook | Lines | Wired | What it encodes | Disposition |
|---|---|---|---|---|
| `fleet_floor_guard.py` | 164 | PostToolUse(Bash), Stop | Keep N background lanes alive | **DELETE** — kill-filed by `.claude/fleet.off` (2026-07-25) for false-positive halts that "block the turn 3x then yield"; still armed on every Bash call |
| `teammate_idle_guard.py` | 180 | TeammateIdle | Nudge idle Agent-Teams teammates | **DELETE** — Agent Teams out of scope |
| `stale_team_pruner.py` | 172 | SessionStart | Reap dead teammate dirs | **DELETE** — same |
| `provider_context_feed_hook.py` | 160 | SessionStart, UserPromptSubmit | Inject cross-provider memory/worktree/idea candidates **on every action prompt** | **DELETE** — this per-turn injection *is* the endless-process surface; replaced by on-demand query |
| `codex_dispatch_nudge.py` | 136 | UserPromptSubmit | Remind to dispatch to Codex | **FOLD** into AGENTS.md prose (reflex already in CLAUDE.md) |
| `cross_provider_drift_guard.py` | 130 | PostToolUse(Write\|Edit) | Keep 4 providers' rule files in sync | **DELETE** — 2 providers remain, both read AGENTS.md |
| `fuse_write_truncation_guard.py` | 123 | PostToolUse(Write\|Edit) | Cowork FUSE tail-truncation | **DELETE** — Cowork out of scope |
| `roster_model_audit.py` | 111 | SessionStart | Audit `.claude/agents/*` model pins | **DELETE** — role files go with Agent Teams |
| `ruff_autofix_on_write.py` | 100 | — | Auto-ruff on write | **DELETE** — orphan, never wired |
| `fuse_pre_write_reject.py` | 96 | PreToolUse(Write\|Edit) | Block Write/Edit on FUSE | **DELETE** — Cowork out of scope |
| `dev_idle_guard.py` | 96 | — | Nudge idle devs | **DELETE** — orphan |
| `session_sync_gate_hook.py` | 69 | SessionStart | Warn when checkout is behind `origin/main` | **KEEP** — caught the 825-commits-behind state this session |
| `latest_model_guard.py` | 68 | PreToolUse(Agent) | Block stale model pins on subagents | **KEEP** |
| `session_reflection_nudge.py` | 68 | — | Ask for REFLECTION.md | **DELETE** — orphan |
| `task_shape_guard.py` | 55 | TaskCreated | Shape-check task prompts | **DELETE** — Agent Teams out of scope |

Three hooks (`dev_idle_guard`, `ruff_autofix_on_write`, `session_reflection_nudge`) are wired
nowhere — 264 lines of dead code the harness carried without noticing.

Target: **15 → 2** (`session_sync_gate_hook`, `latest_model_guard`), plus at most one supervisor
hook added in Phase 5. Net hook count ≤3.

`.claude/settings.json` env to strip: `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS`,
`CLAUDE_CODE_TEAMMATE_MODE`, `TINYASSETS_FLEET_FLOOR_CODEX=8`, `TINYASSETS_FLEET_FLOOR_CLAUDE=6`.

## 5. Skills — 34 skills, 6,348 lines

**Correction to the plan:** the plan counted 25 skills / 4,357 lines from the local checkout, which
was 825 commits behind. `origin/main` carries **34 / 6,348**. Nine skills the plan never enumerated
exist: `api-and-interface-design` (294), `classic-game-design-test` (186),
`conditional-edge-testing` (104), `deprecation-and-migration` (206), `frontend-ui-engineering` (322),
`game-prototyping` (148), `implementation-precedent-scout` (179), `performance-optimization` (350),
`spec-driven-development` (200).

`spec-driven-development` (200) and `openspec` (121) overlap directly — one is redundant.

Deletion criterion (AVO's own): *which model weakness does this encode, and does an Opus-5 /
Fable-5-class model still have it?* Generic software-engineering practice → delete. Project
knowledge a model cannot infer from the repo → keep.

**Keep (~10, project knowledge):** `ui-test` (502 — live connector proof path), `website-editing`
(161), `infra-ops` (60 — DNS/Cloudflare/GoDaddy), `peer-agents` (59 — the Claude↔Codex route),
`external-research-implications` (380), `browser-testing-with-devtools` (302),
`security-and-hardening` (349), `shipping-and-launch` (111), `openspec` (121),
`implementation-precedent-scout` (179 — repo-specific search discipline).

**Delete (~24, generic practice or dated scaffolding):** `planning-and-task-breakdown`,
`incremental-implementation`, `debugging-and-error-recovery`, `code-simplification`,
`subagent-driven-development`, `context-engineering`, `documentation-and-adrs`, `domain-model`,
`improve-codebase-architecture`, `code-review-and-quality`, `test-driven-development`,
`git-workflow-and-versioning`, `skill-authoring`, `using-agent-skills`, `api-and-interface-design`,
`deprecation-and-migration`, `frontend-ui-engineering`, `performance-optimization`,
`conditional-edge-testing`, `classic-game-design-test`, `game-prototyping`, `idea-refine`,
`spec-driven-development` (superseded by `openspec`), and **`auto-iterate`** — which is the ratchet
itself, and whose own text concedes it has no down-mechanism.

Deleting a skill sweeps inbound references (`using-agent-skills` router, Quick Reference table,
sibling cross-links, `AGENTS.md`, `PLAN.md`) and re-runs `scripts/sync-skills.ps1`, per
AGENTS.md § *Project Skills*. The `mirror-parity` (364 files) and `skills-valid` invariants gate this.

## 6. Agent roles and fleet scripts

`.claude/agents/`: `critic` (65), `developer` (59), `navigator` (118), `user` (95), `verifier` (62).
All five exist to staff Agent Teams. With teams out of scope they are dead weight; the two
capabilities worth preserving — independent verification and adversarial review — move to
`peer-agents` subprocess dispatch (Codex on Codex's own budget), which is strictly cheaper than
burning a Claude context on a relay.

Companion deletions: `CLAUDE_LEAD_OPS.md` (156 lines / 13 KB), `scripts/fleet_status.py`,
`scripts/fleet_supervisor.py`, `scripts/fuse_safe_commit.py`, `scripts/fuse_safe_write.py`,
`.claude/fleet.off`, CLAUDE.md §§ *Agent Teams* / *Lead Operations* / both FUSE sections.

**Do not delete before confirming no importer.** Verified this pass: no file under `tinyassets/`
imports any `fleet_*` or `fuse_safe_*` module. Re-verify at deletion time.

## 7. STATUS.md deletion safety

**Production is unaffected.** All five `tinyassets/` matches for `STATUS.md` are *comments*
(`api/branches.py:1121`, `mcp_server.py:66`, `provider_serving_binding.py:336`,
`runtime_singletons.py:26`, `work_targets.py:497`) — no read, no write, no path resolution.
`scripts/uptime_alarm.py:4-5` records that the lead already overrode the design that would have
written alarms into STATUS.md, routing to `.agents/uptime_alarms.log` instead.

**Tooling that parses the board and goes with it:** `scripts/claim_check.py`,
`scripts/concerns_resolve.py`, `scripts/invariants/concerns_staleness.py` (and its registration in
`invariants_run.py`), the STATUS entry in `check_context_budget.py` / `invariants/context_budget.py`.
**Readers to sweep:** `worktree_status.py`, `wt.py`, `capture_idea.py`, `provider_context_feed.py`,
`openspec_flow.py`, `openspec_drain_supervisor.py`, plus 296 tracked files' prose references.

### Live concerns — the real list, and a correction to the plan

**Correction.** The plan named six concerns drawn from the local checkout, which was 825 commits
behind. Three of them (`#1489` unauth LAN, the BYO-LLM refresh-token store, "no OS engine sandbox")
are **no longer on the board** — superseded or folded into newer rows. The list below is what
`origin/main` @ `8cbf9769` actually carries. This is the set that must survive.

| # | Concern | Filed / verified | Evidence |
|---|---|---|---|
| 1 | **P1** `write_brain` persistent prompt-injection: attacker-authored content reaches `write_brain` via `read_commons_shape`/WebFetch, `commit_learning` mislabels it "founder conversation", next turn it is concatenated verbatim into the system prompt — persistently steering an agent that holds `write_graph`/`run_graph`/`connect_compute` authority | 2026-08-24 | `openspec/changes/served-agent-build-run/design-hardening.md` |
| 2 | **P1** Founder-taught canon inherits `DEFAULT_CREATE_VISIBILITY="public"` with no narrowing step — confidential `converse` input is committed by `commit_learning` and returned by anonymous `read_page`/search. **Codex REPRODUCED** | 2026-08-06 | `docs/audits/2026-08-06-cloudflare-os-architecture-implications.md` |
| 3 | **P0** Public-site privacy/deps/CI: private/operator reads; React 1C/1H, Svelte 7H, design 2H; same-repo PRs can request 19 secrets | 2026-07-27 | — |
| 4 | **P0** Graph/provider code can falsely attest or run in-process; router fallback neutralizes isolation refusals | 2026-07-02 / 07-25 | #1573 |
| 5 | **P1** No live failure proof — #1645 repair escalation and reconcile fail/cancel cap are CI/structural-only | 2026-07-23 / 07-26 | — |
| 6 | **P1** Surface parity (served-agent BUILD verbs) PARTIAL: `write_graph` PATCH, `connect_http`, `grant_effector_consent`, `set_engine`/`bind_serving_provider`, remix still missing on the served surface | 2026-08-23 / 08-24 | `openspec/changes/served-agent-build-run/design-hardening.md` |
| 7 | **P1** `EPOCH2_QUEUE_CONSUMER_READY=True` — 3 tests still assert the closed gate; the only blockers of main's `full-tests` tripwire (run 30875123887). Not quarantined | 2026-08-03 / 08-04 | — |
| 8 | **P2** `_current_actor` env fallback bypasses `permissions.py` | 2026-06-30 / 07-22 | `tinyassets/engine_helpers.py:192` |
| 9 | Cloud automation ROLLBACK refused >24h after setup — binding id derives from the definition, so it re-selects the expired original. Covered by test, not fixed | 2026-08-05 | — |
| 10 | Privacy Q6.3 — legacy `set_engine` writes no ceiling; gemini/groq/grok remain fallbacks; ambient no-universe env can reach maintainer auth until V2 | 2026-04-17 / 07-25 | `tinyassets/providers/router.py:89-92` |
| 11 | *Watch* — browser-found plug-and-play fixes live on prod (#2532-#2537, #2550); founder X deposit pending, first organic X post is the proof | 2026-08-25 | — |
| 12 | *Watch* — prod disk 78.6%, ~4.8 GB from 74 min of deploys; guarded by `disk_watch` (80%) + hourly `disk_autoprune` (85%) | 2026-08-25 | — |

Rows 1-10 are durable findings and need a home that outlives STATUS.md. Rows 11-12 are watches with
their own automated guards and expire on their own.

### The Work table is already a pointer, not a backlog

STATUS.md's own Work header says it: *"Queue lives in OpenSpec, not here (2026-08-02): 40 active
changes are the backlog."* Of ~40 Work rows, most cite `openspec/changes/<name>/` as their content
and exist only to say "someone is on this." **Migrating those to GitHub issues would create a third
copy of the same queue.** The correct disposition per row class:

| Row class | Count (approx) | Destination |
|---|---|---|
| Cites an `openspec/changes/*` dir | ~22 | **Delete the row.** OpenSpec already holds it; `python scripts/openspec_flow.py audit` lists them |
| `host-action` / `host-decision` (needs the founder, not an agent) | ~10 | GitHub issue, `concern` label — an agent cannot act on these and they must not vanish |
| `monitoring` / *Watch* | ~5 | Delete. Each names its own automated guard or expiry condition |
| Live security concern | 10 | GitHub issue, `security` label |
| Stale / premise-inverted | TBD at migration | Drop with a one-line reason recorded here |

Per memory `stale-backlog-rows-misdirect`, each row's premise is verified against code before it
moves — several rows already carry self-corrections ("UNCLEAR (triage 2026-08-02)", "re-verify vs
merged #1784", "the change dir does NOT exist yet").

Labels created for the destination this session: `concern`, `security`, `harness`.

**The destination needs pruning first.** 358 open issues: 106 `Deploy failed`, 4 `deploy-failed`,
3 `DR drill FAILED` (113 bot build notifications, all for shas superseded by the 2026-08-23
deploy-chain verification on `ce8f8197`), and 180 `[WIKI-*]` from the auto-change loop that was
**retired 2026-06-25** (`AUTO_FIX_DISABLED=true`). That leaves ~65 human-authored issues. The label
set tells the same story: 70+ labels, of which ~20 are `auto-fix-*` / `writer:*` / `checker:*`
residue from the retired loop.

## 8. What is genuinely under-engineered

Every gate that matters is prose, enforced by nothing:

| Gate | Stated where | Enforcement today |
|---|---|---|
| "Merged is not deployed" (Hard Rule 14) | AGENTS.md | none — five PRs landed 2026-07-21, none shipped |
| Public-surface canary after DNS/tunnel/connector change (Hard Rule 11) | AGENTS.md | `mcp_public_canary.py` exists; invoked by memory, not by a gate |
| Opposite-provider review before build/push/rollout | AGENTS.md § *Project Skills* | a nudge hook that can be ignored |
| Evidence-before-completion | AGENTS.md § *Quality Gates* | prose |
| Context budget | file headers + an invariant | registered, VIOLATED, `pre_commit_scope=False` |
| Stagnation / stuck-loop redirect | AGENTS.md ("if stuck 3+ iterations…") | prose — no trajectory monitor exists |

The last row is AVO's supervisor layer, and its absence is the direct mechanism of "endless process":
nothing in the harness can observe that a session has spent 44% of its commits not touching product
code.

## 9. Rollback map

One branch (`harness-reset`), one commit per phase, one commit per hook group. `git revert <sha>`
restores any single step. This document records what each deletion encoded so a revert is a decision,
not an archaeology project. Migrated concerns get their issue URLs written into the § 7 table as
they land.

## Reproduce

```bash
python scripts/check_context_budget.py
python scripts/invariants_run.py --check-all
for f in .claude/hooks/*.py; do b=$(basename "$f"); grep -q "$b" .claude/settings.json || echo "ORPHAN $b"; done
git log --since=90.days --format='%h' -- STATUS.md | wc -l
for c in $(git log -500 --format='%h'); do git show --name-only --format='' "$c" \
  | grep -qE '^(tinyassets/|WebSite/|deploy/|packaging/|tests/)' || echo "$c"; done | wc -l
git grep -l 'STATUS\.md' | wc -l
gh api repos/Jonnyton/TinyAssets/branches/main/protection --jq '.required_status_checks.contexts'
```
