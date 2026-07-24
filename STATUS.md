# Status

Live steering only. **≤60 lines canonical (~4 KB guidance).** Concerns/Work = one line each; landed rows are deleted; Forever rule = 24/7 uptime with zero hosts online. **Scope (2026-05-19):** project-folder-access AIs; substantive work lives in the MCP brain (`PR-###`/`BUG-###` + dispatcher + auto-change loop), while coordination without a wiki home stays here; check both.

## Concerns

- **[P1 filed:2026-07-23 verified:2026-07-23]** Watch deploy terminal truth: repository repair approved; live pre-image/post-image failure exercises remain.
- **[P1 filed:2026-07-23]** Watch #1645: no post-fix real P0 repair-failure event yet; structural/CI proof only.
- **[P1 filed:2026-07-22 verified:2026-07-23]** Runtime rejects authorized `operator_request`; dispatcher enables only `host_request`. #1628 is spec-only.
- **[P0 filed:2026-07-22 verified:2026-07-22]** Newborn contact has no BYOC/market authority path; never use maintainer quota. See #1582.
- **[P0 filed:2026-07-21 verified:2026-07-21]** #1489: unauth LAN leaks sessions and permits CSRF writes/paid hires. Codex: ADAPT; do not LAN-run.
- **[P1 filed:2026-07-02 verified:2026-07-22]** No OS engine sandbox. Live `converse` is in-process-confined only (WebFetch-only, cwd-pin, rot-prone denylist); #1485 is a fail-closed seam.
- [filed:2026-07-02 verified:2026-07-22] Reshape residuals: WebFetch SSRF guard, `write_page` scope=commons, legacy `mcp_server.py` doors.
- **[P2 filed:2026-06-30 verified:2026-07-22]** slice-3 F5 / escrow F1: `_current_actor` env fallback (engine_helpers.py:192) bypasses permissions.py.
- [filed:2026-07-02 verified:2026-07-22] Dogfood open: persona payload rework + OKF reserved-file frontmatter. Founder-seed-at-create closed by #1462.
- [filed:2026-04-17 verified:2026-07-22] Privacy Q6.3 still platform: gemini/groq/grok remain in the fallback chains (`providers/router.py:89`).
- **[P1 filed:2026-04-30]** Castles II run `28479d8ddfb44488`: `provider_exhausted` at `candidate_discovery` (BUG-038/039); blocks branch-run proof.
- [filed:2026-05-19] Wiki drifting to agent scratch space (81% of post-05-01 notes); host conversation: split coordination off the knowledge wiki?
- [filed:2026-07-13 verified:2026-07-15] `workflow-voice` (dormant) has 3 stale `pending` queue rows — review before ever activating it.

## Work

