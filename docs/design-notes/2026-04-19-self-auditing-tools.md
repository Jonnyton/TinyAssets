---
status: active
status_detail: Task #88 partial impl landed (15c897a); ongoing surface expansion
---

# Self-Auditing Tools — A First-Class MCP Pattern for Trust-Critical Surfaces

**Date:** 2026-04-19
**Author:** navigator
**Status:** Design proposal — not implementation. Awaiting host approval to promote to a Track in the full-platform architecture decomposition.
**Origin:** Devin Asante LIVE Session 2 (`docs/audits/user-chat-intelligence/2026-04-19-devin-session-2.md` §3) surfaced this pattern empirically. The `get_status` MCP verb (commit `15c897a`, task #88) turned a tier-2 BOUNCE into a STRONG PASS by giving the chatbot **structured evidence + structured caveats** instead of opaque state.
**Companion:** `dry_inspect_node` / `preview_node_source` primitive scoped at §6 below.

---

## 1. Headline — what we're proposing

A typed, first-class MCP tool pattern: **self-auditing tools** that return structured evidence + structured caveats about a trust-critical platform behavior, on the explicit principle that the chatbot composes the trust narrative *on top of* the evidence — never in lieu of it.

The Devin Session 2 evidence is the reference implementation: `get_status` returned 5 verbatim config fields + 3 verbatim evidence caveats. The chatbot then said, truthfully, "the connector does not currently have a 'confidential routing' mode turned on; it's buildable, but it isn't on; here are the 4 things that need to be true." Devin moved from BOUNCE to engaged — not because the chatbot was more persuasive, but because the chatbot was more trustworthy by virtue of being **structurally unable to hide the truth**.

---

## 2. Why this matters — the load-bearing claim

Every trust-critical platform surface (privacy, routing, cost, moderation, scope) has the same shape: the user has to believe that something invisible-by-default is happening (or not happening) correctly. Three failure modes recur:

1. **Opaque tool returns vibes.** The tool returns "OK" / "success" / a status string the chatbot summarizes. User has no evidence; chatbot can be agreeable without being correct. *Anti-pattern. Dominant prior shape across the platform.*
2. **Honest-but-uninformative.** The chatbot is honest about uncertainty but has nothing concrete to point at. ("I can't verify that.") User has no path forward. *Devin Session 1 outcome.*
3. **Evidence + caveats + chatbot composition.** The tool exposes both the raw values *and* the limitations of those values. The chatbot has structured material to be trustworthy with. *Devin Session 2 outcome. The pattern this note proposes.*

The third shape is structurally trustworthy. The chatbot **cannot** rubber-stamp because the caveats are part of the tool's contract — the chatbot would have to actively suppress them to mislead, which would be visible to anyone reading the chat or auditing the tool's response. The trust property is enforced by *system-layer shape*, not by chatbot discipline.

This is the load-bearing claim: **we make the chatbot more trustworthy by changing the tools we hand it, not by training it to be more careful.**

---

## 3. Pattern anatomy

A self-auditing tool returns a structured payload with three parts:

```
{
  "evidence": { ...verbatim observed values... },
  "caveats": [ ...what each evidence field does and does NOT prove... ],
  "actionable_next_steps": [ ...optional: what would change the evidence... ]
}
```

**Evidence.** Raw observed values from the system. No editorialization. If the value is unknown, the field is literally `"unknown"` — never inferred, never rounded, never aggregated into a friendly string.

**Caveats.** A *separate* list — not interleaved with evidence — that says what each evidence field's limits are. Examples:
- "`activity_log_line_count=0` means no requests have been served since this session started; it does NOT mean the connector has never served a request before. Persistent state lives elsewhere."
- "`served_llm_type=any` means the connector accepts any LLM type at request time; it does NOT mean a confidential-routing policy is enforced."

**Actionable next steps (optional).** When the chatbot or user wants to change the evidence — "what would I have to do to make this say `local`?" — the tool can include the structured prerequisites.

**Shape discipline:** evidence + caveats live in *separate* keys. They never interleave. This is what makes the chatbot's narrative composition checkable: someone reviewing the chat can grep the tool response for `caveats` and confirm what was said matched the structured truth.

**Separation of concerns.** The tool exposes *observable system state*. The chatbot exposes *user-facing narrative*. Trust-critical statements are forced to be derivable from evidence — the chatbot can't claim something the tool didn't return.

---

## 4. The five successor surfaces

Devin Session 2 closed the trust gap on confidential-tier routing via `get_status`. The same pattern collapses five other in-flight trust gaps into the same primitive. For each, the table below maps which fields belong in `evidence` vs `caveats`. Per-surface MVP cost is small (~few hundred lines per tool), but the trust property compounds — a tier-2 / tier-3 user who learns "Workflow tools are the kind that include their own caveats" generalizes that trust across the rest of the surface.

### 4.1 `get_memory_scope_status`

**Trust gap closed:** Did this read hit the tier I expected? Was the private-universe ACL respected? Memory-scope architecture is `project_memory_scope_mental_model.md` — tiered (node/branch/goal/user/universe) with a no-cross-bleed contract.

| `evidence` | `caveats` |
|---|---|
| `active_tier` (the tier the request was scoped to) | "`active_tier` reflects the tier this read was scoped to; it does NOT prove other tiers were not consulted internally for fallback." |
| `acl_decisions` (last-N reads with their tier + ACL outcome) | "`acl_decisions` is rolling-window N=20; older decisions have aged out." |
| `tier_2_boundary_fired` (bool — did the Stage-2 assertion fire on this request?) | "`tier_2_boundary_fired=false` means the Stage-2 assertion did not block; it does NOT mean the request had no scope-crossing intent." |
| `private_universe_ids_in_scope` (which private universes the actor can read) | "Private universe membership is owner-set; there is no platform-side audit log of membership changes pre-Stage-2c." |

### 4.2 `get_routing_evidence`

**Trust gap closed:** Which provider actually answered my last call? Was it the cheap one or the expensive one? Provider-routing transparency is currently invisible.

| `evidence` | `caveats` |
|---|---|
| `last_n_calls` (provider, model_id, latency_ms, cost_usd, ts — N=10) | "`cost_usd` is per-provider-published rate; actual billing reconciliation may differ." |
| `current_router_policy` (the routing rule that fired for the most recent call) | "`current_router_policy` reflects the policy at request time; subsequent policy changes are not retroactive." |
| `provider_quotas` (per-provider remaining quota / cap) | "Quotas are platform-tracked; provider-side rate limits may apply additionally." |
| `fallback_chain` (ordered list of providers if primary fails) | "The fallback chain is configured at session start; runtime config changes take effect on the next request." |

### 4.3 `get_privacy_decisions`

**Trust gap closed:** What did the chatbot mark public vs private on my last few writes? Was the per-piece classifier's decision the one I expected? Per `project_privacy_per_piece_chatbot_judged.md`: visibility is dynamic, per-piece, chatbot-judged.

| `evidence` | `caveats` |
|---|---|
| `last_n_writes` (artifact_id, classifier_verdict, chatbot_rationale_excerpt, final_visibility — N=10) | "`chatbot_rationale_excerpt` is the chatbot's stated reason; the classifier verdict is the system-side label. Disagreement between them is recorded for audit." |
| `flagged_disagreements` (writes where chatbot and classifier disagreed) | "Disagreement flagging is heuristic; not all true disagreements are caught." |
| `currently_active_privacy_principles` (which principles the chatbot is currently applying) | "Principles are loaded from the platform's privacy spec at session start; changes mid-session require re-load." |

### 4.4 `get_autoresearch_evidence`

**Trust gap closed:** Did my 1000-run karpathy sweep actually use my paid budget cap? What nodes were tried? What was the best score? Per `project_node_autoresearch_optimization.md` and §32 of the full-platform note: autoresearch is day-one, not v1.1.

| `evidence` | `caveats` |
|---|---|
| `runs_completed` (count + run_ids) | "`runs_completed` reflects runs that finished and posted scores; in-flight runs are not counted." |
| `budget_consumed_usd` + `budget_remaining_usd` | "Budget reconciliation is per-completed-run; in-flight runs hold provisional reservations not reflected here." |
| `top_n_results` (sorted by score, with config + score + cost per result) | "`score` is the metric value at run completion; downstream re-evaluation may yield different scores." |
| `incomplete_or_failed_runs` (list with reason) | "Failure attribution is best-effort; transient provider errors may be classified as the wrong cause." |

### 4.5 `get_moderation_audit`

**Trust gap closed:** When my content got flagged, what evidence is on record? What did the rubric say? What's the status of my appeal? Per Q10-host resolution (community-flagged moderation) in §11 of full-platform note.

| `evidence` | `caveats` |
|---|---|
| `flag_history` (per-artifact: flagger_id_anon, ts, rubric_clause_cited) | "`flagger_id_anon` is one-way-hashed; cross-flag correlation is not exposed to anyone but admin." |
| `rubric_verdicts` (per-flag: verdict, reviewer_id_anon, rationale_excerpt) | "Rubric application is per-volunteer; calibration drift between volunteers is acknowledged but not auto-corrected." |
| `appeal_status` (open / decided / final) | "Appeals follow the §22 SUCCESSION runbook; decided appeals can be re-opened only by host admin." |
| `current_rubric_version` (semver of the rubric at flag time) | "Rubric is PR-editable; the version pinned at flag time is what was applied — newer rubric language does not retroactively re-judge." |

---

## 5. Open questions for the host

1. **Pattern promotion: Track Q in full-platform decomposition, or P-extension?** This pattern is comparable in unblock value to the §11 high-leverage Qs (Postgres-canonical, load-test, Fly). Two options:
   - **(a) Track Q (new top-level track).** Self-auditing tools become a 6-7 dev-day discrete track delivering all 5 instantiations as MVP.
   - **(b) P-extension.** Fold into Track P (evaluation-layers unification) since both are observability-shaped.
   - **Recommendation: (a).** Self-auditing tools serve trust (user-facing); evaluation-layers serve quality (system-facing). Different consumers, different motivations, different MVP scopes. Mixing them confuses both.

2. **Implementation order across the 5 surfaces — by trust-blast-radius or by impl ease?** Three plausible orderings:
   - **(a) Trust-blast-radius:** privacy → memory-scope → routing → moderation → autoresearch. Highest-stakes user trust first.
   - **(b) Impl ease:** routing → memory-scope → privacy → autoresearch → moderation. Easiest-first to validate the pattern shape; complex ones last.
   - **(c) User-tier sequencing:** routing (tier-2) → memory-scope (tier-1+2) → privacy (tier-1+2) → autoresearch (tier-1+2) → moderation (tier-1). Match the tier rollout cadence.
   - **Recommendation: (b).** The pattern is novel enough that getting the *first* one right matters more than tackling the highest-stakes surface first. `get_status` already proved out the shape for routing; extending to memory-scope is the smallest delta.

3. **Caveat authoring: hand-written, derived, or both?** Caveats are the load-bearing element of the pattern — bad caveats turn the trust property into theater.
   - **(a) Hand-written per surface.** Highest quality; highest authoring cost; drift risk over time.
   - **(b) Derived from a typed schema.** Each evidence field has a `caveat: str` annotation; the tool surface emits them. Lower drift; more rigid.
   - **(c) Hybrid.** Derived as a baseline; hand-written overrides for surface-specific nuance.
   - **Recommendation: (c).** Get the structural property from (b); preserve narrative quality where it matters via (a). Draft the schema in `tinyassets/protocols.py` if greenlit.

4. **Dry-inspect pairing — separate task or bundled?** §6 below scopes `dry_inspect_node`. Should it ship under the same Track Q, or as a follow-on?
   - **(a) Bundled into Track Q.** Self-auditing covers current state + prospective behavior in one pattern delivery. Cleaner story for users.
   - **(b) Separate follow-on.** Dry-inspect is a different MCP verb shape; bundling adds scope to a track that needs to ship before §11 host-Q answers settle.
   - **Recommendation: (a).** They're the same trust funnel; shipping one without the other leaves a gap exactly where Devin's Session 2 succeeded (he engaged with both `get_status` evidence + the offered dry-inspect node source).

5. **Audit-log retention for evidence fields.** `last_n_calls` / `last_n_writes` etc. need a retention policy.
   - **(a) Rolling window N=20 in-memory.** Cheap, no DB cost, lost on restart.
   - **(b) Persisted with TTL (e.g., 7 days).** DB cost; survives restart; supports retroactive audit.
   - **(c) Persisted indefinitely with user opt-out.** Highest trust; highest privacy footprint.
   - **Recommendation: (b).** 7-day TTL balances the trust property against the privacy footprint. Tier-2 users who care can opt into longer; tier-1 users get the default.

---

## 6. The companion primitive — `dry_inspect_node`

Devin Session 2 surfaced a second pattern that pairs with self-auditing tools: **dry-inspect-before-write**. Where self-auditing tools expose *current state*, dry-inspect exposes *prospective behavior* — what would happen if the chatbot did the thing the user is about to ask for, without the thing actually happening.

**Reference shape:**
```
dry_inspect_node(node_spec) -> {
  "source_code_excerpt": "...",        // what would run, verbatim
  "external_calls": [...],              // every external endpoint it would touch
  "audit_evidence_emitted": [...],      // what self-auditing tools would record
  "side_effects_predicted": [...],      // writes, network, file IO
  "caveats": [...]                      // limits of the prediction
}
```

**Why this is the trust-funnel companion to self-auditing.** Self-auditing answers "what just happened?" Dry-inspect answers "what would happen?" Together they form the full trust loop: the user previews behavior, takes the action, and verifies the prediction matched the audit evidence. Devin Session 2 deployed this loop manually (chatbot offered to show node source + said `get_status` would be the audit primitive after the run); making it a typed pattern hardens the loop.

**Scope:** ~1 dev-day for the MVP shape. Works on any node type; the prediction quality is best-effort for first cut and improves as the platform learns the shape of common nodes.

**Dependency:** depends on the `protocols.py` typed schema work in §5 Q3 if (b) or (c) is picked — otherwise standalone.

---

## 7. The contrast — what we're moving away from

The "opaque tool returns vibes" anti-pattern is the dominant shape today across most MCP surfaces. Examples (not a criticism — just before/after):

- **Before:** `submit_request(payload)` returns `{"status": "ok", "request_id": "..."}`. The chatbot says "I've submitted your request." User has zero evidence about what tier it routed to, what budget it'll consume, when it'll fire, who'll see the output.
- **After (with self-auditing):** Same `submit_request` returns the request_id; the user can then call `get_status` (or the appropriate self-auditing tool for the surface) and see the routing decision, the budget reservation, the visibility tier, the predicted execution timeline. The chatbot composes "I've submitted your request — it's tier-3, will fire in ~45 min when the cascade is idle, and outputs to your private space" *from* the evidence, *with* the caveats.

The pattern is not "every tool becomes self-auditing." It's "every *trust-critical* tool gets a self-auditing companion." Read tools, search tools, ingestion tools — those don't need it. Anything that touches privacy, cost, routing, scope, or moderation does.

---

## 8. What this note does NOT decide

- The exact JSON schema for the `evidence` / `caveats` payload — leave to implementation.
- Whether self-auditing tools share a base class / Pydantic model — implementation detail.
- Performance characteristics of `last_n_*` evidence emission — measure during MVP, optimize if needed.
- Internationalization of `caveats` strings — out of scope for MVP; defer to multilingual rollout (§13 / Q13 of full-platform note).

These come back after host §5 answers.

---

## 9. Cost summary

| Item | Effort |
|---|---|
| `get_status` (already shipped via `15c897a`, task #88) | Done. |
| Pattern schema in `tinyassets/protocols.py` (if Q3 picks (b) or (c)) | ~0.5 dev-day |
| `get_memory_scope_status` MVP | ~1 dev-day |
| `get_routing_evidence` MVP | ~1 dev-day |
| `get_privacy_decisions` MVP | ~1 dev-day |
| `get_autoresearch_evidence` MVP | ~1.5 dev-days (depends on §32 autoresearch landing) |
| `get_moderation_audit` MVP | ~1 dev-day (depends on Q10-host moderation landing) |
| `dry_inspect_node` MVP | ~1 dev-day |
| **Track Q total (excluding `get_status` already-shipped)** | **~7 dev-days** |
| Audit-log retention storage (Q5) | additional ~0.5 dev-day if (b) or (c) picked |

Roughly comparable to Track P (evaluation-layers unification, ~7-8 dev-days). Both serve different consumers and should ship independently if both pass §5 host triage.

---

## 10. The 6th surface — `get_recent_events` (added 2026-04-19, post-Mission 26)

**Status:** SHIPPED via `acfeeeb` (`universe_server: get_recent_events action for tagged log observability`).
**Origin:** Mission 26 #B5 found that concern 1 (Sporemarch dispatch-guard retention) was *chatbot-unverifiable* because no MCP surface exposed dispatch-guard log lines. Same chain-break shape as Devin's LIVE-F8 (pitch-vs-product gap closed by `get_status`). Pattern recognized in `docs/audits/user-chat-intelligence/2026-04-19-mission26-sporemarch-echoes.md` §3 + promoted to host-Q digest v3 as **Q-sat-6**.

### 10.1 Why this is a self-auditing-tools instantiation

The implementation at `tinyassets/universe_server.py:3453-3500+` follows the §3 pattern precisely:

```
{
  "universe_id": <str>,
  "events": [...structured entries with ts/tag/message/raw, most recent first...],
  "source": "activity.log",
  "tag_filter": <str>,
  "caveats": [...strings explaining observation limits...]
}
```

- **Evidence** (`events`): verbatim structured entries from `activity.log` tail.
- **Caveats** (`caveats`): explicit limits — e.g. *"No activity.log found. The daemon may not have run yet in this universe, or the log was cleared."*
- **Tag-prefix filtering** (`tag` parameter): supports caller queries like `tag="dispatch"` matching both `dispatch_guard` and `dispatch_execution`. Compositional with §3's separation of concerns: system exposes raw evidence + observation limits; chatbot composes the trust narrative on top.

### 10.2 The 6 surfaces, updated

§4 of this note enumerated 5 surfaces. Adding the dispatch surface makes 6:

1. `get_memory_scope_status` (§4.1) — memory tier + ACL evidence.
2. `get_routing_evidence` (§4.2) — provider + model + cost per call.
3. `get_privacy_decisions` (§4.3) — per-write classifier verdict + chatbot rationale.
4. `get_autoresearch_evidence` (§4.4) — runs + budget + top-N results.
5. `get_moderation_audit` (§4.5) — flag history + rubric verdicts + appeal status.
6. **`get_recent_events` (§10) — `activity.log` tail with tag-prefix filtering. SHIPPED 2026-04-19.** *Universal observability surface — generalizes beyond a single domain (dispatch); same primitive serves any tag-emitting subsystem.*

### 10.3 Cross-link to Mission 26 + concern resolution chain

Pre-#B5: concern 1 (Sporemarch dispatch-guard retention) was chatbot-unverifiable. Mission 26 Probe A returned CANNOT-VERIFY-VIA-CHATBOT.

Post-shipment of `get_recent_events`: chatbot can now query `get_recent_events(tag="dispatch_guard")` to retrieve dispatch-guard events directly. Concern 1 transforms from "chatbot-unverifiable" to "chatbot-verifiable; daemon needs to actively run for events to accumulate."

This is the same closure shape that `get_status` produced for Devin LIVE-F8. **The pattern is now empirically validated by closure of two distinct chain-break instances** (LIVE-F8 → `get_status`; #B5 → `get_recent_events`). The 6 surfaces in §10.2 above are not aspirational — they're a typed family of fixes for a recurring chain-break shape.

### 10.4 Implication for the remaining 5 surfaces

The empirical validation (×2) elevates the recommendation in §5 Q1 — **Track Q standalone, not P-extension** — from "navigator's preference" to "evidence-backed pattern." The remaining 5 surfaces should ship under the same shape:

```python
{
  "evidence": { ...verbatim observed values... },
  "caveats": [ ...limits + uncertainty markers... ],
  # optional:
  "actionable_next_steps": [ ...what would change the evidence... ]
}
```

Every Track Q sub-task that adds a new surface should reference this canonical shape + the §10 implementation precedent. Pattern-ratification means dev doesn't need to re-derive the structure for each surface — it lifts directly from `_action_get_recent_events`.

### 10.5 What the 6th surface does NOT mean

- It does NOT mean the per-surface design work is done. The other 5 surfaces still need their own field maps (per §4 enumerations) and per-surface caveats authored. `get_recent_events` is a generic log surface; the others are typed-domain surfaces with surface-specific evidence.
- It does NOT mean the dispatch-guard concern (concern 1) is fully resolved. The chatbot can now *see* dispatch events; whether the dispatch-guard *actually retained* its multi-scene-overshoot defense across cycles still requires user-sim mission verification.
- It does NOT supersede `dry_inspect_node` (§6). Dry-inspect is the prospective-behavior companion; `get_recent_events` is current-state evidence. Both are needed for the full trust loop.

### 10.6 Cost-summary update

§9 cost summary updated:

| Item | Effort | Status |
|---|---|---|
| `get_status` (15c897a, task #88) | Done | SHIPPED 2026-04-19 |
| **`get_recent_events` (acfeeeb, task #50 / #B5)** | **Done** | **SHIPPED 2026-04-19** |
| Pattern schema in `tinyassets/protocols.py` | ~0.5 dev-day | Pending Q3 |
| `get_memory_scope_status` MVP | ~1 dev-day | Pending Q5 |
| `get_routing_evidence` MVP | ~1 dev-day | Pending Q5 |
| `get_privacy_decisions` MVP | ~1 dev-day | Pending Q5 |
| `get_autoresearch_evidence` MVP | ~1.5 dev-days | Pending Q5 + §32 |
| `get_moderation_audit` MVP | ~1 dev-day | Pending Q5 + Q10-host |
| `dry_inspect_node` MVP | ~1 dev-day | Pending Q5 (Q8) |
| **Track Q remaining (excluding shipped)** | **~6 dev-days** | (was ~7 pre-`get_recent_events`) |

Track Q remaining work ~6 dev-days — slightly less than originally scoped because `get_recent_events` opportunistically landed during the dispatch-guard concern resolution.

### 10.7 Pattern reuse note for future Track Q sub-tasks

When dev picks up the next Track Q surface (per Q6 impl-ease recommendation, that's `get_memory_scope_status`), the implementation pattern is:

1. Read `_action_get_recent_events` at `tinyassets/universe_server.py:3453` for the canonical shape.
2. Define the per-surface evidence dict matching §4's field map for the chosen surface.
3. Author surface-specific caveats (per §5 Q3 hybrid recommendation: derive a baseline from a typed schema + hand-write surface-specific overrides).
4. Add the action to the dispatcher routing in `tinyassets/universe_server.py` action table.
5. Add tests modeled on whatever covers `_action_get_recent_events`.

No architectural questions to re-answer per surface — pattern is now stable.

---

## 11. Foundation/Feature classification (added 2026-04-19 post host's clarified rule)

Per host's "Foundation End-State vs Feature Iteration" rule (CLAUDE_LEAD_OPS.md, `557b051` refined): **Track Q decomposes into a foundation layer + a feature layer**, not as a single monolith.

### 11.1 Foundation layer — the pattern itself

**The self-auditing-tools shape (evidence + caveats + chatbot composes narrative) is FOUNDATION.** The next surface depends on it being its final shape.

Specifically foundation:
- The `{evidence: {...}, caveats: [...], actionable_next_steps: [...]}` payload shape (§3 pattern anatomy).
- The separation-of-concerns invariant: tools expose observable state, chatbot composes narrative, evidence + caveats are separate keys (never interleaved).
- The two SHIPPED implementations (`get_status` at `15c897a` + `get_recent_events` at `acfeeeb`) — these are the canonical reference shapes future surfaces lift from.
- The optional pattern schema in `tinyassets/protocols.py` (per §5 Q3 hybrid recommendation) — once established, every surface inherits from it.

**Why foundation:** every future Track Q surface depends on this shape being stable. Two shipped instances (`get_status` + `get_recent_events`) prove the shape works; further iteration would be debt-creating, not signal-driven.

**End-state-now status:** the pattern shape has been validated by ×2 closure of distinct chain-break instances (LIVE-F8 + #B5). No further pattern iteration needed; lock and lift from here.

### 11.2 Feature layer — per-surface schemas + caveats authoring

**The specific evidence-schema + caveats authored per surface is FEATURE.** Iterates with real chatbot-usage signal.

Specifically feature:
- Per-surface evidence-field maps (§4.1-§4.5 — memory-scope, routing, privacy, autoresearch, moderation). The *shape* is foundation (§11.1); the *fields chosen* per surface iterate.
- Per-surface caveat text — specific phrasings that prove well-calibrated for trust-narrative composition. Iterate per chatbot's actual usage in live missions.
- Cross-surface conventions (e.g., is there a standard "no data" caveat phrasing that works across all surfaces, or surface-specific?) — discover with use, don't pre-design.
- Audit-log retention TTL (Q9 default 7-day) — iterates if tier-2 friction surfaces.

**Why feature:** §4 enumerated 5 successor surfaces. The exact field map per surface is a best-guess today; chatbot's actual queries against `get_status` + `get_recent_events` will inform what fields the next surfaces need. Wrong-schema-cost is low (alter table + add field, not schema migration); right-schema-from-iteration-cost is high (signal-derived calibration).

**Iteration-OK status:** ship surface 1 (recommend `get_memory_scope_status` per Q6 impl-ease), gather chatbot-usage signal, iterate the field map for surface 2 based on what surface 1 taught us, etc.

### 11.3 Implication for Track Q dispatch

Re-reads §5's Q5 + §9 cost summary through the new lens:

- **Q5 was framed as "Track Q standalone or P-extension?"** Recommendation (a) Track Q standalone STILL holds. But the new framing: **Track Q's foundation layer ships once + locks (already done — ×2 instances); Track Q's feature layer ships per-surface as iteration.** No "Track Q complete" milestone — pattern adds surfaces opportunistically.
- **Q6 was framed as "implementation order across the 5 surfaces."** Recommendation (b) impl-ease STILL holds. With foundation locked, ordering is purely per-surface chatbot-leverage; iterate.
- **§9 cost summary (~6 dev-days remaining) is now interpretable as ~6 dev-days *across 5 features that ship one-at-a-time*, not as one ~6-day milestone.** Each surface adds ~1-1.5 dev-days when it ships.

This re-classification reduces Track Q's perceived cost from "monolithic 6-day Track Q" to "5 independently-shippable feature surfaces, ~1-1.5 days each, ship as chatbot signal demands." Significantly more flexible for prioritization against daemon-economy work (which is foundation and ships first per "Daemon Economy is Foundation" rule).

### 11.4 Pattern reuse, refined

The §10.7 pattern reuse note holds, with one addition: **Foundation parts inherit unchanged. Feature parts adapt per chatbot signal.**

When dev picks up the next surface:
1. *Foundation:* lift from `_action_get_recent_events` shape — payload structure, separation-of-concerns, evidence+caveats keys. **Do not re-derive.**
2. *Feature:* author per-surface evidence + caveats fresh, informed by what user-sim missions have surfaced about that surface's chatbot-leverage gaps. **Iterate freely.**

If chatbot signal indicates the foundation shape itself needs revision (unlikely after 2 shipped instances + 2 chain-break closures), revisit §3. Otherwise: foundation stable, feature iterating.
