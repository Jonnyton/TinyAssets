# OpenSpec grounding audit — Batch C

- **Baseline:** `origin/main` at `7c23c881502460f65cfd5ee81c27042d87743f24` (`coord: fold back forward spec reconciliation (#1615)`)
- **Date:** 2026-07-22
- **Environment:** Codex desktop, Windows PowerShell, repository worktree `wf-openspec-knowledge-memory-reconcile`
- **Method:** static, read-only comparison of canonical specs against implementation and checked-in tests, followed by an independently reviewed exact as-built correction. The correction lane's focused existing-behavior suite passed 217 tests with 7 warnings.
- **Evidence granularity:** non-BUILT rows use decisive line ranges; BUILT rows cite representative exact `file:line` or range anchors for owning implementation boundaries. These pointers do not pretend one range exhaustively proves a distributed contract.
- **Windows safety:** `tests/test_uptime_canary_layer2.py` was not run, per the explicit Windows prohibition.
- **Classification:** `BUILT` means the complete canonical requirement and every listed scenario are represented by shipped code; `PARTIAL` means the named guarantee has a material unimplemented failure/race path; `CONTRADICTED` means shipped behavior directly opposes the canonical statement.

## Result

| Capability | Requirements | Scenarios | Classification |
|---|---:|---:|---|
| `paid-market-economy` | 17 | 38 | 17 BUILT; scenarios 38 BUILT |
| `provider-routing` | 11 | 39 | 11 BUILT; scenarios 39 BUILT |
| `public-website-surface` | 6 | 12 | 6 BUILT; scenarios 12 BUILT |
| `shared-goals-and-convergence` | 15 | 62 | 15 BUILT; scenarios 62 BUILT |
| `universe-lifecycle-and-soul` | 7 | 22 | 7 BUILT; scenarios 22 BUILT |
| `universe-personification-and-relay` | 7 | 20 | 7 BUILT; scenarios 20 BUILT |
| `uptime-and-alarms` | 6 | 18 | 6 BUILT; scenarios 18 BUILT |
| `wiki-commons` | 8 | 25 | 8 BUILT; scenarios 25 BUILT |
| **Total** | **77** | **236** | **77 BUILT; scenarios 236 BUILT** |

## Requirement-by-requirement matrix

Scenario classifications are listed in canonical order.

### `paid-market-economy`

