# OpenSpec Full-Coverage Audit

- **Freshness:** 2026-07-23 UTC; canonical re-audit completed through PR #1619,
  legacy authority classified through PR #1620, and nine independent shipped
  contract groups source-reviewed, synced, and archived
- **Code/spec baseline:** PR #1620 merge on `origin/main` at `8cab31d8`, plus
  archived change `2026-07-23-backfill-independent-shipped-contracts`
- **Scope:** every PLAN module, every Forever Rule surface, canonical
  `openspec/specs/`, active OpenSpec changes, and substantive code landed after
  the 2026-07-19 `spec-out-existing-platform` baseline
- **Method:** requirement-heading inventory, PLAN-to-code-to-spec mapping,
  post-baseline first-parent review, and three independent read-only module
  audits

## Current reconciliation status

The original baseline verdict below is now historical. The repository has
since landed eight Batch A canonical spec files, enriched the core runtime,
provider/credential, and knowledge/memory owners, reclassified the eight
forward-vision files, classified all 52 legacy specification documents, and
archived nine independent shipped-contract backfills. The strict-valid tree
now contains **25 canonical capabilities** and **9 active changes**. The eight
forward-vision capability directories no longer exist under
`openspec/specs/`; their shipped pure-core subsets are canonical and their
unbuilt outcomes are preserved by the active
`build-forward-platform-capabilities` change.

This progress does **not** yet prove full coverage. The canonical grounding
pass identified seven inaccurate requirements; that correction plus the
independently reviewed backfill now makes all 231 canonical requirements true
as written. Eight dependency-bound shipped groups and eight full-platform
target groups remain. The accurate answer is: current canonical OpenSpec
describes built behavior, but not everything built or targeted is fully
specified yet.

### Design-truth conflicts that block blind target-spec transcription

The integrated 2026-04-18 architecture remains a target reference, but newer
PLAN rules supersede or contradict several of its concrete prescriptions. A
future OpenSpec change cannot silently choose among these:

| Conflict | Current evidence | Consequence |
|---|---|---|
| Canonical platform store | PLAN's system-shape reference says Postgres/Supabase is canonical and GitHub is an export sink; PLAN's Open Tensions says that decision is unresolved. | Catalog, collaboration, export, and deletion specs need a host-approved single position. |
| Private data placement | PLAN's Commons-first rule says private content stays on hosts and the platform never stores it; architecture §17 prescribes private Supabase Storage, private concept visibility, and field-level platform records. | Do not spec private platform storage or private platform catalog rows until reconciled. |
| Public tool surface | PLAN fixes five permissioned handles and requires minimal primitives; architecture §§15, 21, 23, 27, 31, and 33 name many standalone RPC/MCP tools. | Preserve behaviors only as targets under the canonical handles unless a new irreducible primitive is approved. |
| Privacy policy ownership | PLAN says threat-model/privacy patterns are community-built while platform code owns only enforcement boundaries; architecture §31 proposes platform privacy-guidance tools and a platform-authored taxonomy. | Separate enforceable data boundaries from community guidance before drafting requirements. |

The diagnostic `plan_module_audit.py` also reports all 11 PLAN modules as
55-64 days old and three missing substrate paths (`tinyassets/runtime/`,
`tinyassets/storage/goals_gates.py`, and `tinyassets/servers/`). PLAN edits
require host approval, so this audit records rather than repairs that drift.

### Current OpenSpec inventory

Fresh strict validation after the independent backfill sync passes for the
whole tree. Canonical OpenSpec contains 25 capabilities, 231 requirements, and 642
scenarios. The nine active
changes contain 104 proposed requirements and 196 top-level tasks, 39
currently checked (nested checklist evidence is excluded from these task
counts):

