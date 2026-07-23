# Status

Live steering only. **≤60 lines canonical (~4 KB guidance).** Concerns/Work = one line each; landed rows are deleted; Forever rule = 24/7 uptime with zero hosts online. **Scope (2026-05-19):** project-folder-access AIs; substantive work lives in the MCP brain (`PR-###`/`BUG-###` + dispatcher + auto-change loop), while coordination without a wiki home stays here; check both.

## Concerns

- **[P0 filed:2026-07-22 verified:2026-07-22]** Newborn contact has no BYOC/market authority path; never use maintainer quota. See #1582.
- **[P0 filed:2026-07-21 verified:2026-07-21]** #1489: unauth LAN leaks sessions and permits CSRF writes/paid hires. Codex: ADAPT; do not LAN-run.
- **[P1 filed:2026-07-02 verified:2026-07-22]** No OS engine sandbox. Live `converse` is in-process-confined only (WebFetch-only, cwd-pin, rot-prone denylist); #1485 is a fail-closed seam.
- [filed:2026-07-02 verified:2026-07-22] Reshape residuals: WebFetch SSRF guard, `write_page` scope=commons, legacy `mcp_server.py` doors.
- **[P2 filed:2026-06-30 verified:2026-07-22]** slice-3 F5 / escrow F1: `_current_actor` env fallback (engine_helpers.py:192) bypasses permissions.py.
- [filed:2026-07-02 verified:2026-07-22] Dogfood open: persona payload rework + OKF reserved-file frontmatter. Founder-seed-at-create closed by #1462.
- [filed:2026-04-17 verified:2026-07-22] Privacy Q6.3 still platform: gemini/groq/grok remain in the fallback chains (`providers/router.py:89`).
- **[P1 filed:2026-04-30]** Castles II run `28479d8ddfb44488`: `provider_exhausted` at `candidate_discovery` (BUG-038/039); blocks branch-run proof.
- [filed:2026-05-19] Wiki drifting to agent scratch space (81% of post-05-01 notes); host conversation: split coordination off the knowledge wiki?
- [filed:2026-07-14 verified:2026-07-14] Watch: anon-write gate LIVE + `ui-test` passed; pending first organic authenticated-user write.
- [filed:2026-07-13 verified:2026-07-15] `workflow-voice` (dormant) has 3 stale `pending` queue rows — review before ever activating it.

## Work