| Canonical requirement | Verdict | Scenarios | Representative implementation evidence | Representative test evidence |
|---|---|---|---|---|
| The money path is flag-gated off and pre-launch | BUILT | 3: BUILT / BUILT / BUILT | `tinyassets/api/market.py:454-462`; `tinyassets/producers/node_bid.py:39-40`; `tinyassets/dispatcher.py:110-111` | `tests/test_payments_escrow_mcp.py:63`; `tests/test_node_bid.py:604,679` |
| Money actions operate only on the authenticated actor | BUILT | 2: BUILT / BUILT | `tinyassets/api/market.py:416-449` | `tests/test_payments_escrow_mcp.py:411-520` |
| Payment-core conversions produce integers while legacy bids permit non-integer scalars | BUILT | 3: BUILT / BUILT / BUILT | `tinyassets/payments/identifiers.py:27-30`; transport conversion at `tinyassets/api/market.py:474,597,688`; scalar-preserving bids at `tinyassets/bid/node_bid.py:46`; float settlement serialization at `tinyassets/bid/settlements.py:120` | `tests/test_payments_escrow_mcp.py:81`; fractional bid assertions at `tests/test_node_bid.py:830,862`; focused correction suite passed |
| Paid-market computation library is pure and I/O-free | BUILT | 2: BUILT / BUILT | representative pure boundaries at `tinyassets/paid_market/index.py:223-290`, `tinyassets/paid_market/forwards.py:167-252`, and `tinyassets/paid_market/ledger.py:60-108` | Conservation/property coverage across `tests/test_paid_market_core.py:66-1498` |
| Node bids are file-backed with atomic single-claim | BUILT | 2: BUILT / BUILT | `tinyassets/bid/node_bid.py:42-52,256` | `tests/test_node_bid.py:187,225,964`; process-race coverage `tests/test_node_bid_claim_stress.py:122-331` |
| Settlement recording rejects pre-existing paths sequentially but is not race-atomic | BUILT | 3: BUILT / BUILT / BUILT | Sequential guard at `tinyassets/bid/settlements.py:101-106`, followed by non-exclusive `Path.write_text` at `:126-129`; concurrent writers can both pass the check | Sequential overwrite and invalid-status tests at `tests/test_node_bid.py:883,908`; race limitation is source-grounded, with no concurrent settlement-writer test |
| Treasury take is conserved basis-point math with a read-only status surface | BUILT | 2: BUILT / BUILT | `tinyassets/treasury/distribution.py:89-104`; read-only connection and status assembly at `tinyassets/treasury/status.py:12-16,43-120` | `tests/test_treasury_distribution.py:177-205`; `tests/test_treasury_status.py:19,90` |
| The pure spot oracle uses settled-trade windows and pair-capped weights | BUILT | 3: BUILT / BUILT / BUILT | `tinyassets/paid_market/index.py:223` | `tests/test_paid_market_core.py:107,195-240` |
| Bucket and hosted-price helpers fail loud without performing transport | BUILT | 2: BUILT / BUILT | `tinyassets/paid_market/buckets.py:68-135`; deterministic conversion and payload parsing at `tinyassets/paid_market/ceiling.py:62-147` | `tests/test_paid_market_core.py:249-292,591-649` |
| Forward validation and settlement are pure, monotone, and conservation-exact | BUILT | 2: BUILT / BUILT | `tinyassets/paid_market/forwards.py:167` | `tests/test_paid_market_core.py:338-563` |
| Training checkpoint settlement is a pure trusted-count oracle | BUILT | 2: BUILT / BUILT | `tinyassets/paid_market/training.py:91` | `tests/test_paid_market_core.py:668-740` |
| Declared license terms compose fail-closed as a pure lattice | BUILT | 2: BUILT / BUILT | `tinyassets/paid_market/license_terms.py:128` | `tests/test_paid_market_core.py:884-914` |
| Pool funding and revenue apportionment conserve caller-supplied order and shares | BUILT | 2: BUILT / BUILT | `tinyassets/paid_market/pool.py:74-218` | `tests/test_paid_market_core.py:762-864` |
| Shuttle allocation and break-even arithmetic are total-first and deterministic | BUILT | 2: BUILT / BUILT | `tinyassets/paid_market/shuttle.py:64` | `tests/test_paid_market_core.py:937-992,1491` |
| Fabrication quotation, ranking, and settlement fail closed at their pure boundaries | BUILT | 2: BUILT / BUILT | `tinyassets/paid_market/fabrication.py:68-266` | `tests/test_paid_market_core.py:1031-1155` |
| Treasury-internal fund arithmetic refuses ambiguous bootstrap state | BUILT | 2: BUILT / BUILT | `tinyassets/paid_market/fund.py:89,218` | `tests/test_paid_market_core.py:1184-1308` |
| Pure matching and ledger-entry builders fail loud and balance | BUILT | 2: BUILT / BUILT | `tinyassets/paid_market/match.py:61-121`; posting validation/application and balanced entry builders at `tinyassets/paid_market/ledger.py:60-232` | `tests/test_paid_market_core.py:1334-1462` |

### `provider-routing`