| Active change | Requirements | Tasks done | Classification |
|---|---:|---:|---|
| `brain-okf-canonical-store` | 7 | 9/16 | future brain-store migration |
| `build-forward-platform-capabilities` | 54 | 1/21 | future boundary/data/demand/hardware/market/training/token umbrella |
| `distributed-execution` | 6 | 1/22 | in-flight authority and external execution program |
| `reconcile-external-connector-manifests` | 9 | 0/27 | connector-product reconciliation, not yet shipped |
| `reconcile-universe-personification-relay` | 7 | 22/33 | surviving unbuilt relay/personification behavior |
| `retire-legacy-live-mcp-tools` | 4 | 0/25 | gated breaking live-surface cleanup |
| `test-identity-and-reset` | 5 | 0/9 | future live identity/reset acceptance substrate |
| `universe-creation` | 8 | 6/33 | residual creation and compute-authority behavior |
| `universe-visibility` | 4 | 0/10 | proposed visibility model |

No product-runtime behavior changed between the original audit baseline
`babce413` and this baseline; the intervening work is spec reconciliation,
focused-test maintenance, and a Windows-stable coordination-script newline.
Therefore the original shipped-surface inventory remains useful evidence, but
its counts and forward/canonical classification were stale and are superseded
by this section.

### Legacy specification inventory is not OpenSpec completion

`docs/specs/` contains 52 Markdown files, all classified filename by filename
in `2026-07-22-legacy-spec-disposition.md`: 16 CANONICAL provenance files, no
ACTIVE owner, 20 CLAIMED inputs assigned to live successor lanes, and 16
HISTORY files. `docs/specs/INDEX.md` now points to OpenSpec rather than claiming
current authority for the legacy directory.

Those files remain design/provenance inputs, not proof that behavior is built.
The same rule applies to `docs/vetted-specs.md`; it is a scoping artifact, not
canonical behavioral truth.

### Fresh canonical grounding results

The original re-audit split 24 canonical capabilities into three independently
reviewed batches. The independent shipped-contract archive adds a fourth
source-grounded batch. Results are requirement/scenario classifications
against current source and focused tests, not an inference from strict syntax
validation.

- **Batch A (8 capabilities):** all 54 requirements and 142 scenarios are
  BUILT as bounded. Work-target helpers use conventional lifecycle values,
  while generic construction/deserialization deliberately permits arbitrary
  lifecycle strings; delayed discard remains explicit.
- **Batch B (8 capabilities):** all 73 requirements and 179 scenarios are BUILT
  as bounded, including their explicit limitations. The audit nevertheless
  found shipped behavior with no complete canonical owner: child-branch
  invocation/await/receipt attachment; the read-only OKF exporter; persisted
  `external_write_results` snapshot/quarantine behavior; and the full live
  `get_status` early-return/session-boundary plus prompt/tool-metadata contract.
- **Batch C (8 capabilities):** all 77 requirements and 236 scenarios are BUILT
  as bounded. The six former mismatches now state the actual integer-conversion
  and legacy-bid boundary, sequential settlement race, configured Goal auth and
  best-effort attribution, fallible founder rollback, tolerant learning
  filters, and mutable/fail-open receipt behavior.
- **Independent backfill (9 capabilities):** all 27 added requirements and 85
  scenarios are BUILT as bounded. The review corrected optional receipt use,
  transitional soul-authority fallthrough, API-delegated merge enforcement,
  partial remote writes and best-effort receipt finalization, narrow Windows
  redaction, seed-based wiki consolidation, stored-output reuse, provider error
  propagation, exact authority-resolver outcomes, and ScenePacket emission.

Overall, **all 231 canonical requirements and all 642 scenarios are BUILT as
written**. This is a grounding result, not a claim of full coverage: eight
dependency-bound groups of shipped behavior still lack canonical ownership, and eight full-platform
target groups still lack complete active owners.

The requirement-by-requirement classifications, source/test anchors, and
reproduction evidence are durable in the companion matrices for
[Batch A](2026-07-22-openspec-grounding-batch-a.md),
[Batch B](2026-07-22-openspec-grounding-batch-b.md), and
[Batch C](2026-07-22-openspec-grounding-batch-c.md).

