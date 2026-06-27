# Host-Q Digest v4 — DRAFT (full-platform §11 residual sweep)

**Date:** 2026-04-19
**Author:** navigator
**Status:** Pre-draft. Hold until v3 ratifies. Then promote to `docs/ops/2026-04-19-host-q-digest.md` (replacing v3).
**Diff intent vs v3:** Sweeps the §11 residual — every full-platform §11 question that wasn't covered by v2/v3's curated subset (Q1/Q2/Q3 in v3 = §11 Q1/Q10/Q7 specifically). Same pre-answering working rule: navigator reasons through, lead ratifies HIGH-confidence, only INTENT-ONLY surface to host.
**Authority:** Per host-issued directive 2026-04-19, navigator pre-answers; lead ratifies HIGH; INTENT-ONLY surface to host. v3 demonstrated the pattern (12 of 13 ratify-by-lead, 1 INTENT-ONLY). v4 applies same discipline to ~19 residual Qs.

---

## Framing

Full-platform §11 has 24 Q-shaped entries. Of those:
- **12 already RESOLVED in note** (Q16, Q4-followup, Q10-host through Q21-host — each marked RESOLVED inline).
- **3 covered by v3** (Q1 Postgres, Q7 Fly, Q10 load-test).
- **1 explicitly DEFERRED** in note (Q15-depth — re-opens at maturity).
- **8 §11 main-list Qs unaddressed** by v3: Q2, Q3, Q4, Q5, Q6, Q8, Q9, Q11, Q12, Q13, Q14.
- **7 nav-flagged Qs** explicitly open: Q18-nav through Q24-nav.