| Canonical requirement | Verdict | Scenarios | Representative implementation evidence | Representative test evidence |
|---|---|---|---|---|
| Every role chain terminates at the local model | BUILT | 2: BUILT / BUILT | `tinyassets/providers/router.py:62-108` | `tests/test_providers.py:1063-1083` |
| Subscription-only provider policy by default | BUILT | 2: BUILT / BUILT | `tinyassets/providers/router.py:242-247` | `tests/test_providers.py:331-379` |
| Hard writer pin disables fallback and fails loud | BUILT | 2: BUILT / BUILT | `tinyassets/providers/router.py:301-379` | `tests/test_provider_allowlist.py:210-241`; `tests/test_provider_auth_router_quarantine.py:189-204` |
| Per-universe engine preference and privacy allowlist | BUILT | 3: BUILT / BUILT / BUILT | `tinyassets/providers/router.py:209-223,320-345` | `tests/test_provider_allowlist.py:81-121` |
| Auth-health quarantine of dead-login subscription providers | BUILT | 3: BUILT / BUILT / BUILT | auth-health policy at `tinyassets/providers/router.py:248-279,375-426`; cached subscription-health implementation at `tinyassets/providers/base.py:540-674` | `tests/test_provider_auth_router_quarantine.py:118-204` |
| Per-node policy routing honors llm_policy overrides | BUILT | 3: BUILT / BUILT / BUILT | `tinyassets/providers/router.py:630-721` | `tests/test_provider_allowlist.py:180-209`; `tests/test_providers.py:395-421` |
| Judge ensemble fans out to all healthy judges in parallel | BUILT | 3: BUILT / BUILT / BUILT | `tinyassets/providers/router.py:848-912` | `tests/test_providers.py:423-476` |
| Chain-drain backoff prevents committing empty prose (BUG-029) | BUILT | 3: BUILT / BUILT / BUILT | `tinyassets/providers/router.py:496-530`; `tinyassets/providers/quota.py:113` | `tests/test_provider_router_bug029.py:126-223` |
| Provider calls use one explicit immutable contract | BUILT | 4: BUILT / BUILT / BUILT / BUILT | frozen contracts at `tinyassets/providers/base.py:19-80`; context forwarding at `tinyassets/providers/call.py:174-208` | `tests/test_per_universe_engine_resolution.py:139,205`; telemetry coverage in `tests/test_provider_router_diagnostics.py:183-215` |
| Runtime eligibility and exhaustion produce bounded cooldowns and structured evidence | BUILT | 6: BUILT / BUILT / BUILT / BUILT / BUILT / BUILT | diagnostic/exhaustion assembly at `tinyassets/providers/router.py:386-539,540-590`; bounded cooldown state at `tinyassets/providers/quota.py:45-134`; status exposure at `tinyassets/api/status.py:1053-1069,1150` | `tests/test_providers.py:133-161,249-275`; `tests/test_provider_router_diagnostics.py:54-215` |
| Subscription auth health is conservative, cached, and non-blocking on status reads | BUILT | 8: BUILT / BUILT / BUILT / BUILT / BUILT / BUILT / BUILT / BUILT | cached health resolution at `tinyassets/providers/base.py:223-238,540-674`; non-probing status reads at `tinyassets/api/status.py:367-390,791-798` | `tests/test_auth_refresh_viability.py:49-357`; `tests/test_api_status.py:226` |

### `public-website-surface`

The website has no focused checked-in unit/acceptance suite for these six requirements. The BUILT classifications below come from direct static-source inspection; the missing focused regression layer is itself test debt.

| Canonical requirement | Verdict | Scenarios | Representative implementation evidence | Representative test evidence |
|---|---|---|---|---|
| The Public Site Ships As A Static Multi-Route Application | BUILT | 2: BUILT / BUILT | `WebSite/site/svelte.config.js:1,8-20`; `WebSite/site/src/routes/+layout.ts:1-3` | No focused checked-in test; production build script is declared at `WebSite/site/package.json` |
| Public Project Views Distinguish Live Reads From Baked Snapshots | BUILT | 2: BUILT / BUILT | `WebSite/site/src/lib/live/project.ts:1-3,174-211`; `WebSite/site/src/routes/host/+page.svelte:32-45,342-354` | No focused checked-in test |
| Browser MCP Reads Use The Public Connector Contract | BUILT | 3: BUILT / BUILT / BUILT | `WebSite/site/src/lib/mcp/live.ts:14,29-31,38-112`; `WebSite/site/vite.config.js:21-29` | No focused checked-in test |
| Status And Loop Presentation Keep Distinct Operational Truths | BUILT | 2: BUILT / BUILT | `WebSite/site/src/lib/mcp/live.ts:983-1104`; `WebSite/site/src/routes/loop/+page.svelte:24` | No focused checked-in test |
| Host And Install Copy States Current Availability Truthfully | BUILT | 2: BUILT / BUILT | `WebSite/site/src/routes/host/+page.svelte:224-259,278`; `pyproject.toml:57-63` | No focused checked-in test |
| Public And Private Indexing Boundaries Are Declared | BUILT | 1: BUILT | `WebSite/site/static/robots.txt:1-38`; `WebSite/site/static/sitemap.xml:1-2` | No focused checked-in test |

### `shared-goals-and-convergence`