| Corrected canonical boundary | Classification | Current limitation retained for hardening |
|---|---|---|
| work-target lifecycle | BUILT | Generic records accept arbitrary lifecycle strings; helpers use conventional values. |
| payment conversions and legacy bids | BUILT | Numeric fractions/bools can coerce through `int(...)`; legacy bid scalars are permissive and v1 settlement serializes float. |
| settlement recording | BUILT | Sequential overwrite is rejected, but check-then-write is not race-atomic. |
| Goal authorization and attribution | BUILT | Authorization follows the configured mode; a successful write survives later attribution failure. |
| authenticated founder creation | BUILT | Index registration is best-effort; rollback can leave durable residue or a partial directory. |
| learning extraction and persistence | BUILT | Filtering is field-specific and not a source-entailment check; handled failures can be narrowed. |
| wiki trigger receipts | BUILT | Receipt creation can fail open and unrestricted updates can replace terminal status. |

The stronger desired guarantees remain owned by the separate
`harden-canonical-absolute-guarantees` lane; this correction does not treat the
limitations as target architecture.

On 2026-07-22, Windows, Python 3.14, focused Batch A evidence passed 1,026
tests; 13 failures were stale-test debt
(11 dispatcher fixtures omit the now-required loop declaration, one desktop
fixture expects the retired `workflow` GUI script, and one Windows assertion
expects LF where the platform writes CRLF). The original Batch A pytest argv
was not retained after reviewer-context compaction; its matrix records that
provenance and a reconstructed explicit evidence-file command without claiming
the reconstruction produced those totals. On the same date/environment,
focused Batch B evidence passed 1,180 tests with 3 skips; three failures were
verification debt because early status responses omit `session_boundary` and
two recursion-limit fixtures omit the runs schema. None of these failures is
counted as proof for a canonical requirement. Batch C began as static
source/test inspection. The correction lane then ran
`python -m pytest -q tests/test_work_targets.py tests/test_node_bid.py
tests/test_goals_surface.py tests/test_api_universe.py
tests/test_universe_intelligence.py tests/test_wiki_trigger_receipts.py`: 217
passed with 7 warnings in 29.37 seconds. The Windows layer-2 uptime canary was
not run.

On 2026-07-22 PT / 2026-07-23 UTC, Windows, Python 3.14, the independent
backfill's 27-file focused suite passed **694 tests** with 8 third-party
deprecation warnings in 35.04 seconds; the cross-provider drift self-test was
clean. Full-tree strict validation passed all **34** current items, and the
sync proof preserved all eight prior canonical files as exact text prefixes
while each of the 27 added requirement headings occurred exactly once. The
Windows layer-2 uptime canary was not run.

### Shipped behavior still missing canonical ownership

The reverse-direction audit also found behavior that exists in source but is
not materially specified by any canonical requirement. These are backfill
obligations, not permission to redesign the behavior:

