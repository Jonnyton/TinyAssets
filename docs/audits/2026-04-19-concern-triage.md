# STATUS.md Concerns — Triage

**Date:** 2026-04-19
**Author:** navigator
**Purpose:** Each STATUS.md concern classified as `dev` (dispatchable code/test work), `user-sim` (live-mission validation), or `host-decision` (waiting on host answer/judgment). Dispatch-ready notes per row.

---

## Triage table

| # | Concern (STATUS.md) | Type | Routing | Dispatch-ready notes |
|---|---|---|---|---|
| 1 | **[2026-04-14] Sporemarch fix (b): verify multi-scene overshoot + dispatch-guard retention in next user-sim.** | **user-sim** | Fold into next non-Devin user-sim mission. | Mission 8 indirectly passed (43→accepted scenes, C15→C16 boundary crossed). The remaining ask is *direct* observation of one accept cycle + +1 advance, plus dispatch-guard retention probe (e). Add as a stop-condition in user-sim's next sporemarch resume. No code change required. |
| 2 | **[2026-04-17] Echoes drift-drafted Scene 1/2/3 still in `output/echoes_of_the_cosmos/story.db`; retest fresh universe vs resume.** | **user-sim** + minor **dev** | A/B mission. | (a) Fresh universe: spawn `echoes_of_the_cosmos_v2` from clean state, ingest the same canon, watch first 3 scenes. (b) Resume: re-spin the existing universe, observe whether the drift-drafted scenes get rejected/revised or get accepted-as-is. Dev component is small: confirm there's no API to "wipe scenes 1-3 only" — if absent, retest is the only validation path. |
| 3 | **[2026-04-17] 589e1fb REST changes need tests: `/votes/{id}/resolve` forced; `/votes/{id}/ballots` now `{"vote": ...}`.** | **dev** | Dispatchable now. | Atomic, low-risk. Add 2 pytest cases in `tests/test_author_server_api.py` (or its post-rename successor): (i) POST `/votes/{id}/resolve` with no body → forced resolution succeeds; (ii) POST `/votes/{id}/ballots` with `{"vote": "yes"}` → ballot recorded; the legacy non-wrapped shape returns 400. ~30-min commit. Watch for collision with #6 if `test_author_server_api.py` is touched there. |
| 4 | **[2026-04-17] Privacy mode note landed: `docs/design-notes/2026-04-18-privacy-modes-for-sensitive-workflows.md`; 3 host Qs remain.** | **host-decision** | Awaiting host. | Note shipped 2026-04-17. The 3 host Qs gate dispatch — until answered, no code task makes sense. Recommend lead surface these Qs alongside the layer-3 §5 Qs in the next host check-in. |
| 5 | **[2026-04-18] `add_canon_from_path` sensitivity note landed: `docs/design-notes/2026-04-18-add-canon-from-path-sensitivity.md`; 3 host asks remain.** | **host-decision** | Awaiting host. | Same shape as #4. Note has 3 specific asks. Once answered, the implementation is small (extract `add_canon_from_path` as its own MCP tool per the note's M1 recommendation, ~0.5 dev-day). Bundle with #4 host check-in. |
| 6 | **[2026-04-18] Claude.ai injection note landed: `docs/design-notes/2026-04-18-claude-ai-injection-hallucination.md`; task #15 still blocked.** | **host-decision** + downstream **dev** | Awaiting host on #15 unblock; then dev-dispatchable. | Task #15 is the Yardi-fabrication fix (per activity.log "task #15 IN PROGRESS"). Status field "still blocked" suggests the design note hasn't received host-greenlight yet OR an upstream constraint persists. Recommend lead confirm with host: is #15 still blocked, or has the in-flight dev work superseded the blocker? If superseded, this concern can be deleted. |
| 7 | **[2026-04-18] `fantasy_daemon/author_server.py` alias risk: snapshot export, not sys.modules rebind; fix there if cross-alias drift appears.** | **dev** (conditional) | Latent — fix-on-detection. | Per the dev handoff at activity.log 2026-04-18T00:15: this is the one shim that uses snapshot re-export instead of `sys.modules[__name__] = workflow.daemon_server`. **If** verifier surfaces cross-alias state-drift in the #6 full-pytest run, this is the proximate cause and a 1-line fix. Otherwise, defer until Phase 5 deletes the shim entirely. Not worth proactive dispatch. |
| 8 | **[2026-04-18] Full-platform architecture supersedes phased plan: `docs/design-notes/2026-04-18-full-platform-architecture.md`.** | **host-decision** + **navigator** follow-up | Awaiting §11 host Qs (16 active). | This is the meta-concern that's blocking the largest amount of downstream work. Per STATUS.md Next §1: 16 active Qs, with Q1 (Postgres-canonical), Q7 (Fly), Q10 (load-test), Q17 (co-maintainer), Q29-31 (autoresearch DSL/budget/conflict), Q32-34 (evaluator cost/authoring/drift) flagged load-bearing. Recommend lead push the host on Q1+Q7+Q10 as the smallest unblocking subset (everything else can wait one cycle). |
| 9 | **[2026-04-19] Navigator follow-up: `docs/design-notes/2026-04-19-modularity-audit.md` flags `universe_server`, discovery, and `daemon_server` seams.** | **navigator** + downstream **dev** | Navigator-curated. | The audit identifies seams to address post-rename. Until rename Phase 5 lands, deferring per §73 (per STATUS.md Next §5 "modularity-audit legacy cleanup deferred per #73"). Navigator should re-audit after Phase 5 to confirm seam list is still accurate, then propose dev tasks. No action this cycle. |

