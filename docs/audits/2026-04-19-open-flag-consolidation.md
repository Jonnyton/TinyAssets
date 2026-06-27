# OPEN-Flag Consolidation — 2026-04-19 Audit

**Status:** Consolidates every `OPEN:` flag across the 13 specs / catalogs / runbooks landed this session. For each: re-check against current memory set (40 entries as of 2026-04-19), tag as **RESOLVED**, **HOST**, or **LATER**.
**Purpose:** give host a single page of genuine open items to answer, separate from stuff memory already resolved or that's truly build-time-only.
**Not authoritative — specs themselves remain canonical.** This doc just rolls up the status.

---

## Tag legend

- **RESOLVED** — memory or another spec covers this; I can update the originating spec's OPEN list on its next touch.
- **HOST** — genuinely needs host decision before the track ships. Escalate to lead.
- **LATER** — can be resolved at build time without blocking; safe to leave open in the spec as a dev-time note.

---

## By-spec audit

### `SUCCESSION.md` §9 (8 flags)

| # | Question | Tag | Notes |
|---|---|---|---|
| Q1 | Vault product — 1Password vs Vaultwarden self-host | **HOST** | Not memory-covered; host preference for ops tooling. |
| Q2 | Email alias provider — Google Workspace / ForwardEmail.net / Proton | **HOST** | Same — ops tooling pref. |
| Q3 | Foundation / LLC setup timing | **HOST** | Legal + financial decision. |
| Q4 | Co-maintainer recruitment strategy — public call vs direct invite | **HOST** | Host recruits; needs their call on style. |
| Q5 | Succession lead vs co-maintainer same person? | **HOST** | Trivially yes at launch per succession memory; flag RESOLVED if host confirms. |
| Q6 | Multi-sig wallet product — Safe vs others | **LATER** | Can pick at mainnet-migration time; testnet is single-key still. |
| Q7 | Backup encryption key scheme — age / GPG / other | **LATER** | Build-time pick; `age` recommended. |
| Q8 | Public transparency cadence — monthly / quarterly / ad-hoc | **HOST** | Host's voice preference. |

### `docs/catalogs/privacy-principles-and-data-leak-taxonomy.md` (6 gaps in §6)

| # | Question | Tag | Notes |
|---|---|---|---|
| 1 | Aggregate / derived-data privacy | **LATER** | v2 catalog work; not MVP. |
| 2 | Cross-node correlation | **LATER** | Research problem; flag for v2. |
| 3 | Time-based re-evaluation | **LATER** | Not MVP. |
| 4 | Jurisdiction-specific rules | **LATER** | v1 is US framing; per-locale is v2+. |
| 5 | Adversarial test cases | **LATER** | Cross-refs #12 injection-hallucination design note. |
| 6 | (implicit in §4.3) — chatbot gas-abstraction override | **RESOLVED** | Per `project_monetization_crypto_1pct.md`: platform sponsors testnet gas; mainnet user-paid. |

### `docs/ops/anthropic-connector-catalog-submission.md` §4 (10 flags)

| # | Question | Tag | Notes |
|---|---|---|---|
| Q1 | Exact submission portal URL | **HOST** | Needs live WebFetch; host can do in <10 min. |
| Q2 | Category list | **HOST** | Depends on Q1. |
| Q3 | Approval criteria + timeline | **HOST** | Depends on Q1. |
| Q4 | Post-listing obligations | **HOST** | Depends on Q1. |
| Q5 | Version-change policy | **HOST** | Depends on Q1. |
| Q6 | Branding compliance — "Claude" usage in descriptions | **HOST** | Needs live check of Anthropic brand guidelines. |
| Q7 | Multi-provider dual-listing | **HOST** | Depends on Q1. |
| Q8 | Developer agreement / click-through | **HOST** | Depends on Q1. |
| Q9 | Post-listing analytics availability | **HOST** | Depends on Q1. |
| Q10 | Localization support | **HOST** | Depends on Q1; note `project_q13_q14_resolutions.md` says multi-lingual day-one product-side. |