| Recommended canonical owner | Missing shipped contract | Coordination edge |
|---|---|---|
| `credential-vault` | Claude OAuth/BYO-key mapping and injection, plus the current temp-and-replace write boundary. | Do not overlap the active fail-closed provider-overlay lane; do not claim cross-process locking that is absent. |
| `daemon-identity-and-host-pool` | Daemon-wiki soul scaffolding, explicitly flagged latest-soul selection, capped/versioned behavior proposals, deregistration, pricing/concurrency fields, and callback-error isolation. | Coordinate `distributed-execution` and `universe-creation`. |
| `daemon-runtime-and-dispatch` | Lease heartbeat ownership, cooperative cancellation, terminal queue GC, and the still-callable-but-no-longer-startup-wired `recover_claimed_tasks`. | Coordinate `distributed-execution`. |
| `graph-execution-substrate` | Child-Branch invocation, mappings, depth/wait modes, terminal propagation, receipt wait, and validated/idempotent existing-child attachment. | Read-coordinate `distributed-execution`; current local receipts are not future signed owner-daemon authority. |
| `knowledge-retrieval-and-memory` | Curated read-only OKF export and its exclusions. | Coordinate `brain-okf-canonical-store`; export does not make OKF the current write-through canonical store. |
| `live-mcp-connector-surface` for metadata; `identity-auth-and-access-control` for status identity | Four-prompt catalog, tool title/tag/annotation invariants, and exact early/config-error/full status variants, including that early responses currently omit `session_boundary`. | Coordinate connector-manifest, legacy-tool-retirement, and identity/reset changes. |
| `universe-lifecycle-and-soul` | Authenticated request-scoped versus anonymous host-global `switch_universe`. | Coordinate `universe-creation` and `test-identity-and-reset`. |
| `uptime-and-alarms` | DNS incident canary, LLM-binding canary, release reconciler, and disk-pressure alert/rotation/auto-prune controller. | Every uptime owner retains its concurrency/load evidence obligation. |

### Full-platform targets with no complete active owner

The active changes preserve many forward requirements, but they do not yet own
the entire full-platform target. New target changes are still required for:

1. the collaborative catalog/control plane after resolving canonical-store,
   private-data, and public-tool-surface conflicts;
2. realtime collaborative editing, node CRUD/discovery/remix/convergence,
   presence, export, and the host/private boundary;
3. moderation, abuse response, appeals, and rate limits;
4. packaged one-click tray installation across supported operating systems;
5. production realtime paid-market inbox, atomic bid matching, claims, and
   delivery (the active market umbrella owns transactions/oracles, not this
   complete workflow);
6. data portability, account deletion, succession, and feedback;
7. node authoring/file I/O, evaluator catalog, and autoresearch surfaces;
8. explicit real-world handoff/outcome linkage beyond generic future adapters.

## Historical baseline verdict (superseded)

TinyAssets is not yet fully represented in OpenSpec.

The 2026-07-19 baseline deliberately created fourteen as-built capability
specs and explicitly excluded the website, desktop tray, and packaging /
distribution surfaces. The uptime reconciliation added one more as-built
capability on 2026-07-22. Substantial shipped behavior remains outside any
canonical requirement/scenario contract, and eight files already under
`openspec/specs/` are forward-vision documents rather than evidence of built
behavior.

At this baseline:

- **15 canonical capabilities carry an explicit as-built baseline** (the
  original fourteen plus `uptime-and-alarms`).
- **8 canonical files are forward-vision specifications** and must not be
  counted as proof of current behavior: `boundary-layer`, `data-commons`,
  `demand-side`, `hardware-creation`, `paid-market-price-index-and-forwards`,
  `paid-market-training`, `pooled-training-ownership`, and
  `token-architecture`.
- **8 pre-existing active changes remain incomplete.** Their delta specs are
  proposed or in-flight behavior, not canonical coverage.
- The repository added material runtime surfaces after the baseline, including
  the Agent Village command center and per-job sandbox runner, without a
  complete canonical coverage foldback.

Strict validation proves syntax and scenario shape. It does not prove that all
shipped behavior is represented, that future-only files are built, or that an
active delta has landed.

## Historical PLAN Module Coverage (superseded)

