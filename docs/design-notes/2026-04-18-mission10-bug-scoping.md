---
status: research
---

# Mission 10 Bug Scoping — Fix-Ready Pointers

**Date:** 2026-04-18
**Author:** navigator
**Status:** Scoping pass. Read-only; no code touched. Avoids rename-in-flight zones.
**Relates to:** tasks #15 (list_canon tier gap), #16 (accept_rate miscount), #17 (control_daemon observability).

All three bugs live in `tinyassets/universe_server.py` (and its collaborators in `tinyassets/ingestion/core.py` + `tinyassets/desktop/dashboard.py`). None touch `domains/fantasy_author/`, `domains/fantasy_daemon/`, `tinyassets/author_server.py`, or `tinyassets/daemon_server.py` — safe during Phase 1 rename.

---

## Bug 1 — `list_canon`/`read_canon` don't surface source-tier files (task #15)

**Where it is:**
- `tinyassets/universe_server.py:3221-3252` — `_action_list_canon`.
- `tinyassets/universe_server.py:3255-3294` — `_action_read_canon`.
- `tinyassets/universe_server.py:1166-1167` — action dispatch.
- `tinyassets/universe_server.py:1075-1098` — tool signature (no `tier` param currently).

**Where the write path goes:**
- `tinyassets/ingestion/core.py:410-427` — `ingest_file` routes user uploads (`user_upload=True`) to `canon/sources/` unconditionally, sets `routed_to="sources"`.
- `tinyassets/universe_server.py:3181-3187` (`_action_add_canon_from_path`) and `:3037-3043` (`_action_add_canon`) both call `ingest_file(user_upload=True)` → every MCP upload lands under `canon/sources/`, never at `canon/`.
- `tinyassets/ingestion/core.py:441-453` — manifest at `canon/.manifest.json` records each ingest with `source_path="sources/<filename>"`.

**Concrete gap:**
`_action_list_canon` walks `canon_dir.iterdir()` (single level, line 3234) and skips dotfiles (line 3235). `canon/sources/` is a directory, so `f.is_file()` at line 3235 is False → source-tier files silently invisible. The `.manifest.json` is skipped by the dotfile filter. There is no `tier` kwarg on the action signature or the tool decorator.

`_action_read_canon` at line 3269 does `canon_dir / safe_name` — can't read a sources-tier file without `sources/<name>` prefix, which the tool signature doesn't expose.

**Fix shape (no code):**
1. Add `tier: str = "all"` kwarg to the `universe` tool signature and thread through `_action_list_canon` / `_action_read_canon`. Accept `"synthesized" | "sources" | "all"`.
2. `list_canon(tier)` walks `canon_dir` for `synthesized`, `canon_dir/sources/` for `sources`, both for `all`. Use the manifest at `canon/.manifest.json` as the authoritative index when present — each entry already carries `routed_to`, so filtering is trivial.
3. `read_canon(filename, tier=…)` resolves the target path by tier: `canon_dir/<name>` or `canon_dir/sources/<name>`. Fall back to searching both if `tier="all"` or unspecified.
4. Preserve backward compatibility: omitting `tier` returns all canon, matching what callers expect post-fix.

---

## Bug 2 — `accept_rate` counts total scenes, not evaluated scenes (task #16)

**Where it is:**
- `tinyassets/desktop/dashboard.py:30-57` — `DashboardMetrics` dataclass, `record_accept`/`record_reject`, `_update_rate`.
- `tinyassets/desktop/dashboard.py:64-97` — `seed_from_db`, the load-bearing bug.

**The read-path is correct.** `tinyassets/universe_server.py:1325-1372` (`_compute_accept_rate_from_db`) filters `verdict IS NOT NULL AND verdict != '' AND verdict != 'pending'` for the denominator and `verdict IN ('accept', 'second_draft')` for the numerator. When the MCP surface reads accept_rate, this function runs and is fine.

**The write-path is wrong at seed time.** `seed_from_db` (line 76-92):
- Line 78-80: `SELECT COUNT(*), SUM(word_count), COUNT(DISTINCT chapter_number) FROM scene_history`.
- Line 82: `self.scenes_complete = row[0]` — total row count, including pending.
- Line 85-88: `SELECT COUNT(*) FROM scene_history WHERE verdict IN ('accept', 'second_draft')` — filters accepted correctly.
- **Line 91: `self._evaluated = row[0]` — sets evaluated to TOTAL scenes, not evaluated scenes.** This is the bug. If 100 scenes exist with 10 accepted + 20 rejected + 70 pending, seed sets `_accepted=10`, `_evaluated=100` → accept_rate=10% instead of 33%.

**Fix shape (no code):**
1. Replace the second query to also compute `evaluated = COUNT(*) WHERE verdict IS NOT NULL AND verdict != '' AND verdict != 'pending'`, mirroring `_compute_accept_rate_from_db`'s logic at line 1354-1358.
2. Assign `self._evaluated = evaluated` on line 91 instead of `row[0]`.
3. Bonus consistency: extract the verdict filter as a module-level SQL constant reused by both `_compute_accept_rate_from_db` and `seed_from_db` so they can't drift again.

