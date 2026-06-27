---
status: active
---

# Minimum-Viable-Launch Narrowing Proposal

**Date:** 2026-04-19
**Author:** navigator
**Status:** Proposal. Host reviews, picks, then becomes the launch spec.
**Relates to:** `docs/design-notes/2026-04-18-full-platform-architecture.md` §10 (full sequencing + dev-day estimates), `docs/audits/2026-04-19-design-note-vs-specs-coherence.md` (drift audit), 11 dev specs under `docs/specs/`.

---

## §1. Current scope + dev-day landscape

**Full scope** (every track fully specified + §24–§31 scenario folds, at dev's honest revised estimates):
- **~29.5–33.5 dev-days with two devs parallelizing, ~35–37 serial.** ~6.5 weeks at upper bound if two devs sustain ~5 dev-days/week net. This is the "build every promise the design note makes" number.

**MVP-narrowed §27 (host-review recommendation in §10)** = T1 chatbot-mediated authoring + T2-lite inline code-view + edit at MVP, full local REPL deferred to v1.1:
- **~27.5–31 dev-days w/2 devs, ~33–35 serial.** ~6 weeks at upper.

**Recommended cut in §10** (MVP-narrowed §27 + skip load-test S6 + keep §30 handoffs):
- **~26–29.5 dev-days w/2 devs.** ~5.5–6 weeks at upper.

**Floor-defer-all** (every documented defer lever pulled, staying within forever-rule):
- **~18–22 dev-days w/2 devs** (computed in §4 below).

This proposal recommends **one narrower cut around ~21–24 dev-days** that still passes the Q21 "everyone uses it every day" acceptance test — explained in §2–§4.

---

## §2. The Q21 "everyone uses it every day" acceptance test

Every proposed cut is evaluated against four concrete scenarios from host directives 2026-04-18 + 2026-04-19:

| # | Scenario (short form) | What it tests |
|---|---|---|
| **A** | `Workflow: payables` → CSV into Voyager + named PDFs | Invocation + attachment I/O + connector push |
| **B** | Vibe-code a max-super-nerd node via chatbot | §27 authoring surface, primitive-level access |
| **C1** | Told chatbot about job → autonomous scope-extension to company-wide distribution | Chatbot scope-extension from catalog + connector-push to org tools |
| **C4** | Book → top-10 fan-out → overnight → 10 alternative next-books | Parallel fan-out, top-N ranking, self-hosted-zero-fee execution |

**Ruling:** if a proposed cut breaks *any* of these four end-to-end, flag as **DO NOT CUT** at MVP. Cuts that preserve all four are safe.

**Additional non-negotiables from forever-rule + §22 succession + §24 product-soul + §25 always-up:**
- System must run 24/7 with bills paid (Q15 host-independent succession).
- Platform must not feel gimmicky/toy (Q21 Real-World-Effect Engine).
- Self-healing + public status dashboard (§25 Q20).
- Privacy-per-piece + concept/instance split (§17 Q2).
- Community-flagged moderation + host-plus-user-sim mod council (§8 Q10/Q17).
- Claude.ai connector-catalog listing (A-follow Q21-nav launch gate).

None of these are "scope" — all are launch-readiness gates. Any cut proposal that trims them is invalid.

---

## §3. Per-track cuttability analysis

For each track, three things: **required for MVP?** (Y/N/Partial), **minimum-viable slice** if partial, **what breaks** end-to-end if dropped.

| Track | MVP? | Minimum slice | What breaks if cut |
|---|---|---|---|
| **A — Schema + Auth** (2d) | **Y — full** | Full schema required; GitHub OAuth required. | Everything. Foundation. |
| **B — Web app** (4d) | **Partial — 2.5d MVP slice** | Landing + `/connect` + `/host` + `/contribute` + catalog browse (read-only). Defer: editor, presence, Realtime widgets. | Scenario A/B: tier-1 can still invoke via Claude.ai MCP; web-app editor isn't a hard path. Scenario C4: public leaderboard view defers. **OK to cut.** |
| **C — MCP gateway** (2d) | **Y — full** | All launch-tier tools from spec #27 §3.1 + `/feedback`, `/node_authoring.show_code`, `submit_request`, `discover_nodes`. Connectors routed through. | Scenarios A/B/C1/C4 all route through this. Cutting breaks everything tier-1 does. |
| **D — Daemon host / tray** (2d) | **Partial — 1.5d MVP slice** | Tray install + host_pool register + 1 visibility (self). Defer: network visibility, paid visibility UI polish, auto-mode toggle polish, earnings dashboard. | Scenario C4 self-hosted-zero-fee still works (just more manual). Tier-2 is narrower at launch but functional. |
| **E — Paid-market flow** (1d) | **Partial — 0.5d MVP slice** | Bid post + claim + settle ledger (off-chain only, no on-chain yet — defer wallet to v1.1). | Scenario A/B/C1: fine (don't need paid market). Scenario C4 "top-10 fan-out overnight on self-hosted daemon = free" still works because self-hosted = zero fee path. **Wallet + crypto defer is biggest MVP narrow.** |
| **F — Moderation MVP** (0.5d → 0.75d w/ backstop) | **Y — full** | Flag + triage queue + rate limits. Host + user-sim mod council. | Forever-rule: every surface needs moderation primitives. Even empty-launch needs flag button. |
| **G — GitHub export sync** (1d → 1.25d w/ diff batching) | **Partial — 0.5d MVP slice** | One-way export (Postgres → `TinyAssets-catalog/` YAML) hourly. Defer: PR-ingest path (users can read but not PR back until v1.1). | Scenario B: vibe-coded nodes still land in Postgres; export snapshot shows them later. Tier-3 can still clone repo + edit directly. **Minor user-facing narrow.** |
| **H — Cloudflare + DNS + deploy** (0.5d host) | **Y — full** | Required for launch. Host task, not dev. |
| **I — Content templates + daemon-brand copy** (0.5d) | **Y — full** | Landing copy, editor copy, "summon the daemon" voice. Must match Q21 serious-utility aesthetic. |
| **J — Load test harness** (3.5–4d per dev #26) | **Partial — 2d MVP slice** | S1-S5 (subscriber fan-out, bid storm, cascade read storm, heartbeat load, hot-node CAS). Skip S6 (cold-start end-to-end), S7 auto-healing rehearsal, S11 parallel fan-out storm. | Scenarios all pass unit/integration tests; load-test gaps mean launch-day discovers contention issues the hard way. Acceptable risk for a narrow MVP. |
| **K — Discovery + remix + convergence** (1–1.5d) | **Partial — 1d MVP slice** | pgvector HNSW + `discover_nodes` RPC + `remix_node` (from §15.3B). Defer: `converge_nodes` two-step flow + `subscribe_similar_in_progress` to v1.1. | Scenario B remix works. Scenario C3 cross-contributor convergence can't happen at launch — but convergence is valuable only when many contributors exist; launch-day doesn't have them yet. **Good defer.** |
| **L — Dual-layer content + per-piece privacy** (1d) | **Y — full** | `concept`/`instance_ref` split + `artifact_field_visibility` + concept-only Postgres role. Non-negotiable per §17 Q2 + Q24 structural training-exclusion. | Entire privacy promise. Cannot cut. |
| **M — Monetization + cold-start + license** (1d) | **Partial — 0.5d MVP slice** | `fulfillment_path` 4-path `submit_request` RPC + `content_license` column with CC0 default. Defer: Base Sepolia wallet-connect + on-chain settlement + multisig to v1.1 (M becomes v1.1 enablement). | Scenario A/B/C1 work — they don't need money to flow. Scenario C4 "free on self-host" works via settlement-mode `self_hosted_zero_fee` branch (already in §18.3 pseudocode). **1% fee stream accrues as ledger entries with `settlement_mode='batched'`, posted to chain at v1.1 mainnet cutover.** Host loses revenue until then; system works. |
| **N — Vibe-coding authoring sandbox** (2.5–4d full, 2d MVP-narrowed per §27.8) | **Partial — 2d MVP slice (T1 + T2-lite per B-follow)** | T1 chatbot-mediated `/node_authoring.*` + sandboxed Edge-Function draft runtime + `/show_code(view)` diff+full. Defer: T2 full local REPL, T3 native-code-PR polish. | **Scenario B is the MVP gate here.** Without T1 + T2-lite, "real nerds can actually edit the code" (B-follow) is broken at launch. T2 full-REPL defer is fine. |
| **Connectors baseline** (1.5d — new spec per audit) | **Y — minimum viable** | GitHub + Gmail + S3/Drive + webhook-generic. Notion defer-acceptable. | Scenario A requires connector push. Without minimum-viable connectors, A fails. Cut to 4-connector baseline (~1d). |
| **Handoffs** (1.5d — new spec per audit) | **Partial — 0.75d MVP slice** | arXiv + CrossRef DOI + GitHub Releases. Defer: ISBN, journal-specific, FDA. | Scenario C3 "cure cancer → peer-reviewed paper" needs DOI/arXiv for the verification-outcome side. **Keep minimum subset; most real-world impact value is in the 3 launch handoffs.** |

---

## §4. Recommended narrowest defensible MVP

**Dev-day total: ~21–24 dev-days with two devs, ~27 serial.** ~4.5 weeks at upper. Honors forever-rule + all four Q21 scenarios + all §22/§24/§25/§29/§31 launch gates.

**Launch-day feature matrix — what ships:**

| Feature | Ships at MVP? | Notes |
|---|---|---|
| Claude.ai MCP connector (self-discovery catalog listing) | Yes | A-follow launch gate; Q21-nav ops track |
| `Workflow: X` invocation with attachment I/O | Yes | Scenario A |
| `discover_nodes` RPC + top-N + semantic + structural match | Yes | Full §15.1 response block |
| Vibe-code a node via chatbot (T1 authoring + T2-lite inline code-view) | Yes | Scenario B, B-follow |
| `remix_node` (N-parent lineage) | Yes | Scenario B co-design |
| `converge_nodes` (two-step propose + ratify) | No — defer to v1.1 | Low utility at empty launch; adds 0.5d |
| Connector push — GitHub / Gmail / S3 / generic-webhook | Yes | Scenario A + C1 |
| Real-world handoff — arXiv / DOI / GitHub Releases | Yes | Scenario C3 verification pipeline |
| Parallel fan-out (top-N) | Yes | Scenario C4 |
| Self-hosted daemon = 0% fee | Yes | Scenario C4 overnight-free path |
| Paid-market bid + claim + settle | Yes (off-chain ledger) | On-chain defer to v1.1 |
| Wallet-connect + on-chain settlement + 1% fee to treasury | **No — defer to v1.1** | Ledger reservations accrue; host loses real-currency revenue until v1.1 |
| Multisig treasury (Sepolia-tested) | No — binds at real-currency cutover | Per §22.4 phase-split, not MVP gate |
| CC0 license metadata on export | Yes | §19 |
| Per-piece privacy: concept/instance + chatbot-judged field visibility | Yes | §17 Q2, non-cuttable |
| Privacy-principles catalog + `get_privacy_principles` tool | Yes | §31, non-cuttable per C-follow |
| Moderation: flag / admin queue / rate limits / host+user-sim council | Yes | §8 Q10 Q17, non-cuttable |
| Feedback channels A/B/C (GitHub + `/feedback` + Discord placeholder) | Yes | §23 Q18 |
| Auto-healing self-heal rehearsal (J-S7) | **Partial — defer S7 to v1.1** | Keep S1-S5 load-test; accept launch-day is the auto-heal test |
| Public status dashboard | Yes | §25 Q20, non-cuttable |
| GitHub catalog export (one-way) | Yes | §4 + §32 |
| Catalog PR-ingest path | No — defer to v1.1 | Read-only export at MVP |
| `SUCCESSION.md` runbook | Yes | §22 Q15, non-cuttable |
| Secret vault populated | Yes | §22 Q15, non-cuttable |
| Web app editor + presence + Realtime widgets | **Partial — catalog browse only** | Full editor defers; T1 authors via Claude.ai MCP |
| Moderation rubric in repo | Yes | §8 |
| T3 native-code node authoring PR flow | Partial — repo + CONTRIBUTING.md exist, `git clone + edit YAML` works; full native-code authoring surface defers | B-follow scope |

**Dev-day per track at recommended MVP:**

| Track | MVP dev-days | Notes |
|---|---|---|
| A | 2 | Full |
| B | 2.5 | Browse + onboarding only; editor deferred |
| C | 2 | Full gateway |
| D | 1.5 | Self-visibility tray; paid UI minimal |
| E | 0.5 | Off-chain ledger only |
| F | 0.75 | Full MVP moderation |
| G | 0.5 | One-way export; no PR-ingest |
| H | 0.5 host-day | Required |
| I | 0.5 | Full copy |
| J | 2 | S1-S5 only |
| K | 1 | Discovery + remix; converge defers |
| L | 1 | Full privacy |
| M | 0.5 | `fulfillment_path` + license column; no wallet/on-chain |
| N | 2 | T1 + T2-lite per B-follow |
| Connectors | 1 | 4-baseline |
| Handoffs | 0.75 | arXiv + DOI + GitHub Releases |
| **Total dev:** | **~18.5** |  |
| **Total w/ 2-dev parallelization overhead + variance:** | **~21–24 w/2 devs, ~27 serial** |  |

---

## §5. What we gain by going narrow

- **4.5 weeks to real users** (at upper bound) vs 6 weeks full-scope. ~1.5 weeks earlier = ~30% faster time-to-first-real-feedback.
- **Forever-rule preserved** — every surface works 24/7 as a complete system, just with fewer shipped features in the catalog, editor polish, and cryptocurrency surface.
- **Q21 "real-world effect engine" preserved** — scenarios A / B / C1 / C3 / C4 all work end-to-end at MVP. User can process invoices, vibe-code nodes, extend scope to distribute work, submit papers to arXiv, fan out 10 book variants overnight on their own daemon. The product feels like what was promised.
- **Q17 "user-sim is first user" preserved** — user-sim can dogfood every surface at launch; organic adoption grows from there.
- **v1.1 defer list is concrete** — wallet/on-chain settlement, converge proposals, editor polish, T2-full-REPL, PR-ingest, S6/S7/S11 load-test scenarios. Clear "what lands next" story.

---

## §6. What we risk by going narrow

Enumerated by scenario + known-deferral:

- **Scenario A (payables):** works end-to-end at MVP. No risk.
- **Scenario B (vibe-coded max-super-nerd node):** T1 + T2-lite covers "real nerds can edit the code." Full T2 local-REPL defer means tier-2 users with deep customization needs have a slightly awkward experience. **Accept.**
- **Scenario C1 (autonomous scope-extension):** connector-push to GitHub + Gmail + webhook generic covers the "push to rest of company" pattern for most orgs. Notion/Slack-specific pushes defer. **Small risk — 10–20% of orgs may want a connector we haven't shipped yet; webhook-generic is the fallback.**
- **Scenario C3 (cure cancer → published paper):** arXiv + DOI + GitHub Releases covers the aspirational handoff story. FDA + journal-specific APIs defer. **Acceptable — the "publish to arXiv" story carries the demo.**
- **Scenario C4 (top-10 fan-out overnight):** works end-to-end on self-hosted daemon (zero fee path ships at MVP). Paid-market fan-out also works off-chain (ledger entries accrue). On-chain posting defers. **Accept.**
- **Wallet / on-chain settlement defer:** platform-as-a-business takes no real revenue until v1.1. Settlements accrue as off-chain ledger entries; on mainnet cutover day, accrued balances post on-chain. Host loses ~0–6 weeks of real-currency revenue depending on launch→v1.1 gap. **Primary risk — host accepts or rejects this specifically.**
- **Editor defer:** web-app users browse-only at launch. They can invoke via Claude.ai chat; cannot visually edit a node outside chat. **Acceptable for a chatbot-first product posture.**
- **Converge defer:** single-user-authored nodes aren't combined at launch. Convergence value compounds with contributor count; launch-day has few contributors. **Low risk.**
- **Auto-heal S7 scenario defer in load-test:** launch-day auto-heal is untested. If a bad deploy happens week 1, real users see it. **Medium risk — recommend keeping S7 if host is risk-averse; 0.3d cost.**

---

## §7. Host decision asked

**One question:**

> **Accept the narrowed MVP at ~21–24 dev-days w/2 devs (~4.5 weeks upper), deferring wallet/on-chain settlement + convergence + web-app editor + T2-full-REPL + load-test S6/S7/S11 + PR-ingest + 2 connectors (Notion, Slack) to v1.1 — OR ship the fuller scope at ~27–32 dev-days (~6 weeks upper) with everything above included at launch?**

**Trade-off in one sentence:** narrower = ~1.5 weeks earlier to real-user feedback + loses on-chain revenue stream + editor polish until v1.1; fuller = all scenarios fully shipped from day one but ~30% longer dev time.

Navigator recommends **accept narrowed MVP** on the reasoning that user-sim-as-first-user (Q17) + forever-rule (all surfaces work 24/7) + Q21 scenarios-all-work is the correct product-correctness bar, and everything deferred is a v1.1-eligible feature that doesn't break a user's ability to get real work done.

---

## §8. What doesn't count as "post-launch" work

**These are LAUNCH GATES per forever-rule + §22 + §24 + §25 + §29 + §31. Not optional. Not deferrable.** The narrowed MVP includes all of them.

| Launch gate | Why non-negotiable |
|---|---|
| **§22 succession runbook current + secret vault populated** | Forever-rule Q15 — "if host dies tomorrow, system keeps running." `SUCCESSION.md` is the runbook a successor follows. |
| **§22 moderator council ≥2 operators in code path** | Launch-day-zero = host + user-sim per Q17; primitive must exist. |
| **§24 product-soul — serious-utility aesthetic, outcome-first copy** | Q21 fail-state = gimmicky/toy. Landing + editor + tray copy must lead with real deliverables. |
| **§25 public status dashboard + auto-deploy on green-CI** | Q20 "nothing is broken on return from vacation" — dashboard + auto-deploy are the visible-operability surface. |
| **§29 chatbot behavioral patterns (scope-extend + transparent privacy narration)** | Q21 scenarios C1 + C2 literally depend on these behaviors. |
| **§31 privacy-principles + data-leak-taxonomy catalog v1** | C-follow — chatbot consults catalog for every safety call. `get_privacy_principles` tool must return real entries. |
| **§17 dual-layer concept/instance_ref + concept-only Postgres role** | Q2 privacy-per-piece hard guarantee. No MVP without this. |
| **§16 CC0 license metadata + two-repo structure (`TinyAssets/` + `TinyAssets-catalog/`)** | Q5/Q7 fully-open license. Structural. |
| **§7 GitHub OAuth single-identity across all 3 tiers** | Q15 tier-migration feature depends on it; §22 succession depends on it. |
| **§26 Claude.ai connector catalog listing** | A-follow — primary onboarding path for tier-1 (95% of users). Q21-nav ops track. |
| **§23 feedback channels A/B/C in place + user-sim dogfooding loop** | Q18 — "real users won't notice a change" because user-sim ran loop first. |
| **§8 `flag_content` / `list_review_queue` / `resolve_flag` / `appeal_decision` primitives** | Q10 community-flagged moderation. |
| **Tier-1 zero-install + tier-2 one-click install + tier-3 clone works** | Three-tier capability matrix from Q-three-tiers. |

**Total forever-rule + launch-gate dev-day cost is already absorbed in the per-track MVP estimates above** — this section exists only to prevent future "can we also defer succession?" confusion. The answer is no.

---

**Recommendation: ship narrowed MVP (~21–24 dev-days w/2 devs).** Awaiting host decision on §7's single question.