| PLAN module | Existing canonical coverage | Material uncovered as-built behavior |
|---|---|---|
| Engine & Domains | `graph-execution-substrate`, universe specs | Installed `tinyassets.domains` entry-point discovery, filesystem dev fallback, registry isolation, domain protocols, and reference-domain registration (`tinyassets/discovery.py`, `registry.py`, `domain_registry.py`, `protocols.py`, `domains/*`) |
| Daemon Platform | `daemon-runtime-and-dispatch` | Daemon create/summon/control/banish, soul fingerprint/fork lineage, model binding and capacity warnings, soul-guided eligibility, host registration/heartbeat and bid polling (`daemon_registry.py`, `dispatcher.py`, `host_pool/`) |
| Brain | `knowledge-retrieval-and-memory` | Typed mini-Brain promotion lifecycle, capture/search/quality/wiki promotion, episodic/temporal consolidation, output versioning, reflexion/style/criteria learning, node-scope context (`daemon_brain.py`, `memory/`, `learning/`) |
| Goals & Gates | `shared-goals-and-convergence`, `evaluation-outcomes-and-attribution` | Ordered protocols and rollback, common-node/archive discovery, full work-target review state, gate claim/retract/list/bonus lifecycle (`api/market.py`, `work_targets.py`, domain review phases) |
| Evolution & Evaluation | `evaluation-outcomes-and-attribution` | Generic `Evaluator`/`EvalResult` protocol, layered structural/editorial/process evaluation, real-world outcome adapters, acceptance-scenario registry/dispatch/normalization, learning lifecycle (`evaluation/`, `outcomes/evaluators.py`, `learning/`) |
| Providers | `provider-routing`, `credential-vault` | Provider response/config/context contracts, missing-vault host-secret stripping, Codex refresh viability evidence, provider snapshot/cooldown status (`providers/base.py`, `api/status.py`) |
| API & MCP Interface | `live-mcp-connector-surface` | Complete prompt catalog, tool titles/tags/annotations/behavior hints, and `get_status` release-receipt/caveat reader contract (`universe_server.py`, `api/status.py`) |
| Distribution & Discoverability | partial live/directory wording; active unsynced connector delta | Local MCPB and Claude plugin products, desktop host app, OSS clone/install contract, and domain-plugin discovery. `reconcile-external-connector-manifests` is the owner for the three connector products and must land rather than be duplicated. |
| Harness & Coordination | none | Claim classification/reaping, worktree state map, provider-context checkpoints, drift guard, living-file coordination, and Agent Village command-center observation/dispatch contracts (`scripts/*`, `command_center/`) |
| Uptime & Alarms | `uptime-and-alarms` | Tier-3 fresh-clone workflow is shipped but unspecced; canaries do not cover tray install, discovery/remix/live collaboration, paid-market inbox, or moderation. The latter surfaces are unbuilt rather than omitted as-built behavior. |
| Constraints | none | ASP loading, validation, surface scoring, and synthesis (`constraints/`). Current missing-rule behavior warns and continues, contradicting PLAN's fail-loud target; the as-built spec must state that limitation without endorsing it. |

## Historical Forever Rule Surface Coverage (superseded)

| Surface | Current evidence | Classification |
|---|---|---|
| Tier-1 chatbot connector | Remote transport/auth/handle catalog is canonical | Partial: collaboration semantics, node CRUD/remix/presence, prompt/metadata and full status contract are not fully canonical |
| Tier-3 OSS clone | Nightly clone/install/import/smoke workflow exists | Built but unspecced; smoke explicitly excludes feature correctness |
| Tier-2 tray install | Windows-first source tray/dashboard exists; public host page states no packaged installer | Source runtime built but unspecced; one-click installer target unbuilt |
| Node discovery/remix/convergence/live collaboration | Only plugin-domain discovery and limited local node reuse search exist | Target architecture is unbuilt and has no active complete OpenSpec contract |
| Paid-market inbox/bid matching | Flag-off file-backed bids plus Wave-1 host REST polling exist | Pre-launch subset partially canonical; production realtime inbox/atomic matching unbuilt |
| Moderation/abuse response | Architecture and rubric documents only | Unbuilt and not represented by an active complete OpenSpec change |
| Cross-surface uptime | MCP/wiki/daemon/revert/paging/recovery/deploy/backup paths canonical | Partial until each built surface has its own probe and unbuilt Forever surfaces land |