This sweep covers the 8 + 7 = 15 unaddressed entries (Q15-depth left DEFERRED per host's earlier explicit framing).

---

## Pre-answered recommendations — §11 residual

Same self-audit method as v3: cross-check each recommendation against host signal in (a) memory, (b) STATUS.md, (c) recent host messages, (d) PLAN.md. HIGH if no contradiction + technical/derivable. INTENT-ONLY if irreducible host taste/pace/priority. MEDIUM if no contradiction but recommendation has weaker evidentiary anchor.

| Q | Pre-answer | Confidence | Rationale + host-signal cross-check |
|---|---|---|---|
| **§11 Q2 — Supabase as the stack** | **Yes (recommended in note)** | HIGH | Directly downstream of v3 Q1 (Postgres-canonical). Note's §3.2 vendor scorecard ranks Supabase strongest on every axis except "ultimate control"; Postgres is portable (lift-and-shift to self-hosted preserves no-lock-in property). Convex/Firebase have lock-in problems. Self-hosted Hetzner cheaper at 100k DAU but ops-heavier now. No host signal favoring alternatives. |
| **§11 Q3 — Realtime = versioned rows + broadcast + presence (not CRDT)** | **Yes (recommended in note)** | HIGH | Per note's §2.2: this is the "not Notion-style live shared-prose editing" call. TinyAssets doesn't have an artifact type that needs character-by-character collaboration today. CRDT is large eng investment (Yjs) for a use case that doesn't exist. Recommendation = "ship the simple thing that works for the actual use case." Reversible if a needs-CRDT artifact type emerges. |
| **§11 Q4 — GitHub OAuth at launch** | **Yes (recommended in note)** | HIGH | Per note's §7: matches the user base (developers comfortable with GitHub OAuth). Host memory `project_collab_model_split.md` ("TinyAssets content = wiki-open via chatbot... Platform code = GitHub fork-and-PR") aligns — GitHub is already the contributor surface. Native-accounts added when non-developer sign-up bounces ≥15%. |
| **§11 Q5 — Moderation day-one is manual** | **Yes (recommended in note)** | HIGH | Per note's §8 + Q10-host RESOLVED (community-flagged moderation, volunteer-mod review against rubric). Manual day-one is consistent. Automated classification deferred until volume forces it — no host signal contradicts. |
| **§11 Q6 — Self-only daemon hosting is install default** | **Yes (recommended in note)** | HIGH | Per note's §5.4 + host memory `project_daemon_default_behavior.md` (host-needs-first cascade; opt-in for `network` / `paid`). Opt-in matches the conservative-by-default privacy posture. Tray toggles surface visibility opt-ins. |
| **§11 Q8 — Distribution horizon confirmation (~26-29.5 dev-days, MVP-narrowed §27 + skip S6 + keep §30)** | **Confirm recommended estimate** | INTENT-ONLY | Distribution horizon framing IS a host-pace question — host owns "weeks not months" intent. Note has 7+ levers (full §27 vs MVP-narrowed, defer §30 handoffs, defer real-world badges, skip S6 or S11, defer wallet, defer per-field privacy, defer diff-view). The recommendation reflects nav's read but the *which-cuts-acceptable* call is host taste. **SURFACE TO HOST.** |
| **§11 Q9 — Cascade step-3 ranking: daemon-judged or control-plane-suggested default** | **(a) fully daemon-judged** | HIGH | Matches host memory `project_daemon_default_behavior.md` ("daemon decides cascade behavior") + note's explicit "anything else it thought" latitude framing. (b) suggested-default could come later as additive without breaking (a)-style daemons. |
| **§11 Q11 — Minimum signal set for discover_nodes** | **(a) ship full block** | HIGH | Host memory `project_full_platform_target.md` ("design the final system, no phased rollout") + note's "build the final target, no phases" discipline. Cost delta vs minimal subset is small (~0.5d) against avoiding v2 schema migration. No host signal favors phased shipping. |
| **§11 Q12 — Cross-domain recommendations on by default** | **(a) on** | HIGH | Host memory `project_convergent_design_commons.md` ("TinyAssets design is Wikipedia-scale public collaborative effort... convergence tools are first-class, not edge-case"). Cross-domain surfacing IS where convergence compounds (structural patterns repeat across domains). Default-off loses the emergent-pattern property. |
| **§11 Q13 — Per-piece granularity: per-field as backbone or per-step coarser** | **(a) per-field as backbone** | HIGH | Host memory `project_privacy_per_piece_chatbot_judged.md` ("visibility is dynamic, per-piece, chatbot-judged") explicitly endorses the finest-grain shape. Per-step-only would force a v2 schema migration (per note's risk analysis) — explicit cost of phased shipping. |
| **§11 Q14 — Training-data exclusion: separate Postgres role or trust-tagging** | **(a) separate role** | HIGH | Host memory `project_privacy_per_piece_chatbot_judged.md` + Q14-host RESOLVED (multilingual permissionless) + the "not training data, not collected, not at risk" promise being load-bearing. (b) trust-tagging = silent-leak failure mode; (a) = permission-error failure mode. Hard Rule 8 ("fail loudly") applies. |
| **Q15-depth (governance above multisig)** | **DEFERRED (note already resolves)** | n/a | Already explicitly DEFERRED in note. Re-opens at TVL/community-scale trigger. No action this sweep. |
| **§11 Q18-nav — Node-primitive authoring API: (a) Python sandboxed / (b) WASM / (c) JSON-schema IR** | **(a) Python sandboxed** | MEDIUM | Recommendation (a) matches platform Python toolchain + Scenario B's "full primitive" directive + note's nav-recommended option. Sandbox engineering cost absorbed by §27.8. **Why MEDIUM not HIGH:** the security-vs-expressiveness tradeoff has a nontrivial host-taste component — a host who weights security ceiling > expressiveness might prefer (c). Lead can ratify (a) as the engineering call; flag-back if host prefers caps over capability. |
| **§11 Q19-nav — §27 MVP scope (T1 + T2-lite per B-follow)** | **REVISED (note already revises) — T1 + T2-lite** | n/a | Note explicitly REVISED 2026-04-19 per B-follow ("real nerds can edit code at day one, not v1.1"). Adds ~1d back to track N; full local REPL still defers to v1.1. Already lead-ratified-implicitly via the B-follow. No action. |
| **§11 Q20-nav — Launch connectors confirm (GitHub, Gmail/SMTP, Drive, Notion)** | **Confirm recommended set** | HIGH | Note's tier-1 launch connectors are the universal-coverage minimum (auth + email + storage + docs). No host signal contradicts. Voyager + vertical-specific tools are community-contributed post-launch (per note + scenario directives). Verticals can't be picked exhaustively pre-launch anyway. |
| **§11 Q21-nav — Claude.ai connector catalog listing** | **Navigator investigates in parallel** | INTENT-ONLY | Per note: "actionable asks" include submission process, timeline, requirements. **The "who owns this research" question IS a host call** — could be host (ops-style task), navigator (parallel research), or dev (with ops sub-task). Recommendation: **navigator picks it up as the primary research task** if host doesn't claim it. **SURFACE TO HOST** to confirm assignment. (My nav-time is currently the cheapest-marginal-cost surface.) |
| **§11 Q22-nav — Diff view in `/node_authoring.show_code` at MVP or v1.1** | **Include diff view at MVP** | HIGH | Note's recommendation; ~0.25d adds. Without diff view, co-design iteration quality drops significantly. Same logic as Q11 — small cost, large quality impact, no host signal contradicts. |
| **§11 Q23-nav — Privacy-principles catalog launch scope** | **Authorize navigator to draft v1 catalog (~12 entries per §31.3)** | HIGH | Recommendation per note. Navigator already has the §31.3 list as scaffolding; the v1 draft is mechanical work + light judgment. Doesn't require host taste; scope is constrained to load-bearing system points. Lead can ratify and authorize. |
| **§11 Q24-nav — Three execution specs (Track N + Connectors + Handoffs) not yet drafted** | **Dispatch all three to dev as pre-draft spec tasks** | HIGH | Recommendation per note. All three are identified as MVP blockers; all three already have estimates absorbed in §10 (~2d / ~1.5d / ~1.5d). Same shape as existing track K/L/M specs. Mechanical dev work; no architectural ambiguity remaining. **Lead can dispatch immediately as 3 parallel dev tasks once R7 storage split lands** (so spec authors aren't writing against an in-flight module). |

---

## Self-audit summary (v4)

- **HIGH (13 of 15):** §11 Q2, Q3, Q4, Q5, Q6, Q9, Q11, Q12, Q13, Q14, Q20-nav, Q22-nav, Q23-nav, Q24-nav. Lead ratifies all without further host check.
- **MEDIUM (1):** §11 Q18-nav (Python sandboxed). Default to (a); flag-back if host prefers caps over capability.
- **INTENT-ONLY (2):** §11 Q8 (distribution horizon levers — host-pace call), §11 Q21-nav (connector-catalog research ownership — host-resourcing call).
- **DEFERRED (2):** Q15-depth, Q19-nav (already resolved/revised in note).

**Effective host load from v4:** 2 questions instead of 15. Combined with v3's 1 INTENT-ONLY (Q-priv-1), **total host load across both digests = 3 questions.** From a starting surface of 13 + 15 = 28 raw Q-shaped entries.

---

## Cheat sheet for fastest unblock (v4 standalone)

| If host has time for... | Answer | Unlocks |
|---|---|---|
| **30 seconds** | Q8 (distribution horizon) only | Confirms which dev-day cuts are acceptable; unlocks final scope cut for MVP. |
| **2 minutes** | Q8 + Q21-nav | Above + assigns connector-catalog research owner (likely navigator). |
| **3 minutes** | Q8 + Q21-nav + Q18-nav | Above + ratifies Python-sandboxed authoring API (or amends to WASM/JSON-IR). |

---

## Combined unblock cheat-sheet (v3 + v4)

| If host has time for... | Answer | Effect |
|---|---|---|
| **3 minutes** | v3 Q-priv-1 + v4 Q8 + v4 Q21-nav | All INTENT-ONLY across both digests resolved. Lead can ratify everything else (HIGH + MEDIUM) and dispatch the entire MVP queue. |

**Recommend the 3-minute combined path.** Total host time investment: 3 minutes. Total unlocked: refactor execution sequence + MVP track decomposition (~24-29 dev-days) + Track Q (~7 dev-days) + layer-3 rename (~3-4 dev-days) + privacy work + node-authoring + connectors + handoffs + connector-catalog research initiated.

---

## What this v4 draft does NOT decide

- Whether v4 promotes immediately or batches with v3. (Lead decides at promotion time. Recommend single combined v3+v4 promotion since both have the same "ratify HIGH + escalate INTENT-ONLY" shape.)
- The handful of items the host will actually write back about. (That's the single-message-back the digest is designed to elicit.)
- Whether to extend the pre-answering pattern into other host-decision surfaces (privacy spec §6 Qs, add_canon §5 Qs — both already covered in v3). The pattern is documented; future digest revisions can apply it without re-deriving.