| Canonical requirement | Verdict | Scenarios | Representative implementation evidence | Representative test evidence |
|---|---|---|---|---|
| Goals are first-class shared primitives on a single dispatch surface | BUILT | 3: BUILT / BUILT / BUILT | dispatch table at `tinyassets/api/market.py:2347-2369`; SQLite Goal persistence at `tinyassets/daemon_server.py:2565-2616`; git-backed persistence at `tinyassets/catalog/backend.py:567-639` | `tests/test_goals_surface.py:51-76`; git/SQLite coverage in `tests/test_outcome_gate_git_backend.py:117-214` |
| Branches converge on a Goal by binding | BUILT | 3: BUILT / BUILT / BUILT | `tinyassets/api/market.py:1283-1364` | `tests/test_goals_surface.py:200-240` |
| A canonical branch version records the Goal's best-known version, author/host-only | BUILT | 3: BUILT / BUILT / BUILT | `tinyassets/api/market.py:2153-2247`; persistent canonical/history operations at `tinyassets/daemon_server.py:2683-2801` | `tests/test_goals_run_canonical.py:218-314` |
| run_canonical executes against the canonical binding with optional leaderboard refresh | BUILT | 3: BUILT / BUILT / BUILT | `tinyassets/api/market.py:2339-2344,2360-2363` | `tests/test_goals_run_canonical.py:225-423` |
| The Goal leaderboard is synthesized by a user-bound selector branch | BUILT | 5: BUILT / BUILT / BUILT / BUILT / BUILT | selector handler/table at `tinyassets/api/market.py:2364-2368` | `tests/test_goals_set_selector.py:77-315,464-515` |
| Recognized Goal actions use the configured authorization mode and contribution attribution is best-effort | BUILT | 4: BUILT / BUILT / BUILT / BUILT | unknown-action boundary and dispatch at `tinyassets/api/market.py:2380-2446,2581-2604`; provider modes at `tinyassets/auth/provider.py:1112-1151`; authorization branches at `tinyassets/auth/middleware.py:368-413` | `tests/test_predeploy_auth_hardening.py:58-62`; happy-path/rejection at `tests/test_goals_surface.py:639-675`; append-failure behavior is source-grounded |
| Per-universe participation in shared Goals is opt-in via subscriptions | BUILT | 2: BUILT / BUILT | fresh-install default and subscription operations at `tinyassets/subscriptions.py:34,88-95,122-158`; subscribed-only producer path at `tinyassets/producers/goal_pool.py:236-272,451-460` | `tests/test_goal_pool.py:657-736,978` |
| Goal Branch protocols are ordered metadata, not an executor | BUILT | 5: BUILT / BUILT / BUILT / BUILT / BUILT | protocol handlers in `tinyassets/api/market.py:2358-2359` | `tests/test_goals_ladder_shape.py:140-214` |
| Common-node discovery compares exact node identifiers | BUILT | 4: BUILT / BUILT / BUILT / BUILT | common-node handler at `tinyassets/api/market.py:2355` | `tests/test_goals_surface.py:475-521` |
| Archive consultation uses a fixed server-side parent heuristic | BUILT | 3: BUILT / BUILT / BUILT | archive handler at `tinyassets/api/market.py:2356` | `tests/test_goals_surface.py:409-474` |
| Outcome-gate ladders are flag-gated Goal metadata with scoped definition authority | BUILT | 5: BUILT / BUILT / BUILT / BUILT / BUILT | ladder handlers at `tinyassets/api/market.py:2717-2814`; persistence at `tinyassets/daemon_server.py:3294-3315` | `tests/test_outcome_gates.py:64-159`; `tests/test_outcome_gate_git_backend.py:262-298` |
| Gate claims support claim, retract, and visibility-aware listing lifecycle | BUILT | 10: all BUILT | claim/from-run/retract/list handlers at `tinyassets/api/market.py:2841-3371`; persistent lifecycle at `tinyassets/daemon_server.py:3427-3619`; git-backed claim persistence at `tinyassets/catalog/backend.py:643-746` | `tests/test_outcome_gate_claims.py:67-213,402-494`; `tests/test_gates_claim_from_branch_run.py:123-391` |
| The outcome leaderboard deterministically ranks active ladder progress | BUILT | 4: BUILT / BUILT / BUILT / BUILT | `tinyassets/api/market.py:3373-3422`; ranking implementation at `tinyassets/daemon_server.py:3623-3690` | `tests/test_outcome_gate_claims.py:229-325` |
| Gate bonus attachment is paid-market-gated and node-only | BUILT | 4: BUILT / BUILT / BUILT / BUILT | gate-bonus handlers at `tinyassets/api/market.py:3428-3523` | `tests/test_gate_bonuses_mcp.py:84-173`; schema coverage `tests/test_gate_bonuses_schema.py:69-122` |
| Gate bonus resolution is single-winner but has current stranded states | BUILT | 4: BUILT / BUILT / BUILT / BUILT | `tinyassets/api/market.py:3538-3665` | `tests/test_gate_bonus_release.py:83-329`; `tests/test_gate_bonuses_mcp.py:278-498` |

