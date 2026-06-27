# Author → Daemon Rename — End-State Spec

**Date:** 2026-04-19 (refined post host's Foundation-vs-Feature clarification)
**Author:** navigator
**Status:** Re-scope of `docs/exec-plans/completed/2026-04-19-author-to-daemon-rename-status.md` §5 (A1-D2 sequence) per host's **"Foundation End-State vs Feature Iteration"** standing rule (CLAUDE_LEAD_OPS.md, `557b051` refined).
**Foundation/Feature classification:** **FOUNDATION.** Module paths and identifiers are load-bearing for everything else (every import, every test fixture, every doc cross-reference depends on the final shape). Per the rule: foundation builds to end-state in one commit, no phases. **Path B (freeze aliases as permanent feature) is no longer viable** — would lock in dual-naming as load-bearing infrastructure forever, contradicting the foundation classification.
**Supersedes:** §5 of the rename-status doc. The A1 → A2 → A3 → A4 → A5 → B1 → C1 → C2 → D1 → D2 ladder is **abandoned**.
**Prior work preserved:** `72e696e` (Phase 1 Part 1) + `7dde417` (Phase 1 Part 2.5) + `acfeeeb` etc. all stay landed. Compat shims in place via `_rename_compat.py` are working as transition mechanism — but now retire in the end-state commit, not as permanent infrastructure.

---

## 1. The end-state path (Path A confirmed)

Per host's Foundation-vs-Feature rule + lead's directive, **Path A is the only viable shape.** Path B (freeze aliases) deferred-to-history below the table for context but no longer a real choice.

### Path A — One end-state commit, full rename to final shape

Single commit ships:
- All identifier renames (`Author` class → `Daemon`, `register_author` → `register_daemon`, etc.).
- All internal call-sites switched to canonical names.
- All test fixtures updated to canonical names.
- All compat aliases removed (`Author = Daemon`, `register_author = register_daemon`).
- All shims removed (`tinyassets/author_server.py`, `fantasy_author/`, `domains/fantasy_author/`).
- `TINYASSETS_AUTHOR_RENAME_COMPAT` flag removed (along with its conditional code paths in `_rename_compat.py`).
- DB schema rename (`author_definitions` → `daemon_definitions`, etc.) + ID-prefix backfill (`"author::"` → `"daemon::"`).
- Brand-pass copy in MCP tool descriptions, error strings, README.

**Atomic. No bailout. No partial states.** Either the commit lands green or it doesn't land.

### Path B — Freeze current alias state as permanent (REJECTED per Foundation rule)

Originally scoped as: treat `_rename_compat.py`'s deep-submodule alias loader as a permanent feature, not a transition mechanism. **Rejected** because:
- Aliases-as-permanent locks in dual-naming infrastructure → contradicts "foundation = end-state" rule (every new dev encounters two identifier systems).
- `_rename_compat.py` becomes load-bearing project-lifetime infrastructure for what should be transient.
- Compat-shim bandage is exactly the shape the foundation-end-state rule explicitly rejects.

Preserved here for context only. **Path A is the path.**

---

## 2. Recommendation: Path A, with realistic estimate

### Why Path A

1. **Aliases as permanent feature contradict the underlying rename intent.** The point of the rename was to retire "author" as the agent identifier — having two parallel identifier systems in perpetuity defeats the purpose.
2. **Phase 1 Part 1 + 2.5 already shipped the high-cost half** — module + package moves landed (`72e696e`, `7dde417`). Phase 2-5 is mostly mechanical sweeps (identifier renames + test updates + shim deletion). The atomic commit is large but composed of mechanical work, not novel design.
3. **The carve-out in the standing rule applies:** *"This rule does NOT override atomic-commit discipline. One logical change = one commit."* The whole rename IS one logical change. End-state shipment satisfies both rules.
4. **`_rename_compat.py` deep-submodule loader is already overkill for permanent compat.** If kept permanently, it's load-bearing infrastructure for an aesthetic mismatch — high engineering cost for something that should be transient.

### Why not Path B

- Operationally cheaper short-term but accumulates conceptual debt: every new dev encounters two identifier systems and must learn the convention.
- The brand pass alone (~0.5 dev-day) is path-agnostic; it ships either way.
- Locks in the deep-submodule alias loader as permanent infrastructure — `tinyassets/_rename_compat.py` becomes load-bearing for the project's lifetime.

### Realistic Path A dev-day estimate (atomic = no bailout)

Per host's framing — "atomic and final means no bailout points" — the estimate is higher than the A1-A5 sum because:

- **Test fixture sweep** must be one mechanical pass: every `monkeypatch.setattr("workflow.author_server.X", Y)` retargets to `workflow.daemon_server.X`; every `assert author_id == "author::..."` retargets to `daemon::`; every test fixture creating `Author()` instances retargets. **~69 test files** touch the rename surface (per grep). Mechanical but voluminous.
- **DB migration must be idempotent + tested fresh + tested upgrade.** Schema changes touch `author_definitions`, `author_forks`, `author_runtime_instances`, plus `author_id` columns on `branch_definitions`, `goals`, etc. Per Phase 0 audit, content-authorship sites are zero, so the migration is additive-no-backfill; still needs proper test coverage on both fresh-DB and upgrade-DB paths.
- **ID-prefix backfill** is one SQL statement (`UPDATE … SET id = REPLACE(id, 'author::', 'daemon::')`) but must be transactional + tested.
- **Brand-pass copy** in MCP tool descriptions, error strings, README — ~10-15 user-facing strings; can review by grep (`"author"` case-sensitive in `tinyassets/universe_server.py` + `tinyassets/daemon_server.py` + `README.md`).
- **No shim back-compat after this commit.** Anything that imports `from fantasy_author.X import Y` outside this commit's sweep breaks immediately. Means the commit also has to:
  - Update every external script in `scripts/` (small surface).
  - Update every doc cross-reference (~20-30 doc files mention the old names).
  - Update `pyproject.toml` entry points (`fantasy-author-cli` → `fantasy-daemon-cli` if any exist).

**Estimate: ~3-4 dev-days for one contributor working serially.** Higher than the A1-A5 sum (~3-4 dev-days with parallelism, ~5-6 serial) because:
- No parallelism possible (single coherent commit, single test-suite gate).
- No bailout points (verifier full-pytest must pass at the end of the single commit, not at intermediate phase boundaries).
- Mechanical sweep is faster than the per-phase planning + per-phase commit overhead, partially offsetting the atomic constraint.

### Risk register

- **Risk: test suite breaks at the verifier gate.** Recovery requires the dev to either (a) iterate on the same WIP commit until green, or (b) revert the work-in-progress and start over. **Mitigation:** dev maintains a local WIP branch with frequent local-only checkpoints; pushes the single end-state commit only after full pytest + ruff green locally.
- **Risk: a deep monkeypatch in a test file misses the sweep and silently passes by patching the wrong (shimmed) module.** **Mitigation:** post-sweep grep for `monkeypatch.setattr("workflow.author_server` and `monkeypatch.setattr("fantasy_author` MUST return zero results. Fail-loud assertion gate.
- **Risk: external scripts in `scripts/` reference old paths.** **Mitigation:** sweep `scripts/` in same commit. ~5-10 files.
- **Risk: docs in `docs/` reference old paths.** **Mitigation:** historical docs (specs, design notes, exec-plans-not-active) are *intentionally* preserved — they are records of past state. Active docs (PLAN.md, AGENTS.md, STATUS.md, README.md, INDEX.md, active exec plans) get updated. Per the parent plan's §2 exclusion list.
- **Risk: DB migration races with a running daemon.** **Mitigation:** migration runs on daemon startup with a lock; daemon refuses to start until migration completes. Tested via fresh-DB + upgrade-DB fixtures.

---

## 3. Sequencing relative to other in-flight work

- **Independent of refactor R1-R13.** R2 (bid promotion), R3 (compat deletion), R7 (storage split) all touch different files. R7 (storage split) renames `daemon_server.py` to `tinyassets/storage/daemons.py`; the rename end-state commit can absorb that move if R7 hasn't shipped, OR follow R7 if R7 ships first. **Recommend:** R7 ships first (~2 dev-days), then rename end-state commits with the new module locations already established.
- **Cancels remaining §5 sequence (A1-D2) in `docs/exec-plans/completed/2026-04-19-author-to-daemon-rename-status.md`.** Update that doc to mark §5 as superseded by this one.
- **Layer-3 universe→workflow rename (Q10-Q12) follows the same pattern.** Per host directive on Path A, the layer-3 rename should also collapse to one end-state commit. Recommend separate exec plan for layer-3 end-state — same shape, different surface.

---

## 4. Decision points for lead

1. ~~Path A or Path B?~~ **Path A confirmed** per Foundation classification.
2. **Dispatch when?** Three options: (i) immediately after R7 lands; (ii) immediately after R2 + R3 + R7 all land (refactor wave complete); (iii) after the daemon-economy first-draft (per "Daemon Economy is Foundation" rule, daemon-economy ranks above cleanup). **Recommend (iii)** — rename is foundation but daemon-economy is also foundation AND ships product. Foundation-vs-foundation tie-break: ship the one that unblocks more downstream work first. Daemon-economy unblocks tier-2 earnings + autoresearch + 4-fulfillment-paths; rename end-state unblocks "no more dual-naming for new contributors." Daemon-economy wins on unblock-leverage.
3. **Solo dev or pair?** Recommend solo (single coherent commit; pairing creates merge conflicts on a sweep this large).

---

## 5. Update trigger for rename-status doc

Once lead decides Path A or B:

- **If A:** mark §5 of `docs/exec-plans/completed/2026-04-19-author-to-daemon-rename-status.md` as SUPERSEDED, link to this doc as the current spec.
- **If B:** mark §5 as ABANDONED, document the freeze-as-feature decision in `_rename_compat.py` docstring + add to PLAN.md Module Layout section.

Either way, the §5 task list (A1-D2) stops being a dispatch candidate.

---

## 6. Summary for dispatcher

- **Path A (recommended):** ~3-4 dev-days, single contributor, atomic end-state commit. No bailout points. Sequences after R7 storage split + after daemon-economy first-draft.
- **Path B (alternative):** Aliases stay forever; brand pass ships standalone (~0.5 dev-day); `_rename_compat.py` becomes permanent infrastructure.
- **§5 of rename-status doc is now obsolete** under either path. Update needed.
- **Layer-3 universe→workflow rename (Q10-Q12)** should follow the same end-state pattern. Separate exec plan recommended.