---

## Summary by routing

**Dev-dispatchable now (1):**
- Concern 3 — votes REST tests. Single atomic commit, ~30 min.

**Dev-dispatchable conditional / latent (1):**
- Concern 7 — alias-risk fix-on-detection.

**User-sim dispatchable (2):**
- Concern 1 — Sporemarch direct-observation probe (fold into next sporemarch mission).
- Concern 2 — Echoes A/B fresh-vs-resume mission.

**Host-decision waiting (5):**
- Concern 4 — privacy mode 3 Qs.
- Concern 5 — add_canon_from_path 3 asks.
- Concern 6 — Claude.ai injection / #15 unblock confirmation.
- Concern 8 — full-platform architecture 16 §11 Qs (highest leverage).
- (Concern 6's downstream dev work also gated.)

**Navigator-curated, deferred (1):**
- Concern 9 — modularity-audit seams; revisit post-Phase 5.

---

## Recommended actions

**For dev backlog (immediate):**
- Add concern 3 (votes REST tests) as a STATUS.md Work row when dev finishes #6/#7. Estimated ~30 min; good "next-up" filler.

**For user-sim backlog:**
- After Devin Session 2 finishes (currently in_progress as task #3), the next non-Devin mission should fold concerns 1 + 2 as primary objectives. Recommend running them sequentially in one session: concern 2 (Echoes fresh-vs-resume A/B) first because it's a clean state-check; concern 1 (Sporemarch direct-accept observation) second because it requires waiting for a live accept cycle.

**For host check-in (next opportunity):**
- Bundle the unblock requests:
  - Concern 4 (privacy 3 Qs)
  - Concern 5 (add_canon_from_path 3 asks)
  - Concern 6 (#15 status confirmation — still blocked or superseded?)
  - Concern 8's smallest unblocking subset: Q1 (Postgres-canonical) + Q7 (Fly) + Q10 (load-test). These three answers alone unlock breaking full-platform tracks A-P into Work rows.
  - Layer-3 design note's §5 Qs (5 Qs from `docs/design-notes/2026-04-19-universe-to-tinyassets-server-rename.md`).

**For navigator (this session):**
- No additional curation needed on concern 9 until Phase 5 lands.
- After Devin Session 2 outcome arrives, draft a user-chat intelligence report at `docs/audits/user-chat-intelligence/2026-04-19-devin-session-2.md` per the standing user-chat intelligence rule.

---

## What this triage does NOT do

- Does not modify STATUS.md Concerns directly. Per `feedback_status_md_host_managed.md`, host curates Concerns; navigator proposes only.
- Does not promote concerns to Work rows. That's a lead decision after host answers gate it.
- Does not estimate full-platform §11 Q answer effort (that's the host's load-bearing call, not navigator's to size).
