# Bid Cluster → `tinyassets/bid/` Package — Execution Plan

**Date:** 2026-04-19
**Author:** navigator
**Status:** Pre-staged dev-executable plan. Sequenced as **R2** in `docs/exec-plans/active/2026-04-19-refactor-dispatch-sequence.md`. Smallest-dep refactor on the ladder; second-claimable post-Q4-approval (R1 STEERING already shipped).
**Scope:** Promote 4 flat top-level bid modules to a single `tinyassets/bid/` package per the Module Layout commitment in `PLAN.md.draft`.
**Effort:** ~0.5 dev-day. Single contributor.

---

## 1. Why this is the next-up canonical Module Layout commit

Per the spaghetti audit hotspot #3a, the bid cluster is 4 small modules at top-level totaling ~677 LOC, all about per-node paid-market mechanics. None individually big enough to deserve top-level visibility; together they're a coherent subsystem. Per `PLAN.md.draft`'s migration policy ("flat module > 500 LOC OR overlapping sibling responsibility → gets a subpackage"), this is the simplest possible promotion to `tinyassets/bid/`.

**Why this one first** (after R1 STEERING):
- Zero dependency on rename Phase 5, layer-3, Stage 2c, or engine/domain separation.
- ~11 import call-sites total — small mechanical sweep.
- Pre-existing deprecation shim pattern (`bid_ledger.py` re-exports from `bid_execution_log.py`) provides a precedent for the move's back-compat shape.
- Sets the *canonical first commit* under the new Module Layout — every future bid-related work goes in `tinyassets/bid/`, anchoring the architectural commitment.

---

## 2. Files in scope

### 2.1 Source moves (4 modules)

| Old path | New path | LOC | Notes |
|---|---|---|---|
| `tinyassets/node_bid.py` | `tinyassets/bid/node_bid.py` | 386 | Primary NodeBid dataclass + I/O. |
| `tinyassets/bid_execution_log.py` | `tinyassets/bid/execution_log.py` | 139 | Per-universe daemon-local activity log. **Filename shortened** — the `bid_` prefix is redundant inside `tinyassets/bid/`. |
| `tinyassets/bid_ledger.py` | `tinyassets/bid/ledger.py` | 32 | Deprecation shim re-exporting from `bid_execution_log`. **Same prefix-shortening.** |
| `tinyassets/settlements.py` | `tinyassets/bid/settlements.py` | 120 | Cross-host immutable ledger. |

### 2.2 New file

| New path | Contents |
|---|---|
| `tinyassets/bid/__init__.py` | Re-exports the public API for back-compat: imports the most-used names from each submodule and exports them at the package level. See §4 for shape. |

### 2.3 Mirror files

Same 4 moves + 1 new under `packaging/claude-plugin/plugins/tinyassets-universe-server/runtime/tinyassets/bid/`. Byte-equal to canonical per existing mirror discipline.

### 2.4 Top-level back-compat shims (4)

| Path | Purpose |
|---|---|
| `tinyassets/node_bid.py` (NEW shim) | `from workflow.bid.node_bid import *` + `__all__` re-export. One deprecation cycle. |
| `tinyassets/bid_execution_log.py` (NEW shim) | `from workflow.bid.execution_log import *` + re-export. |
| `tinyassets/bid_ledger.py` (RETAINED — was already a shim) | Update internal import to point to `workflow.bid.execution_log` instead of `workflow.bid_execution_log`. |
| `tinyassets/settlements.py` (NEW shim) | `from workflow.bid.settlements import *` + re-export. |

After one release cycle, all 4 top-level shims delete (mirrors author-daemon Phase 5 pattern).

---

## 3. Call-site sweep — 11 imports across canonical tree