## Historical Canonical-Looking Material (superseded)

- The eight forward-vision files listed in the verdict are design requirements,
  not an as-built baseline.
- `live-mcp-connector-surface` proves connector routing, not node remix, live
  collaboration, moderation, tray installation, or provider-funded execution.
- `shared-goals-and-convergence` proves Goal/Branch convergence, not the full
  §15 node-discovery/remix surface.
- `paid-market-economy` explicitly describes the flag-off, file-backed
  pre-launch subset; it does not prove a production inbox or matcher.
- `reconcile-external-connector-manifests`, `distributed-execution`, and other
  active deltas are not canonical until implementation, sync, review, and
  archive complete.
- `prototype/full-platform-v0/` and the integrated architecture note are target
  evidence, not shipped behavior.

## Historical Reconciliation Batches (completed or superseded)

The full-spec program must preserve capability boundaries and avoid active
change collisions.

### Batch A — new canonical capabilities for shipped, unowned behavior

1. `domain-plugin-runtime` — installed/dev domain discovery, registry and
   protocol contracts.
2. `daemon-identity-and-host-pool` — daemon identity/control, host
   registration/heartbeat and current bid polling. Soul-guided dispatcher
   selection remains Batch B work under its existing canonical owner.
3. `evaluation-runtime-and-scenarios` — generic evaluator/result protocol,
   layered evaluators and acceptance-scenario execution.
4. `desktop-host-runtime` — current source-installed tray, launcher, dashboard,
   notifications and shortcut behavior; explicitly no packaged-installer claim.
5. `development-coordination-runtime` — claim/worktree/context/drift tools and
   the Agent Village command-center's observed/dispatch behavior.
6. `constraint-evaluation` — current ASP rule loading, checking, synthesis and
   the warn-and-continue limitation.
7. `oss-clone-and-install` — supported clone/install/import/smoke/escalation
   contract from the nightly Tier-3 workflow.
8. `public-website-surface` — built SvelteKit routes, snapshot/live-data
   provenance, public proof/status and truthful host/install presentation.

#### Batch A requirement-to-evidence map

Each numbered item below maps one delta-spec requirement, in file order, to
the repository evidence reviewed on 2026-07-22. Tests are corroboration; the
runtime/workflow/site file remains the behavior owner.

- **`domain-plugin-runtime`:** (1) installed/editable discovery →
  `tinyassets/discovery.py`, `tests/test_discovery.py`; (2) isolated
  auto-registration → `tinyassets/discovery.py`; (3) configured registry
  identity → `tinyassets/registry.py`, `tests/test_discovery.py`; (4) opaque
  callable registry/compile rejection → `tinyassets/domain_registry.py`,
  `tinyassets/graph_compiler.py`, `tests/test_unified_execution.py`; (5) current
  protocol surface → `tinyassets/protocols.py`, `domains/*/skill.py`; (6)
  legacy discovery/config-name mismatch → `pyproject.toml`,
  `domains/fantasy_daemon/skill.py`.
- **`constraint-evaluation`:** (1) base-rule loading and missing-file warning →
  `tinyassets/constraints/asp_engine.py`,
  `tests/test_asp_engine_data_file.py`; (2) satisfiability/evidence return →
  `asp_engine.py`, `tests/test_asp_solver.py`; (3) shared surface conversion and
  score → `constraint_surface.py`; (4) extract/generate bounded synthesis →
  `constraint_synthesis.py`; (5) never-block attempt-limit behavior →
  `constraint_synthesis.py`, `tests/test_synthesis_skip_fix.py`; (6) Clingo
  dependency and textual potential-violation bounds → `asp_engine.py`.
