# Pair Convergence: #57 surgical rollback design ↔ attribution-layer-specs + canary infrastructure

**Date:** 2026-04-25
**Author:** navigator
**Pair:** dev-2's #57 surgical rollback proposal (`docs/design-notes/2026-04-25-surgical-rollback-proposal.md`, committed `b64dd0f`) ↔ navigator's attribution-layer-specs (`docs/design-notes/2026-04-25-attribution-layer-specs.md`) + existing canary scripts + run-cancellation primitives + branch_versions.parent_version_id.
**Note on numbering:** the design references "Task #57" but the canary-to-patch_request spec also lives at navigator's Task #57 in earlier framing. To avoid confusion: this audit reviews dev-2's surgical rollback proposal, NOT my canary spec.
**Purpose:** cross-check #57's design calls against the substrate it depends on. Surface unresolved gaps + new opens that didn't appear in either solo doc.

---

## Stamp

**PAIR CONVERGES.** All five named cross-checks pass. Three substantive new opens surface from the pairing, including one operational concern that needs a small spec follow-on (canary determinism under bisect replay) and one cross-doc seam (watch-window vs. canary→file_bug throttle).

---

## 1. Cross-check resolution per substrate dependency

| Substrate | Resolution |
|---|---|
| **attribution-layer-specs §6.1 weight table (P0=-10, P1=-3, P2=-1)** | **CONVERGES — weights are USED, not re-derived.** §4 ("Reuse of existing canary infrastructure") explicitly says "Each canary's existing exit-code ladder maps directly to a `caused_regression` weight via attribution-layer-specs §6.1: P0=-10, P1=-3, P2=-1." §6 Q5 explicitly closes this — "reuse attribution-layer-specs §6.1 verbatim APPROVED." Clean delegation. |
| **attribution-layer-specs §1.5 caused_regression event shape** | **CONVERGES with one structural sharpening.** §2 step 5 emits "one `caused_regression` event per rolled-back version per attribution-layer-specs §1.5." But attribution-layer-specs §6.3 specifies that regression weight is *distributed proportionally* to the merge actors' positive shares (`caused_regression.weight[actor] = severity_magnitude * (actor_merge_share / sum_of_shares)`). #57 says "one event per rolled-back version" — implication: **one event per (version, actor) pair**, not just per version. Worth tightening the language; design intent is consistent, wording is tighter in §6.3. Implementation-time clarification, not design-doc gap. |
| **Existing canary scripts (PROBE-001/-002/-003/-004 + revert_loop_canary)** | **CONVERGES — canaries reused as-is via existing exit-code ladder.** §4's "Reuse of existing canary infrastructure" enumerates all five canaries with their script paths, maps exit-codes to weights. **However:** see §3 below — bisect-replay assumes canary determinism, which not all canaries provide. |
| **Existing run cancellation primitive (`run_cancels` table at `tinyassets/runs.py:129-132`)** | **CONVERGES — Q6's "rolled_back_during_execution" cancellation flows through existing primitive.** §6 Q6 says "cancel the run with structured `failure_class='rolled_back_during_execution'`. Run's terminal status flips to `cancelled`." That's exactly the existing cancel path; new failure_class is a tag, not a new mechanism. **Composition with #58 attribution layer-specs §6.4 reversal:** if a rollback is itself reversed (false-positive correction per §6.4 of attribution layer), in-flight runs that were cancelled by the rollback don't re-resume — they're terminated. The reversal corrects the credit ledger but doesn't reanimate cancelled runs. This is correct semantics; flag as cross-doc constraint to verify in test coverage. |
| **`branch_versions.parent_version_id` closure walk** | **CONVERGES — closure-walk uses both `parent_version_id` and `branch_definitions.fork_from`.** §2's `compute_rollback_set` walks both relations correctly. **One subtle thing:** the closure includes ALL published versions of any forked branch_def, not just versions published after the rolled-back parent. If branch X forked from rolled-back version V at time T1, and branch X published versions at T2, T3, T4, all three of X's versions land in the closure regardless of whether they actually reference rolled-back content. Conservative — over-rolls-back rather than under-rolls-back. Worth pinning this as the explicit conservative choice. |

**Net composition health:** five-for-five clean composition. The design correctly delegates to substrate it didn't author. No re-derivation, no contradictions. **The convergence-loop pattern continues to produce tighter integration than predicted from solo design.**

---

## 2. Convergence with my canary→file_bug seam (different cross-cutting check)