### `universe-lifecycle-and-soul`

| Canonical requirement | Verdict | Scenarios | Representative implementation evidence | Representative test evidence |
|---|---|---|---|---|
| Universe identity is an opaque, time-sortable serial | BUILT | 2: BUILT / BUILT | `tinyassets/ids.py:20-33,44-62` | `tests/test_ids.py:18-39` |
| Universe creation is atomic and self-serializing | BUILT | 3: BUILT / BUILT / BUILT | `tinyassets/api/universe.py:4697-4717,4808-4825` | generated-id coverage `tests/test_first_contact.py:247-254,623-633`; rollback is source-inspected, with no focused failure-injection test |
| Creation seeds a blank, linked OKF soul bundle | BUILT | 3: BUILT / BUILT / BUILT | `tinyassets/api/universe.py:4720-4726`; `tinyassets/universe_bundle.py:364-407` | `tests/test_universe_bundle.py:45-199` |
| Authenticated creation grants founder ownership and binds a home | BUILT | 5: BUILT / BUILT / BUILT / BUILT / BUILT | best-effort registration, founder writes, marker split, and fallible uncompensated rollback at `tinyassets/api/universe.py:4697-4825` | Happy-path ownership at `tests/test_universe_write_boundary.py:148-169`; marker/home behavior at `tests/test_first_contact.py:504-633`; failure limitations are source-grounded |
| Governed soul edits are the sole learning-write path | BUILT | 4: BUILT / BUILT / BUILT / BUILT | `tinyassets/soul_edit.py:176-218` | `tests/test_soul_edit.py:42-192,363-394` |
| Soul edits are serialized and compare-and-swap guarded | BUILT | 2: BUILT / BUILT | `tinyassets/soul_edit.py:153-218` | `tests/test_soul_edit.py:225-278` |
| Clean-slate reset is the only lifecycle-end | BUILT | 3: BUILT / BUILT / BUILT | `tinyassets/reset.py:75-123` | `tests/test_reset_universes.py:54-117` |

### `universe-personification-and-relay`

| Canonical requirement | Verdict | Scenarios | Representative implementation evidence | Representative test evidence |
|---|---|---|---|---|
| Persona identity is sourced from the learned self-model, never the operational soul | BUILT | 2: BUILT / BUILT | `tinyassets/persona.py:30-50,94-127`; `tinyassets/universe_self_model.py:43-101` | `tests/test_persona.py:101-142,198-244` |
| Embodiment lives only in sanctioned channels; tool-result persona data is not an instruction | BUILT | 2: BUILT / BUILT | `tinyassets/universe_server.py:189-211`; `tinyassets/api/prompts.py:22-40` | `tests/test_persona.py:268-304,344-392` |
| The chatbot is a thin relay; first-person contact is the default and the chatbot never speaks as the universe | BUILT | 2: BUILT / BUILT | `tinyassets/api/prompts.py:469-474`; `tinyassets/universe_server.py:926-927` | `tests/test_relay_ux_prompts.py:25`; `tests/test_persona.py:344-392` |
| converse runs one first-person turn on the universe's assigned engine, grounded in its own bundle | BUILT | 4: BUILT / BUILT / BUILT / BUILT | `tinyassets/universe_intelligence.py:408-438`; sandbox-incapable provider refusal in provider implementation | `tests/test_universe_intelligence.py:33-87`; `tests/test_converse_handle.py:39-57` |
| The engine turn is confined by a fail-closed sandbox | BUILT | 2: BUILT / BUILT | `tinyassets/universe_intelligence.py:96-109,432-437` | `tests/test_universe_intelligence.py:262-295` |
| Learning is a separate tolerant model-extracted step with field-specific filtering, and reply delivery survives failures | BUILT | 5: BUILT / BUILT / BUILT / BUILT / BUILT | tolerant parse at `tinyassets/universe_intelligence.py:237-275`; field filters, identity-only regex, governed-read narrowing, and per-item handling at `:295-405`; reply preservation at `:439-444` | `tests/test_universe_intelligence.py:102-184,300-327`; unsupported-output and governed-read limitations are source-grounded |
| The MCP converse handle is founder-only and fail-closed | BUILT | 3: BUILT / BUILT / BUILT | `tinyassets/universe_server.py:916-960` | `tests/test_converse_handle.py:15-57` |