**Cluster observation:** all 10 unblock on host doing the 30-min WebFetch research. Not 10 questions; 1 research task.

### `docs/specs/2026-04-18-full-platform-schema-sketch.md` §6 (9 flags)

| # | Question | Tag | Notes |
|---|---|---|---|
| Q1 | Network-visibility allowlist mechanism — per-node ACL vs per-user trusted-peers | **LATER** | v1 only uses public/private; network visibility unused at MVP. |
| Q2 | `host_pool.provider` — enum vs open text | **LATER** | Build-time pick; text + app-side CHECK recommended. |
| Q3 | Network-visibility RLS policy | **LATER** | Depends on Q1. |
| Q4 | `artifact_field_visibility` RLS dispatcher | **LATER** | Build-time SQL polish. |
| Q5 | Embedding compute location — inline / Edge Function / pre-computed | **LATER** | Recommendation pre-computed at caller; can flip. |
| Q6 | `improvement_cycle_id` table spec | **LATER** | Flagged deferred to #53 convergence spec (landed). |
| Q7 | `known_failure_modes` source table | **LATER** | Can be derived from `moderation_decisions` + `node_activity`; not new schema. |
| Q8 | `schema_compat_score` algorithm | **LATER** | Build-time; recommend structural-hash + field-type similarity. |
| Q9 | Whole-universe `sensitivity_tier` × per-field-visibility interaction | **RESOLVED** | `project_privacy_per_piece_chatbot_judged.md` §4 — per-field is canonical; sensitivity_tier survives for whole-universe opt-out only. |

### `docs/specs/2026-04-18-load-test-harness-plan.md` §9 (8 flags)

| # | Question | Tag | Notes |
|---|---|---|---|
| Q1 | Grafana Cloud free vs self-host k6 | **LATER** | Can start on free tier, migrate. |
| Q2 | Supabase test-project always-on vs branching | **LATER** | Start option (a); revisit when branching GAs. |
| Q3 | Dedicated loadtest-catalog repo vs production | **HOST** | Small ask; host decides if they want the extra repo. |
| Q4 | S7 mock-ledger vs real-ledger | **LATER** | Ship real-ledger; spec already has +0.3d flagged. |
| Q5 | PR subset cadence | **LATER** | Build-time tuning. |
| Q6 | Locust alternative for Python-cohesion | **RESOLVED** | k6 picked; Python sidecar resolves cohesion. |
| Q7 | S8 tier-share scale — 1k DAU-equiv sufficient? | **LATER** | Build-time; can iterate. |
| Q8 | Nightly-failure paging mechanism | **HOST** | Host ops preference. |

### `docs/specs/2026-04-18-mcp-gateway-skeleton.md` §10 (9 flags)

| # | Question | Tag | Notes |
|---|---|---|---|
| Q1 | JWT signing — HS256 vs RS256 | **LATER** | HS256 recommended; build-time pick. |
| Q2 | Rate-limit storage — Upstash vs Supabase unlogged | **LATER** | Upstash recommended. |
| Q3 | `add_canon_from_path` path-trust model | **HOST** | Cross-refs `2026-04-18-add-canon-from-path-sensitivity.md` — navigator's open item. |
| Q4 | FastMCP streaming vs polling | **LATER** | Check FastMCP release notes at build. |
| Q5 | Multi-region launch scope | **LATER** | `ord` only recommended at launch. |
| Q6 | `min=2` cold-start cost | **LATER** | ~$10-15/mo/region; affordable. |
| Q7 | Bearer token lifetime | **LATER** | 14d recommended. |
| Q8 | Audit-log scope | **LATER** | Mutations-only recommended. |
| Q9 | S9 chaos-test gap in #26 | **LATER** | Flag for #26 amendment; ~0.2d add. |

### `docs/specs/2026-04-18-paid-market-crypto-settlement.md` §11 (10 flags)

