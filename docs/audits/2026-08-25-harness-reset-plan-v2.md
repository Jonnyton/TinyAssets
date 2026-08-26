# Harness reset — execution plan v2 (post-Codex)

**Supersedes** the v1 plan. **Base:** `origin/main` @ `8cbf9769` · **Branch:** `harness-reset`
**Gate:** Codex returned `REJECT` on v1; nine claims verified, all held
(`docs/audits/2026-08-25-harness-reset-codex-review.md`). **Baseline:**
`docs/audits/2026-08-25-harness-reset-baseline.md`.

## What changed from v1, and why

| v1 said | v2 says | Why |
|---|---|---|
| Reap ~125 worktrees | **Inventory each of 61 dirs + 26 registered; preserve dirty content first** | `../wf-consumer-activation` holds 213 uncommitted insertions incl. `tinyassets/runs.py`. No git revert restores that |
| Delete STATUS.md, then sweep readers | **Retire its executable consumers first, then migrate, then delete** | `openspec_drain_supervisor.py:410` writes+commits it; `openspec_flow.py:215` snapshots it; `command_center/collector.py:558` reads it at runtime |
| Migrate concerns to GitHub issues; prune the issue flood | **`docs/concerns/<slug>.md` is canonical**; optional issue link; no bulk close | Issues are externally mutable, network-dependent, absent from a clone. Bulk-closing unrelated history to tidy a destination is not a harness fix |
| 3 hooks are orphaned | **They are wired** — via `.claude/settings.shared.json:27,39` and `.claude/agents/developer.md:14` | v1's orphan check grepped only the gitignored local `settings.json` |
| Skills 25 → ~9 | **Classify all 34 explicitly**; migrate project-specific sections out of skills that die | v1's manifest omitted 11 skills that exist |
| Delete `CLAUDE_LEAD_OPS.md` | **Move its Foundation End-State rule to `PLAN.md` first** | Cited from `tinyassets/storage/__init__.py:26` and `tinyassets/bid/__init__.py:14` |
| New `scripts/gates/run.py`, 4 gates | **Reshape into `scripts/invariants_run.py`**; drop `public_surface` + `evidence`; `deployed_sha` post-deploy only | The runner already exists. The canary already runs at `deploy-prod.yml:203`. A merge gate cannot require prod to contain an unmerged head |
| Rollback = git revert | **Non-git rollback record** for worktrees, GitHub state, branch protection, scheduled tasks | Git cannot restore deleted uncommitted files or reopen external state |

**Host decision on the supervisor (2026-08-25):** Codex recommended deleting Phase 5; the concern
was put to the host and the host chose **build the full supervisor as planned**, including the
persistent event stream. Building it as specified.

**AVO framing:** the six-capability mapping is dropped as post-hoc. The one operative criterion is
kept, and it predates AVO (memory `ai-dev-process-research-2026-08`, 2026-08-02): *which model
weakness does this scaffold encode, and does a current model still have it?*

---

## Phases

**P1 — Preserve at-risk work.** Inventory every worktree individually. Any dirty/untracked content
is committed to its own branch or bundled to `docs/audits/harness-reset-preserved/`. Record every
path. Nothing is deleted in this phase. *Gate: zero dirty registered worktrees, or an explicit
per-path abandonment recorded.*

**P2 — Retire the board's executable consumers, then the board.** In order, separate commits:
retire/repoint `openspec_drain_supervisor` STATUS writes, `openspec_flow` STATUS snapshotting, and
`command_center/collector.py` STATUS reads → migrate the 10 durable concerns to
`docs/concerns/<slug>.md` verbatim with re-verification → delete `STATUS.md`, its `@` import,
`claim_check.py` (+3 importers swept), `concerns_resolve.py`, `invariants/concerns_staleness.py` →
AGENTS.md three-files → two-files. *Gate: no runtime reader remains; every concern has a file.*

**P3 — Delete the dated scaffolds.** Corrected manifest: 13 hooks (keeping `session_sync_gate_hook`,
`latest_model_guard`), **including the `settings.shared.json` and `developer.md` wirings**;
Agent Teams env; 5 agent roles; `LAUNCH_PROMPT.md`; `CLAUDE_LEAD_OPS.md` (after its design rule moves
to `PLAN.md`); `fleet_*`/`fuse_safe_*` + tests; Cowork residue (`scripts/cowork-bootstrap.sh`,
`.agents/cowork-session-bootstrap.md`, `COWORK_HANDOFF_*`, `.cowork-*`,
`WebSite/HOOKS_FUSE_QUIRKS.md`); `scripts/merge_readiness.py`; 24 of 34 skills with project-specific
sections migrated first. One commit per group.

**P4 — Gates into the existing runner.** `context_budget` → `pre_commit_scope=True` with retuned
ceilings; new `deployed_sha` (post-deploy) and `crossfamily` (external authority, not a
self-committed verdict file) invariants; wire `invariants_run.py --pre-commit` as a CI required
check. Delete the AGENTS.md prose each one replaces. *No `scripts/gates/`.*

**P5 — AGENTS.md to invariants-only.** ~493 → ~120 lines; CLAUDE.md ~223 → ~40. Everything else to
`docs/reference/*.md`. The budget pawl from P4 is what holds it.

**P6 — Supervisor (host-directed, full build).** Persistent PostToolUse event log + normalization +
storage + retention + false-positive policy + tests, and one `Stop` hook that trips on repeated
identical failures. Churn predicate must exempt spec/docs/security lanes — Codex's objection that it
would flag this very reset is correct and is a test case.

## Verification

Unchanged from v1 except: (2) becomes "no hook file is unreferenced across `settings.json`,
`settings.shared.json`, and agent frontmatter"; (3) becomes `invariants_run.py --pre-commit` required
in branch protection; (5) becomes "every concern has a `docs/concerns/` file, verified individually."
