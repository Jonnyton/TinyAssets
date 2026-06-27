# Stress-Test Scenario Checklist

**Status:** planner + dev collab, 2026-04-14. Living doc.
**Audience:** user steering via MCP; user-sim for automated regression.
**Priority:** P0 likely-in-normal-use + MCP-recoverable. P1 user-visible edge. P2 internal consistency only.

Each scenario: *steps → expected → failure mode caught*. P0 set is the user-sim regression floor.

---

## 1. Cross-universe isolation

Lessons: Ashwater leak, Sporemarch KG contamination.

| # | P | Scenario | Steps | Expected | Fails if |
|---|---|---|---|---|---|
| 1.1 | 0 | Switch-and-query probe | Create `probe-a` + `probe-b` with distinct premises; in one session, switch_universe + query_world on each | Each query returns only its own entities; response leads with `Universe: <id>` | Runtime singleton leaks across universes |
| 1.2 | 1 | Concurrent-session probe | Two MCP clients act on different universes simultaneously | Each request lands in its own universe | Shared-process active-universe race |
| 1.3 | 1 | Explicit universe_id mismatch | `give_direction universe_id=probe-a` while active universe is `probe-b` | Direction lands in probe-a; response confirms | Active-universe override silently swallows explicit param |
| 1.4 | 2 | KG/vector defense-in-depth | Write rows during probe-a cycle; dump; assert `universe_id=probe-a` | Rows carry universe_id | Path-isolation is sole defense (open Concern 2026-04-14) |

## 2. Request flooding (submit_request → work_targets, `#18` pipeline)

| # | P | Scenario | Steps | Expected | Fails if |
|---|---|---|---|---|---|
| 2.1 | 0 | Burst submission | 50 submit_request calls in <5s | All 50 land as distinct WorkTargets; daemon's next cycle sees all 50 | Silent drops from `_read_json` `[]` fallback; file-write race |
| 2.2 | 1 | Duplicate request_id | Submit twice with identical id OR submit → materialize → re-submit | Idempotent on request_id; no duplicate WorkTargets | Duplicate targets fill queue from retry |
| 2.3 | 1 | Oversize text | `submit_request text=<50MB>` | Server rejects with clear error (`#18` follow-up 2) | Silent truncation; disk-fill; parser crash |
| 2.4 | 1 | Corrupt requests.json | Hand-edit to invalid JSON; restart daemon; submit | Daemon fails loud, refuses operation on file (`#18` follow-up 1) | Silent `[]` fallback masks state corruption |
| 2.5 | 2 | Cancel mid-materialize | Submit then give_direction category=error before next cycle | Unambiguous lifecycle outcome | Zombie WorkTarget with mixed state |

## 3. Daemon stop / restart / recovery

| # | P | Scenario | Steps | Expected | Fails if |
|---|---|---|---|---|---|
| 3.1 | 0 | Cycle-noop streak | No premise; 5 cycles | Self-pause at streak=5 with `idle_reason="universe_cycle_noop_streak"` | No-op spin forever (`#6` regression) |
| 3.2 | 0 | Restart clears stopped | Trigger 3.1; set premise; tray-restart | Clean resume; streak reset | Stopped state persists across restart |
| 3.3 | 1 | Mid-cycle kill | Start scene write; kill; restart | In-flight marked `interrupted`; checkpoint recovers; no partial scene | Partial-commit corruption |
| 3.4 | 1 | Fast restart cycle | Tray restart ×3 in <10s | Clean final binding; no singleton leak | Stale runtime.py singletons between restarts |

## 4. Phase 6.1 gates flag (`b6722bd`)

| # | P | Scenario | Steps | Expected | Fails if |
|---|---|---|---|---|---|
| 4.1 | 0 | Flag-off sanity | `GATES_ENABLED=off`; call `gates claim` | Clear "gates disabled" response (not 500, not silent) | Tool registered without backing = confusing error |
| 4.2 | 0 | Flag-on first claim | `GATES_ENABLED=on`; propose + define_ladder + bind + claim | Claim lands; `goals leaderboard metric=outcome` returns ranked entry | Stub rewire broken at `_action_goal_leaderboard @ 6229-6264` |
| 4.3 | 1 | OFF→ON mid-session | 3 claims fail on OFF; flip to ON; retry | Retries succeed; no residue; exactly 3 rows | Failed-attempt state blocks retry |
| 4.4 | 1 | Ladder edit with claims | Ladder `[A,B,C]`; claim A+C; reladder `[A,X,C]` | A+C preserved; B marked `orphaned=true`; leaderboard ignores | Silent data loss when rung disappears |
| 4.5 | 2 | Retract → re-claim | Claim A; retract; re-claim A | Reactivates row; no duplicate | Retract breaks claim idempotency |

## 5. Goal-Branch binding