| # | Question | Tag | Notes |
|---|---|---|---|
| Q1 | Gas abstraction at mainnet | **LATER** | Memory `project_monetization_crypto_1pct.md` implies platform-sponsors at mainnet below threshold; confirm. |
| Q2 | On-chain / off-chain read of "crypto-native" | **RESOLVED** | `project_q10_q11_q12_resolutions.md` Q4-follow-up: batched under $1 + per-bid above. My Option A recommendation matches. |
| Q3 | Multi-chain support at launch | **LATER** | Base-only recommended. |
| Q4 | Wallet library — wagmi/viem/etc. | **LATER** | viem + WalletConnect recommended. |
| Q5 | Dispute arbitration post-MVP | **LATER** | Not MVP. |
| Q6 | Treasury governance migration trigger | **HOST** | Succession memory §36: "trigger defined, not improvised" — host sets the $$ threshold. |
| Q7 | Fee-tunability progressive vs flat | **RESOLVED** | Memory says flat 1%. |
| Q8 | Per-capability refund policy | **LATER** | Build-time tuning. |
| Q9 | Multi-token settle | **LATER** | Workflow token only recommended. |
| Q10 | KYC / sanctions screening | **HOST** | Legal — host + counsel. |

### `docs/specs/2026-04-18-daemon-host-tray-changes.md` §11 (10 flags)

| # | Question | Tag | Notes |
|---|---|---|---|
| Q1 | Code-signing cert procurement | **HOST** | ~$400/yr; host action pre-launch. |
| Q2 | Auto-update mechanism pick | **LATER** | Squirrel / Velopack / Sparkle — build-time. |
| Q3 | Offline cold-start UI policy | **LATER** | Recommend allow-pick-later. |
| Q4 | Cascade-log retention | **LATER** | 7-day rolling recommended. |
| Q5 | Crash-report channel — Sentry SaaS vs self-host | **LATER** | Sentry SaaS recommended at launch. |
| Q6 | Multi-user per machine | **LATER** | Recommend yes. |
| Q7 | Headless daemon mode | **LATER** | v2; flagged. |
| Q8 | Package-manager ingestion (brew / winget / apt) | **LATER** | Post-initial-launch. |
| Q9 | Local-first pin UI surface | **LATER** | Recommend yes. |
| Q10 | MCPB bundle vs standalone primary | **HOST** | Needs host's distribution preference. |

### `docs/specs/2026-04-18-export-sync-cross-repo.md` §11 (10 flags)

| # | Question | Tag | Notes |
|---|---|---|---|
| Q1 | License specifier — CC0 vs CC-BY-SA vs MIT-style | **RESOLVED** | Host confirmed **CC0-1.0** (host Q7 answer; also relayed in an earlier handoff). |
| Q2 | Per-node license override column | **LATER** | Post-MVP. |
| Q3 | Bot-key storage — Supabase Vault vs env var | **LATER** | Vault recommended. |
| Q4 | Human-review bottleneck on catalog PRs | **HOST** | Cross-refs §14.7; reviewer recruitment is a launch-readiness task. |
| Q5 | Two-repo vs single-repo-with-branches | **RESOLVED** | Memory `project_collab_model_split.md` + host task-description `tinyassets-catalog-v0/README.md` confirms two-repo. |
| Q6 | Structural-hash UX in PR body | **LATER** | Build-time UX polish. |
| Q7 | Bulk-import collision | **LATER** | Build-time tuning. |
| Q8 | DCO vs CLA | **RESOLVED** | Memory `project_license_fully_open_commons.md` + moderation_rubric v1 + #32 spec all converge on DCO. |
| Q9 | `TinyAssets-catalog/` repo owner — same org vs separate | **HOST** | Host decides GitHub org structure. |
| Q10 | Search-engine indexing on catalog repo | **RESOLVED** | Memory: commons-adoption goal; index-friendly. |

### `docs/specs/2026-04-18-web-app-landing-and-catalog.md` §9 (10 flags)

