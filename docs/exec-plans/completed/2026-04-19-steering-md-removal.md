# STEERING.md Removal — Execution Plan

**Date:** 2026-04-19
**Author:** navigator
**Status:** Removal plan — not implementation. Awaiting host greenlight before dispatch.
**Scope:** Delete `STEERING.md` from repo root + clean up the small surface of references.
**Effort:** ~30-45 min dev work across 3 atomic commits.

---

## 1. What STEERING.md was, and why it's no longer load-bearing

**What it was.** A 20-line file at repo root with four "standing directives" (Built ≠ Done, Build Toward Future, Universal Ingestion, Living Documents) that the daemon read at session start. Original purpose: a small steady-state directive surface for the daemon to consult before acting, separate from STATUS.md (live state) and PLAN.md (architecture).

**When it was load-bearing.** Single commit on this file: `36f097a` ("Initial commit: Workflow engine + Fantasy Author daemon"). It has not been edited since. Both `tinyassets/notes.py` and `packaging/.../runtime/tinyassets/notes.py` carry a docstring saying literally *"Notes replace STEERING.md, editorial output, and verdict routing."* That replacement happened in the unified-notes refactor (per `notes.py` docstring §2-6). The STEERING.md file has been functionally orphaned since `notes.json` became the per-universe directive surface.

**Why it should leave now.** It contradicts the Three Living Files rule in `AGENTS.md` ("AGENTS.md owns process truth, PLAN.md owns design truth, STATUS.md owns live-state truth"). STEERING.md presents itself as a fourth directive surface but its content has migrated — three of its four directives now live in canonical files (Built ≠ Done → AGENTS.md "How to Work"; Living Documents → AGENTS.md "Three Living Files"; Build Toward Future → PLAN.md cross-cutting principles), and Universal Ingestion is product-design content that belongs in PLAN.md if it isn't already. Leaving STEERING.md in place perpetuates a stale fourth source of truth.

---

## 2. Reference inventory (canonical tree only — worktrees handled separately in §6)

Eight non-worktree references total:

| Path | Type | Action |
|---|---|---|
| `STEERING.md` | The file itself | Delete (Commit 3). |
| `INDEX.md:15` | Doc citation in repo map | Trim line (Commit 1 OR Commit 3 — see §3). |
| `docs/launch-prompt-audit.md:65` | Historical audit reference (mentions STEERING.md as one of several files story-author writes to) | Leave as-is; this is an audit record of past state, not active doc. **No action.** |
| `.claude/agents/retired/story-author.md:19,31` | Retired agent definition; references STEERING.md as a directive surface the agent used. | Leave as-is; the agent is in `retired/` precisely because that role has been retired. **No action.** |
| `.claude/agent-memory/critic/evaluator_blind_spots.md:14` | Persona memory item ("Wilderness encounter when STEERING explicitly directed village fallout"). Historical example in a fantasy-author context. | Leave as-is; persona memory file. **No action.** |
| `tinyassets/notes.py:3-4` | Module docstring saying *"Notes replace STEERING.md, editorial output, and verdict routing."* + `:253` "These are the user's steering inputs..." | Trim docstring reference to STEERING.md (the historical "what this replaces" is now obsolete; the unified-notes paragraph stands on its own). Keep `:253` "steering inputs" — that's a generic English usage. (Commit 2.) |
| `packaging/claude-plugin/plugins/tinyassets-universe-server/runtime/tinyassets/notes.py:3-4` | Mirror of above; must stay byte-equal. | Same trim as canonical. (Commit 2.) |
| `packaging/dist/tinyassets-universe-server-src/tinyassets/notes.py:3` | Stale pre-rename dist staging output. | Will regenerate on next packaging build; **no action**. |
| `tinyassets/mcp_server.py:76` | `tags={"notes", "steering", "direction"}` on an MCP tool. "steering" here is a tag value, generic English usage. | Leave as-is. **No action.** |

**Net write surface:** 4 files (`STEERING.md` deleted, `INDEX.md` trimmed, `tinyassets/notes.py` docstring trimmed, plugin-mirror `notes.py` docstring trimmed). Plus the 30+ worktree copies, addressed separately in §6.

---

## 3. Proposed commit sequence — 2 atomic commits

I originally scoped 2-3 commits per the parent task. Reading the surface, **2 commits is the right granularity** — citation + code-reference cleanup land in one commit each. No third commit needed because the worktree residue is not part of any committable surface (per §6).

### Commit 1 — `docs: drop STEERING.md docstring reference from notes.py`

**Files:**
- `tinyassets/notes.py` — trim line 3-4 docstring reference to STEERING.md.
- `packaging/claude-plugin/plugins/tinyassets-universe-server/runtime/tinyassets/notes.py` — same trim.

**Suggested message:**
```
docs: drop STEERING.md docstring reference from notes.py

The "Notes replace STEERING.md" line was load-bearing during the
unified-notes refactor as historical context. Notes is now the
established primitive; the historical replacement note is no longer
informative. Removing in advance of STEERING.md file deletion.
```

