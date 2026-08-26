# Codex cross-family review — harness reset plan

**Date:** 2026-08-25 · **Reviewer:** Codex CLI (GPT family), read-only, `codex-cli 0.146.0`
**Base:** `origin/main` @ `8cbf9769` · **Brief:** refute the plan; default to reject
**Verdict: REJECT** — the reset objective survives; the execution plan does not.

## Independent verification by Claude (the plan's author)

Every checkable claim below was re-verified against the code before the verdict was accepted.
**All nine held.** The ones that changed the plan:

| Codex claim | Verified | Evidence |
|---|---|---|
| The "3 orphaned hooks" are wired | **TRUE — my error** | `ruff_autofix_on_write` + `session_reflection_nudge` in `.claude/settings.shared.json:27,39` (merged by `scripts/setup_claude_settings.py --apply`); `dev_idle_guard` in `.claude/agents/developer.md:14` frontmatter. My orphan check grepped only `.claude/settings.json`, which is gitignored and machine-local |
| "Nothing writes STATUS.md programmatically" is false | **TRUE — my error** | `scripts/openspec_drain_supervisor.py:410` calls `_set_status_claim()` then `git add STATUS.md` and commits; it also shells `scripts/claim_check.py` at `:670`. `scripts/openspec_flow.py:215` snapshots it. `command_center/collector.py:558` reads it at runtime. The narrow claim survives only for `tinyassets/` — all five hits there are comments |
| The worktree reap destroys uncommitted product code | **TRUE — would have been irreversible** | `../wf-consumer-activation` holds **213 insertions / 78 deletions** across 9 uncommitted files including `tinyassets/runs.py`, `tinyassets/foreground_run_provider.py`, `tests/test_run_provider_session.py`, and the `run-provider-authority` OpenSpec change. No `git revert` restores these |
| Worktree count is wrong | **TRUE — my error** | 61 sibling `wf-*` **directories**, not 101. My `ls -d .../wf-*` matched archive files too |
| `CLAUDE_LEAD_OPS.md` holds design truth | **TRUE** | Its Foundation End-State rule (`:9`) is cited from `tinyassets/storage/__init__.py:26` and `tinyassets/bid/__init__.py:14`. Must move to `PLAN.md` before deletion |
| The public-surface gate duplicates CI | **TRUE** | `.github/workflows/deploy-prod.yml:203` already runs the `--assert-handles` canary, followed by the release-state receipt at `:222` |
| `deployed_sha` as a PR-required check is circular | **TRUE** | A merge gate cannot require production to already contain an unmerged PR head. Valid only as a post-deploy check |
| `scripts/gates/` duplicates the invariants runner | **TRUE** | `scripts/invariants_run.py:54` is the existing registry-and-runner |
| STATUS's `#1489` is a misreference | **TRUE** | PR #1489 is *"feat(command-center): recover the Agent Village"*, MERGED — not the LAN/CSRF vulnerability the row claims |

**Converged independently:** Codex's flaw #1 (the plan's baseline numbers are wrong at the pinned
sha) and #3 (the concern list is stale and incomplete) were both found by the Phase 0 baseline audit
before this review returned, and it arrived at Codex's exact figures — 62,082 B, 21,170/56,
34 skills / 6,348 lines, 12 concern rows. Two families, same numbers.

**Not accepted as stated:** Codex's #8 (AVO/NOOA is decorative) is a fair charge against the plan's
*mapping table*, and the six-capability framing does not license calling separate CI subprocesses
"typed methods." But the one operative use of AVO in this reset — *"which model weakness does this
scaffold encode, and does a current model still have it?"* — is a real deletion criterion that
predates the AVO framing (memory `ai-dev-process-research-2026-08`, 2026-08-02) and survives without
it. Recorded as: keep the criterion, drop the branding.

---

## Codex's review, verbatim

VERDICT: reject

**Material flaws**