| # | Question | Tag | Notes |
|---|---|---|---|
| Q1 | SvelteKit adapter-static vs Cloudflare Pages | **LATER** | Build-time pick. |
| Q2 | OG image library — satori vs Resvg vs Figma-templates | **LATER** | satori recommended. |
| Q3 | `/editor` file-paste import | **LATER** | ~0.2 d add; post-MVP decision. |
| Q4 | Real-time presence payload — avatar in Presence vs fetch separately | **LATER** | Fetch separately recommended. |
| Q5 | Moderation triage UI scope — queues vs arbitrary | **RESOLVED** | Moderation rubric v1.0 + spec #36 specify queues; this is consistent. |
| Q6 | Accessibility target — full AA vs partial-with-plan | **HOST** | Legal + resource question. |
| Q7 | Analytics product | **LATER** | Plausible recommended. |
| Q8 | Error-tracking — Sentry SaaS vs self-host | **LATER** | Sentry SaaS recommended. |
| Q9 | i18n scaffold extent | **RESOLVED** | My spec amendment e7f5437 + memory `project_q13_q14_resolutions.md` lock: English-only launch, `[lang]` prefix scaffolded. |
| Q10 | `/editor` WebSocket fallback to long-poll | **LATER** | Supabase Realtime handles. |

### `docs/specs/2026-04-18-moderation-mvp.md` §10 (8 flags)

| # | Question | Tag | Notes |
|---|---|---|---|
| Q1 | `N_auto_hide_threshold` default | **LATER** | 3 recommended; tunable per artifact kind. |
| Q2 | Tier-2 earn-metric pick | **RESOLVED** | My spec §5.3 picks (a) 20 paid + 4 weeks; no conflicting memory. |
| Q3 | Flag-accuracy demote window | **LATER** | 20-flag window recommended. |
| Q4 | Mod rotation cadence — 30d vs version-tied | **LATER** | Version-tied recommended. |
| Q5 | Public moderation-decisions log scope | **LATER** | Recommended public metadata, private flagger. |
| Q6 | Comment moderation rate limits | **LATER** | Separate looser limits recommended. |
| Q7 | DMCA counter-notice flow | **HOST** | Legal; out-of-MVP scope; host + counsel. |
| Q8 | Age-gate signals from chatbot provider | **RESOLVED** | Memory `project_q10_q11_q12_resolutions.md` Q11: no platform age-gate, rely transitively. |

### `docs/specs/2026-04-18-remix-and-convergence-detail.md` §OPEN (7 flags)

| # | Question | Tag | Notes |
|---|---|---|---|
| Q1 | Ratifier threshold per source | **LATER** | MVP: owner=1 per source. Scales later. |
| Q2 | Force-converge by admin-pool | **LATER** | Not MVP; recommend NO. |
| Q3 | Chatbot-merged RPC variant — separate or param | **LATER** | Build-time pick. |
| Q4 | Cross-domain convergence domain-choice UX | **LATER** | Build-time polish. |
| Q5 | Remix licensing — compatibility check | **RESOLVED** | CC0 throughout; non-issue. |
| Q6 | Remix of superseded node | **RESOLVED** | My spec §K.4 answers: YES. Self-answered. |
| Q7 | Convergence involving private node | **LATER** | Recommend: publish first, then propose. |

### `docs/audits/2026-04-18-universe-server-directive-relocation-plan.md` (no OPEN section, but note)

This plan's dev-time-execution surface became obsolete per my #27 §8 pre-execution of the canonical `control_station` prompt in the new MCP gateway skeleton. **Flag as RESOLVED-via-supersession**: the directive relocation ships in the new gateway on track C, not via edits to `tinyassets/universe_server.py`. Task #15 can be formally retired.

### `docs/specs/2026-04-19-plan-b-selfhost-migration-playbook.md` §8 (6 flags, post-audit)