- **`daemon-identity-and-host-pool`:** (1) soul identity/lineage →
  `tinyassets/daemon_registry.py`, `tests/test_daemon_registry.py`; (2) model
  binding/runtime slot reuse → the same files; (3) ownership-scoped control →
  `daemon_registry.py`, `tests/test_soul_scoped_effect_authority.py`; (4) REST registration/heartbeat →
  `tinyassets/host_pool/{client,registration,heartbeat}.py`,
  `tests/test_host_pool_client.py`; (5) poll-only, non-claiming bid discovery →
  `tinyassets/host_pool/bid_poller.py`, `tests/test_host_pool_client.py`.
- **`evaluation-runtime-and-scenarios`:** (1) `Evaluator`/`EvalResult` bounds →
  `tinyassets/evaluation/__init__.py`, `tests/test_evaluator_protocol.py`; (2)
  layered native evidence/adapters → `tinyassets/evaluation/{process,coding_process}.py`,
  `tests/test_process_evaluation.py`; (3) injected-prober outcome behavior →
  `tinyassets/outcomes/evaluators.py`, `tests/test_outcome_evaluators.py`; (4)
  acceptance-scenario field validation → `tinyassets/evaluation/scenario_runner.py`,
  `tests/test_scenario_runner.py`; (5) registry dispatch/terminal normalization →
  the same files; (6) synchronous MCP dispatcher and report-only budgets →
  `tinyassets/evaluation/scenario_dispatchers/mcp_call.py`,
  `tests/test_scenario_dispatcher_mcp_call.py`.
- **`desktop-host-runtime`:** (1) singleton/source tray/tunnel opt-in →
  `tinyassets_tray.py`, `tests/test_tray_singleton.py`,
  `tests/test_tinyassets_tray.py`; (2) provider controls/preferences →
  `tinyassets_tray.py`, `tinyassets/preferences.py`,
  `tests/test_tray_preferences.py`; (3) shared active-universe root →
  `tinyassets_tray.py`, `tests/test_tinyassets_tray.py`; (4) observable
  supervision/readiness → `tinyassets_tray.py`,
  `tests/test_tinyassets_tray_watchdog.py`; (5) launcher/dashboard/shared-tray/
  notification behavior → `tinyassets/desktop/`, `tests/test_desktop.py`; (6)
  source-only Windows shortcut utility → `tinyassets/desktop/create_shortcut.py`.
- **`development-coordination-runtime`:** (1) advisory session freshness →
  `scripts/session_sync_gate.py`; (2) claim classification/collision/reaping →
  `scripts/claim_check.py`; (3) worktree lane classification →
  `scripts/worktree_status.py`, `tests/test_worktree_status.py`; (4) lifecycle
  context ranking/filtering → `scripts/provider_context_feed.py`,
  `tests/test_provider_context_feed.py`; (5) diagnostic cross-provider drift →
  `scripts/check_cross_provider_drift.py`,
  `scripts/invariants/cross_provider_drift.py`; (6) read-oriented village
  aggregation/auth → `command_center/{collector,server}.py`,
  `tests/command_center/{test_collector,test_server}.py`; (7) explicit talk and
  hire writes → `command_center/server.py`, `tests/command_center/test_hire.py`.
- **`oss-clone-and-install`:** (1) scheduled/manual fresh editable clone →
  `.github/workflows/tier3-oss-clone-nightly.yml`; (2) structural import/smoke
  gates → the workflow, `scripts/tier3_smoke.py`,
  `scripts/import_graph_smoke.py`, `tests/smoke/`; (3) GitHub failure issue →
  the workflow's escalation step; (4) Ubuntu/Python-3.11 structural-only bounds
  → the workflow plus `scripts/tier3_smoke.py`'s stated scope.
- **`public-website-surface`:** (1) static route/asset contract →
  `WebSite/site/svelte.config.js`, `src/routes/`, `static/`; (2) baked/live
  provenance → `WebSite/site/src/lib/live/project.ts`, snapshot files, host and
  project routes; (3) browser MCP transport → `src/lib/mcp/live.ts`,
  `vite.config.js`; (4) reachability versus movement →
  `src/lib/components/VitalSigns.svelte`, `src/routes/{loop,patch-loop}/`; (5)
  current host/install availability → `src/routes/host/+page.svelte`; (6)
  crawler boundaries → `static/{robots.txt,sitemap.xml}`.