1. **The baseline is factually wrong at the pinned SHA.** Fresh measurements at `8cbf9769` found 62,082 always-loaded bytes, `STATUS.md` at 21,170 bytes/56 lines, 15 hooks, 5 active agent-role files, and 34 skills/6,348 lines—not 62,715, 15,526/72, 16, 6, and 25/4,357. The three allegedly orphaned hooks are not orphaned: `ruff_autofix_on_write.py` and `session_reflection_nudge.py` are installed by [.claude/settings.shared.json](C:/Users/Jonathan/Projects/wf-harness-reset/.claude/settings.shared.json:20), while `dev_idle_guard.py` is wired in [.claude/agents/developer.md](C:/Users/Jonathan/Projects/wf-harness-reset/.claude/agents/developer.md:10). The shared settings are actively merged by [setup_claude_settings.py](C:/Users/Jonathan/Projects/wf-harness-reset/scripts/setup_claude_settings.py:97). The deletion manifest was built without a complete caller scan.

2. **Deleting `STATUS.md` as written disables active executable systems.** The statement “nothing writes STATUS.md programmatically” is false. [openspec_drain_supervisor.py](C:/Users/Jonathan/Projects/wf-harness-reset/scripts/openspec_drain_supervisor.py:410) edits and commits STATUS claims, and shells into `claim_check.py` at [line 670](C:/Users/Jonathan/Projects/wf-harness-reset/scripts/openspec_drain_supervisor.py:670). [openspec_flow.py](C:/Users/Jonathan/Projects/wf-harness-reset/scripts/openspec_flow.py:215) includes it in immutable snapshots. The Agent Village reads it at runtime in [command_center/collector.py](C:/Users/Jonathan/Projects/wf-harness-reset/command_center/collector.py:558). Current policy requires the local drain to remain active until cloud cutover in [AGENTS.md](C:/Users/Jonathan/Projects/wf-harness-reset/AGENTS.md:197). The three named workflows do not read the file, and `tinyassets/` has no runtime file import; that limited safety claim survives. The broader cutover does not.