| Task | Files | Depends | Status |
|------|-------|---------|--------|
| **Fail closed universe provider auth overlay** — partial overlay or swallowed helper error can retain inherited host subscription credentials | openspec/changes/fail-closed-provider-auth-overlay/; openspec/specs/credential-vault/spec.md; tinyassets/providers/base.py; tests/test_credential_fail_closed.py | #1607 | claimed:codex-gpt56-desktop ACTIVE 2026-07-22 |
| **Harden canonical absolute guarantees** — money/settlement, attribution, birth, learning, receipts | openspec/changes/harden-canonical-absolute-guarantees/; tinyassets/payments/identifiers.py; tinyassets/bid/node_bid.py; tinyassets/bid/settlements.py; tinyassets/api/market.py; tinyassets/api/universe.py; tinyassets/universe_intelligence.py; tinyassets/wiki/trigger_receipts.py; tests/test_payments_schema.py; tests/test_node_bid.py; tests/test_api_market.py; tests/test_api_universe.py; tests/test_universe_intelligence.py; tests/test_wiki_trigger_receipts.py | private Goal visibility lane first; active paid/universe/relay lanes | pending |
| **Enforce private Goal read visibility** — signed owner request identity only; no caller/env authority; explicit signed host exception requires separate decision | openspec/changes/enforce-private-goal-read-visibility/; openspec/specs/shared-goals-and-convergence/spec.md; tinyassets/daemon_server.py; tinyassets/api/market.py; tests/test_private_goal_visibility.py; tests/test_goals_surface.py; tests/test_branch_visibility.py; tests/test_api_market.py; packaging/claude-plugin/plugins/tinyassets-universe-server/runtime/tinyassets/daemon_server.py; packaging/claude-plugin/plugins/tinyassets-universe-server/runtime/tinyassets/api/market.py | retire/supersede draft #1554; alias list/search/get regressions; opposite-provider review | pending |
| **Backfill 8 dependency-bound shipped contracts into canonical OpenSpec** — credential, daemon identity/runtime, graph, OKF, live MCP, universe switch, uptime | openspec/changes/backfill-dependent-shipped-contracts/ | credential/distributed/OKF/connector/universe/release lanes | pending |
| **Correct merged legacy disposition after PR #1622 authority review (draft PR #1621)** | docs/audits/2026-07-22-legacy-spec-disposition.md; docs/specs/INDEX.md; openspec/changes/brain-okf-canonical-store/tasks.md | #1622 | claimed:codex-gpt56-desktop ACTIVE 2026-07-22 |
| **Review draft PR #1623 corrected authority** — opposite-provider gate pending | openspec/changes/archive/2026-07-23-correct-independent-backfill-authority/; openspec/specs/external-effect-adapters/spec.md; openspec/specs/provider-routing/spec.md; docs/audits/2026-07-22-openspec-full-coverage-audit.md; tinyassets/providers/call.py; packaging/claude-plugin/plugins/tinyassets-universe-server/runtime/tinyassets/providers/call.py | #1621 legacy correction; opposite-provider approval | claimed:codex-gpt56-desktop ACTIVE 2026-07-22 |
| **Promote runtime-fiction memory graph into OpenSpec** | openspec/changes/runtime-fiction-memory-graph/ | brain-okf-canonical-store | pending |
| **Reconcile shipped hyperparameter-importance evaluator contract** | openspec/changes/reconcile-hyperparameter-importance-evaluator/ | legacy disposition correction; science-domain lane | pending |
| **Resolve target-spec PLAN conflicts** — store, private data, primitive contracts, privacy guidance | PLAN.md | host selects coherent positions | host-decision |
| **Specify uncovered full-platform targets** — collaboration, moderation, tray, market, portability, authoring, handoffs | openspec/changes/complete-full-platform-target-specs/ | PLAN decisions; build-forward-platform-capabilities | pending |
| **Release reconcile event trigger** — retain cron backstop; also reconcile after proven-under-load `Docker build smoke` completions; stable concurrency coalesces stampedes | .github/workflows/release-reconcile.yml, openspec/changes/release-reconcile-event-trigger/ | live runs 1892, 1883 | claimed:codex-gpt5-desktop ACTIVE 2026-07-22 |
| **R2-1a set_engine must constrain allowed_providers** — host-credential half LANDED 92dd60c5 (fail-closed + mutation proof). Still open: a founder's own key silently falls through the writer chain to a provider they never chose | tinyassets/providers/router.py, tinyassets/api/engine.py, tests/ | - | pending |
| **R2-1b provider receipt** — no receipt exists, so 92dd60c5 is asserted but UNAUDITABLE in prod. Design decided: thread provider off the same result object, NOT the `_last_provider` global (races); report credential class; cover BOTH converse writer calls | tinyassets/providers/call.py, tinyassets/universe_intelligence.py, tests/ | R2-1a | pending |
| **R2-4 wiki onboarding split** — read_page returns agent-coordination logs; assistant refused to build and offered to replace TinyAssets with a chat artifact (live 2026-07-21) | tinyassets/api/wiki.py, wiki/ | - | in-flight PR #1550 |
| **Universe-personification relay survivors** — #1515 retires the reversed change; successor stays active/unbuilt. Page-write boundary awaits host decision + complete mutation inventory | openspec/changes/reconcile-universe-personification-relay/ | #1583 host decision, universe-visibility, brain-okf-canonical-store, live-mcp-connector-surface | pending |
| Paid-market Track E Wave 2 transport as an OpenSpec change; renumber migrations + add schema_migrations before 006–008 go live | openspec/, tinyassets/paid_market/ | - | pending |
| In-node enqueue flag flip — Codex ADAPT asks landed (`graph_compiler.py:1406-1560`), still dark; §14 proof passes but global-queue + per-origin lineage caps have no concurrent boundary coverage | tinyassets/graph_compiler.py, tests/test_node_enqueue_*.py | `docs/audits/2026-05-30-in-node-enqueue-codex-review.md` | dev-ready |
| External directory acceptance — registry metadata repaired; needs clean ChatGPT/Claude proof + first-user evidence | docs/ops/mcp-* | - | host-action |
| OpenAI app submission hardening — `chatgpt-app-submission.json` on disk; submission docs/proof pending | chatgpt-app-submission.json, docs/ops/openai-app-submission-*.md | clean ChatGPT proof | dev-ready |
| Land #1484 — `_repo_root()` conflated `TINYASSETS_REPO_ROOT` (storage) with the bundled-source root, emptying deployed review context. The env is load-bearing; do NOT drop it | tinyassets/api/universe.py, deploy/compose.yml | - | host-review |
| Restore authenticated wiki write-roundtrip canary coverage — lost to the #1441 anon-write gate by design; needs a canary service credential | docs/ops/acceptance-probe-catalog.md, scripts/uptime_canary.py | - | host-decision |
| Mark-branch canonical decision (Task #33 phase 0) | live MCP `goals action=propose/bind/set_canonical` | - | host-decision |
| BUG-018 canonical filename trailing-hyphen — rename canonical, or `wiki action=promote` a draft over it? | wiki | - | host-decision |
| Fire DR drill #3 via workflow_dispatch | `.github/workflows/dr-drill.yml` | - | host or lead-with-PAT |
| Re-register `TinyAssets DEV` ChatGPT connector as workspace admin | OpenAI workspace admin | - | host-action |
| Memory-scope Stage 2c flag | - | 30d clean | monitoring |

## Live brain notes

Provider capacity: Claude unavailable until the 2026-07-24 evening PT reset; use non-Claude capacity. Brain sweep: `.claude/agent-memory/navigator/wiki_sweep_cursor.md`; in flight PR-129/131/139; universes Meridian Ashes / Etsy Printify v2 / Markovic.

## Next

1. **Cheat-loop CI retired (host 2026-06-25)** — `AUTO_FIX_DISABLED=true`; strip intake/writer/checker machinery, keep get_status, deploy lanes, MCP canaries, dispatcher.
2. **No-shims-ever** + **platform responsibility model** + **public-surface probes after DNS/tunnel/Worker/connector changes** (canonical: https://tinyassets.io/mcp).
3. **Scoping rules apply to design questions themselves** — if X composes from primitives, do NOT offer "platform builds it" when steering.
4. **Spec-driven development is the standard (host 2026-07-19)** — every substantive change starts as an OpenSpec change; as-built specs in `openspec/specs/`.