**Secondary concern (non-blocking):** `record_reject` at line 51-53 increments `_evaluated` on every non-accept call. If the daemon ever calls it with a `pending` verdict instead of holding until a real reject, the runtime counter will diverge from the DB truth. Audit daemon-side callers before closing this ticket — but not in scope for the minimal fix.

---

## Bug 3 — `control_daemon status` observability gap (task #17)

**Where it is:**
- `tinyassets/universe_server.py:3297-3376` — `_action_control_daemon` (handles `pause`/`resume`/`status`).
- `tinyassets/universe_server.py:3344-3371` — the `status` branch, the thin one.
- `tinyassets/universe_server.py:1427-1469` — `_daemon_liveness`, the telemetry builder.
- `tinyassets/universe_server.py:1238-1291` — `_last_activity_at` and `_staleness_bucket`.

**Status contradiction mechanism:** `phase` (line 1456) reads `current_phase` from `status.json` — written by the daemon when it enters a phase, never updated if the daemon crashes mid-phase. `staleness` (line 1441) derives from `activity.log` mtime, which only advances when the daemon is actually running. Result: `phase="running"` + `staleness="dormant"` after a silent crash. Both are technically "correct for their source" — but the caller has to reconcile two truths.

**Missing observability fields** (all derivable from files already on disk):
- `pending_signal_counts`: `worldbuild_signals.json` queue depth (unconsumed signal count per type). The synthesis-skip incident would have been diagnosable in one call with this field.
- `hard_priority_counts`: `hard_priorities.json` active + blocking counts. Shows whether the daemon has a reason to reroute.
- `time_in_phase_seconds`: `now - status.json::last_updated`. Detects long-running phases (worldbuild at 18 minutes would have stood out).
- `evaluator_streak`: consecutive REVERT count (from `scene_history` tail) — paired with RC-3 concern, makes the "3× REVERT" visible without pulling the full ledger.

**Fix shape (no code):**
1. Make `phase_human` the authoritative single-word state; demote `phase` to a sub-field. Extend `_phase_human` precedence to override raw phase when `staleness == "dormant"` — `"stalled-in-<raw_phase>"` beats `"running"` when activity.log has been silent for >24h. The decoupling between two sources is real; the fix is to expose ONE reconciled answer plus the raw inputs for debugging.
2. Extend `_daemon_liveness` (tinyassets/universe_server.py:1427) to include:
   - `pending_signals` dict — read `worldbuild_signals.json`, group by signal type, count unconsumed entries.
   - `time_in_phase_seconds` — compute from `status.json::last_updated` vs `datetime.now(timezone.utc)`.
   - `evaluator_streak` — read the last N rows of `scene_history` ordered by timestamp desc, count consecutive `verdict='revert'`.
3. Thread these through the three sites that read liveness today (`_action_list_universes` line 1496, `_action_inspect_universe` line 1533, `_action_control_daemon` line 3368).
4. Update `phase_human` (`tinyassets/universe_server.py:1294`) precedence so `staleness == "dormant"` takes priority over raw_phase. Likely shape: if `staleness == "dormant"` and `raw_phase` not in the terminal set, return `"stalled-in-<raw_phase>"` instead of bare `raw_phase`.

**Non-code recommendation:** write the observability fields to a named shape (`DaemonLiveness` TypedDict) in `tinyassets/universe_server.py` near line 1427. Three call sites consuming the same dict justifies the type.

---

## Sequencing + collision notes

- All three bugs touch `tinyassets/universe_server.py` and `tinyassets/desktop/dashboard.py`. **Zero overlap with `domains/*` or `tinyassets/author_server.py`.** Safe to dispatch while Phase 1 rename is in flight.
- Bug 2 (dashboard) is lowest risk — one file, one line change + one test. Could be an early-landing confidence-builder.
- Bug 1 requires a tool signature change (`tier` kwarg on `universe`). Heads-up for the MCP schema consumers (Claude Desktop re-registers on reconnect, no special migration). Action-level param addition is additive; no caller break.
- Bug 3 is the most structural. Extending `_daemon_liveness` affects three read sites; `phase_human` precedence change is user-visible. Land last, with a brief changelog note.

---

## Sources

- Concern: `docs/concerns/2026-04-16-synthesis-skip-echoes.md` (RC-2 bite-loop hypothesis overlaps with Bug 3's observability gaps).
- Ingestion: `tinyassets/ingestion/core.py:410-453` (ingest routing + manifest), `:1-30` (file header docs).
- Tool surface: `tinyassets/universe_server.py:1075-1217` (universe tool), `:1427-1469` (_daemon_liveness).
- Metrics: `tinyassets/desktop/dashboard.py:30-97` (DashboardMetrics + seed_from_db).
