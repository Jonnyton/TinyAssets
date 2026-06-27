# Dirty-Tree Audit — 2026-04-19

Task #7 classification of remaining uncommitted state after `ba1d3c3` (layer-2 rebrand) landed. Head: `ba1d3c3`. Pre-existing commits `72e696e` (Phase 1 Part 2) and `1c80409` (tree consistency) already on main.

**Categories:** (a) Intentional WIP, (b) Orphaned drift, (c) Should-have-shipped, (d) Test/script shrapnel.

**No files were modified, deleted, or reverted during this audit.**

---

## Summary by disposition

- 4 cohesive commit targets recommended (see bottom).
- 1 deferred cluster (rename Phase 1 compat extensions — coordinate with navigator's #8 rename-status delta before landing).
- 0 orphaned drift detected.

---

## Root living docs

| Path | Cat | Verdict | Action |
|------|-----|---------|--------|
| `AGENTS.md` | (c) | Verifier/navigator/uptime-forever-rule rewrites coherent with current session architecture; tester+reviewer+explorer refs replaced with verifier+navigator; adds Forever Rule (24/7 uptime) + Three Living Files table. | Ship in commit **[LIVING-DOCS]**. |
| `STATUS.md` | (c) | Budget/lifecycle rewrite + concern decomposition outputs + full-platform §11 queue. | Ship in **[LIVING-DOCS]**. |
| `PLAN.md` | (c) | Adds install-readiness + software-surface Principles — aligns with forever-rule + memory docs. | Ship in **[LIVING-DOCS]**. |
| `LAUNCH_PROMPT.md` | (c) | Team roster rewrite (navigator/verifier replacing planner/explorer/tester/reviewer). | Ship in **[LIVING-DOCS]**. |
| `CLAUDE_LEAD_OPS.md` | (c) | Same agent-rename sweep (tester/reviewer → verifier). | Ship in **[LIVING-DOCS]**. |
| `docs/launch-prompt-audit.md` | (a) | Small edit; same team-rename coherence. | Ship in **[LIVING-DOCS]**. |
| `docs/reality_audit.md` | (a) | LF/CRLF + minor text edits; same family. | Ship in **[LIVING-DOCS]**. |

## Agent/skill definition churn (.claude/, .agents/)

| Path | Cat | Verdict | Action |
|------|-----|---------|--------|
| `.claude/agents/developer.md` | (c) | Swaps reviewer/tester → verifier; removes 2026-04-14 test-discipline rules; clarifies test boundary (dev writes, verifier runs). Matches current session's actual behavior. | Ship in **[AGENT-DEFS]**. |
| `.claude/agents/user.md` | (c) | Persona-driven user-sim rewrite. Coherent with memory note `project_user_sim_persona_driven.md`. | Ship in **[AGENT-DEFS]**. |
| `.claude/agents/explorer.md` | (c) | Deleted — role merged into `navigator.md`. | Ship in **[AGENT-DEFS]**. |
| `.claude/agents/planner.md` | (c) | Deleted — role merged into `navigator.md`. | Ship in **[AGENT-DEFS]**. |
| `.claude/agents/reviewer.md` | (c) | Deleted — role merged into `verifier.md`. | Ship in **[AGENT-DEFS]**. |
| `.claude/agents/tester.md` | (c) | Deleted — role merged into `verifier.md`. | Ship in **[AGENT-DEFS]**. |
| `.claude/agents/story-author.md` | (c) | Deleted — obsolete persona. | Ship in **[AGENT-DEFS]**. |
| `.claude/agents/navigator.md` | (c) | New — navigator agent def (plan-mode, PLAN.md owner). | Ship in **[AGENT-DEFS]** (`git add` explicitly). |
| `.claude/agents/verifier.md` | (c) | New — verifier agent def (proactive quality gate). | Ship in **[AGENT-DEFS]** (`git add` explicitly). |
| `.claude/agents/retired/` | (a) | New directory (untracked). Contents = archived older defs. | Inspect contents before shipping; ship in **[AGENT-DEFS]** if archival-only. |
| `.agents/skills/team-iterate/SKILL.md` | (c) | Skill update for agent-team loop; canonical. | Ship in **[AGENT-DEFS]**. |
| `.claude/skills/team-iterate/SKILL.md` | (c) | Mirror of above (must stay byte-matched). | Ship in **[AGENT-DEFS]**. |
| `.agents/activity.log` | (a) | 106 lines of session narrative appended across prior sessions. Historical; coordination record. | Ship in **[AGENT-DEFS]** or stand-alone trivial commit; low risk. |
| `scripts/sync-skills.ps1` | (a) | Minor edit (LF/CRLF + comment). | Ship in **[AGENT-DEFS]**. |

## Rename Phase 1+ compat extensions (tinyassets/ canonical + packaging mirror)

| Path | Cat | Verdict | Action |
|------|-----|---------|--------|
| `tinyassets/_rename_compat.py` | (a) | Extends rename compat with `_RenameAliasLoader`, `install_module_alias` — aliases old module paths to new canonical. Active Phase 1–4. | **DEFER** to navigator-coordinated Phase-1-Part-3 commit. See §Deferred. |
| `tinyassets/desktop/launcher.py` | (a) | Host tray migration (`TrayApp` → `HostTrayService.shared().bind_dashboard`) + start/stop guards. Non-rename UX improvement bundled into rename-era churn. | Ship separately as **[TRAY-SINGLETON]** — maps to STATUS Work row #23 ("Tray singleton"). |
| `tinyassets/discovery.py` | (a) | Adds `rename_compat_enabled()` branch that appends `fantasy_author` alias to discovered domain list. Phase 1 shim behavior. | **DEFER** with _rename_compat.py. |
| `tinyassets/knowledge/models.py` | (a) | Adds `FactHardness` enum + `hardness` field on `FactWithContext`. Independent of rename; knowledge model extension. | Ship as **[KG-HARDNESS]** standalone OR fold into upcoming Fix-C follow-up. Needs one-line owner confirmation from navigator. |
| `domains/fantasy_author/__init__.py` | (a) | Adds `install_module_alias` call + attribute delegation. Phase 1 shim. | **DEFER** with _rename_compat.py. |
| `fantasy_author/__init__.py` | (a) | Same Phase 1 shim pattern as domains/. | **DEFER** with _rename_compat.py. |
| `fantasy_author/__main__.py` *(untracked)* | (a) | Back-compat CLI shim; one-line `from fantasy_daemon.__main__ import *`. Part of Phase 1 shim set. | **DEFER** with _rename_compat.py. |
| `domains/fantasy_author/phases/` *(untracked dir)* | (a) | Needs inspection — likely phases/ shim submodules for import surface preservation. | Inspect before shipping; **DEFER** with _rename_compat.py. |

**Mirror-side rename compat** (must stay byte-matched to canonical above):
| Path | Cat | Verdict | Action |
|------|-----|---------|--------|
| `packaging/.../runtime/tinyassets/_rename_compat.py` | (a) | Identical to canonical. | **DEFER** with canonical counterpart. |
| `packaging/.../runtime/tinyassets/desktop/launcher.py` | (a) | Identical to canonical (tray singleton). | Ship with **[TRAY-SINGLETON]**. |
| `packaging/.../runtime/tinyassets/discovery.py` | (a) | Identical to canonical. | **DEFER** with canonical. |
| `packaging/.../runtime/tinyassets/knowledge/models.py` | (a) | Identical to canonical. | Ship with **[KG-HARDNESS]**. |

## Packaging mirror sync-forward (task #17 Fix C catch-up)

Canonical is at `05ce779` (#17 synthesis-skip fix + bite diagnostics). Mirror was behind; these are sync-forward deltas so mirror catches up byte-for-byte with canonical.

| Path | Cat | Verdict | Action |
|------|-----|---------|--------|
| `packaging/.../runtime/tinyassets/ingestion/core.py` | (c) | Adds `last_bite_outcomes` field on `ManifestEntry`. Mirror-side sync of #17. | Ship in **[MIRROR-SYNC]**. |
| `packaging/.../runtime/tinyassets/ingestion/extractors.py` | (c) | Adds `_LAST_BITE_OUTCOMES` + bite synthesis diagnostics. Mirror-side sync of #17. | Ship in **[MIRROR-SYNC]**. |
| `packaging/.../runtime/tinyassets/retrieval/router.py` | (c) | 1-line mirror sync. | Ship in **[MIRROR-SYNC]**. |
| `packaging/.../runtime/tinyassets/universe_server.py` | (c) | 444/-444 — intent-disambiguation + control_station prompt relocation + tool-description churn. Canonical of this file shows no diff in `git status`, so the canonical version is already at HEAD and the mirror is catching up. | Ship in **[MIRROR-SYNC]**. |
| `packaging/.../runtime/tinyassets/runs.py` | (c) | 1-line (pre-existing canonical edit already landed). Mirror catch-up. | Ship in **[MIRROR-SYNC]**. |
| `packaging/.../runtime/tinyassets/work_targets.py` | (c) | 1-line (pre-existing canonical edit already landed). Mirror catch-up. | Ship in **[MIRROR-SYNC]**. |

Parity verification (performed during audit, no files modified):
```
diff tinyassets/_rename_compat.py       <mirror>   → identical
diff tinyassets/desktop/launcher.py     <mirror>   → identical
diff tinyassets/discovery.py            <mirror>   → identical
diff tinyassets/knowledge/models.py     <mirror>   → identical
diff tinyassets/ingestion/core.py       <mirror>   → identical
diff tinyassets/ingestion/extractors.py <mirror>   → identical
diff tinyassets/retrieval/router.py     <mirror>   → identical
diff tinyassets/runs.py                 <mirror>   → identical
diff tinyassets/universe_server.py      <mirror>   → identical
diff tinyassets/work_targets.py         <mirror>   → identical
```

## Test/script shrapnel

| Path | Cat | Verdict | Action |
|------|-----|---------|--------|
| `tests/test_author_server_api.py` | (d) | Ruff/isort blank-line formatting only. No semantics change. | Ship in **[TEST-FORMAT]** with sibling files. |
| `tests/test_graph_topology.py` | (d) | Ruff/isort: reorders imports to `from langgraph.graph import END` after `fantasy_author` imports + inserts blank lines. No semantics change. | Ship in **[TEST-FORMAT]**. |
| `tests/test_synthesis_skip_fix.py` | (d) | Same ruff blank-line formatting. | Ship in **[TEST-FORMAT]**. |

## Prototype (uptime Phase 1a scaffolding)

| Path | Cat | Verdict | Action |
|------|-----|---------|--------|
| `prototype/full-platform-v0/Dockerfile` | (a) | Small diff (LF/CRLF + dependency lines likely). Part of uptime Phase 1a work referenced in `docs/exec-plans/active/2026-04-18-uptime-phase-1a-static-landing.md`. | Needs proto owner decision. Ship with **[PROTO]** or leave WIP. |
| `prototype/full-platform-v0/requirements.txt` | (a) | Same phase; dependency bump. | Ship with **[PROTO]**. |

## Design notes (untracked, should-have-shipped)

All have been referenced from STATUS.md Concerns / Work rows / activity.log. None is speculative one-off.

| Path | Cat | Should ship? |
|------|-----|-------------|
| `docs/design-notes/2026-04-14-memory-scope-defense-in-depth.md` | (c) | Yes — referenced by memory-scope Stage-1/2 concerns. |
| `docs/design-notes/2026-04-14-packaging-mirror-decision.md` | (c) | Yes — already referenced by build_plugin.py / build_bundle.py docstrings that shipped in earlier commits. |
| `docs/design-notes/2026-04-14-private-branch-visibility-3path.md` | (c) | Yes — visibility/privacy foundation note. |
| `docs/design-notes/2026-04-15-memory-scope-tiered.md` | (c) | Yes — referenced by `project_memory_scope_mental_model` memory. |
| `docs/design-notes/2026-04-15-node-software-capabilities.md` | (c) | Yes — referenced by PLAN.md principle that just landed in dirty state. |
| `docs/design-notes/2026-04-17-engine-domain-api-separation.md` | (c) | Yes — host-review STATUS Work row #11 cites it. |
| `docs/design-notes/2026-04-18-add-canon-from-path-sensitivity.md` | (c) | Yes — STATUS concern cites it. |
| `docs/design-notes/2026-04-18-mission10-bug-scoping.md` | (c) | Yes — pointers for tasks #15/16/17. |
| `docs/design-notes/2026-04-18-nodescope-unification.md` | (c) | Yes — post-2c-flip follow-up. |
| `docs/design-notes/2026-04-18-persistent-uptime-architecture.md` | (c) | Yes (superseded but referenced); keep for traceability. |
| `docs/design-notes/2026-04-18-privacy-modes-for-sensitive-workflows.md` | (c) | Yes — STATUS concern cites it. |
| `docs/design-notes/2026-04-18-scene-scoped-kg-cleanup.md` | (c) | Yes — post-#17 follow-up design. |
| `docs/design-notes/2026-04-19-modularity-audit.md` | (c) | Yes — STATUS Concerns cites it. |
| `docs/design-notes/2026-04-19-universe-to-workflow-server-rename.md` | (c) | Yes — navigator's #4 layer-3 rename design note (just completed). |
| `docs/design-notes/INDEX.md` | (c) | M — already updated to reference the new notes. Ships with them. |
| `docs/exec-plans/INDEX.md` | (c) | M — same coherence. |
| `docs/exec-plans/active/2026-04-15-author-to-daemon-rename.md` | (c) | Yes — the active rename exec plan that STATUS Work row #3 cites. |
| `docs/exec-plans/active/2026-04-16-memory-scope-stage-2b.md` | (c) | Yes — memory-scope exec plan. |
| `docs/exec-plans/active/2026-04-18-uptime-phase-1a-static-landing.md` | (c) | Yes — referenced in INDEX.md update. |
| `docs/exec-plans/active/2026-04-19-author-to-daemon-rename-status.md` | (c) | Yes — navigator's task #8 output. |

All ship together as **[DOCS]** (one commit, all design notes + exec plans + index updates).

---

## Deferred cluster

**Rename Phase 1 compat extensions** — `tinyassets/_rename_compat.py`, `tinyassets/discovery.py`, `domains/fantasy_author/__init__.py`, `fantasy_author/__init__.py`, `fantasy_author/__main__.py`, `domains/fantasy_author/phases/`, plus mirror pair. These extend Phase 1 beyond what landed in `72e696e`. Do not ship until navigator's task #8 rename-status delta clarifies whether these are Phase-1-Part-3 extensions, Phase-2 preview, or orphaned from a prior WIP attempt. Risk: shipping prematurely could conflict with the planned Phase 2 module rename (`fantasy_author/` directory move) or change the shim surface before tests cover the new aliases.

**Recommended dispatch:** wait for navigator's #8 status output (which exists at `docs/exec-plans/active/2026-04-19-author-to-daemon-rename-status.md` — ship that note as part of [DOCS], then read it, then decide).

---

## Recommended commit sequence (for lead dispatch)

Order matters: ship mirror-sync + docs first (low-risk, unblocks), then agent defs (team-state coherence), then living docs (references new team), then tray singleton + KG hardness as isolated features. Each commit uses explicit paths — no `git add -A`.

1. **[MIRROR-SYNC]** — mirror catch-up for #17 Fix C + other landed canonical edits.
   Paths:
   - `packaging/claude-plugin/plugins/tinyassets-universe-server/runtime/tinyassets/ingestion/core.py`
   - `packaging/claude-plugin/plugins/tinyassets-universe-server/runtime/tinyassets/ingestion/extractors.py`
   - `packaging/claude-plugin/plugins/tinyassets-universe-server/runtime/tinyassets/retrieval/router.py`
   - `packaging/claude-plugin/plugins/tinyassets-universe-server/runtime/tinyassets/universe_server.py`
   - `packaging/claude-plugin/plugins/tinyassets-universe-server/runtime/tinyassets/runs.py`
   - `packaging/claude-plugin/plugins/tinyassets-universe-server/runtime/tinyassets/work_targets.py`
   Proposed message: `packaging mirror: sync canonical #17 Fix C + control_station + small deltas`

2. **[DOCS]** — all untracked design notes + exec plans + two INDEX updates.
   All 14 design notes + 4 exec plans + `docs/design-notes/INDEX.md` + `docs/exec-plans/INDEX.md`.
   Proposed message: `docs: batch-ship design notes + exec plans referenced by STATUS/Concerns`

3. **[TEST-FORMAT]** — ruff/isort shrapnel in 3 test files.
   Paths: `tests/test_author_server_api.py`, `tests/test_graph_topology.py`, `tests/test_synthesis_skip_fix.py`
   Proposed message: `tests: ruff isort blank-line formatting (no semantic change)`

4. **[AGENT-DEFS]** — teammate role consolidation (tester/reviewer/planner/explorer/story-author → verifier/navigator).
   Paths: `.claude/agents/developer.md`, `.claude/agents/user.md`, `.claude/agents/explorer.md` (D), `.claude/agents/planner.md` (D), `.claude/agents/reviewer.md` (D), `.claude/agents/tester.md` (D), `.claude/agents/story-author.md` (D), `.claude/agents/navigator.md` (new), `.claude/agents/verifier.md` (new), `.claude/agents/retired/` (new dir — confirm archive-only first), `.agents/skills/team-iterate/SKILL.md`, `.claude/skills/team-iterate/SKILL.md`, `scripts/sync-skills.ps1`, `.agents/activity.log`.
   Proposed message: `agents: consolidate roles — verifier + navigator replace tester/reviewer/planner/explorer/story-author`

5. **[LIVING-DOCS]** — AGENTS/STATUS/PLAN/LAUNCH_PROMPT/CLAUDE_LEAD_OPS/launch-prompt-audit/reality_audit.
   Proposed message: `docs: living-doc sync — Forever Rule, verifier/navigator refs, install-readiness principle`

6. **[TRAY-SINGLETON]** — STATUS Work row #23.
   Paths: `tinyassets/desktop/launcher.py` + mirror pair.
   Proposed message: `tray: single host tray service, bind/unbind per dashboard (closes #23)`
   Note: STATUS row also mentions `universe_tray.py`, `start-universe-server.bat`; those are already at rest on main. Only the launcher change is in the dirty tree. If the row's intent included bat-file touches, they already landed in `1b29d92` (tray launcher bat references renamed tinyassets_tray.py). Confirm with lead before marking #23 closed.

7. **[KG-HARDNESS]** — `FactHardness` enum on `FactWithContext`.
   Paths: `tinyassets/knowledge/models.py` + mirror pair.
   Proposed message: `kg: add FactHardness enum + hardness field on FactWithContext`
   Needs: one-line navigator confirmation this isn't mid-flight in a larger #17 follow-up or memory-scope work.

8. **[PROTO]** (optional) — prototype/full-platform-v0 Dockerfile + requirements.txt. Low-priority; can wait for uptime Phase 1a owner.

**Deferred (post-navigator #8):**
9. **[RENAME-PHASE-1-SHIMS]** — `tinyassets/_rename_compat.py`, `tinyassets/discovery.py`, `domains/fantasy_author/__init__.py`, `fantasy_author/__init__.py`, `fantasy_author/__main__.py`, `domains/fantasy_author/phases/` + mirror pair. Hold until navigator's #8 rename-status delta is read.

---

## Non-findings

- **No orphaned drift.** Every dirty entry traces to a concrete in-flight workstream documented in STATUS.md, activity.log, exec plans, or memory.
- **No canonical/mirror divergence.** All 10 canonical/mirror pairs in the dirty tree are byte-identical.
- **No competing test state.** Ruff/isort shrapnel is cosmetic and isolated to 3 test files.
- **No merge hazards.** No unmerged paths, no conflict markers.