### `uptime-and-alarms`

| Canonical requirement | Verdict | Scenarios | Representative implementation evidence | Representative test evidence |
|---|---|---|---|---|
| Host-Independent Public Canary And Incident Lifecycle | BUILT | 3: BUILT / BUILT / BUILT | schedule and alarm orchestration at `.github/workflows/uptime-canary.yml:24-46,421-683`; MCP probe at `scripts/mcp_public_canary.py:70-79,188-240,295`; consecutive-red state at `scripts/uptime_canary.py:166-245` | `tests/test_mcp_public_canary.py:51-100`; `tests/test_uptime_canary.py:225-330` |
| Durable Acknowledgement-Aware Emergency Paging | BUILT | 3: BUILT / BUILT / BUILT | ladder/acknowledgement logic at `scripts/pushover_page.py:40-168,244-304`; issue-marker sink at `.github/workflows/uptime-canary.yml:592-671` | `tests/test_pushover_page.py:37-211,317-404` |
| Layered Bounded Host Recovery | BUILT | 3: BUILT / BUILT / BUILT | `deploy/tinyassets-daemon.service:30-31,57`; `deploy/tinyassets-watchdog.timer:20`; `deploy/daemon-watchdog.sh:14,26,78`; `deploy/daemon-watchdog.timer:7` | Python watchdog: `tests/test_watchdog.py:76-394`; the shell watchdog has no direct focused test and was source-inspected |
| Class-Specific P0 Triage And Re-Probe | BUILT | 3: BUILT / BUILT / BUILT | classifier at `scripts/triage_classify.py:248-339`; class-specific workflow branches and re-probe at `.github/workflows/p0-outage-triage.yml:117-159,174-438,493-572` | `tests/test_triage_classify.py:25-373`; `tests/test_p0_triage_workflow.py:55-237` |
| Digest-Pinned Deploy Admission Rollback And Receipt | BUILT | 3: BUILT / BUILT / BUILT | digest admission/previous-image capture at `.github/workflows/deploy-prod.yml:119-200`; receipt and failure incident at `:832-975`; env installer boundary at `deploy/install-tinyassets-env.sh:1-138` | `tests/test_deploy_prod_workflow.py:53-534`; release receipt read `tests/test_api_status.py:122-165` |
| Nightly Two-Tier Backup And Manual Fresh-Host Data-Restore Drill | BUILT | 3: BUILT / BUILT / BUILT | strict brain/full backup tiers at `deploy/backup.sh:107-185,217-243`; restore-without-start at `deploy/backup-restore.sh:112-166`; drill transfer/start/probe at `.github/workflows/dr-drill.yml:256-359` | `tests/test_backup_script.py:106-393`; `tests/test_backup_restore_drill_invariants.py:36-231`; `tests/test_dr_drill_workflow.py:96-384` |

### `wiki-commons`