**Discipline:**
- Pure docstring change. No semantic change.
- Mirror byte-equal to canonical. Verify with `diff tinyassets/notes.py packaging/.../runtime/tinyassets/notes.py`.
- `ruff check` on touched files (no-op for docstring change but practice).

### Commit 2 — `docs: delete STEERING.md (superseded by notes.json + AGENTS.md + PLAN.md)`

**Files:**
- `STEERING.md` — delete.
- `INDEX.md` — remove line 15 `- [STEERING.md](STEERING.md)`.

**Suggested message:**
```
docs: delete STEERING.md (superseded by notes.json + AGENTS.md + PLAN.md)

STEERING.md hadn't been edited since 36f097a (initial commit) and
predated the unified-notes refactor that moved per-universe directives
into notes.json. Its four standing directives are subsumed by:

- "Built ≠ Done" → AGENTS.md "How to Work" (verification gate).
- "Build Toward Future" → PLAN.md cross-cutting principles.
- "Universal Ingestion" → PLAN.md ingestion module spec.
- "Living Documents" → AGENTS.md "Three Living Files" rule.

Removing the file eliminates a stale fourth source of truth (per
AGENTS.md "Truth is typed, not singular" rule).

INDEX.md trim removes the dangling link.
```

**Discipline:**
- File deletion — explicit `git rm STEERING.md`.
- INDEX.md edit is one-line trim.
- No `git add -A` (per AGENTS.md commit discipline).

---

## 4. Behavior-change check — is this a breaking commit?

**No runtime behavior change.** Verified by grep:
- `tinyassets/notes.py` references STEERING.md only in module docstring (lines 3-4); never reads the file.
- `tinyassets/mcp_server.py:76` has `"steering"` as a tag string (generic English usage); no file dependency.
- No `Path("STEERING.md")` / `open("STEERING.md")` / `read_text` of STEERING.md anywhere in canonical or mirror tree.
- No agent config reads STEERING.md at session start (none of the active `.claude/agents/*.md` files reference it; only the retired `story-author.md` did, and that agent is in `retired/`).

**Test surface impact: zero.** No test imports, mocks, or asserts against STEERING.md content.

**Daemon behavior impact: zero.** The daemon reads `notes.json` per-universe; STEERING.md was the pre-unification surface and has been silently superseded.

**Documentation cross-reference impact: minimal.** The 3 references in `docs/launch-prompt-audit.md`, `.claude/agents/retired/story-author.md`, `.claude/agent-memory/critic/evaluator_blind_spots.md` are all *historical record* files (audit / retired agent / persona memory) where the STEERING.md mention is part of a description of past state. Leaving them as-is preserves the historical record. Editing them to remove the references would be rewriting history.

**Conclusion: SAFE to ship as a non-breaking cleanup.** Dev does not need a green-light beyond this design note.

---

## 5. Risk register

- **Risk:** A dev session reads `INDEX.md`, follows the link, gets a 404 → confusion. **Mitigation:** Commit 2 trims INDEX.md in the same atomic change as the file delete. Single commit means no transient broken-link state.
- **Risk:** A future contributor greps for "STEERING.md" looking for the original document and finds only references in historical files (audit, retired agent, persona memory). **Mitigation:** Acceptable — those references explain themselves in context ("we used to have a STEERING.md"). Acceptable historical decay.
- **Risk:** A plugin-mirror sync misses the `notes.py` docstring change. **Mitigation:** Commit 1 explicitly touches both canonical + mirror in the same commit; the standing mirror byte-equality test (`tests/test_packaging_build.py`) catches drift.
- **Risk:** Worktree copies of STEERING.md (~30+ across `.claude/worktrees/`) confuse a worktree-spawning provider. **Mitigation:** Worktrees are per-provider scratch; each provider rehydrates its worktree from the canonical tree. Worktree copies of STEERING.md will disappear on next worktree rotation. Not blocking.

---

## 6. Worktree residue — explicitly NOT part of this plan

`.claude/worktrees/*/STEERING.md` (~30+ copies, one per worktree). These are:
- Per-provider scratch trees, never committed to main.
- Inherited from initial worktree spawn (which copied from main when STEERING.md was canonical).
- Will reset on the next worktree rotation, after which freshly-spawned worktrees will not have a STEERING.md (because main no longer does).

**No action proposed.** Cleaning worktree-side files would require touching each provider's working tree, which is outside the scope of a main-tree change. Letting them age out is correct.

---

## 7. Sequencing relative to other in-flight work

- **Independent of rename Phase 1 Part 2.5 (task #17).** No file overlap.
- **Independent of layer-3 universe→workflow rename.** No file overlap.
- **Independent of any active dev task.** STEERING.md has no test / runtime / packaging dependency.
- **Can ship at any cadence.** No serialization required.

**Recommend dispatch:** opportunistic — when dev has 30 minutes between higher-priority tasks. Not a critical-path item.

---

## 8. Summary for dispatcher

- 2 atomic commits, ~30 min total dev work.
- Pure cleanup — no runtime behavior change, no test impact, no daemon impact.
- Worktree residue handled passively (next worktree rotation).
- Historical references in audit / retired-agent / persona-memory files left intact (records of past state, not stale active references).
- No host green-light required beyond this note.