| File | Line | Current import | New import |
|---|---|---|---|
| `fantasy_daemon/__main__.py` | 333 | `from workflow.bid_execution_log import append_execution_log_entry` | `from workflow.bid.execution_log import append_execution_log_entry` |
| `fantasy_daemon/__main__.py` | 335 | `from workflow.node_bid import (…)` | `from workflow.bid.node_bid import (…)` |
| `fantasy_daemon/__main__.py` | 342 | `from workflow.settlements import (…)` | `from workflow.bid.settlements import (…)` |
| `tinyassets/universe_server.py` | 2073 | `from workflow.node_bid import read_node_bids` | `from workflow.bid.node_bid import read_node_bids` |
| `tinyassets/universe_server.py` | 2107 | `from workflow.settlements import settlements_dir` | `from workflow.bid.settlements import settlements_dir` |
| `tinyassets/universe_server.py` | 2623 | `from workflow.node_bid import (…)` | `from workflow.bid.node_bid import (…)` |
| `tinyassets/executors/node_bid.py` | 30 | `from workflow.node_bid import NodeBid` | `from workflow.bid.node_bid import NodeBid` |
| `tinyassets/producers/node_bid.py` | 23 | `from workflow.node_bid import read_node_bids, validate_node_bid_inputs` | `from workflow.bid.node_bid import read_node_bids, validate_node_bid_inputs` |
| `tinyassets/settlements.py` (newly a shim — internal sibling import is moot post-move) | — | (settlement helpers reference NodeBid via TYPE_CHECKING) | (handled by relative imports inside the new `tinyassets/bid/` package) |
| `tests/test_phase_g_node_bid.py` | many lines (~10 distinct imports) | `from workflow.node_bid …`, `from workflow.bid_execution_log …`, `from workflow.settlements …` | `from workflow.bid.node_bid …`, etc. |
| `tests/test_phase_h_claim_stress.py` | 32, 206, 257, 343 | `from workflow.node_bid …`, `import workflow.node_bid as nb_mod` | `from workflow.bid.node_bid …`, `import workflow.bid.node_bid as nb_mod` |
| `tests/test_phase_h_dashboard.py` | 187, 188, 402, 410, 418 | mixed bid imports | mirror moves |

**Discipline:** all sweeps go through *new* import paths. Top-level shims exist to catch *external* callers (third-party consumers of the engine) — internal callers should not depend on shims.

**Migration script (recommended):** dev can use `git grep -l 'from tinyassets\.\(node_bid\|bid_execution_log\|bid_ledger\|settlements\)' --` + a sed script. ~5 minute mechanical pass.

---

## 4. Shape of `tinyassets/bid/__init__.py`

Public re-exports for the most-imported names. Goal: existing `from workflow.bid import NodeBid` works without specifying submodule.

```python
"""Per-node paid-market bid mechanics.

Bid surface consists of:
- node_bid: NodeBid dataclass + I/O + claim semantics
- execution_log: per-universe daemon-local activity log (mutable)
- ledger: deprecation shim for old bid_ledger import (delete next cycle)
- settlements: cross-host immutable settlement ledger (write-once)

Per Module Layout commitment (PLAN.md §Module Layout) — flat
top-level bid_*.py modules promoted to this package 2026-04-XX.
Top-level shims in tinyassets/{node_bid,bid_execution_log,bid_ledger,
settlements}.py re-export this package for one deprecation cycle.
"""

from workflow.bid.node_bid import (
    NodeBid,
    bid_path,
    bids_dir,
    claim_node_bid,
    read_node_bid,
    read_node_bids,
    validate_node_bid_inputs,
)
from workflow.bid.execution_log import (
    LEDGER_FILENAME,
    LEDGER_LOCK_FILENAME,
    append_execution_log_entry,
    append_ledger_entry,
    execution_log_path,
    ledger_path,
    read_execution_log,
)
from workflow.bid.settlements import (
    SCHEMA_VERSION,
    SettlementExistsError,
    record_settlement_event,
    settlement_path,
    settlements_dir,
)

__all__ = [
    # node_bid
    "NodeBid",
    "bid_path",
    "bids_dir",
    "claim_node_bid",
    "read_node_bid",
    "read_node_bids",
    "validate_node_bid_inputs",
    # execution_log
    "LEDGER_FILENAME",
    "LEDGER_LOCK_FILENAME",
    "append_execution_log_entry",
    "append_ledger_entry",
    "execution_log_path",
    "ledger_path",
    "read_execution_log",
    # settlements
    "SCHEMA_VERSION",
    "SettlementExistsError",
    "record_settlement_event",
    "settlement_path",
    "settlements_dir",
]
```

Dev should verify this list matches the actual public surface by reading each module's existing `__all__` and exported names — adjust as needed before committing.

---

## 5. Commit sequence — 2 atomic commits

### Commit 1 — package promotion + import rewrites + top-level shims

**Files:**
- 4 source `git mv` operations (canonical + mirror = 8 file moves; canonical paths shown above).
- New `tinyassets/bid/__init__.py` + mirror.
- 4 new top-level shim files (canonical + mirror = 8 shim files).
- Update all 11 call-sites listed in §3 to use new import paths.
- Test suite update — `tests/test_phase_g_node_bid.py`, `tests/test_phase_h_claim_stress.py`, `tests/test_phase_h_dashboard.py`.