#### Batch A verification

- **2026-07-22, Windows:** `openspec validate
  complete-as-built-spec-coverage --type change --strict --no-interactive
  --json` passed with no issues.
- **2026-07-22, Windows, Python 3.14:** the focused evidence suite passed
  **576 tests**, skipped 3, and deliberately deselected the two known unrelated
  Windows assertions (`workflow` GUI-entry rename drift and LF/CRLF formatting).
  `tests/test_uptime_canary_layer2.py` was not selected or run.
- **2026-07-22, Windows, Node/npm:** `npm ci` followed by `npm run build` in
  `WebSite/site/` completed successfully and the static adapter wrote `build/`.
  The build retained existing unused-CSS/tsconfig warnings; `npm ci` also
  reported 18 dependency-audit findings (2 low, 10 moderate, 6 high), neither
  introduced nor remediated by this documentation-only lane.

### Batch B — enrich existing canonical capabilities

- `knowledge-retrieval-and-memory`: mini-Brain and long-horizon
  memory/learning lifecycle.
- `daemon-runtime-and-dispatch`: soul-guided selection and complete work-target
  review state.
- `shared-goals-and-convergence`: protocol, reuse discovery and gate lifecycle.
- `evaluation-outcomes-and-attribution`: relationship to the generic evaluator
  runtime and outcome adapters.
- `provider-routing` + `credential-vault`: provider contracts, host-secret
  isolation and evidence/status behavior.
- `live-mcp-connector-surface`: full prompt/tool metadata and status-reader
  contract; coordinate the active connector-manifest delta.
- `uptime-and-alarms`: Tier-3 clone monitoring and only those cross-surface
  probes that are actually shipped.

Batch B must run collision checks immediately before each spec write because
active changes may sync into the same canonical files.

### Batch C — specify unbuilt full-platform targets as active changes

These must not be synced into as-built canonical specs until implemented:

1. node discovery, remix, convergence and live collaboration;
2. moderation, abuse response, appeals and rate limits;
3. packaged one-click tray installation across supported operating systems;
4. production paid-market inbox, atomic bid matching and realtime delivery;
5. remaining distributed-execution authority/transport/effect work;
6. forward-vision data, demand, training, hardware and token capabilities.

The existing integrated architecture remains design rationale; OpenSpec changes
must carry the executable SHALL/scenario contracts and tasks.

## Completion Proof

“Full spec” is proven only when all of the following are true:

1. Every substantive shipped module/surface maps to at least one strict-valid
   canonical requirement with executable scenarios and current source owners.
2. Every intentional absence or wart is stated as an as-built limitation, not
   silently promoted into desired behavior.
3. Every target-only requirement lives in an active OpenSpec change (or is
   explicitly retired), never masquerades as canonical as-built truth, and has
   file-bounded implementation tasks.
4. Every landed delta is synced and archived; no completed change remains
   active and no active change is counted as shipped.
5. Canonical specs pass strict validation and independent code-grounding review.
6. Public and uptime-sensitive surfaces retain their required rendered,
   concurrency/load, CI, and post-fix evidence gates when behavior changes.

**Current verdict: NOT COMPLETE.** Criterion 1 fails on the eight
dependency-bound shipped backfill groups above; criterion 3 fails on the eight
full-platform target groups without complete active owners. Criterion 5 now
passes: all 231 requirements and 642 scenarios are independently grounded and
strict-valid.
Criterion 6 additionally requires an explicit concurrency/load proof task in
every uptime-target change before that change can be treated as done. STATUS.md
owns the backfill, runtime-hardening, legacy-disposition, PLAN-decision, and
remaining target-spec successor lanes.