| Task | Files | Depends | Status |
|------|-------|---------|--------|
| **Fail closed universe provider auth overlay** — partial overlay or swallowed helper error can retain inherited host subscription credentials | openspec/changes/fail-closed-provider-auth-overlay/; openspec/specs/credential-vault/spec.md; tinyassets/providers/base.py; tests/test_credential_fail_closed.py | #1607 | claimed:codex-gpt56-desktop ACTIVE 2026-07-22 |
| **Harden canonical absolute guarantees** — money/settlement, Goal attribution, birth, learning, receipts | openspec/changes/harden-canonical-absolute-guarantees/; tinyassets/{payments/identifiers.py,bid/node_bid.py,bid/settlements.py,api/market.py,api/universe.py,universe_intelligence.py,wiki/trigger_receipts.py}; focused tests | full-coverage audit; Resolve seven canonical OpenSpec drift findings; active paid/universe/relay lanes | pending |
| **Backfill remaining credential-vault shipped contracts** — canonical owner landed via #1607; alias/first-record selection remains; re-check fixed-temp truth after #1606 disposition | openspec/changes/backfill-credential-vault-shipped-contracts/ | fail-closed provider overlay releases `openspec/specs/credential-vault/spec.md`; #1606 or declared successor settles replacement semantics/disposition | pending |
| **Promote runtime-fiction memory graph into OpenSpec** | openspec/changes/runtime-fiction-memory-graph/ | brain-okf-canonical-store | pending |
| **Promote future hyperparameter science node/fixtures** — target-only sweep schema, methods, warnings, and artifacts; do not conflate with the shipped evaluator | openspec/changes/hyperparameter-importance-science-domain/ | science-domain owner/design review | pending |
| **Fold approved target architecture into PLAN** — typed authorities; private-by-default placement; seven composable public routers; context-scoped policy/best-practice packs applied with user/chatbot intent | PLAN.md; docs/audits/2026-07-23-full-platform-plan-decision-packet.md | host direction received 2026-07-24; Claude opposite-provider review before PLAN/OpenSpec/build/push | pending |
| **Specify PLAN-gated full-platform targets** — catalog/collaboration, discovery/remix, presence, portability/deletion/succession/feedback | openspec/changes/complete-plan-gated-platform-targets/ | PLAN store/private-data/primitive/privacy decisions; build-forward-platform-capabilities | pending |
| **Release reconcile event trigger** — retain cron backstop; also reconcile after proven-under-load `Docker build smoke` completions; stable concurrency coalesces stampedes | .github/workflows/release-reconcile.yml, openspec/changes/release-reconcile-event-trigger/ | live runs 1892, 1883 | claimed:codex-gpt5-desktop ACTIVE 2026-07-22 |
| **R2-1a set_engine must constrain allowed_providers** — host-credential half LANDED 92dd60c5 (fail-closed + mutation proof). Still open: a founder's own key silently falls through the writer chain to a provider they never chose | tinyassets/providers/router.py, tinyassets/api/engine.py, tests/ | - | pending |
| **R2-1b provider-attempt receipts** — strict-valid result-local reply + learning evidence; preserve `call_provider()->str`; no secret-bearing fields or invented sink | openspec/changes/provider-attempt-receipts/ | #1606 / R2-1a apply blocker; runtime files remain unclaimed | pending |
| **R2-4 wiki onboarding split** — read_page returns agent-coordination logs; assistant refused to build and offered to replace TinyAssets with a chat artifact (live 2026-07-21) | tinyassets/api/wiki.py, wiki/ | - | in-flight PR #1550 |
| **Universe-personification relay survivors** — host delegated page-write boundary: one `write_page`, explicit `scope=commons|universe`, ambiguous intent fails closed, all shells converge | openspec/changes/reconcile-universe-personification-relay/; future canonical page-write boundary change | complete mutation inventory; universe-visibility; brain-okf-canonical-store; live-mcp-connector-surface; independent review | pending |
| **Retire `/mcp-directory`; converge every host on canonical `/mcp`** — one product name, endpoint, seven-handle experience, privacy/auth/annotation contract, and catalog | openspec/changes/retire-mcp-directory-surface/; openspec/specs/live-mcp-connector-surface/spec.md; tinyassets/{directory_server.py,universe_server.py,connector_catalog.py}; deploy/cloudflare-worker/{worker.js,worker.test.js}; server.json; packaging/mcpb/manifest.json; docs/ops/mcp-*; tests/ | host directive 2026-07-24; reconcile-external-connector-manifests; rendered ChatGPT/Claude migration proof | pending |
| **Implement paid-market workflow + live-price targets** — durable inbox/bid/match/claim/delivery plus quote authority and manipulation controls | tinyassets/paid_market/; prototype/full-platform-v0/migrations/; tests/test_paid_market_core.py; tests/test_api_market.py | active `paid-market-track-e-wave-2-transport` and `paid-market-live-price-discovery`; Harden canonical absolute guarantees; #1440; R2-1; S14/B36; boundary/tenant/domain owners | pending |
| **Observe post-fix in-node enqueue use** — #1672 merged; no production-clean user evidence yet | production traces/logs; STATUS.md | deploy #1672, then inspect organic enqueue use | monitoring |
| External directory acceptance — migrate registry/hosts to canonical `/mcp`; then needs clean ChatGPT/Claude proof + first-user evidence | docs/ops/mcp-* | retire-mcp-directory-surface | host-action |
| OpenAI app submission hardening — target canonical `/mcp`; update seven-handle tests/copy, serve domain challenge, refresh proof | chatgpt-app-submission.json, docs/ops/openai-app-submission-*.md, deploy/cloudflare-worker/{worker.js,worker.test.js} | retire-mcp-directory-surface; `TinyAssets` re-registration + clean ChatGPT proof | dev-ready |
| Land #1484 — `_repo_root()` conflated `TINYASSETS_REPO_ROOT` (storage) with the bundled-source root, emptying deployed review context. The env is load-bearing; do NOT drop it | tinyassets/api/universe.py, deploy/compose.yml | - | host-review |
| **Specify least-privilege authenticated wiki write canary** — current probe proves anonymous rejection + old-marker read, not authenticated write/read; add scoped M2M identity before any secret | openspec/changes/authenticated-wiki-write-canary/; openspec/specs/{identity-auth-and-access-control,uptime-and-alarms}/spec.md; tinyassets/auth/workos_provider.py; tinyassets/api/permissions.py; scripts/wiki_canary.py; .github/workflows/uptime-canary.yml; docs/ops/acceptance-probe-catalog.md; tests/ | auth/permission review; anonymous gate remains separate | pending |
| Provision production wiki-canary service principal and GitHub secret after scoped M2M support lands | WorkOS admin; GitHub Actions secrets | authenticated-wiki-write-canary implementation + review | host-action |
| Register the ChatGPT connector as `TinyAssets` against canonical `https://tinyassets.io/mcp`; verify exactly 7 handles | OpenAI workspace admin | retire-mcp-directory-surface + canonical `/mcp` review-safety proof | host-action |

## Live brain notes

Provider capacity: Claude unavailable until the 2026-07-24 evening PT reset; use non-Claude capacity. Brain sweep: `.claude/agent-memory/navigator/wiki_sweep_cursor.md`; in flight PR-129/131/139; universes Meridian Ashes / Etsy Printify v2 / Markovic.

## Next

1. **Cheat-loop CI retired (host 2026-06-25)** — `AUTO_FIX_DISABLED=true`; strip intake/writer/checker machinery, keep get_status, deploy lanes, MCP canaries, dispatcher.
2. **No-shims-ever** + **platform responsibility model** + **public-surface probes after DNS/tunnel/Worker/connector changes** (canonical: https://tinyassets.io/mcp).
3. **Scoping rules apply to design questions themselves** — if X composes from primitives, do NOT offer "platform builds it" when steering.
4. **Spec-driven development is the standard (host 2026-07-19)** — every substantive change starts as an OpenSpec change; as-built specs in `openspec/specs/`.