| Canonical requirement | Verdict | Scenarios | Representative implementation evidence | Representative test evidence |
|---|---|---|---|---|
| Wiki root resolution and page-substrate layout | BUILT | 3: BUILT / BUILT / BUILT | `tinyassets/api/helpers.py:172-204`; `tinyassets/api/wiki.py:2352` | `tests/test_wiki_scaffold.py:28-77`; path coverage in `tests/test_wiki_path_resolver.py` |
| Seed taxonomy is a set of defaults, not a closed whitelist | BUILT | 3: BUILT / BUILT / BUILT | category/slug handling in `tinyassets/api/wiki.py:478-553` | `tests/test_wiki_tools.py:296-337` |
| Draft-then-promote gate for freeform pages | BUILT | 3: BUILT / BUILT / BUILT | `tinyassets/api/wiki.py:796-887,1136-1201` | `tests/test_wiki_tools.py:265-304,426-475` |
| Typed filings bypass the draft gate with per-kind IDs and dedup | BUILT | 3: BUILT / BUILT / BUILT | `tinyassets/api/wiki.py:1978-2130` | `tests/test_wiki_file_bug.py:465-595`; `tests/test_wiki_file_bug_dedup.py:56-131` |
| Compare-and-swap patch and supersede lifecycle | BUILT | 3: BUILT / BUILT / BUILT | `tinyassets/api/wiki.py:889-1005,1228-1326` | patch/supersede coverage in `tests/test_wiki_tools.py:351-417,638-680` |
| Action surface, universe ACL, and scope gating | BUILT | 3: BUILT / BUILT / BUILT | action tables at `tinyassets/api/wiki.py:2319-2348`; universe root routing at `:2352` | `tests/test_wiki_tools.py:716-721,915-948`; ACL coverage in `tests/test_api_wiki.py` |
| First-party canon writes bypass the MCP ACL gate; in-node access is read-only | BUILT | 3: BUILT / BUILT / BUILT | first-party canon writer at `tinyassets/api/wiki.py:2362-2430`; in-node read-only mapping at `tinyassets/graph_compiler.py:1387-1388`; publication effector at `tinyassets/effectors/wiki_write_back.py:274-481` | `tests/test_wiki_write_back_effector.py:54-187`; canon integration in `tests/test_universe_intelligence.py:206-251` |
| Trigger receipts use one mutable per-attempt row attempted before enqueue | BUILT | 4: BUILT / BUILT / BUILT / BUILT | fail-open pending insert/enqueue at `tinyassets/api/wiki.py:2154-2290`; mutable row and unrestricted updates at `tinyassets/wiki/trigger_receipts.py:115-330`; orphan detection at `:382-410` | Normal transitions/orphans at `tests/test_wiki_trigger_receipts.py:62-127,212-239`; receipt-failure/terminal-overwrite limitations are source-grounded |

## Reconciled limitations and hardening successors

The six former Batch C mismatches now state current behavior exactly and are
BUILT as bounded. They are not the desired endpoint. The separate
`harden-canonical-absolute-guarantees` lane owns strict integer parsing and bid
migration, exclusive settlement creation, durable Goal attribution,
transactional founder creation, source-grounded learning, and guarded
single-terminal receipts, with the named adversarial/concurrency tests.

## Active-change overlap

- `openspec/changes/build-forward-platform-capabilities/specs/paid-market-economy/spec.md:3-19` adds two FUTURE transaction-transport/differential-test requirements.
- `openspec/changes/test-identity-and-reset/specs/universe-lifecycle-and-soul/spec.md:49-83` adds five FUTURE scoped-test-reset scenarios.
- `openspec/changes/universe-creation/specs/universe-lifecycle-and-soul/spec.md:3-45` adds four FUTURE lifecycle requirements and eight scenarios.
- `openspec/changes/reconcile-universe-personification-relay/specs/universe-personification-and-relay/spec.md:13-176` adds seven FUTURE personification requirements and seventeen scenarios.
- No active delta targets `provider-routing`, `public-website-surface`, `shared-goals-and-convergence`, `uptime-and-alarms`, or `wiki-commons`.

## Material shipped behavior still lacking canonical behavioral coverage

- Provider bridge retry/fallback: three attempts with exponential delay plus optional fallback response at `tinyassets/providers/call.py:174-192,213-266`.
- Goal compatibility aliases (`list_workflow_goals`, `search_workflow_goals`, `get_workflow_goal`, `propose_workflow_goal`) at `tinyassets/api/market.py:2371-2392`.
- Authenticated request-scoped versus anonymous host-global `switch_universe` behavior at `tinyassets/api/universe.py:4650-4688`.
- Wiki action names are catalogued, but the substantive cosign, protected/hash-guarded delete, consolidation, lint, and project-sync contracts are not: `tinyassets/api/wiki.py:1007,1055,1431,1535,1891`.
- DNS incident canary at `.github/workflows/dns-canary.yml:13-16,80-181`.
- LLM-binding incident canary at `.github/workflows/llm-binding-canary.yml:18-20,50-219`.
- Release reconciliation controller at `.github/workflows/release-reconcile.yml:41-45,68-172`.
- Disk-pressure issue/rotation/auto-prune path at `deploy/tinyassets-disk-watch.service:1-45` and `deploy/tinyassets-disk-watch.timer:20`.

## Quality note

The recurring grounding failure is over-broad absolute wording supported only by happy-path tests: `never floats`, `write-once`, `every successful write`, mandatory registration, `fail-closed`, and `single terminal` each lacks the adversarial conversion, failure, or race test needed to substantiate it. Future as-built backfills should require at least one failure/race test for each absolute guarantee before classifying it BUILT.
