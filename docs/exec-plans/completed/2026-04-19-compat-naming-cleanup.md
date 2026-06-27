# Compat Naming Cleanup — Execution Plan

**Date:** 2026-04-19
**Author:** navigator
**Status:** Pre-staged dev-executable plan. Sequenced as **R3** in `docs/exec-plans/active/2026-04-19-refactor-dispatch-sequence.md`. Smaller than expected — the audit's "naming collision risk" framing turned out to be even simpler at code-level.
**Scope:** Resolve the `tinyassets/compat.py` vs `tinyassets/_rename_compat.py` naming ambiguity. Surprise finding: `compat.py` is documentation-only with zero imports.
**Effort:** ~5-15 minutes. Single trivial commit.

---

## 1. Surprise finding from the audit

The spaghetti audit (hotspot #5) flagged `tinyassets/compat.py` (90 LOC) and `tinyassets/_rename_compat.py` (188 LOC) as a naming-collision risk worth a ~0.5 dev-day investigation + rename. Reading the actual file:

**`tinyassets/compat.py` is a 90-line module-docstring-only file.** Lines 1-89 are a multi-line docstring documenting the obsolete Phase 2 fantasy_author → workflow + domains/ extraction transition. Line 90 is `"""` closing the docstring. **There are zero defs, zero classes, zero `__all__`, zero imports.** It is a documentation file with a `.py` extension.

Verified by grep: **zero call sites** anywhere in the canonical tree, mirror tree, or test suite import from `workflow.compat`. The file is dead documentation that survived the rename Phase 1 landings unnoticed.

**Implication:** R3 is not a refactor; it's a deletion. Cost reduces from ~0.5 dev-day to ~5 minutes.

---

## 2. What `compat.py` actually documents

Module docstring describes the in-flight Phase 2 extraction (Phase 2a / Phase 2b / Phase 3) — when `fantasy_author/` was being split into `tinyassets/` (engine) + `domains/fantasy_author/` (domain). That extraction completed in `b395d19` (Phase 1 Part 1) + `72e696e` (Phase 1 Part 2) + `7dde417` (Phase 1 Part 2.5). The Phase 2 the docstring describes never matched the eventual phase numbering in the parent rename plan (`docs/exec-plans/active/2026-04-15-author-to-daemon-rename.md`), and the architectural facts it asserts about `fantasy_author/` "remaining fully functional with original imports unchanged" no longer hold — `fantasy_author/` is now a back-compat shim package (per Phase 1 Part 2.5's `install_module_alias` flow).

In short: the docstring is **historically inaccurate as of today** and serves no live reader. Any reader hitting it would be misled, not informed. Deletion is correct, not just convenient.

---

## 3. Files in scope

| Path | Action | Notes |
|---|---|---|
| `tinyassets/compat.py` | **DELETE** | Zero imports; documentation-only; historically inaccurate; obsolete. |
| `packaging/claude-plugin/plugins/tinyassets-universe-server/runtime/tinyassets/compat.py` | **DELETE (mirror)** | Byte-equal to canonical per mirror discipline. |

**Files NOT touched:**
- `tinyassets/_rename_compat.py` — keeps its name. The `_` prefix correctly signals "internal," and the `_rename_compat` qualifier is unambiguous about scope (Author→Daemon rename window). Rename to `_alias_loader.py` was on the table per the spaghetti audit, but with `compat.py` removed there's no naming collision to resolve. **No-op.**
- Any other compat-related file. There are no others.

---

## 4. Single atomic commit

### Commit — delete `tinyassets/compat.py` (obsolete Phase 2 documentation)

**Files:**
- `git rm tinyassets/compat.py`
- `git rm packaging/claude-plugin/plugins/tinyassets-universe-server/runtime/tinyassets/compat.py`

**Suggested commit message:**
```
refactor: delete tinyassets/compat.py (obsolete Phase 2 documentation)

The file was a 90-line docstring-only module documenting the in-flight
fantasy_author → workflow + domains/ extraction (Phase 2). That extraction
completed via b395d19 + 72e696e + 7dde417, and the architectural facts
the docstring asserts no longer hold: fantasy_author/ is now a back-compat
shim package, not a parallel-functional fantasy_author/ tree.

Zero imports from workflow.compat anywhere in the tree (canonical, mirror,
or tests). Deletion has no behavior impact.

Resolves R3 of docs/exec-plans/active/2026-04-19-refactor-dispatch-sequence.md
(reduced from ~0.5 dev-day naming-clarity refactor to ~5-min deletion after
audit revealed compat.py is dead documentation, not a code module).

tinyassets/_rename_compat.py keeps its name (no naming collision once
compat.py is gone; "_rename_compat" already unambiguous about scope).
```

**Verification:**
- `ruff check` (no-op — touching only deleted files).
- Full pytest sanity (no test imports from `workflow.compat` per grep verification; full suite should be green with no behavior change).
- Mirror byte-equal: deletion in canonical + mirror in same commit; `tests/test_packaging_build.py` mirror-parity check confirms.

---

## 5. Behavior-change check

**Zero behavior change.** Verified by grep: no canonical, mirror, test, or external script imports from `workflow.compat`. Removing the file removes no code that anything depends on.

**Documentation impact:** the obsolete docstring stops misleading future readers. Net positive for repo clarity.

---

## 6. Sequencing relative to other refactor blocks

R3 is now **independent of all other refactor blocks** (file deletion, no shared dependencies). Originally sequenced behind R8 (Phase 5) per the spaghetti audit's "easier post-Phase 5" framing — that framing assumed R3 would touch `_rename_compat.py`, but with `compat.py` going away unilaterally and `_rename_compat.py` keeping its name, the R8 dependency dissolves.

**R3 can ship anytime.** Recommend bundling with R1 (STEERING removal) shape — both are "delete obsolete documentation" commits, both run in seconds. Or ship standalone whenever dev has 5 spare minutes.

---

## 7. Updated spaghetti-audit hotspot status

Hotspot #5 in `docs/audits/2026-04-19-project-folder-spaghetti.md` should be updated post-R3 ship:
- Risk severity: was "naming collision risk"; becomes "RESOLVED — `compat.py` deleted, `_rename_compat.py` unambiguous standalone."
- Cost: was ~0.5 dev-day investigation + rename; becomes 5-minute deletion.

Recommend nav update spaghetti audit hotspot #5 entry post-R3 commit (one-line edit).

---

## 8. Summary for dispatcher

- **1 atomic commit, 2 file deletions** (canonical + mirror).
- **5-minute dev work.** Zero risk, zero behavior change.
- **Independent of all other refactor blocks** — ship-anytime.
- **Recommended bundle target:** with R1 STEERING shape (both are obsolete-documentation deletions); or whenever dev has 5 spare minutes between blocks.
- **Hotspot #5 status:** RESOLVED post-ship; spaghetti audit gets a one-line update.