This wasn't in lead's brief but surfaces from re-reading: my canary→file_bug spec (`2026-04-25-canary-to-patch-request-spec.md`) and #57's watch-window/bisect both consume the same canary outputs but at different abstraction layers.

| Aspect | canary→file_bug spec | surgical rollback (#57) |
|---|---|---|
| **Trigger** | Canary returns RED any time | Canary returns RED **during a published version's watch-window** |
| **Action** | Files a patch_request via `_wiki_file_bug` | Runs bisect-on-canary, identifies version, emits `caused_regression`, optionally rolls back |
| **Throttle** | Canary-side throttle (6h per (canary_name, failure_class)) | None — every RED during watch-window is a candidate |
| **Dedup** | Server-side Jaccard similarity check | None — bisect produces deterministic version_id attribution |

**Composition observation: the two seams are COMPLEMENTARY, not duplicative.**
- canary→file_bug is the **forward pipeline**: detect → file → invest → fix.
- surgical rollback is the **safety net**: detect → rollback if attribution succeeds.

Both fire on the same canary RED. Both write to the wiki/contribution-ledger surfaces. **They should not double-count.** Implementation-time concern: when a canary RED triggers BOTH a patch_request filing AND a bisect+rollback, the rolled-back version's `caused_regression` event already attributes the regression — the patch_request becomes redundant if the rollback succeeded.

**Recommended composition rule (NEW from this pair-read):** when surgical rollback emits a successful `caused_regression` (bisect identified a culprit + rollback executed), the canary→file_bug seam should detect the existing rollback record and skip filing OR file with a "rolled-back-already" tag for tracking. **Add this to the canary→file_bug spec's open questions** as cross-doc seam reconciliation; not a #57 gap.

---

## 3. Fresh open Qs surfaced by the pairing

Three substantive opens that didn't appear in either solo doc:

1. **Bisect-replay determinism for canaries that mutate state.** §4 says `replay_canary_at_version` "reconstructs the runtime state at the version's published-at timestamp — for canaries that probe MCP endpoints, this means running the canary against the still-live system." But `wiki_canary.py` (PROBE-003) is a **write-roundtrip canary**: it writes to `drafts/canary/uptime-probe.md`, reads back, asserts content match. Replaying this canary against multiple versions in quick succession could leave canary draft content in the wiki across runs (not idempotent against rapid replay). **Recommendation:** bisect-replay must use a probe-script-specific cleanup hook OR scope the wiki canary's draft slug per-bisect-run (e.g., `drafts/canary/uptime-probe-bisect-<run_id>.md`). Open Q for #57 v2 OR a small canary-cleanup spec.

2. **Watch-window timer persistence under daemon restart.** §3 says "the engine schedules a watch-window timer." But if the daemon restarts mid-watch-window, what re-establishes the timer? Two options: (a) timers are persistent (write to a `watch_window_schedule` table + reload at startup), (b) `branch_versions.published_at + watch_window_seconds` is computed on-demand (no scheduled timer; canary RED checks "is this version still in watch-window?" against the columns at evaluation time). **Recommendation: option (b) — on-demand computation.** Avoids a timer table + restart-recovery complexity. The canary running just queries `WHERE published_at > (now() - watch_window_seconds)` to find suspects. Worth pinning explicitly.

3. **Atomic rollback under high merge concurrency.** §2 atomic execution acquires a "rollback-lock against every `branch_version_id` in the closure." If a closure spans 50 versions and a parallel `publish_branch_version` call holds a write-lock on one of them, the rollback waits — and during that wait, the canary that triggered the rollback may fire again, kicking off a SECOND rollback bisect that targets the same closure. Need to make rollback re-entrant: if a rollback is in-flight for closure C, a second bisect-trigger pointing at C should join (not start new). **Recommendation:** rollback engine maintains in-flight rollback registry keyed by `min(branch_version_id in closure)`; second bisect checks registry, joins or skips. Out of scope for v1 if merge velocity is low; flag for v2.

---

## 4. Implementation-time constraints (separate from design-doc gaps)

To land in the dispatch task's verification list, not as design-doc rework:

- **Closure-walk performance budget.** §2's recursive walk is O(closure_size). At low merge velocity, fine. At high velocity (10+ merges/day for months), the closure can grow large; cap or batch walk. Flag for [PENDING #57-impl-perf-test].
- **`compute_rollback_set` test coverage** — must include diamond-dependency case (B forked from V1 + V2, both V1 and V2 in closure → B's versions land once, not twice). Set semantics, not list semantics.
- **`runs.failure_class="rolled_back_during_execution"`** — new failure_class joins the existing taxonomy at `universe_server.py:7060`. Per the convention from canary spec + run_branch audit, this should follow the same shape as other classes: structured `(error, failure_class, suggested_action)` triple.
- **Confirmation-step flake handling (§4 confirmation step).** "If confirmation is GREEN, the bisect is invalidated." But what if the canary is intermittently flaky? §4's confirmation runs once. **Recommendation:** if confirmation is GREEN AND a subsequent canary run goes RED again within X minutes, re-trigger bisect. Cap re-triggers per (canary, version) pair to prevent loops.
- **Pushover host page on P0 (§5)** — secret/config plumbing exists per canary spec; verify before dispatch.
- **`runs action=rollback_merge` host-only authority check** — must follow the same authority model as `set_canonical` per audit-50 (storage-layer authority refactor is the load-bearing prerequisite — flagged in v2 §4 as Phase A item 1).
- **`get_rollback_history` read-only authority** — per #57 §5 has no auth restriction; consistent with project pattern but worth verifying privacy-flagged actors don't leak via this endpoint.
- **Replay-against-live-system contention.** Per §3 above, write-roundtrip canaries left in PROBE-003 leave wiki state that could pollute subsequent canary runs even outside bisect. Worth a separate canary-state-isolation pass.

---

## 5. Roadmap deltas

Three updates for v2 vision / roadmap revision:

1. **Phase E item 23 (`bisect-on-canary`) + item 24 (`atomic-rollback-set`) sub-decompose** into:
   - **23a:** schema additions (`branch_versions.status`/`rolled_back_*`/`watch_window_seconds` columns).
   - **23b:** closure-walk implementation (`compute_rollback_set`) + test coverage.
   - **23c:** atomic execution transaction + canonical re-pointing logic.
   - **24a:** watch-window detection (on-demand computation per §3 Q2).
   - **24b:** bisect algorithm + replay infrastructure + canary-cleanup hooks.
   - **24c:** MCP action surface (`runs action=rollback_merge` + `get_rollback_history`).

2. **Cross-doc seam reconciliation.** Surgical rollback (#57) + canary→file_bug (canary spec) interaction needs explicit composition rule (§2 above). Add as a Phase C/E coordination item.

3. **Phase E item 23a depends on Phase B item 8 SHIP.** `caused_regression` event emission needs the contribution ledger live; the rollback can't emit if the table doesn't exist. Sequencing: Phase B item 8 (ledger schema) → Phase E item 23 (rollback emits to it). Roadmap §1 graph already has B → E implicitly; making it explicit prevents accidental parallel dispatch of incompatible orderings.

---

## 6. References

- Audit target: `docs/design-notes/2026-04-25-surgical-rollback-proposal.md` (#57, dev-2 — committed `b64dd0f`).
- Substrate cross-checked:
  - `docs/design-notes/2026-04-25-attribution-layer-specs.md` (#58 — §1.5 caused_regression event shape; §6.1 weight table; §6.3 actor-proportional distribution; §6.4 reversal/correction).
  - `docs/design-notes/2026-04-25-contribution-ledger-proposal.md` (#48 — single-table emit-site pattern).
  - `docs/design-notes/2026-04-25-canary-to-patch-request-spec.md` (canary spec — same canaries consumed at different abstraction layer; cross-doc seam in §2 above).
  - `docs/design-notes/2026-04-25-variant-canonicals-proposal.md` (#47 — canonical re-pointing on rollback).
  - `docs/design-notes/2026-04-25-runner-version-id-bridge.md` (#54 — immutable version snapshots).
- Existing canary scripts: `scripts/mcp_public_canary.py`, `scripts/uptime_canary_layer2.py`, `scripts/wiki_canary.py`, `scripts/mcp_tool_canary.py`, `scripts/revert_loop_canary.py`.
- Existing run-cancel primitive: `tinyassets/runs.py:129-132` (`run_cancels` table).
- Schema substrate: `tinyassets/branch_versions.py:25-67` + `tinyassets/daemon_server.py:404-411` (fork_from).
- v2 vision: `docs/design-notes/2026-04-25-self-evolving-platform-vision-v2.md` Phase E §6 + §3 contribution surfaces.
- Pair-reads completed: #59 (#54↔#56), #60 (#50↔#56), #62 (audit-53 solo), #65 (this).