**Suggested commit message:**
```
refactor: promote bid surface to tinyassets/bid/ package

First Module Layout commitment per PLAN.md (post-Q4 approval).
Consolidates 4 flat top-level modules (node_bid + bid_execution_log
+ bid_ledger + settlements) into tinyassets/bid/.

- Internal call-sites migrated to new paths (~11 imports).
- tinyassets/{node_bid,bid_execution_log,bid_ledger,settlements}.py
  retained as one-cycle deprecation shims re-exporting the package.
- Test suite updated to new paths; shims remain green-tested by the
  packaging mirror byte-equal check.

R2 of docs/exec-plans/active/2026-04-19-refactor-dispatch-sequence.md.
Closes spaghetti audit hotspot #3a.
```

**Verification:**
- Full pytest. Touches ~3 test files; expected zero behavior change.
- `ruff check` on touched files.
- Mirror byte-equal: existing `tests/test_packaging_build.py` parity check covers it; if a new file is added (the `__init__.py`), confirm the parity check enumerates it.

### Commit 2 — (optional, later) top-level shim deletion

Ships **one release cycle later** — same pattern as author-daemon Phase 5. Not part of R2 dispatch; queued as a follow-up.

**Suggested commit message:**
```
refactor: remove tinyassets/bid/ top-level shims (one-cycle bake complete)

Deletes tinyassets/{node_bid,bid_execution_log,bid_ledger,settlements}.py
after one release cycle of dual-import compatibility.

External callers must now import from workflow.bid.* (per the package's
__init__.py public re-exports).
```

---

## 6. Behavior-change check — what this preserves and what shifts

**Preserves (zero observable change):**
- All public names continue to import successfully via top-level shim re-exports.
- Mirror byte-equality preserved by parallel moves.
- Test suite passes with no logic changes — only import path updates.

**Shifts (mechanical only):**
- 4 file paths under canonical tree change from flat to package-nested.
- Mirror paths shift identically.
- ~11 call-sites updated to new paths.

**No semantic change anywhere.** This is a pure namespace promotion.

---

## 7. Risk register

- **Risk:** Test suite missed import. **Mitigation:** full pytest + grep for any `workflow.{node_bid,bid_execution_log,bid_ledger,settlements}` import that wasn't migrated; the top-level shim catches missed sites with deprecation-warning visibility.
- **Risk:** Packaging mirror parity check missed the new `tinyassets/bid/__init__.py`. **Mitigation:** existing `tests/test_packaging_build.py` enumerates files; verify it picks up the new path before commit. If it whitelists explicit paths, add the new ones.
- **Risk:** A test-fixture monkeypatches `workflow.node_bid` at the *module* level, which now resolves through a shim. **Mitigation:** the shim uses `from workflow.bid.node_bid import *` + `__all__` re-export — does NOT use the deep-submodule alias loader pattern from `_rename_compat.py`. If a test patches `workflow.node_bid.X = Y`, it will set the attribute on the shim module, NOT on the canonical module. **Worth a one-line check:** if any test does `monkeypatch.setattr("workflow.node_bid.X", ...)`, retarget to `workflow.bid.node_bid.X`. Grep finds these in seconds.
- **Risk:** External (third-party) callers depend on the old paths. **Mitigation:** the entire point of the one-cycle shim window is to give external callers time to migrate; deprecation warnings surface during use.

---

## 8. Sequencing relative to R3-R12

**Independent.** R2 has zero file overlap with:
- R3 (`compat.py` naming) — different files.
- R4 (layer-3 rename) — different files.
- R5/R6 (`universe_server.py` + engine/domain split) — different files (R5 *imports* from bid surface but the import sites are listed in §3 and update mechanically).
- R7 (`daemon_server.py` split) — different files.
- R10 (entry-point discovery) — different files.
- R11 (runtime cluster promotion) — different files.
- R12 (servers package promotion) — different files.

R2 can ship before, parallel to, or after any of these. Recommend **first** post-Q4-approval to anchor the architectural commitment with the smallest-cost canonical example.

---

## 9. Summary for dispatcher

- **2 atomic commits** (immediate move + future shim deletion).
- **~0.5 dev-day** for commit 1; commit 2 is one-cycle-later, ~5 min.
- **Pure namespace promotion**, zero semantic change.
- **First canonical Module Layout commit** post-Q4 approval — sets precedent for R7 (storage package), R11 (runtime package), R12 (servers package).
- **Risk: monkeypatch retarget** is the only non-mechanical thing dev needs to verify; everything else is git mv + sed.

When host approves Q4 (PLAN.md.draft), this is the first refactor commit dev can claim. If host also clears Q-host-action-1 (LLM endpoint bind) in the same window, dev can ship R2 + the bind in a single coordinated push.
