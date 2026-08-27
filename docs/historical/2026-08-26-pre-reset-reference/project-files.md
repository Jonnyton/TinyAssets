# Project files — what lives where

**HISTORICAL — superseded.** Describes machinery deleted by the 2026-08-25/26 harness reset. Do not cite as live; see [README.md](README.md).

Repo map for agents. Pointer-loaded per
[ADR-002](../decisions/ADR-002-static-vs-dynamic-context-budget.md): `AGENTS.md`
keeps the three living files plus the ownership rule that isn't derivable, and
points here for the full table.

The three living files (`AGENTS.md` process truth, `PLAN.md` design truth,
`STATUS.md` live-state truth) are described in `AGENTS.md` § *Three Living
Files* — that split is load-bearing and stays there.

| File | Audience | Purpose |
|------|----------|---------|
| `AGENTS.md` | Any AI, any tool | How to work, team norms, hard rules. |
| `STATUS.md` | Any AI, any tool | Live state: task board, concerns, watch, archive. |
| `PLAN.md` | Any AI, any tool | Architecture, principles, design decisions. |
| `README.md` | Any human or AI | Fast project orientation. |
| `CODEX.md` | Codex | Thin routing layer. |
| `scripts/docview.py` | Any AI, any tool | Scoped reader for large Markdown/text/JSON artifacts that should not be read raw. |
| `scripts/capture_idea.py` | Any AI, any tool | Fast append helper for the idea inbox. |
| `scripts/claim_check.py` | Any AI, any tool | Multi-provider session-start helper. Classifies STATUS.md Work rows as CLAIMABLE / BLOCKED / IN-FLIGHT / HOST-OWNED / STALE. Run with `--provider <yourname>` before claiming work. |
| `scripts/worktree_status.py` | Any AI, any tool | Worktree cold-start helper. Shows dirty current checkouts, missing or incomplete `_PURPOSE.md`, orphaned/missing paths, active lanes, parked drafts, and PR/STATUS promotion gaps. |
| `scripts/provider_context_feed.py` | Any AI, any tool | Lifecycle checkpoint feed for provider memories/configs, ideas, research artifacts, automation notes, and worktree handoffs. Run at claim/plan/build/review/foldback/memory-write checkpoints. |
| `scripts/sync-skills.ps1` | Repo maintenance | Re-sync `.agents/skills/` into `.claude/skills/`. |
| `CLAUDE.md` | Claude Code only | Thin routing layer. |
| `CLAUDE_LEAD_OPS.md` | Claude Code lead | Situational: user-sim loops, dev team management, token efficiency. Not auto-loaded. |
| `.claude/agents/*.md` | Claude Code only | Individual agent definitions. |
| `.claude/agent-memory/<name>/` | Claude Code teammate `<name>` only (write); any AI (read) | Per-teammate persistent memory. **Owned by the named teammate; other agents and other providers must NOT write here.** Read-only access is fine when context is needed. If a non-owner has a useful observation for another teammate, route it via SendMessage / activity log / a docs note, not by writing into the memory directory. |
| `.agents/skills/*/SKILL.md` | Codex + project agents (canonical source) | Canonical skill definitions. Edit here first. |
| `.claude/skills/*/SKILL.md` | Claude Code only | Mirror of `.agents/skills/` refreshed by `scripts/sync-skills.ps1`. |
| `.agents/activity.log` | Any AI, any tool | Short cross-session activity feed for coordination. |
| `ideas/*.md` | Any AI, any tool | Idea capture, triage, and shipped traceability. |
| `knowledge/*.md` | Any human or AI | Human-readable compiled knowledge companion to `knowledge.db`. |
| `docs/exec-plans/*.md` | Any AI, any tool | Multi-step execution plans and landing history. |
| `docs/conventions.md` | Any AI, any tool | Stable documentation and linking patterns. |
| `docs/reference/environment-variables.md` | Any AI, any tool | Canonical env-var catalog. |
| `docs/reference/worktree-discipline.md` | Any AI, any tool | Canonical worktree/branch lane procedure. |
| `docs/reference/fuse-write-discipline.md` | Cowork sessions | FUSE write + git-plumbing rules, recipes, escalation ladder. |
| `docs/reference/convention-placement.md` | Any AI, any tool | Which file a new convention belongs in, and the drift auto-heal. |
| `docs/reference/project-files.md` | Any AI, any tool | This file. |
| `docs/decisions/INDEX.md` | Any AI, any tool | ADR directory surface. |
| `docs/specs/INDEX.md` | Any AI, any tool | Feature/change spec directory surface. |

**Keep this table honest.** Three of its rows pointed at deleted files
(`INDEX.md`, `notes.json`, `LAUNCH_PROMPT.md`) for long enough that agents were
being sent to paths that did not exist. When you delete or rename a tracked
file, update this row in the same change.
