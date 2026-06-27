# Pitch-vs-Product Alignment Audit

**Date:** 2026-04-19
**Author:** dev (task #90 / T-8 per navigator Devin-session1 intelligence report §3.2)
**Scope:** every user-facing promise on `prototype/web-app-v0` + MCP-tool user-facing copy + `CONTRIBUTING.md` tier-3 pitch.
**Source of truth for MVP boundary:** `docs/design-notes/2026-04-19-minimum-viable-launch-narrowing.md` §4 (launch-day feature matrix — ~21-24 dev-day MVP).

---

## 1. Why this audit exists

Devin bounced at live exchange 4 because the platform's confidential-tier pitch (from the `/host` page + MCP tool surface) made promises the product couldn't verify. Classical pitch-vs-product gap: "the pitch is writing checks the product isn't cashing." Navigator §T-8 proposed this audit as preventative — catch the rest of the gap before more users hit it.

**Acceptance rule:** every user-facing claim tagged **(c) v1.1** or **(d) aspirational** must be either (i) removed from launch copy, (ii) re-framed as "coming soon" with explicit target, or (iii) left in copy only if host explicitly accepts the churn-risk.

**Tag legend:**
- **(a) ships today** — live on main, verifiable in current HEAD.
- **(b) ships at MVP launch** — within the ~21-24 dev-day MVP scope per §4 narrowing.
- **(c) v1.1 / post-MVP** — explicitly deferred per §4, real but future.
- **(d) aspirational** — not on any current track; aspirational framing.
- **(a/b/c)** — partial; some functionality ships in one tier, rest later.

---

## 2. Landing page (`prototype/web-app-v0/src/routes/+page.svelte` + `landing.*` i18n keys)

| # | Claim (copy source) | Tag | Reality | Recommendation |
|---|---|---|---|---|
| L1 | **"Summon the daemon."** (hero_title) | (b) MVP | Tray ships at track D MVP slice (1.5d), 1 provider self-visibility only. | Keep; metaphor not a specific functionality claim. |
| L2 | **"Design custom multi-step AI workflows. Real execution, not simulation."** (hero_subtitle) | (b) MVP | Track N MVP-narrowed ships T1 + T2-lite authoring + Deno Edge sandbox. Real execution ships via track C/K. | Keep. "Real execution" is accurate against c97feac+27d67d3 LIVE-F2 fabrication guards. |
| L3 | **"Your chatbot becomes a workshop. Your daemon does the work."** (hero_tagline) | (b) MVP | Tier-1 chatbot-mediated flow is the MVP primary path. | Keep. |
| L4 | **"Try in Claude.ai (zero-install)"** (cta_connect) | (b) MVP | `/connect` page shipping at MVP with MCP URL + setup steps. | Keep. |
| L5 | **"Host a daemon (one-click)"** (cta_host) | (b) MVP | Tray installer ships at track D MVP (Windows signed per §12.9); macOS/Linux at launch-day per SUCCESSION. "one-click" is marketing-aesthetic but accurate for Windows. | **Minor risk**: macOS/Linux installers may not be signed at MVP. README flags this; landing copy could add "Windows installer signed; macOS/Linux AppImage in beta." Deferrable. |
| L6 | **"Contribute to the OSS core"** (cta_contribute) | (a) ships today | MIT platform + CC0 content + CONTRIBUTING.md landed `e67b9fc`. | Keep. |
| L7 | Step 1: "Chat with your AI (Claude.ai, etc.). Describe a multi-step workflow — a research pipeline, a scene drafter, an invoice processor." | (b) MVP | Maya invoice workflow lives in catalog `invoice-payables.yaml` + `monthly-close-package.yaml` (#80). Research + scene workflows live. | Keep. |
| L8 | Step 2: "Your chatbot designs it with you, pulling from a public library of workflow nodes built by other users. It reuses, remixes, or creates." | (a/b) | `discover_nodes` RPC + `remix_node` ship at MVP. Actual "library built by other users" is empty at launch day zero (cold-start problem per §M-1). Library-of-one (host seed) at launch. | **Gap**: "built by other users" implies a populated library. At launch-day-zero it's host-seeded only. Recommend soften to "a public library you can browse, remix, or add to." |
| L9 | Step 3: "When you're ready, a daemon runs it. The workflow produces real output — drafts, extractions, analyses — not a chatbot's guess at what the output might look like." | (b) MVP | Real execution via track C/K runtime + hard rule 5 in control_station prevents simulation. | Keep. The "not a chatbot's guess" framing is load-bearing for trust. |
| L10 | "Real execution. The daemon actually runs your workflow; it doesn't pretend." | (b) MVP | Same as L9. | Keep. |
| L11 | "Open commons. Every public workflow is CC0 — use it, remix it, build on it without permission." | (a) today | License pinned, CC0 metadata column ships per §4. | Keep. |
| L12 | **"Your data stays yours. Concept-layer public; instance-layer private; never training data."** | (b) MVP | Per-piece privacy ships MVP per §4 (non-cuttable). "Never training data" — partially. Workflow's own surface doesn't train on user data; chatbot providers (Claude / GPT) may per THEIR policies. | **Gap**: "never training data" could mislead. Claude.ai's data-use policy IS the user's responsibility to know. Recommend: "Never used as training data by Workflow. Your chatbot provider's training policy is separate — check Claude.ai / ChatGPT / etc. directly." |
| L13 | "Pay for what you need. Free to use. Optional: pay daemons to run workflows faster (1% platform fee, crypto-native)." | (a/c) split | Free to use ships today. Paid-market ledger (off-chain) ships MVP per §4. **Wallet-connect + on-chain settlement + 1% fee to treasury defer to v1.1.** | **Gap**: "crypto-native" implies on-chain today. At MVP the ledger is off-chain reservations; on-chain cutover is v1.1. Recommend: "Optional: pay daemons to run workflows faster (1% fee, crypto settlement in v1.1)." |

---

## 3. `/connect` page

| # | Claim | Tag | Reality | Recommendation |
|---|---|---|---|---|
| C1 | "Zero install. Just paste one URL." | (b) MVP | `tinyassets.io/mcp` gateway ships at track C MVP. Worker-routed to tunnel origin `mcp.tinyassets.io`. (Pre-launch drafts named `api.tinyassets.io/mcp`; that subdomain was never created — reserved as a future alias.) | Keep. |
| C2 | MCP URL = `https://tinyassets.io/mcp` | (c) v1.1 preview | Gateway spec is #27 exec plan; rewrite is post-MVP boundary-crossing work. Legacy `tinyassets/universe_server.py` surface is what lives behind the URL today via tray + tunnel. | **Gap**: URL is live today but backing implementation is legacy. Doesn't affect users (surface contract matches). No copy change needed; note in launch readiness. |
| C3 | "Start a new chat and say: 'summon me a daemon for [what you want to build].'" | (b) MVP | chatbot-assumes-Workflow principle (hard rule 7 landed `27d67d3`) means chatbot routes on plausible intent. | Keep. |
| C4 | Examples "Accounting / Research / Writing / Cooking / Legal / Code / Journalism / Email" (8 domains) | (a/b) mixed | Accounting: bookkeeping nodes shipped #80. Research: shipped. Writing: essay-line-editor shipped #80. Cooking: `recipe-scaler` shipped. Legal / Code / Journalism / Email: not yet in catalog as node YAMLs. | **Gap**: 4 of 8 examples have no backing catalog content. Legal + Code + Journalism + Email examples promise workflows that don't exist at launch. Recommend: (i) drop the 4 missing examples OR (ii) flag them as "community-wanted — be the first to contribute." |
| C5 | FAQ "Does it work with ChatGPT / Gemini / etc?" → "Claude.ai has the smoothest setup today." | (a) today | MCP protocol is open. Claude.ai is the only tested client per Q21-nav. | Keep. Honest framing. |
| C6 | FAQ "What happens to my data?" → "The workflow design ... is public by default ... Your actual data ... stays on your own machine or in owner-only storage. Never training data." | (b) MVP | Per-piece privacy ships MVP. Same caveat as L12 — "never training data" should clarify the boundary. | Apply same fix as L12. |
| C7 | FAQ "What if a workflow does the wrong thing?" → "Every real-world action ... requires explicit per-invocation confirmation. ... No cached consent." | (b) MVP | Per spec #68 §5.2 (irreversible = per-invocation confirm) + #69 §6.3. Irreversible-action confirm ships MVP. | Keep. Contract is load-bearing; product delivers. |
| C8 | FAQ "Can I run a workflow without executing it for real?" → "Yes. Say 'dry-run' and any workflow simulates without calling external systems." | (b) MVP | `test_run(dry=true)` per spec #67 §2.4 ships MVP. | Keep. |
| C9 | Trust signal "Per-piece privacy judged by your chatbot, not by us" | (b) MVP | Per-piece + chatbot-judged per §17 + memory. | Keep. |
| C10 | Trust signal "Export or delete your data anytime" | (a/b) | Export path exists in tier-3 (git clone); account-level export from web app is §35 beyond MVP slice. Deletion per `/account` legal page defers. | **Gap**: "anytime" is strong. Recommend: "Export (tier-3 today, web UI at MVP). Delete on request." |

---

## 4. `/host` page — privacy/routing claims (highest-risk surface per Devin LIVE-F8)

| # | Claim | Tag | Reality | Recommendation |
|---|---|---|---|---|
| H1 | "Host a Daemon" / "Run workflows for yourself or for the community." | (b) MVP | Track D 1.5d MVP slice: host_pool register + 1 visibility (self). | Keep. |
| H2 | **"First-run wizard takes under 5 minutes."** | (b) MVP | §12 acceptance gate 1 pins this. | Keep, but acceptance-criterion-backed. |
| H3 | **"The tray icon shows status + cascade decisions."** | (b) MVP | Tray status + cascade log sections in spec #30 §1.1. | Keep. |
| H4 | "By default, your daemon runs an active cascade: it handles your own requests first, then picks up paid work it's qualified for, then helps with public requests." | (a/b) | Cascade logic ships in legacy dispatcher (track E off-chain MVP slice). Paid work step semantics are off-chain until v1.1 wallet-connect. | **Minor gap**: "paid work" implies paid-settled today. At MVP ledger reservations accrue; on-chain cutover is v1.1. Recommend footnote: "Paid work is ledger-reserved at MVP; on-chain settlement lands in v1.1." |
| H5 | **"Paid work pays you in the project's testnet token today (real chain post-launch)."** | (c) v1.1 | Explicit "testnet / real post-launch" wording is already aligned. Matches §M on wallet-defer. | Keep. **This is exactly the pitch-alignment pattern we want elsewhere.** |
| H6 | "Platform takes 1%; you get 99%." | (c) v1.1 | Ledger %: MVP accrues as ledger entries; real cutover v1.1. Framing says "today" — implies active. | **Gap**: could imply money is flowing today. Recommend: "Platform will take 1%; you'll keep 99% (takes effect at v1.1 real-chain cutover)." |
| H7 | **Visibility mode "Self only" / "Network" / "Paid"** | (b/c) split | Self: ships MVP per §4 track D slice. Network: ships post-MVP per §4 defer. Paid: off-chain only MVP; on-chain v1.1. | **Gap**: Network mode is presented as equal-peer with Self + Paid; it defers to v1.1. Recommend: flag Network as "v1.1" in the copy, or drop Network from launch-day pitch. |
| H8 | FAQ "What hardware do I need?" → "Any modern laptop or desktop. ... doesn't need a GPU of its own." | (a) today | Ollama-local is opt-in; local LLM needs memory but no hard GPU requirement. | Keep. |
| H9 | FAQ "Will my electric bill skyrocket?" → "No more than normal chat use." | (a) today | Accurate for default config. | Keep. |
| H10 | **FAQ "What if my daemon crashes mid-job?" → "The platform detects disconnects within 90 seconds. In-flight work reverts, requester's funds are refunded, someone else picks it up. No data loss."** | (b/c) split | Disconnect detection ships MVP (presence TTL <120s per §12 acceptance 5). **"Requester's funds are refunded"** — refund path requires paid-market settlement, which is off-chain only at MVP. | **Gap**: "funds are refunded" at MVP refunds a ledger reservation, not real money. At v1.1+ refund is real. Recommend: "In-flight work reverts; someone else picks it up. Ledger reservation refunded (real-money refund lands at v1.1 cutover)." |
| H11 | FAQ "Can I run multiple daemons?" → "Yes. 1 per provider (Claude, Codex, etc.) is free. Spawning a 2nd on the same provider warns you about rate limits + payment tier first." | (c) v1.1 | Multi-spawn policy is per-provider-free-tier documented in memory; UI gating at 2nd+ ships per §30 spec §4. | **Gap**: "warns you about ... payment tier" implies paid-tier detection lives in the tray at MVP. That's a v1.1 polish. Recommend: "Spawning a 2nd on the same provider may hit rate limits. Paid-tier detection lands in v1.1." |
| H12 | FAQ "Who sees the work my daemon runs?" → "Only you (for self + your own work) or the requester (for network/paid work)." | (b/c) split | "Network" mode defers v1.1 (see H7). | Same as H7. |
| H13 | FAQ "What if someone tries to use my daemon for something I don't want?" → "Capabilities are per-node. If you don't host email-sender, you can't be asked to send email. Flag inappropriate requests; the platform's moderation queue reviews." | (b) MVP | Per §4 moderation ships MVP non-cuttable. Per-capability enforcement is track D surface. | Keep. |
| H14 | FAQ "Can I leave my daemon running while I sleep?" → "Yes — that's the design. Active-mode cascade runs continuously..." | (b) MVP | Cascade + auto-mode toggle ships per §30 §1.1 (defer auto-mode *polish* per §4). | Keep. |
| H15 | **Trust signal "Your host, your keys. Daemon talks outbound-only — no inbound ports."** | (a) today | Architecturally true: tray connects outbound to Supabase Realtime; no listener. | Keep. Strong trust signal. |
| H16 | Trust signal "Single tray instance per machine. Double-clicking the icon never spawns duplicates." | (a) today | Task #6 landed as `622cf54`. Tested. | Keep. |
| H17 | Trust signal "Uninstall anytime — your data stays on your machine." | (a) today | Default behavior. | Keep. |

### 4a. Missing from `/host` — the Devin LIVE-F8 gap

The `/host` copy does NOT currently promise confidential-tier routing or local-only pinning — which means Devin's bounce happened at a **spec-not-yet-pitched** surface. The new `get_status` primitive (commit `15c897a`) + #79 spec-level confidential-tier observability answer the question; the copy doesn't yet advertise them. That's correct for now (advertise only once the user-visible route badge ships per #79 §13.1). **Deferred — no action.**

---

## 5. `/contribute` page

| # | Claim | Tag | Reality | Recommendation |
|---|---|---|---|---|
| T1 | "The platform itself is open source. So is the workflow catalog." | (a) today | MIT + CC0. | Keep. |
| T2 | "Clone the repo, read CONTRIBUTING.md, submit a PR." | (a) today | CONTRIBUTING.md landed `e67b9fc`; repo clonable. | Keep. |
| T3 | "Merged catalog PRs round-trip into the Postgres catalog within seconds of merge — other users see your change immediately." | (b/c) split | GitHub export-sync MVP slice is **one-way** (Postgres → YAML); **PR-ingest is v1.1 per §4**. Copy promises bidirectional. | **GAP**: real pitch/product mismatch. Copy says PR → Postgres works; product at MVP is Postgres → YAML only. Recommend: "Merged catalog PRs land in the repo; Postgres round-trip (so chatbot users see them immediately) lands at v1.1." |
| T4 | FAQ "How fast do PRs merge?" → "Typo/docs fix: hours. Feature PR on a spec'd track: 1-3 days. Architecture-touching PR: a week of review. We prefer small PRs merged quickly over big ones debated forever." | (b) MVP | CONTRIBUTING.md SLA: 48h first-response / 5d full review / 10d merge-decision. Copy "hours / 1-3 days / a week" is looser. | **Minor inconsistency**: CONTRIBUTING.md = concrete SLA; landing = softer timeline. Reconcile to the CONTRIBUTING.md SLA or flag landing as "typical, not guaranteed" (CONTRIBUTING.md already guarantees). Recommend: align landing copy to CONTRIBUTING.md concrete numbers so contributors see one SLA surface. |
| T5 | FAQ "Who reviews PRs?" → "Tier-3 contributors (anyone with ≥3 merged PRs by default). The host + admin-pool members merge." | (a/b) | ≥3 merged PRs threshold is in CONTRIBUTING.md; admin-pool size 1-2 at launch per SUCCESSION.md caveat. | Keep. Matches CONTRIBUTING.md. |
| T6 | Community "Discord (TBD) — Planned post-launch; for now discussion stays in GitHub." | (c) v1.1+ | Explicitly flagged as TBD / post-launch. | Keep. **This is the right pattern — user sees the future item AS future.** |
| T7 | Trust signal "If the host disappears, the community keeps running per SUCCESSION.md." | (a/b) | SUCCESSION.md runbook is live; bus-factor ≥2 is §22 gate at real-currency cutover, NOT MVP gate. | **Gap**: at launch-day-zero admin pool = 1 (host). "Community keeps running" presumes co-maintainer exists. Recommend: "The SUCCESSION.md runbook + admin-pool rotation ensure continuity as the co-maintainer pool grows post-launch." |

---

## 6. Catalog (`/catalog`) page

| # | Claim | Tag | Reality | Recommendation |
|---|---|---|---|---|
| K1 | **"Browse workflow nodes, goals, and branches built by the community."** | (a/b) | Goals + branches ship. "Built by the community" is L8 redux — at launch-day-zero it's host-seeded. | Same fix as L8. Recommend: "Browse workflow nodes, goals, and branches — host-seeded at launch, community-built over time." |
| K2 | "empty_state": "No nodes yet — check back after launch." | (a) today | Honest empty-state copy already. | Keep. **Good pattern.** |
| K3 | "Remix this in Claude.ai" (remix_cta) | (b) MVP | `remix_node` RPC ships MVP. | Keep. |
| K4 | "Fork to my workspace" (fork_cta) | (b/c) | Fork semantics require account-authenticated workspace. Web-app account-scoped workspace is §35 beyond MVP. | **Gap**: "my workspace" implies account-scoped working area. Doesn't exist yet. Recommend: "Save for later (fork to your account; coming at launch)." or drop CTA. |

---

## 7. Server status (`/status`) page

| # | Claim | Tag | Reality | Recommendation |
|---|---|---|---|---|
| S1 | "Live platform health. Degrades gracefully — never shows blank." | (b) MVP | Status dashboard is §25 Q20 non-cuttable per §4. | Keep. |
| S2 | "All systems operational." / "Partial degradation — workflows still run, some features may be slow." | (b) MVP | Graceful-degradation framing ships MVP. | Keep. |

---

## 8. MCP tool descriptions (user-facing bits the chatbot surfaces)

Post-#89 vocab-hygiene pass, the tool descriptions are minimal I/O contracts. No explicit promises. **No changes needed.**

The `get_status` tool's `caveats` field (#88) is load-bearing — the response itself narrates the pitch/product gap ("Legacy surface does NOT enforce per-universe sensitivity_tier..."). This is the correct pattern: the product tells the chatbot exactly what's vs isn't ready, so the chatbot can narrate honestly.

---

## 9. Summary of GAPS (action items)

Ranked by bounce-risk severity (highest first):

| # | Gap | Severity | Fix effort |
|---|---|---|---|
| **G1** | Landing L13 "crypto-native" implies on-chain today; wallet defers to v1.1. | **High — financial-promise risk** | Trivial copy edit |
| **G2** | `/host` H6 "Platform takes 1%" implies money flows today. | **High — financial-promise risk** | Trivial copy edit |
| **G3** | `/host` H10 "funds are refunded" implies real-money refund. | **High — financial-promise risk** | Trivial copy edit |
| **G4** | `/contribute` T3 "catalog PRs round-trip in seconds" — product is one-way at MVP. | **High — direct pitch/product mismatch** | Trivial copy edit |
| **G5** | Landing L12 / `/connect` C6 "never training data" could mislead re: chatbot-provider policy. | **Medium — compliance-adjacent** | One clarifying sentence |
| **G6** | `/host` H7 Network-visibility mode presented equal to Self/Paid; defers v1.1. | **Medium — promises absent feature** | Tag as v1.1 or remove |
| **G7** | `/connect` C4 examples Legal/Code/Journalism/Email — no backing catalog content. | **Medium — cold-start gap** | Drop 4 examples or tag as "community-wanted" |
| **G8** | Landing L8 / catalog K1 "built by other users" — empty at launch. | **Low — soften wording** | Trivial copy edit |
| **G9** | `/host` H11 "warns about payment tier" — v1.1 polish. | **Low — overstates** | Tag as v1.1 |
| **G10** | `/contribute` T4 SLA ("hours / 1-3 days / a week") inconsistent with CONTRIBUTING.md concrete SLA. | **Low — consistency** | Align to CONTRIBUTING.md |
| **G11** | `/contribute` T7 "community keeps running" — admin pool 1 at launch. | **Low — aspirational framing** | Soften to "as the pool grows" |
| **G12** | `/connect` C10 "Export or delete anytime" — web UI defers post-MVP. | **Low — capability overstated** | Tag tiers |
| **G13** | Catalog K4 "Fork to my workspace" — account-workspace defers. | **Low — capability overstated** | Drop CTA or tag |
| **G14** | Landing L5 "Host a daemon (one-click)" — macOS/Linux may not be signed. | **Low — platform-specific** | README footnote sufficient |

**4 High-severity gaps all relate to crypto/money language.** The pattern is the same: MVP accrues ledger entries; real money flows at v1.1 cutover. Fix is uniform: add "v1.1" or "real-chain cutover" qualifier to every money-flow claim.

---

## 10. Recommended copy changes (ready-to-apply)

### 10.1 Landing page (`landing.*` in `en.json`)

**L13** — `landing.why_points[3]`:
```diff
-"Pay for what you need. Free to use. Optional: pay daemons to run workflows faster (1% platform fee, crypto-native)."
+"Pay for what you need. Free to use. Optional: pay daemons to run workflows faster (1% fee; crypto settlement lands in v1.1)."
```

**L12** — `landing.why_points[2]`:
```diff
-"Your data stays yours. Concept-layer public; instance-layer private; never training data."
+"Your data stays yours. Concept-layer public; instance-layer private; never used as training data by Workflow. (Your chatbot provider's policy is separate — check Claude.ai / ChatGPT directly.)"
```

**L8** — `landing.how_it_works_steps[1]`:
```diff
-"Your chatbot designs it with you, pulling from a public library of workflow nodes built by other users. It reuses, remixes, or creates."
+"Your chatbot designs it with you, pulling from a public library you can browse, remix, or add to. It reuses, remixes, or creates."
```

### 10.2 `/host` page (`host.*`)

**H6** — `host.earnings_preview`:
```diff
-"Paid work pays you in the project's testnet token today (real chain post-launch). Platform takes 1%; you get 99%. Settlements batch under $1 equivalent and go on-chain above that. You can request payout anytime."
+"Paid work pays you in the project's testnet token today. Platform will take 1%; you'll keep 99% (takes effect at v1.1 real-chain cutover). Settlements batch under $1 equivalent and go on-chain above that. You can request payout anytime."
```

**H7** — `host.visibility_modes[1]` (Network):
```diff
-"Your daemon runs for you + a list of GitHub handles you explicitly trust. No strangers. No money changes hands. Useful for small teams / collaborator networks."
+"(Coming in v1.1.) Your daemon runs for you + a list of GitHub handles you explicitly trust. No strangers. No money changes hands. Useful for small teams / collaborator networks."
```

**H10** — `host.faq` "What if my daemon crashes mid-job?":
```diff
-"The platform detects disconnects within 90 seconds. In-flight work reverts, requester's funds are refunded, someone else picks it up. No data loss."
+"The platform detects disconnects within 90 seconds. In-flight work reverts; someone else picks it up. Ledger reservation is refunded (real-money refund takes effect at v1.1 real-chain cutover). No data loss."
```

**H11** — `host.faq` "Can I run multiple daemons?":
```diff
-"Yes. 1 per provider (Claude, Codex, etc.) is free. Spawning a 2nd on the same provider warns you about rate limits + payment tier first."
+"Yes. 1 per provider (Claude, Codex, etc.) is free. Spawning a 2nd on the same provider may hit rate limits. Paid-tier detection lands in v1.1."
```
> **Retracted 2026-04-24.** Both the `-` and `+` lines above are wrong. Host normal state = 1 always-on daemon, no per-provider allowance model. Multi-daemon is host-driven ad-hoc testing. The tier-2 daemon-allowance question (how many free daemons for external users) is unresolved and not yet designed. Do not use either line above in copy.

### 10.3 `/connect` page (`connect.*`)

**C4** — `connect.examples`: drop Legal, Code, Journalism, Email OR flag each as "community-wanted." Recommend drop; rebuild list with real-catalog-backed examples.

**C6** — same as L12.

**C10** — `connect.trust_signals[2]`:
```diff
-"Export or delete your data anytime"
+"Export your data (tier-3 today via git, web UI at MVP). Delete on request."
```

### 10.4 `/contribute` page (`contribute.*`)

**T3** — `contribute.what_happens_next`:
```diff
-"Merged engine PRs ship in the next release (weekly). Merged catalog PRs round-trip into the Postgres catalog within seconds of merge — other users see your change immediately. Your attribution is preserved on the provenance chain."
+"Merged engine PRs ship in the next release (weekly). Merged catalog PRs land in the repo immediately; Postgres round-trip (so chatbot users see them) lands at v1.1. Your attribution is preserved on the provenance chain."
```

**T4** — `contribute.faq` "How fast do PRs merge?":
```diff
-"Depends on scope. Typo/docs fix: hours. Feature PR on a spec'd track: 1-3 days. Architecture-touching PR: a week of review. We prefer small PRs merged quickly over big ones debated forever."
+"Per CONTRIBUTING.md: first-response ≤48h weekday-median, full review ≤5 days, merge decision ≤10 days absent blocker. Typo fixes land fast; architecture-touching PRs use the full review budget. Escalation path on the repo if SLA is breached."
```

**T7** — `contribute.trust_signals[2]`:
```diff
-"If the host disappears, the community keeps running per SUCCESSION.md."
+"The SUCCESSION.md runbook + admin-pool rotation ensure continuity as the co-maintainer pool grows post-launch. Bus-factor target ≥2 binds at real-currency cutover."
```

### 10.5 Catalog page (`catalog.*`)

**K1** — `catalog.subtitle`:
```diff
-"Browse workflow nodes, goals, and branches built by the community."
+"Browse workflow nodes, goals, and branches — host-seeded at launch; community-built over time."
```

**K4** — `catalog.fork_cta`:
```diff
-"Fork to my workspace"
+"Save for later"
```

---

## 11. Non-gaps (confirming accuracy)

These claims are correct as-is; explicitly confirming so copy isn't over-corrected:

- Hero "Summon the daemon" — metaphor, not a specific feature claim. Keep.
- "Real execution, not simulation" — backed by c97feac / 27d67d3 / 4ef0769 LIVE-F2 mitigations + hard rule 5. Keep.
- Trust signal "Your host, your keys. Daemon talks outbound-only" — architecturally accurate. Keep.
- Empty-state copy "No nodes yet — check back after launch." — exemplary pitch-alignment. Keep.
- `/host` H5 "testnet today, real chain post-launch" — **exactly the pattern other claims should follow.** Keep.
- `get_status` tool response `caveats` field — honest self-disclosure. Keep. (Non-web-app surface but worth noting as exemplar.)

---

## 12. Launch-readiness integration

Add to `docs/ops/launch-readiness-checklist.md` as a new §:

- [ ] **Pitch-vs-product gaps G1-G14 resolved.** Either (a) apply proposed copy edits from §10, (b) explicitly mark a claim as accepted-risk with host sign-off, or (c) ship the feature.

High-severity (G1-G4, crypto/money claims) should be hard-gated on launch. Medium (G5-G7) should be soft-gated (amendable post-first-100-user-signup). Low (G8-G14) can run as a post-launch copy sweep.

---

## 13. Cross-references

- `docs/audits/user-chat-intelligence/2026-04-19-devin-session1.md` §T-8 — source directive.
- `docs/design-notes/2026-04-19-minimum-viable-launch-narrowing.md` §4 — launch-day feature matrix (canonical MVP boundary).
- `docs/ops/launch-readiness-checklist.md` — where §12 integration lands.
- `CONTRIBUTING.md` — concrete SLA that T4 should align to.
- `SUCCESSION.md` — admin-pool posture referenced in T7.
- commit `15c897a` — `get_status` caveats pattern as exemplar of honest self-disclosure.
- commit `0670131` — vocab-hygiene pass (completed task #89, sibling scope to this audit).
- Memory `project_real_world_effect_engine.md` — pitch/product alignment is directly the "fail state: gimmicky or like a toy" guardrail.