| # | Question | Tag | Notes |
|---|---|---|---|
| Q1 | Hetzner vs other self-host (Linode / Vultr / OVH) | **LATER** | Build-time pick; Hetzner recommended per uptime note §3.3. |
| Q2 | Terraform vs Docker-Compose for provisioning | **LATER** | Build-time; Docker-Compose recommended for simplicity at v1 scale. |
| Q3 | Monthly vs quarterly restore-rehearsal cadence | **LATER** | Build-time ops discipline. |
| Q4 | Supabase Realtime OSS vs roll-our-own if archived | **LATER** | Contingent trigger; not blocking. |
| Q5 | Pre-cutover DB replication mechanism | **LATER** | Build-time pick. |
| Q6 | Contingency if GitHub bans the project — alt VCS | **HOST** | Host picks pre-committed fallback (GitLab vs self-hosted Gitea). |

### `docs/catalogs/integration-patterns.md` §6 (5 flags, post-audit)

| # | Question | Tag | Notes |
|---|---|---|---|
| Q1 | Multi-pattern branches — single primary vs hybrid | **LATER** | v1 single primary + secondary_patterns[]; revisit at v2. |
| Q2 | Chatbot-suggested pattern match in discover_branches | **LATER** | Post-MVP UX enhancement. |
| Q3 | Pattern linting | **LATER** | v2 tooling. |
| Q4 | Streaming as MVP scope | **HOST** | Task description says "streaming = post-MVP typically"; confirm or re-scope. |
| Q5 | Saga primitive support | **LATER** | Post-MVP; needs compensation-handler node schema. |

### `docs/catalogs/node-type-taxonomy.md` §7 (5 flags, post-audit)

| # | Question | Tag | Notes |
|---|---|---|---|
| Q1 | Multi-type nodes | **LATER** | v2 allows secondary_type column; v1 single primary. |
| Q2 | User-extensible taxonomy | **LATER** | v1 fixed list; v2 extensible if community demands. |
| Q3 | Auto-classification by chatbot | **LATER** | UX enhancement; chatbot proposes user confirms. |
| Q4 | Historical bulk-classification pass | **LATER** | Migration task at real launch. |
| Q5 | `discover_nodes` type filter at launch | **LATER** | Recommend expose as param; build-time pick. |

### `docs/specs/2026-04-18-remix-and-convergence-detail.md` §K.8b post-audit additions

Post-merge rollback RPC added in amendment `2516992`. No new OPEN flags from that amendment — it closed the "rollback path" gap from the original task.

---

## Memory quotes for RESOLVED flags