3. **The security migration list is stale, incomplete, and partly false.** Current `STATUS.md` has twelve concern/watch rows, not the plan’s six. The plan would miss the P1 persistent `write_brain` injection, P1 confidential learning becoming public, P0 site/privacy/secrets exposure, and P0 false provider attestations at [STATUS.md lines 2–6](C:/Users/Jonathan/Projects/wf-harness-reset/STATUS.md:2). Conversely:

   - GitHub `#1489` is an unrelated merged Agent Village recovery [PR](https://github.com/Jonnyton/TinyAssets/pull/1489), not the cited LAN/CSRF vulnerability.
   - Cross-origin session fixation is already regression-tested at [tests/test_onboarding_session_refresh.py](C:/Users/Jonathan/Projects/wf-harness-reset/tests/test_onboarding_session_refresh.py:298).
   - The raw refresh-token JSON concern is real at [tinyassets/onboarding/__init__.py](C:/Users/Jonathan/Projects/wf-harness-reset/tinyassets/onboarding/__init__.py:72), but it must be split from the already-fixed CSRF claim.
   - OS sandbox work already has an owning [OpenSpec change](C:/Users/Jonathan/Projects/wf-harness-reset/openspec/changes/engine-os-sandbox/tasks.md:1).
   - The T2/write-ACL flaw is already recorded in [byo-llm-deposit-surface/design.md](C:/Users/Jonathan/Projects/wf-harness-reset/openspec/changes/byo-llm-deposit-surface/design.md:100).
   - `_current_actor` is already an as-built limitation in [paid-market-economy/spec.md](C:/Users/Jonathan/Projects/wf-harness-reset/openspec/specs/paid-market-economy/spec.md:29).

   “Triage first” and “migrate these verbatim” conflict. GitHub issues alone are externally mutable, noisy, network-dependent, and absent from a clone. Use one tracked `docs/concerns/<slug>.md` per unresolved concern as canonical evidence, linking any GitHub issue and owning OpenSpec. Do not bulk-close unrelated issue history merely to make the destination look cleaner.

4. **The deletion categories were not safely closed.**

   - **Fleet scripts:** I found no `.github/workflows` or `tinyassets/` callers. `fleet_status.py` is imported only by `fleet_supervisor.py` and `fleet_floor_guard.py`; safe after explicitly stopping processes and deleting those consumers.
   - **FUSE scripts:** neither `fuse_safe_commit.py` nor `fuse_safe_write.py` is imported or invoked by `.github/workflows` or `tinyassets/`. They are safe to delete given Cowork’s removal, with their tests/docs.
   - **Hooks:** no production/CI runtime dependency, but the shared-settings and role-frontmatter consumers above were missed.
   - **Agent roles:** there are five active files, not six. They are not production/CI dependencies, but [LAUNCH_PROMPT.md](C:/Users/Jonathan/Projects/wf-harness-reset/LAUNCH_PROMPT.md:1) remains entirely Agent-Teams-specific and would become dangling.
   - **`CLAUDE_LEAD_OPS.md`:** most fleet material is obsolete, but its founder-approved “Foundation End-State” design rule at [line 9](C:/Users/Jonathan/Projects/wf-harness-reset/CLAUDE_LEAD_OPS.md:9) is referenced from product modules such as [tinyassets/storage/__init__.py](C:/Users/Jonathan/Projects/wf-harness-reset/tinyassets/storage/__init__.py:26). Move that design truth into `PLAN.md` before deletion.
   - **Skills:** the manifest omits 11 of the actual 34 skills, so “25 → ~9” cannot occur as specified. Deleting `code-review-and-quality` also discards the binding 2026-08-20 shape-before-hardening directive at [line 18](C:/Users/Jonathan/Projects/wf-harness-reset/.agents/skills/code-review-and-quality/SKILL.md:18). Deleting `git-workflow-and-versioning` discards TinyAssets-specific dirty-worktree/data-loss discipline at [line 61](C:/Users/Jonathan/Projects/wf-harness-reset/.agents/skills/git-workflow-and-versioning/SKILL.md:61). Migrate those project-specific sections; generic debugging/planning prose can go.

5. **Phase 2’s worktree reap is the most likely irreversible failure.** Fresh inspection found 61 sibling `wf-*` directories and 26 registered worktrees, not ~125. More importantly, `../wf-consumer-activation` contains nine uncommitted product/spec/test files—213 insertions and 78 deletions—including `tinyassets/runs.py`. Other registered lanes are dirty or in flight. Deleting those directories loses content that no `git revert` can restore. Approval of a plan with an unresolved wildcard is not informed approval of each later-changing absolute directory.

6. **Phase 3 builds a second gate framework and contains a circular gate.** A PR-required `deployed_sha` check cannot require production to contain an unmerged PR head. The public canary is already executed by [deploy-prod.yml](C:/Users/Jonathan/Projects/wf-harness-reset/.github/workflows/deploy-prod.yml:203), followed by release-state publication at [line 222](C:/Users/Jonathan/Projects/wf-harness-reset/.github/workflows/deploy-prod.yml:222). The repository already has an invariant runner in [scripts/invariants_run.py](C:/Users/Jonathan/Projects/wf-harness-reset/scripts/invariants_run.py:54). Adding `scripts/gates/` duplicates both.

   `crossfamily.py` is also unsound: a committed `.agents/verdicts/<sha>.json` changes the SHA it supposedly approves and is self-attestable unless an external authority signs/posts it. `evidence.py` can verify that strings exist, not that evidence proves the claim. “No prose gate survives” confuses machine-observable conditions with judgment.

7. **Phase 5 is the same ratchet under a new name.** One Stop hook has no specified event stream from which to know that the same file was edited, the same test failed, or the same gate failed three times. Implementing those predicates requires persistent PostToolUse logging, normalization, storage, retention, false-positive policy, and tests—another harness subsystem. “Zero product-line churn” would flag legitimate security reviews, specs, docs, and this reset itself. Add nothing until transcript measurements prove a repeated failure class and a much smaller deterministic check can catch it.

8. **AVO/NOOA is decorative framing, not the diagnosis.** NVIDIA defines the six capabilities as model-facing interfaces on one Python object: typed arguments/returns, live-object references, generated Python actions, Python orchestration loops, typed object fields, and callable context/event APIs. Its typed gates work because deterministic checks and model reasoning share one object and trace. NVIDIA also calls NOOA an experimental surface, not a replacement for existing harnesses. [NVIDIA’s six-capability description](https://developer.nvidia.com/blog/six-agent-harness-capabilities-for-higher-model-performance/) does not justify mapping `STATUS.md` to “object state” or separate CI subprocesses to NOOA typed methods. The AVO supervisor monitors an autonomous search trajectory; it does not validate a Claude Code Stop hook. The reset may be right, but AVO is post-hoc branding on “delete stuff.”

9. **The rollback section is false.** Git revert cannot reopen bulk-closed GitHub issues, undo branch-protection changes, restore scheduled tasks/processes, or recover deleted uncommitted worktree files. “One commit per phase” also contradicts Phase 1’s separate migration/deletion commits and Phase 2’s external filesystem operations.

10. **The plan leaves obvious dead surfaces behind.** With the host decisions, it should also remove or rewrite:

   - [LAUNCH_PROMPT.md](C:/Users/Jonathan/Projects/wf-harness-reset/LAUNCH_PROMPT.md:1);
   - [.claude/settings.shared.json](C:/Users/Jonathan/Projects/wf-harness-reset/.claude/settings.shared.json:2) and its setup script;
   - Agent Village’s STATUS/Kimi/background-dispatch paths in [command_center/collector.py](C:/Users/Jonathan/Projects/wf-harness-reset/command_center/collector.py:5);
   - `scripts/cowork-bootstrap.sh`, `.agents/cowork-session-bootstrap.md`, active root `COWORK_HANDOFF_*`, `.cowork-*`, and `WebSite/HOOKS_FUSE_QUIRKS.md`;
   - orphaned community-loop classifier [scripts/merge_readiness.py](C:/Users/Jonathan/Projects/wf-harness-reset/scripts/merge_readiness.py:1);
   - the local OpenSpec drain/scheduled-task stack if “background Claude fleets are out” includes autonomous drain workers.

**Must-change before executing**

1. Rebuild Phase 0 from the pinned SHA with an exhaustive, generated manifest: exact tracked target, every caller/importer/config reference, tests, active process/task, and migration destination.
2. Make `docs/concerns/` canonical; migrate every current concern individually with verbatim source text plus re-verification, mitigation, owner artifact, and optional issue URL. No GitHub backlog purge.
3. Retire or replace `openspec_drain_supervisor`, `openspec_flow` STATUS classification, and Agent Village STATUS consumption before deleting the file.
4. Inventory every worktree individually. Dirty/untracked content must be committed, patched/bundled, or explicitly abandoned by exact path. Reaping gets its own non-git rollback record.
5. Replace the skill plan with an explicit classification of all 34 skills. Preserve/migrate project-specific review sequencing, worktree safety, UI testing, deploy, security, conditional-edge, and skill-sync knowledge.
6. Delete Phase 3’s new gate directory. Wire `check_context_budget.py --strict` directly into existing CI; keep the existing deploy canary and release receipt. Leave judgment gates as judgment unless an external, head-SHA-bound authority is designed.
7. Delete Phase 5. Reconsider only after post-reset telemetry demonstrates a concrete repeated-loop failure.
8. Add rollback procedures for GitHub state, branch protection, scheduled tasks, and worktree artifacts—not merely git commits.

**What survives**

- The reset objective and the binding two-peer/no-fleet/no-Cowork decisions.
- Removing the STATUS import and deleting the board—after its executable consumers and concerns are migrated.
- Deleting Agent Teams, fleet-floor hooks/scripts, FUSE guards/wrappers, and generic process skills.
- Keeping `session_sync_gate_hook`, `latest_model_guard`, OpenSpec specifications, public canary, release receipt, and genuinely project-specific skills.
- A strict context-budget CI check and a staged end-to-end trial on a real live product task.