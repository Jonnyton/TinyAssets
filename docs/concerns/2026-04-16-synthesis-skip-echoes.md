# Synthesis-skip diagnosis — echoes_of_the_cosmos Mission 9

**Status:** Diagnosis. No code changes proposed without lead approval.
**Task:** #16. Sibling concern: STATUS.md "Synthesis race" (2026-04-16).
**Evidence:** `output/echoes_of_the_cosmos/{canon/.manifest.json, worldbuild_signals.json, hard_priorities.json, activity.log}`.

## Observed behavior

Mission 9 uploaded two canon files via `add_canon_from_path`, then the daemon drafted Scenes 1–3 without ever seeing the uploaded canon. Drafts REVERTED on "Zero premise world terms found." Worldbuild ran 18 minutes after Scene 1 started — AFTER three reverted drafts. Only the 9.6 KB source synthesized; the 130 KB source produced `synthesized_docs: []`.

## Ground truth from disk

- **hard_priorities.json** — both source files have `status: "active", hard_block: true`, created 2026-04-17 05:11:10 UTC. The priority surface worked.
- **worldbuild_signals.json** — both signals still queued. Never consumed.
- **canon/.manifest.json** — RESONANCE (9.6 KB) → 8 synthesized docs; ECHOES (130 KB) → `synthesized_docs: []`, no `synthesis_attempts` counter. Handler returned empty without raising.
- **activity.log** — Scene 1 start 05:13:20, three REVERTs at 0.67/0.68/0.67, Worldbuild "starting cycle" at 05:31:10. Log ends there (worldbuild in flight or killed).
- **canon/** — 8 `magic_*.md` synthesized from RESONANCE, all with `.reviewed` sidecars (model=`ollama-local`). No echoes-derived docs.

## Root cause #1 — `run_book` is atomic from the universe graph's view (primary)

Sequence:
1. Daemon entered `run_book` before uploads arrived. (`foundation_priority_review` ran once, saw no hard priorities, routed to `dispatch_execution` → `run_book`.)
2. `add_canon_from_path` uploads landed DURING `run_book`. `sync_source_synthesis_priorities` correctly created two hard-block priorities and appended signals.
3. `run_book` is a single graph node that runs the whole book subgraph synchronously. It does not re-consult hard_priorities mid-run. Three scene drafts completed + reverted before control returned.
4. `universe_cycle` re-entered `foundation_priority_review` at 05:31:10, which finally saw the priorities and routed to `worldbuild`.

**Design gap:** dispatch assumes canon state is stable at the start of a book run. With live MCP uploads the assumption doesn't hold. No mid-run checkpoint for "has a hard priority appeared since we started?"

Code pointers:
- `domains/fantasy_author/graphs/universe.py:454,480` — `run_book` added as a single graph node; dispatch table routes to it without re-checking signals after entry.
- `domains/fantasy_author/phases/foundation_priority_review.py:42-51` — hard-priority gate only runs at cycle boundaries.
- `domains/fantasy_author/phases/dispatch_execution.py:98-102` — `_determine_task` fallback is `run_book` when no intent keyword matches; no "synthesize_source queued?" check.

## Root cause #2 — 130 KB synthesis returned empty (secondary)

`synthesize_source` called `_synthesize_bite_by_bite` (130 KB > `_TIER2_THRESHOLD=50_000`). Target bite size 30 KB → ~5 bites. Manifest shows 0 docs emitted.

Three hypotheses, in order of likelihood:

1. **Provider returned empty/non-JSON on every bite.** `_parse_synthesis_response` returns `{}` on parse failure; no bite contributed to `all_docs`. Consistent with `ollama-local` being used (model=`ollama-local` in the `.reviewed` sidecars) — smaller local models drift toward chat responses on long prompts with complex JSON schema asks.
2. **`_verify_and_fill_gaps` post-pass zeroed the dict.** Less likely; that function appends topics, doesn't delete. But worth ruling out.
3. **Silent exception inside the per-bite loop.** `extractors.py:389-391` catches and logs but continues — if all five bites raise, `all_docs` stays empty. No explicit error log observed in activity.log; this would be in the daemon stderr, not this log file.

**Evidence narrowing:** handler at `worldbuild.py:691-710` calls `synthesize_source()`, which returned `[]`. That took the `logger.warning("Synthesis produced no documents for %s", source_file)` branch → returned `False` to the signal loop → `_record_synthesis_failure(canon_dir, source_file)` → should have bumped `synthesis_attempts` on the manifest entry. **But the manifest has NO `synthesis_attempts` key for ECHOES** — meaning either (a) synthesis hasn't been attempted yet on this file (worldbuild died before reaching it since `_MAX_DOCS_PER_CYCLE=2` and RESONANCE was signal idx 0), OR (b) `_record_synthesis_failure` silently failed. Hypothesis (a) is more consistent with the "worldbuild log ends at 'starting cycle'" state.

**Likeliest story:** worldbuild successfully synthesized RESONANCE, started ECHOES, and is either still running (130 KB bite-by-bite against a local model is slow — 5 bites × N-second provider calls) or crashed between signals. `canon/.manifest.json` and `hard_priorities.json` updates correspond to bewteen-step writes, so ECHOES hasn't finished yet or failed during the bite loop.

## Sibling concern (RC-3) — REVERT-3× ignored by control loop

Not in scope for this diagnosis (STATUS.md tracks as separate concern). Flag for visibility: evaluator fired REVERT on S1/S2/S3 with scores 0.67–0.68. Daemon kept drafting regardless. Control-loop should have halted or escalated after N consecutive reverts. Separable fix.

## Proposed phase-list of fixes (if lead approves)

**Fix A — dispatch-level signal check (RC-1, high-value, low-risk).**
- In `dispatch_execution._determine_task`, add: if `worldbuild_signals.json` contains any unconsumed `synthesize_source` signal for a file whose manifest entry has `synthesized_docs == []` and no `synthesis_attempts >= MAX`, force `return "worldbuild"` regardless of intent/role.
- Alternative placement: `foundation_priority_review` already detects these — but by the time dispatch chooses, the state is already routed. Simplest to add a redundant guard at dispatch.
- Estimated: ~50 lines + 2 tests. One commit.

**Fix B — mid-`run_book` pre-scene guard (RC-1, deeper, higher value).**
- Between scenes inside the book subgraph, consult hard_priorities. If a new hard-block priority appeared since the run started, bail out of `run_book` and let the universe loop re-dispatch to worldbuild.
- Alternative, cheaper: `run_book` checks once at entry (after orient) whether hard_priorities is non-empty; if yes, immediately return without drafting.
- Estimated: ~100 lines + state-machine test. One commit.

**Fix C — synthesis bite-loop diagnostics (RC-2).**
- Log per-bite outcomes at INFO level inside `_synthesize_bite_by_bite`: bite size, provider response length, parsed-doc count. Current code logs success counts but not the per-bite failure pattern.
- When `all_docs` is empty at end, emit a warning with the input size and the failure pattern so a future synthesis-skip debug doesn't require source-code spelunking.
- Estimated: ~30 lines + diagnostic test (mock provider returning empty). One commit.

**Fix D — synthesis retry semantics (RC-2 defense-in-depth).**
- Currently `_record_synthesis_failure` bumps `synthesis_attempts`; after `_MAX_SYNTHESIS_RETRIES=3` the source is permanently failed. If the 130 KB file actually was truncated/malformed, we want the 3-retry cap. But if it's a flaky local model, the host needs a way to reset the counter via MCP.
- Propose: a `reset_synthesis_attempts` MCP action OR a manifest-edit exposed via `add_canon_from_path(path=X, reset_attempts=True)`.
- Estimated: ~30 lines + 1 test. Follow-on to D.

**Recommended landing order:** Fix A + Fix C in one sprint (low-risk, addresses visible symptoms). Fix B next sprint after design review (touches `run_book` contract). Fix D after Fix B so retry reset has clear semantics.

## What I did NOT do

- Did not fix any code.
- Did not restart the daemon.
- Did not re-run the Mission 9 synthesis (daemon may still be alive; host decides).
- Did not touch the echoes_of_the_cosmos universe directory beyond read-only inspection.

Lead: flag which fixes (A/B/C/D) you want scoped into tasks, and whether the REVERT-3× concern should combine with Fix B into a single "dispatch awareness" landing or stay separate.

## Addendum 2026-04-16 — cross-checked against critic report

Critic's `output/critic_reports/2026-04-16-echoes-synthesis-critique.md` measured the downstream drift and reached the same RC-1 conclusion independently. Three new data points:

### Q (lead) — why did run_book start before ingestion finished?

Timestamp audit:
- Scene 1 start: **05:13:20** (activity.log).
- RESONANCE ingest: **05:13:31** (manifest `ingested_at`).
- ECHOES ingest: **05:13:58** (manifest `ingested_at`).
- Worldbuild cycle: **05:31:10** — 17m 50s after Scene 1 start, three REVERTs later.

Scene 1 started 11 seconds BEFORE the first ingest completed because the host dispatched `start_daemon` on the empty universe *before* calling `add_canon_from_path`. No race in the code — the execution order at the MCP layer was wrong: start-daemon came first, uploads second. But the bug isn't the host's ordering; it's that `run_book` accepts an empty-canon universe as a valid starting state. There is no "is this universe ready to write?" precondition. A universe with placeholder premise + zero canon docs + zero KG facts should not be draftable, yet the daemon cheerfully drafted 3 scenes anyway.

The 17-min worldbuild gap origin: `run_book` as a single graph node executes the full book subgraph (all scenes of chapter 1 as dispatched by `foundation_priority_review`'s initial target selection) before returning to `universe_cycle`. The daemon's universe-level loop only re-enters `foundation_priority_review` AFTER `run_book` completes. Three scenes × ~5-6 min per scene = the 17-min gap.

### Q (lead) — KG wipe+rebuild, or flag to rebuild-from-canon-only?

Critic is correct that `knowledge.db` is now durably contaminated: 53 facts, 43 entities, 60 edges all have `seeded_scene` IDs pointing to drifted drafts (e.g. `echoes_of_the_cosmos-B1-C1-S1_chunk_*`). Hallucinated entity `ally`, `blast_door`, `primary_airlock` etc. will resurface in future retrievals as "canon."

Recommend: **Fix E — synthesis completion should wipe draft-seeded KG rows.** After `_handle_synthesize_source` succeeds for any source, delete `entities`/`edges`/`facts` rows whose `seeded_scene` matches `{universe}-B*-C*-S*_chunk_*` pattern (drift drafts) while preserving rows whose `seeded_scene` matches a canon-doc pattern. Safer than wipe-all. Implement as a one-shot post-synthesis cleanup. ~40 lines + test.

Alternative: an MCP `clean_drift_kg(universe_id)` action for manual trigger. Host calls it after synthesis lands.

### Q (lead) — structural REVERT-3× halt (RC-3)

Critic flagged this same concern independently. The structural evaluator correctly fired REVERT on S1, S2, S3 all with "Zero premise world terms found" — that's the strongest possible signal. The daemon ignored it and kept drafting. This is NOT the same bug as RC-1 (the synthesis race) — even with synthesis-gated dispatch, if the evaluator is saying "zero premise terms" three times running, the control loop should halt drafting and route to `reflect` or worldbuild.

Propose: **Fix F — REVERT streak halt.** In `run_book` (between scenes), if the last N commits all returned `verdict=REVERT` with zero structural-term score, force early exit to `universe_cycle` with a `reflect` task. ~30 lines + test. Adjacent to Fix B (mid-`run_book` re-check); both fixes share the "check between scenes" hook so they should land together.

### Q (lead) — can I use notes.json `399af5d2` as the signal?

No — that note is the `grounding_quality` ProcessCheck firing AFTER a scene commit (code at `tinyassets/evaluation/process.py:272`). It's a lagging evaluator signal, not a leading precondition. By the time the note fires, a scene has already been drafted on no canon. Good diagnostic; bad gate.

The correct leading precondition is what critic and my Fix A both point at: **block `run_book` when unconsumed `synthesize_source` signals exist for files whose `synthesized_docs == []`**. That check runs BEFORE any scene drafts, at `dispatch_execution` or at `run_book` entry.

### Revised fix-list (supersedes the 4 above)

- **Fix A (revised)** — `run_book` entry barrier. At `run_book` first line, check `worldbuild_signals.json` for unconsumed `synthesize_source` entries whose manifest entry shows `synthesized_docs == []`. If any exist, return an empty result with a `needs_synthesis` flag on state; `universe_cycle` re-routes to `foundation_priority_review` which will now see the hard_priority and dispatch worldbuild. ~60 lines + 2 tests. **Primary fix.** Critic's "missing blocking gate" framing.
- **Fix C** — bite-loop per-bite diagnostics (unchanged from original list). Needed for next debug. ~30 lines + test.
- **Fix E (new)** — post-synthesis drift-KG cleanup. Delete entities/edges/facts with `seeded_scene` matching the drift pattern. ~40 lines + test. Cleans the existing echoes contamination and prevents recurrence in any universe that goes through a similar race.
- **Fix F (new, was RC-3)** — REVERT-3× streak halt in `run_book`. ~30 lines + test.

Demoted from original list:
- **Fix B** (mid-`run_book` re-check on arbitrary hard_priority appearance) — Fix A covers the canon-upload case, which is the realistic race. The broader "any hard_priority can interrupt drafting" is a much larger contract change; defer until a second concrete case appears.
- **Fix D** (retry-counter reset) — RC-2 hasn't actually fired (no `synthesis_attempts` on ECHOES manifest yet). Defer until the 130 KB file actually completes-and-fails.

### Recommended sprint shape

One commit, small: Fix A + Fix C + Fix E + Fix F. Total ~160 lines + 4 tests. All share the `run_book` entry/between-scene hooks, so the code change is concentrated in `domains/fantasy_author/graphs/universe.py` + `domains/fantasy_author/phases/dispatch_execution.py` + a new KG-cleanup helper. Independently revertable. Ships the barrier (A), the diagnostics (C), the cleanup (E), and the halt (F) as one coherent "synthesize-before-drafting" contract enforcement.

Alternative if lead wants ultra-narrow: Fix A alone as MVP, then C + E + F as a follow-on. My preference is the combined commit since the affected code paths overlap.
