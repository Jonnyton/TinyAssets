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
| **Moderation authority contract** — #1662 APPROVED at `62c47ae2`; store/service/API/discovery/§14 remain incomplete | tinyassets/moderation/__init__.py; tinyassets/moderation/models.py; tinyassets/moderation/policy.py; tests/test_moderation_authority.py; docs/audits/2026-07-23-canonical-production-store-decision-packet.md | task 1.4 opposite-family APPROVE; host decision: canonical production store/migration home; no new MCP handle | in-flight PR #1662 |
| **Plan flag intake mutation** — pure non-mutating planner only; no persistence/API/router or atomicity claim | tinyassets/moderation/service.py; tests/test_moderation_service.py; STATUS.md; .agents/worktrees.md; REFLECTION.md | stacked on #1662 authority contract; canonical-store decision still blocks committed mutation and discovery | claimed:codex-gpt5-desktop-moderation-flags ACTIVE 2026-07-23 |
| **Monitor converged host uptime installation** — prove exact landed commit on disposable Debian plus real install workflow and watchdog/disk/backup/prune executions | docs/audits/2026-07-23-host-uptime-installer-concurrency-proof.md; production workflow/systemd evidence | post-merge exact SHA | monitoring |
| **Fail closed universe provider auth overlay** — partial overlay or swallowed helper error can retain inherited host subscription credentials | openspec/changes/fail-closed-provider-auth-overlay/; openspec/specs/credential-vault/spec.md; tinyassets/providers/base.py; tests/test_credential_fail_closed.py | #1607 | claimed:codex-gpt56-desktop ACTIVE 2026-07-22 |
| **Harden canonical absolute guarantees** — money/settlement, Goal attribution, birth, learning, receipts | openspec/changes/harden-canonical-absolute-guarantees/; tinyassets/{payments/identifiers.py,bid/node_bid.py,bid/settlements.py,api/market.py,api/universe.py,universe_intelligence.py,wiki/trigger_receipts.py}; focused tests | full-coverage audit; Resolve seven canonical OpenSpec drift findings; active paid/universe/relay lanes | pending |
| **Backfill remaining credential-vault shipped contracts** — canonical owner landed via #1607; alias/first-record selection remains; re-check fixed-temp truth after #1606 disposition | openspec/changes/backfill-credential-vault-shipped-contracts/ | fail-closed provider overlay releases `openspec/specs/credential-vault/spec.md`; #1606 or declared successor settles replacement semantics/disposition | pending |
| **Promote runtime-fiction memory graph into OpenSpec** | openspec/changes/runtime-fiction-memory-graph/ | brain-okf-canonical-store | pending |
| **Promote future hyperparameter science node/fixtures** — target-only sweep schema, methods, warnings, and artifacts; do not conflate with the shipped evaluator | openspec/changes/hyperparameter-importance-science-domain/ | science-domain owner/design review | pending |
| **Resolve target-spec PLAN conflicts** — store, private data, primitives, privacy guidance | PLAN.md | full-coverage audit; host selects coherent positions | host-decision |
| **Specify PLAN-gated full-platform targets** — catalog/collaboration, discovery/remix, presence, portability/deletion/succession/feedback | openspec/changes/complete-plan-gated-platform-targets/ | PLAN store/private-data/primitive/privacy decisions; build-forward-platform-capabilities | pending |
| **Release reconcile event trigger** — retain cron backstop; also reconcile after proven-under-load `Docker build smoke` completions; stable concurrency coalesces stampedes | .github/workflows/release-reconcile.yml, openspec/changes/release-reconcile-event-trigger/ | live runs 1892, 1883 | claimed:codex-gpt5-desktop ACTIVE 2026-07-22 |
| **R2-1a set_engine must constrain allowed_providers** — host-credential half LANDED 92dd60c5 (fail-closed + mutation proof). Still open: a founder's own key silently falls through the writer chain to a provider they never chose | tinyassets/providers/router.py, tinyassets/api/engine.py, tests/ | - | pending |
| **R2-1b provider-attempt receipts** — strict-valid result-local reply + learning evidence; preserve `call_provider()->str`; no secret-bearing fields or invented sink | openspec/changes/provider-attempt-receipts/ | #1606 / R2-1a apply blocker; runtime files remain unclaimed | pending |
| **R2-4 wiki onboarding split** — read_page returns agent-coordination logs; assistant refused to build and offered to replace TinyAssets with a chat artifact (live 2026-07-21) | tinyassets/api/wiki.py, wiki/ | - | in-flight PR #1550 |
| **Universe-personification relay survivors** — #1515 retires the reversed change; successor stays active/unbuilt. Page-write boundary awaits host decision + complete mutation inventory | openspec/changes/reconcile-universe-personification-relay/ | #1583 host decision, universe-visibility, brain-okf-canonical-store, live-mcp-connector-surface | pending |
| **Implement paid-market workflow + live-price targets** — durable inbox/bid/match/claim/delivery plus quote authority and manipulation controls | tinyassets/paid_market/; prototype/full-platform-v0/migrations/; tests/test_paid_market_core.py; tests/test_api_market.py | active `paid-market-track-e-wave-2-transport` and `paid-market-live-price-discovery`; Harden canonical absolute guarantees; #1440; R2-1; S14/B36; boundary/tenant/domain owners | pending |
| In-node enqueue flag flip — Codex ADAPT asks landed (`graph_compiler.py:1406-1560`), still dark; §14 proof passes but global-queue + per-origin lineage caps have no concurrent boundary coverage | tinyassets/graph_compiler.py, tests/test_node_enqueue_*.py | `docs/audits/2026-05-30-in-node-enqueue-codex-review.md` | dev-ready |
| External directory acceptance — registry metadata repaired; needs clean ChatGPT/Claude proof + first-user evidence | docs/ops/mcp-* | - | host-action |
| OpenAI app submission hardening — `chatgpt-app-submission.json` on disk; submission docs/proof pending | chatgpt-app-submission.json, docs/ops/openai-app-submission-*.md | clean ChatGPT proof | dev-ready |
| Land #1484 — `_repo_root()` conflated `TINYASSETS_REPO_ROOT` (storage) with the bundled-source root, emptying deployed review context. The env is load-bearing; do NOT drop it | tinyassets/api/universe.py, deploy/compose.yml | - | host-review |
| Restore authenticated wiki write-roundtrip canary coverage — lost to the #1441 anon-write gate by design; needs a canary service credential | docs/ops/acceptance-probe-catalog.md, scripts/uptime_canary.py | - | host-decision |
| Mark-branch canonical decision (Task #33 phase 0) | live MCP `goals action=propose/bind/set_canonical` | - | host-decision |
| BUG-018 canonical filename trailing-hyphen — rename canonical, or `wiki action=promote` a draft over it? | wiki | - | host-decision |
| **Monitor hardened DR drill #3** — dispatch exact landed SHA; record bounded provider result, checksum/restored-state proof, and deletion outcome | docs/ops/dr-drill-log.md; production workflow/issue evidence | hardening PR must land before re-dispatch | monitoring |
| Re-register `TinyAssets DEV` ChatGPT connector as workspace admin | OpenAI workspace admin | - | host-action |

## Live brain notes

Provider capacity: Claude unavailable until the 2026-07-24 evening PT reset; use non-Claude capacity. Brain sweep: `.claude/agent-memory/navigator/wiki_sweep_cursor.md`; in flight PR-129/131/139; universes Meridian Ashes / Etsy Printify v2 / Markovic.

## Next

1. **Cheat-loop CI retired (host 2026-06-25)** — `AUTO_FIX_DISABLED=true`; strip intake/writer/checker machinery, keep get_status, deploy lanes, MCP canaries, dispatcher.
2. **No-shims-ever** + **platform responsibility model** + **public-surface probes after DNS/tunnel/Worker/connector changes** (canonical: https://tinyassets.io/mcp).
3. **Scoping rules apply to design questions themselves** — if X composes from primitives, do NOT offer "platform builds it" when steering.
4. **Spec-driven development is the standard (host 2026-07-19)** — every substantive change starts as an OpenSpec change; as-built specs in `openspec/specs/`.