Amendment (task #54): cite the specific memory directive text for each RESOLVED tag so auditor can verify without following the reference.

| Flag | RESOLVED by memory | Memory's decisive quote |
|---|---|---|
| Schema spec §6 Q9 (universe sensitivity_tier × per-field) | `project_privacy_per_piece_chatbot_judged.md` | "Privacy-tier inheritance is node-piece-scoped, not node-scoped. Old mental model (entire-universe `sensitivity_tier`) is too coarse." |
| Paid-market spec §11 Q2 (on-chain vs off-chain) | `project_q10_q11_q12_resolutions.md` | "Paid settlements batched under $1-equivalent; above threshold settle on-chain." |
| Paid-market spec §11 Q7 (fee-tunability) | `project_monetization_crypto_1pct.md` | "Platform charges 1% fee on every paid transaction." (flat, not progressive) |
| Export-sync spec §11 Q1 (license specifier) | (resolved via host Q7 message, not memory — memory file `project_license_fully_open_commons.md` still flags both CC0 + CC-BY-SA as open) | Host confirmed CC0-1.0 in-session (commit `7a42e8e` memory update referenced "CC0 1.0 for workflow content"). |
| Export-sync spec §11 Q5 (two-repo vs single-repo) | `project_collab_model_split.md` | "Workflow content = wiki-open editing. Platform code = GitHub fork-and-PR." Distinct surfaces → distinct repos. |
| Export-sync spec §11 Q8 (DCO vs CLA) | `project_license_fully_open_commons.md` | "Contributors agree to the chosen license on tier-3 GitHub PR and tier-1 publish (DCO-style, not CLA)." |
| Export-sync spec §11 Q10 (SEO indexing) | `project_license_fully_open_commons.md` | "Goal is to become what everyone uses, whether through this platform or repurposed inside the global OSS community." Indexing-friendly required for this goal. |
| Web-app spec §9 Q5 (moderation triage UI scope) | `docs/specs/2026-04-18-moderation-mvp.md` + `moderation_rubric.md` | Spec + rubric fix queues as the scope. |
| Web-app spec §9 Q9 (i18n posture) | `project_q13_q14_resolutions.md` | "Multi-lingual day one, chatbot translates." → English-only launch + scaffold the `[lang]` route reserved. |
| Moderation spec §10 Q2 (tier-2 earn metric pick) | (self-resolved in spec §5.3) | My pick (a) 20 paid + 4 weeks — no conflicting memory; user preference recorded in spec. |
| Moderation spec §10 Q8 (age-gate) | `project_q10_q11_q12_resolutions.md` | "Platform does NOT ask user age. Platform does NOT verify age." → rely transitively on chatbot provider. |
| Remix+convergence spec OPEN Q5 (remix licensing) | `project_license_fully_open_commons.md` | CC0 throughout; compatibility check is a no-op at v1. |
| Remix+convergence spec OPEN Q6 (remix of superseded) | (self-resolved in spec §K.4) | Explicit YES: concept still valid; superseded status just means it's not the current canonical. |
| Load-test spec §9 Q6 (Locust alternative for Python-cohesion) | (self-resolved in spec §1) | k6 picked + Python sidecar bridges the Python code-reuse ask. |
| SUCCESSION.md §9 Q5 (succession lead = co-maintainer?) | `project_host_independent_succession.md` | "contributor recruitment is a launch-readiness task." At launch, same person OK; at scale, separate. |
| Privacy catalog §6.6 (chatbot gas-abstraction override) | `project_monetization_crypto_1pct.md` | Platform sponsors testnet gas implicit; mainnet user-paid. Not strictly quoted but implied by "crypto-native from day one" with no user-facing crypto UX friction mentioned. |

## Aggregate

| Tag | Count | What to do |
|---|---|---|
| **RESOLVED** | 16 (13 original + 3 post-audit quotes) | Update the originating spec's OPEN list to cite memory/spec resolving it. Low-priority cleanup; no action required pre-launch. |
| **HOST** | ~22 (20 original + Q4 integration-patterns streaming + Q6 plan-B VCS fallback) | **Genuine decisions host needs to make.** Many cluster (Anthropic submission = 10 Qs that collapse to 1 WebFetch task). Real count of independent decisions: ~12. |
| **LATER** | ~75 (60 original + 15 post-audit across plan-B + integration-patterns + node-taxonomy specs) | Build-time picks; safe to leave open in specs. Address as the build lands; most have my recommendation in the OPEN entry. |

**Net pre-launch host-action items (collapsed):**

1. **Anthropic directory submission research** (30-min WebFetch task, resolves 10 flags).
2. **Vault tooling + email-alias provider** (pair of ops-tool picks; 15 min).
3. **Foundation/LLC setup timing** (legal/financial decision).
4. **Succession-lead + co-maintainer recruitment strategy** (host's style call).
5. **Code-signing cert procurement** (~$400/yr, Windows EV + macOS Developer ID).
6. **GitHub org structure** (single org vs separate for TinyAssets/ + TinyAssets-catalog/).
7. **MCPB vs standalone tray distribution primary** (host product preference).
8. **Accessibility target pick** (full AA vs partial-with-plan).
9. **DMCA counter-notice process** (legal; host + counsel).
10. **KYC / sanctions posture** (legal; host + counsel; pre-mainnet only).
11. **Streaming workflows at MVP?** (integration-patterns §6.6 Q4; default: post-MVP).
12. **Pre-committed VCS fallback** (plan-B §8 Q6; GitLab vs Gitea vs other — used if GitHub bans the project).

Item 1 is 30 min. Items 2-4 are each under an hour. Items 5-7 are project-management. Items 8-10 are legal-adjacent and not blocking for testnet launch. Items 11-12 are operational-resilience picks with defaults that work.

**None of these block pre-spec work.** All tracks A-K stay execution-ready even with these unresolved; the specs just flag "at build time dev will need host's answer on Q1."