| # | P | Scenario | Steps | Expected | Fails if |
|---|---|---|---|---|---|
| 5.1 | 0 | Bind to non-existent Goal | `goals bind goal_id=ghost branch_def_id=<valid>` | Clean error; Branch remains unbound | Silent invalid FK write |
| 5.2 | 1 | Unbind during active claims | Propose+bind+claim; then unbind | Claims preserved (they're on branch+rung); leaderboard drops branch from that Goal | Cascade deletes claims OR orphans them unreadably |
| 5.3 | 1 | Delete Goal with bindings | Bind 3 Branches; soft-delete Goal | Goal hidden from list; branches' goal_id survives with "deleted" marker | Invisible orphan Branches |

## 6. Concurrent daemon + MCP actions

| # | P | Scenario | Steps | Expected | Fails if |
|---|---|---|---|---|---|
| 6.1 | 0 | MCP write during cycle | Daemon in `run_book`; submit `give_direction` same window | Both writes land; daemon picks up note next orient | Last-writer-wins clobber; daemon stale read |
| 6.2 | 1 | Concurrent claim + ladder update | `gates claim` + `goals update gate_ladder_json` on same Goal | Both succeed; no orphan | Claim lands against stale ladder |
| 6.3 | 2 | Rapid give_direction | 20 calls in 2s; daemon reads between | Daemon sees all 20 or stale-reads acceptably; zero silent drops | Write-truncation on concurrent read |

## 7. Malformed inputs

| # | P | Scenario | Steps | Expected | Fails if |
|---|---|---|---|---|---|
| 7.1 | 0 | Empty required fields | Each write action with empty/missing required field | Clear rejection naming field | Validator gap exposes 500 |
| 7.2 | 1 | Unicode identifiers | `create_universe universe_id="📕-universe"` | Either reject with rule OR round-trip correctly | Path crash; slug collision |
| 7.3 | 1 | Size caps | `add_canon` 10MB body; `set_premise` 1MB | Cap enforced with clear error (audit all write actions) | Disk-fill; memory exhaustion |
| 7.4 | 2 | Null optional fields | Every action, `null` for each optional | Treated as absent; no crash | None vs "" normalization gap |

## 8. Phase A regression surfaces (landing `#20`)

Phase A renames concept #2 (SQL `branches` → `universe_fork`) and deletes `universe.branches.json` stub. Regression targets:

| # | P | Scenario | Steps | Expected | Fails if |
|---|---|---|---|---|---|
| 8.1 | 0 | `list_branch_defs` returns workflows | Post-Phase-A call to renamed action | Returns user-registered BranchDefinitions, not stub `[{"id":"main"}]` | Rename didn't swap both sites |
| 8.2 | 0 | `list_universe_forks` returns real forks | Post-Phase-A call on universe with multiple forks | Returns SQL `branches` table content under new name | Rename broke SQL query |
| 8.3 | 1 | Legacy MCP clients calling `list_branches` | Old chat calls pre-rename name | Clear deprecation error OR transparent redirect to the right one of the two | Silent 500 confuses users mid-rename |
| 8.4 | 2 | SQL schema migration idempotence | Run Phase A migration twice | Second run is no-op; no duplicate index errors | Migration not idempotent on ADD COLUMN IF NOT EXISTS pattern |

## 9. `#18` producer/consumer seam (dev)

Code-level failures on the `submit_request → requests.json → materialize_pending_requests → WorkTarget → authorial_priority_review` seam. Pinning tests for shipped #22 items live in `tests/test_submit_request_wiring.py`.

| # | P | Scenario | Steps | Failure mode | Subsystem |
|---|---|---|---|---|---|
| 9.1 | 0 | Materialize/cycle seam race | 2 threads: concurrent `submit_request` with a stubbed-slow `materialize` running between them | Read-modify-write loss: submit A reads `[]`, B reads `[]`, last writer wins — one append erased | `tinyassets/work_targets.py` + `tinyassets/universe_server.py:_action_submit_request`; no file lock on `requests.json` |
| 9.2 | 1 | Corruption invisibility on `inspect` | Hand-corrupt `requests.json`; call `universe inspect` | Post-#22 warn is logged but `inspect` still reports `pending_requests=0` — indistinguishable from "no pending"; user can't see their request is stuck | `_action_inspect_universe` should probe byte length + surface `requests_status=corrupt` |
| 9.3 | 2 | 32-bit request_id collision | Monkeypatch `os.urandom(4)` to fixed bytes; submit twice in same wall-clock second | `request_id` collides → `target_id=request-<req_id>` collides → `upsert_work_target` silently clobbers first with second's text; user A's intent lost | `_action_submit_request` entropy: `os.urandom(4)` → widen to 8 bytes |
| 9.4 | 1 | SQLite lock → JSON fallback drift | Hold long-running write txn on `universe_work_targets`; run `materialize_pending_requests` with 5 pending | Upsert times out → `save_work_targets` writes entire list to JSON while SQLite keeps pre-txn rows; next `load_work_targets` returns stale SQLite view | `tinyassets/author_server.upsert_work_target_dict` + `tinyassets/work_targets.upsert_work_target` silent JSON fallback |

## 10. Structural / archaeological (explorer)

Failures surfaced only by reading the architecture map across modules — things that won't show up in a per-feature stress test because the seam crosses subsystems or encodes an invariant that's documented in one file and assumed in another. Lessons: Sporemarch contamination, the 3-way "branch" name collision, the two orthogonal execution models, `runtime.py`'s per-process binding invariant.

| # | P | Scenario | Steps | Expected | Fails if |
|---|---|---|---|---|---|
| 10.1 | 0 | **Daemon vs `run_branch` on same universe** (Model A × Model B shared-artifact race) | Universe X has an active daemon cycle mid-write; in parallel, `extensions action=run_branch` a workflow whose inputs write into universe X's notes.json / work_targets.json / LanceDB | Both execution models coordinate writes (lock, queue, or explicit serialization); no torn JSON; no double-commit into KG | The two models assume exclusive access to `universes/X/` and stomp each other. This is the load-bearing "Branch ⊥ Universe" claim tested under concurrency — if it fails, the architecture's two-execution-model premise doesn't hold. |
| 10.2 | 0 | **Silent process death in tray triad** (tray-managed MCP + cloudflared + per-universe daemons) | With ≥2 universes running and a tunnel active, kill each of (cloudflared, MCP server, one daemon) in isolation — `taskkill /F /PID` or equivalent — one at a time, restart the tray between probes | Tray detects the death within ≤10s, surfaces it (tray icon / notification / dashboard), and the other two stay up; user loses zero durable work | Any one death is invisible in the tray UI, OR cascades to sibling processes, OR corrupts the universe it was bound to. Operational-trust foundation — silent daemon death = user drafts work they'll never see committed. |
| 10.3 | 0 | **Singleton rebind without reset** (Sporemarch-class regression guard) | Add a test that asserts: any code path which changes the active universe for `tinyassets/runtime.py` singletons (`knowledge_graph`, `vector_store`, `raptor_tree`, `memory_manager`, `embed_fn`, `universe_config`) calls `runtime.reset()` between bindings. Static check + runtime assertion if second `bind` is attempted on non-reset state | `DaemonController._cleanup()` is the only legitimate rebind path today; test enforces invariant going forward | A refactor introduces an in-process switch_universe path that skips `reset()`. Writer is fed cross-universe retrieval hits. Reproduces the pre-2026-04-11 Ashwater leak described in `tinyassets/runtime.py:25-30`. |
| 10.4 | 1 | **3-way `branch` name collision under lookup** | Post-Phase-A, in universe X: register a BranchDefinition with id `main` (concept #3); in the same universe, create a SQL `universe_forks` row also named `main` (concept #1). Call every action that resolves a bare `branch` / `branch_id` parameter — `run_branch`, `list_branches` (if still routed), `submit_request branch_id=main`, `give_direction branch_id=main`, goals bind | Every action resolves unambiguously — either by requiring a qualified type, or because the parameter is typed at the schema level (BranchDefinition-ref vs universe-fork-ref) | Any action resolves `main` to whichever table it checks first. Phase A resolved the rename half; this probe confirms the lookup-path half. Low incidence today but high blast radius once Goals + universe-forks are both user-facing. |
| 10.5 | 1 | **`inspect_universe` N-file flood vs daemon writes** | Daemon mid-cycle in universe X; MCP client fires 30× `universe inspect universe_id=X` in <5s. Inspect reads status.json + notes.json + work_targets.json + PROGRAM.md + activity.log + output/ tree per call (`universe_server.py:1166-1245`) | Inspect returns consistent snapshots (possibly stale, never torn); daemon's own writes to the same files aren't slowed measurably | Concurrent readers produce partial JSON parses (read mid-write), OR inspect's IO starves the daemon's write path, OR the response balloons past MCP payload limits on large universes with deep output trees. |
| 10.6 | 2 | **`REQUESTS_FILENAME` import centralization regression** (#22 follow-up) | After #22 centralized the `requests.json` filename constant, assert via static grep: no module outside `tinyassets/author_server.py` (or wherever the constant lives) references the literal string `"requests.json"`. Add as a lint-style check or pytest collection-time assertion | Single source of truth for the filename; reviewer-flagged hazard from #22 stays closed | A future contributor re-introduces the literal; producer and consumer drift apart, reviving the #18 silent-drop class. Cheap pinning test. |

---

## P0 regression floor

Cross-universe 1.1 · Flooding 2.1 · Daemon 3.1/3.2 · Gates 4.1/4.2 · Binding 5.1 · Concurrency 6.1 · Malformed 7.1 · Phase A 8.1/8.2 · `#18` 9.1 · Structural 10.1/10.2/10.3. **14 scenarios — user-sim runs this on every restart-worthy change.** P1 on release candidates; P2 on demand.

## Out of scope

Perf benchmarks · security fuzzing · provider-outage · git-layer stress (Phase 7 surface).

## Authoring

Planner owns §1-8, dev owns §9, explorer owns §10. New scenarios welcome via PR; pick P0/P1/P2 based on user-exposure + recoverability; name the failure mode.
