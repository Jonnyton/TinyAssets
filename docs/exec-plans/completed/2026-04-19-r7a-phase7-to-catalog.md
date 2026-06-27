# R7a — Move Phase 7 Storage to `tinyassets/catalog/`

**Date:** 2026-04-19
**Author:** navigator
**Status:** Pre-staged dev-executable plan. Sequenced as **R7a in `docs/exec-plans/active/2026-04-19-refactor-dispatch-sequence.md`** — ships immediately before R7 (storage split).
**Trigger:** Dev-flagged collision: `tinyassets/storage/` is currently occupied by Phase 7 git-native catalog backend, but PLAN.md §Module Layout reserves `storage/` for the daemon_server-split bounded-context modules. R7 (per `docs/exec-plans/active/2026-04-19-storage-package-split.md`) cannot proceed until the path is freed.
**Verdict:** **Option C — re-home Phase 7 to `tinyassets/catalog/`.** Reasoning in §1.

---

## 1. Verdict reasoning — why C, not A/B/D

| Option | What it does | Verdict |
|---|---|---|
| **A — different dir for daemon_server split** (`tinyassets/host_db/`, `tinyassets/multiplayer/`) | Renames the R7 target away from `storage/`. Requires PLAN.md §Module Layout amendment (replacing `storage/` with new name in the 5-subpackage commitment). Phase 7 keeps its current path. | **Rejected.** PLAN.md just promoted (Q4 ratified, `#64`); amending §Module Layout the same day undermines the architectural commitment. The 5-subpackage names are user-facing PLAN.md commitments, not internal aliases — changing them on the first conflict signals the layout isn't load-bearing. |
| **B — co-habit under `storage/`** | Phase 7 catalog-serialization + daemon_server bounded-contexts share the same package. | **Rejected.** Conflates two distinct shapes: Phase 7 is YAML-export-and-git-reconciliation (catalog interchange format); daemon_server-split is bounded-context storage (accounts, requests, etc., shared `_connect()`). Different consumers, different schemas, different test surfaces. Recreates the spaghetti the audit was meant to undo. |
| **C — re-home Phase 7 to `tinyassets/catalog/`** | Phase 7 moves to `tinyassets/catalog/`. Frees `storage/` for daemon_server split. ~17 fan-in to update. | **RECOMMENDED.** See below. |
| **D (lead's 4th)** — Phase 7 moves DOWN under `storage/catalog/`; daemon_server-split goes to `storage/host_db/`; new `storage/backend.py` becomes a generic protocol | Conceptually clean ("storage = any durable mechanism"). Adds 2 nesting levels for everything. | **Rejected.** Existing `storage/backend.py` is NOT a generic protocol — it's specifically the StorageBackend protocol for the YAML-vs-SQLite-cache cutover (Phase 7 spec). Calling it `storage/backend.py` post-rename misleads future readers. Forcing it generic adds engineering work + maintains a name that no longer reflects the file's role. |

**Why C wins on first principles:**

1. **`docs/specs/phase7_github_as_catalog.md` literally names the spec "github_as_catalog."** The load-bearing word is "catalog" — that's what Phase 7 IS. Calling the package `storage/` was an under-specified placeholder name; `catalog/` is more accurate.
2. **Phase 7's responsibility is YAML serialization + git reconciliation for the catalog export path.** That's not "storage" in the bounded-context sense (where multiple subsystems share `_connect()` + migrations); that's "catalog interchange format."
3. **`storage/backend.py` reads (per its docstring) as Phase-7-specific:** *"Storage backend protocol for Phase 7 dual-write cutover."* The name `backend` is ambiguous; `catalog/backend.py` (with the same content) reads as "the catalog interchange backend" — accurate.
4. **Keeping `storage/` for the daemon_server split** matches PLAN.md §Module Layout's stated intent: bounded-context storage layers (accounts, universes_branches, requests_votes, notes_work_targets, goals_gates) sharing `_connect()` + migrations. That's the canonical "storage" semantic.

**Confidence: HIGH.** Driven by what the spec literally calls itself, not nav's preference.

---

## 2. Files in scope for R7a

| Old path | New path |
|---|---|
| `tinyassets/storage/__init__.py` | `tinyassets/catalog/__init__.py` |
| `tinyassets/storage/backend.py` | `tinyassets/catalog/backend.py` |
| `tinyassets/storage/layout.py` | `tinyassets/catalog/layout.py` |
| `tinyassets/storage/serializer.py` | `tinyassets/catalog/serializer.py` |
| `packaging/.../runtime/tinyassets/storage/__init__.py` | `packaging/.../runtime/tinyassets/catalog/__init__.py` (mirror) |
| `packaging/.../runtime/tinyassets/storage/backend.py` | `packaging/.../runtime/tinyassets/catalog/backend.py` (mirror) |
| `packaging/.../runtime/tinyassets/storage/layout.py` | `packaging/.../runtime/tinyassets/catalog/layout.py` (mirror) |
| `packaging/.../runtime/tinyassets/storage/serializer.py` | `packaging/.../runtime/tinyassets/catalog/serializer.py` (mirror) |

**8 file moves total** (4 canonical + 4 mirror). All `git mv`.

---

## 3. Call-site sweep — 17 imports

| File | Current imports | New imports |
|---|---|---|
| `tinyassets/identity.py:28` | `from workflow.storage.layout import slugify` | `from workflow.catalog.layout import slugify` |
| `tinyassets/storage/backend.py:33,34,644` | self-relative — collapse to `from workflow.catalog.layout import …` etc. (or `from .layout import` pattern if the file uses sibling imports) | mechanical |
| `tinyassets/storage/__init__.py:26,36,37` | self-relative re-exports | mechanical retarget |
| `tinyassets/universe_server.py:44,8298,8417,8536` | `from workflow.storage import (…)` and `from workflow.storage.layout import slugify` | `from workflow.catalog import (…)` / `from workflow.catalog.layout import slugify` |
| `tests/test_backend_factory.py:19` | `from workflow.storage import (…)` | `from workflow.catalog import (…)` |
| `tests/test_outcome_gate_git_backend.py:74,118,141,150,173,199,225` | mixed `workflow.storage.*` imports | mechanical retarget |
| `tests/test_phase7_h2_goals_cutover.py:60,80,233` | `from workflow.storage import invalidate_backend_cache` | `from workflow.catalog import invalidate_backend_cache` |
| `tests/test_phase7_h3_branch_cutover.py:72,93,115` | same | mechanical retarget |
| (any other call sites surfaced by full grep at commit time) | sweep | mechanical |

**Discipline:** all sweeps go through *new* paths (`workflow.catalog.*`). **No back-compat shim** — Phase 7 is internal infrastructure (tests + universe_server), no external consumers depend on the old path. Per "No Phased Migrations" rule, ship end-state, no transitional aliases.

**Migration script:** `git grep -l 'from tinyassets\.storage\|tinyassets\.storage' --` + sed retarget. ~10-15 minutes mechanical.

---

## 4. Single atomic commit

### Commit — `refactor: move Phase 7 storage to tinyassets/catalog/`

**Files:**
- 4 canonical `git mv` operations.
- 4 packaging-mirror `git mv` operations.
- ~17 import call-site updates across canonical + mirror + tests.
- Update `tinyassets/storage/__init__.py` references inside `__init__.py` body to `workflow.catalog`.

**Suggested commit message:**
```
refactor: move Phase 7 storage to tinyassets/catalog/

Resolves a R7-blocking name collision: tinyassets/storage/ was occupied
by Phase 7 git-native catalog backend (YAML+SQLite cache for the
github_as_catalog export path), but PLAN.md §Module Layout reserves
storage/ for the daemon_server bounded-context split (R7).

Phase 7's purpose is catalog interchange (YAML serialization + git
reconciliation), not bounded-context storage. The spec name itself —
phase7_github_as_catalog.md — confirms catalog/ is the load-bearing
word. Renaming aligns the path with the actual responsibility.

- 8 file moves (4 canonical + 4 mirror).
- ~17 import call-sites retargeted to workflow.catalog.*.
- Zero behavior change. No shim — no external consumers.
- Frees tinyassets/storage/ for R7 daemon_server split.

R7a in docs/exec-plans/active/2026-04-19-refactor-dispatch-sequence.md.
```

**Verification:**
- Full pytest. Test surface touched (~12 test files import-level only); no logic changes.
- `ruff check` on touched files.
- Mirror byte-equality preserved (parallel canonical + mirror moves in same commit; `tests/test_packaging_build.py` parity check confirms).

---

## 5. Behavior-change check

**Zero behavior change.** Pure namespace move. All function bodies + class definitions + module-level state unchanged.

**Risk: a test does `monkeypatch.setattr("workflow.storage.X", Y)`** — sweep includes those. Grep `monkeypatch.setattr.*workflow.storage` catches them.

---

## 6. PLAN.md §Module Layout — does it need updating?

**No.** PLAN.md §Module Layout already lists `tinyassets/storage/` as the canonical home for bounded-context storage layers (the daemon_server-split target). It does NOT mention Phase 7 or catalog work. Re-homing Phase 7 to `tinyassets/catalog/` doesn't contradict the §Module Layout commitment — it CLARIFIES it.

However, **PLAN.md §Module Layout is incomplete** by not naming `tinyassets/catalog/`. After R7a lands, recommend a small PLAN.md amendment adding `tinyassets/catalog/` as a recognized subpackage (alongside auth/, checkpointing/, evaluation/, etc. — the "existing subpackages that already conform" list).

**Specific amendment** (post-R7a):
> Add to PLAN.md §Module Layout's "Existing subpackages that already conform" line:
> `auth/, catalog/, checkpointing/, constraints/, …`

Tiny edit (one word inserted). Can ship in same commit as R7a or as a follow-up doc commit. Recommend same commit (consistency).

---

## 7. Sequencing within refactor wave

Updated R1-R13 ladder (§5 of `2026-04-19-refactor-dispatch-sequence.md`):

| Refactor | Status |
|---|---|
| R1 STEERING removal | SHIPPED |
| R2 bid promotion | Pending Q4 (now ratified per #64) |
| R3 compat-naming deletion | Pending Q4 |
| R4 layer-3 rename | Awaiting Q10-Q12 host answers (now defaulted via v3) |
| **R7a Phase 7 → catalog/** | **NEW: ships immediately before R7.** ~30 min dev work. |
| **R7 daemon_server → storage/ split** | **Now unblocked** post-R7a. |
| R5 universe_server split | Sequences after R7 (per `2026-04-19-storage-package-split.md` §8). |
| (rest unchanged) | |

R7a is mechanical, low-risk, ~30 min. Adds zero meaningful delay to R7 dispatch.

---

## 8. Update needed for R7 spec itself

`docs/exec-plans/active/2026-04-19-storage-package-split.md` currently assumes `tinyassets/storage/` is empty. Add a one-line dependency note:

> **Depends on R7a (`2026-04-19-r7a-phase7-to-catalog.md`)** — frees `tinyassets/storage/` from Phase 7 catalog backend before R7 splits daemon_server into storage/ context modules.

Doing this in the same nav turn as this R7a spec.

---

## 9. Summary for dispatcher

- **R7a verdict: Option C (re-home Phase 7 to `tinyassets/catalog/`).** HIGH confidence, driven by spec name + responsibility shape, not taste.
- **Single atomic commit, ~30 min dev work.** 8 file moves + ~17 import retargets + optional 1-line PLAN.md amendment.
- **Zero behavior change.** No shim (no external consumers).
- **R7 unblocked** post-R7a.
- **Rejected A/B/D** for documented reasons in §1.
- **Confidence: HIGH** per Foundation/Feature axis (this is foundation — naming locks in load-bearing surface). Lead can ratify and dispatch.
