## Context

The public connector advertises exactly seven handles. `read_graph(target="branch")` delegates to exact `get_branch` and therefore requires a caller to already know a `branch_def_id`; `write_graph(target="branch")` delegates only to `patch_branch`. The internal branch adapter already has visibility-filtered list and atomic full-definition build seams, but they are not safe to publish unchanged: listing is unbounded, author/approval fields are caller-influenceable, fork visibility is not checked first, validation can echo the submitted definition, and branch creation has no transactional idempotency. Freshness check on 2026-07-25 found no `UNIVERSE_SERVER_USER` configuration in `deploy/` or `.github/workflows/`; production therefore cannot treat that environment fallback as authenticated authority.

The four registered MCP prompts also predate the canonical handle fold. They teach `extensions`, `goals`, `gates`, `wiki`, and `community_change_context`, while the active retirement change removes those hidden registrations. The retirement change cannot safely remove those tools until the canonical branch equivalents, migrated prompt consumers, and rendered proof land. Live wiki pages require a separate exact-path correction manifest. The current SHA-256 precondition is a useful stale-write guard but is not atomic compare-and-swap because the read/check/write sequence has no lock; repository prompt corrections cannot be treated as proof that live content changed.

Runtime files are owned by the active universe-creation, universe-visibility, and `control_station` prompt-truth lanes; newborn BYOC behavior landed in #1759 and is a read-only base. Retire-legacy caller inventory v4 landed in #1772 and left implementation pending; this packet adds its missing first-contact replacement gates as retire-legacy tasks 2.3a and 4.0 without claiming runtime. Those active runtime owners remain explicit read-only dependencies. No `broad-test` lane exists. This change therefore produces the contract and review packet only.

## Goals / Non-Goals

**Goals:**

- Make branch discovery, first complete branch creation, and deliberate publication possible through the existing seven handles.
- Publish closed, bounded, non-enumerating request/result/error contracts.
- Bind new branch ownership and new-node authorship to verified request authority while preserving inherited remix provenance.
- Make durable branch creation body-bound idempotent, make validation failures atomic, and reconcile attribution through an idempotent outbox instead of pretending multiple stores share one transaction.
- Make registered first-contact guidance truthful for canonical handles and current source-code isolation limits.
- Define scale and rendered-chatbot proofs before runtime landing.

**Non-Goals:**

- No eighth MCP tool, hidden compatibility registration, magic default branch, or parallel authoring substrate.
- No runtime edit, canonical-spec sync/archive, deployment, live wiki write, or rollout in this lane.
- This lane does not itself repair the existing exact-branch related-wiki projection leak. New catalog/create/publish runtime, deployment, prompts, and rendered inspection remain hard-blocked until the universe-visibility owner lands or accepts safe canonical/internal exact-branch projections and their shared helper.
- No private-branch authoring or catalog proxy in V1. This packet selects no private-data custody mode and rules none in or out; a later private route requires a PLAN-approved change naming its chosen custody mode, trust boundaries, storage, and routing. This packet adds no platform private row or `is_private` substitute.
- No compute, provider, execution, purchasing, or market authority follows from listing or creating a branch.

## Decisions

### 1. Extend targets, not tools

`read_graph(target="branches")` becomes the branch catalog. `read_graph(target="branch")` remains exact inspection. `write_graph(target="branch")` becomes a closed create-patch-publish union. Explicit `publish=true` mints a catalog-published version; ordinary patch snapshots never publish implicitly. This preserves the exact seven handles and uses established branch ownership instead of re-advertising the legacy `extensions` surface.

Alternative rejected: add `list_branches` or `build_branch` tools. They are conveniences over the canonical graph handles and would permanently increase the public tool budget.

### 2. Use closed, versioned DTOs

Create accepts `BranchCreateDefinitionV1` in `definition_json`. It has a fixed top-level allowlist and `schema_version="branch-definition-v1"`. V1 is deliberately a prompt-template starter format: it positively specifies the allowed node, edge, conditional-edge, and state-field objects and excludes `source_code`, `node_ref`, invoke/await references, effects, skills, arbitrary metadata, and per-node/provider policies until canonical approval, authority, and provenance paths exist. Identifiers, caller-authored provenance, approval, publication, timestamps, statistics, ownership/ACL, universe/tenant, and related-wiki fields are server-owned and rejected in the structural locations where those fields could grant authority. A one-MiB total body cap plus numeric collection/string caps bounds validation and storage work.

Creation requires no `branch_id` or `changes_json`; patching requires both and forbids `definition_json`; publication requires `branch_id`, `publish=true`, and an idempotency key but neither payload. The existing top-level `write_graph.visibility` parameter must remain at its `"public"` default and is not duplicated inside the definition. Any non-default goal/request/universe/visibility field, a patch idempotency key, mixed payload, or incomplete mode fails before a handler runs. The handle docstring becomes target-specific so it does not call idempotency mandatory for patch mode. The adapter maps the create definition to the existing internal build seam only after authority and shape validation.

Alternative rejected: overload `changes_json` for both create and patch. That makes mode selection ambiguous and invites accidental partial creation.

### 3. Authority is verified and non-enumerating

The server derives the new branch owner and every newly authored node's author from the authenticated request principal. V1 excludes fork, copy, node-reference, Goal binding, and source-code creation, so it neither fabricates nor erases inherited provenance. A future remix contract must preserve immutable source author/provenance separately from current branch ownership. `UNIVERSE_SERVER_USER`, caller-supplied author fields, graph membership, and a branch name are never positive authority.

The same protection applies at the shared staging/helper layer used by canonical and retained legacy patch aliases: protected author/approval/identifier fields are rejected before staging, `force` cannot bypass ownership through MCP, newly added inline nodes derive their author from the verified principal, and any admitted source mutation clears approval. The legacy source-approval action cannot retire until a canonical approval route exists or source-code patching is separately migrated away.

### 4. Catalog scope is `published` or `mine`

The default `published` scope returns commons branches whose branch version and separate `BranchCatalogPublication` record are both active. Authenticated `mine` matches an internal verified-principal-derived `author_subject`, never the legacy free-text author column, and never indexes or proxies private content under any custody mode. Until PLAN approves a replacement, the catalog consumes the pre-existing `branch_definitions.visibility='public'` column only as a fail-closed commons predicate; explicit publish re-checks that stored row rather than trusting the mode sentinel. There is no public `all`, `visible`, `include_private`, or universe-membership shortcut.

Results preserve the handle's existing unset/default limit of 30 and cap explicit limits at 100. A canonical-database catalog projection gives bounded filtering and non-starving keyset ordering `(created_at DESC, branch_def_id ASC)`, so unrelated mutations do not invalidate a walk. The ten-minute AES-256-GCM cursor has a closed envelope, a durable per-key unique 32-bit issuer-prefix lease plus 64-bit counter nonce, full 128-bit tag, immutable last-examined tuple, and actor/filter digest. `TINYASSETS_BRANCH_CRYPTO_KEYRING` supplies versioned root keys; HKDF separates cursor encryption from idempotency HMAC, rotation retains prior keys for the configured record lifetime (minimum 24 hours), and absent/malformed configuration fails catalog/create/publish closed. A `published` result verifies active version/publication records and the current monotonic publication revision; compare-and-advance outbox consumption prevents delayed events from regressing the pointer. Periodic maintenance reconciles drift without mutating state from the read-only handle. The response exposes no hidden total count. Summaries use exact bounded fields, split ordinary and conditional edge counts, and report structural validation rather than ambiguous execution readiness. They are deliberately smaller than exact branch reads and never carry node bodies, prompts, source, wiki metadata, gate/custody data, or execution authority.

Alternative rejected: expose the internal `published/all/mine` scopes directly. `all` is ambiguous at a public boundary and risks turning an internal host option into an enumeration contract.

### 5. Create is body-bound idempotent

Create and publish require printable-ASCII 16–128 character `idempotency_key` values. The raw key is HMAC-fingerprinted under HKDF-derived keyring secrets and actor scope, and each command is bound to an RFC 8785 canonical digest. Retry lookup and unique alias reservation cover every retained secret version, preventing rotation or rolling servers from creating a duplicate. Create uses a connection-accepting canonical-branch transaction. Publish looks up actor/key replay before resolving mutable branch content, then uses a connection-accepting version-store transaction that preserves operational snapshots while committing a separate owner-attributed `BranchCatalogPublication`, monotonic revision, idempotency result, and outbox event. Consumers compare-and-advance by revision so delayed events cannot regress the catalog pointer. Same-key/same-command replay within the configured minimum-24-hour retention returns the original result; changed-branch reuse conflicts. Optional at-least-once consumers apply their effect and unique `event_id` dedupe in one transaction or use an inherently idempotent effect. Source-control/GitHub export is downstream and is not part of mutation success.

Alternative rejected: deduplicate on branch name. Branch names are intentionally non-unique and part of the user-designed commons.

### 6. V1 creation is commons-only

Public creation can land in the platform commons. V1 rejects any non-public visibility before persistence and does not query, proxy, or index private content under any custody mode. This avoids resolving the open PLAN private-data decision locally. A later private-authoring change must name its selected custody mode, trust boundaries, storage, and routing and receive the required design approval.

The existing `visibility` column is Phase-6.2.2 drift relative to PLAN's private-data model. V1 consumes only `visibility='public'` as a temporary fail-closed commons predicate and does not create or legitimize platform private rows.

### 7. Guidance has one canonical vocabulary

The registered `control_station`, `meet_universe`, `extension_guide`, and `branch_design_guide` prompts must describe workflows using only the seven handles and their supported targets. The first-contact path starts with `converse`; starter-branch examples compose catalog, create, inspect, explicit publish, and rediscovery through `read_graph`/`write_graph`. V1 guidance is prompt-template-only. An optional `run_graph` step first requires requester-owned BYOC/market provider authority and must never use maintainer/founder quota. Advanced source-code authoring stays out of the first-contact path until a canonical approval route exists; any broader guide must disclose that the current compiled path is not OS-isolated rather than promising sandbox execution.

Live wiki corrections are enumerated separately with exact paths, pre-image hashes, replacement text, dry-run evidence, and post-image hashes. The current hash precondition is documented as race-prone; no live mutation occurs until a wiki owner supplies serialized/locked atomic patching or another reviewed single-writer boundary. A repository prompt change never implies a live wiki mutation.

### 8. Acceptance includes concurrency and a rendered user journey

Before runtime landing, a deterministic fixture exercises 500 logical clients and 1,000 mixed operations (750 catalog reads, 200 creates, 50 publishes) under the production SQLite journaling/busy-timeout configuration, including tied immutable timestamps, 100 concurrent identical retries, unsupported-private requests, deliberate-versus-snapshot publication, mutation-during-pagination completion, nonce uniqueness/tampering, and cross-actor cursor replay. It must show no 5xx, restricted metadata leak, duplicate/partial create/publication, silent pagination duplicate/skip or starvation, or extra advertised handle, with p99 under three seconds on declared hardware and topology. A forced full 400-candidate window records no more than 400 version plus 400 publication-row verifications and discloses version-store query count/batching so fan-out is falsifiable.

Final acceptance then uses a real browser-rendered chatbot through `https://tinyassets.io/mcp`: discover a branch without an ID, create a new complete public branch, inspect it, explicitly publish it, and rediscover it while preserving the exact seven-tool listing. Any run uses requester-owned BYOC/market authority. None of the new catalog/create/publish modes can deploy while canonical `read_graph(target="branch")`, internal/legacy `get_branch`, `describe_branch`, or their shared related-wiki helper can reveal restricted page metadata. Post-fix organic use is checked separately or left as a STATUS watch.

## Risks / Trade-offs

- **[Risk] The internal build seam accepts unsafe ownership/provenance fields.** → Validate positive nested V1 DTOs, preserve inherited provenance, and mutation-test every excluded authority field.
- **[Risk] Pagination can skip, duplicate, starve, reuse a GCM nonce, or accept forged context.** → Use immutable two-column ordering, capped last-examined scanning, closed AEAD, key-issuance limits, and actor/filter binding.
- **[Risk] Validation responses disclose prompts/source.** → Return bounded field paths and codes only; never echo `definition_json`.
- **[Risk] Private creation conflicts with commons-first PLAN or settles open custody research.** → Keep V1 commons-only, choose no custody mode, and require any private route to name its mode and boundaries in a separately approved design.
- **[Risk] Catalog/create/publish IDs amplify the existing exact-get wiki leak.** → Hard-block all three new modes, deployment, prompts, and rendered inspection until every exact branch path and shared helper provides a visibility-safe projection.
- **[Risk] Patch snapshots silently appear published.** → Add explicit publish mode and catalog eligibility, route all writers through `publish_branch_version`, and keep operational snapshots non-catalog.
- **[Risk] Missing or misrotated cryptographic keys weaken anonymous catalog/create idempotency.** → Catalog the keyring and fail closed with no ephemeral defaults.
- **[Risk] Active owners land incompatible seams.** → Keep this lane spec-only, obtain explicit owner accept/adapt, then rebase and rerun current-main review before runtime claim.
- **[Risk] Corrected prompts coexist with stale live wiki pages.** → Keep an exact two-surface manifest and require a serialized/locked patch boundary before any live mutation.

## Migration Plan

1. Land this strict-valid spec/review packet as a blocked draft after Claude Opus 5 review.
2. Obtain accept/adapt from the current universe-creation, universe-visibility, and `control_station` prompt-truth owners; preserve landed newborn-BYOC behavior from #1759; and provision/catalog `TINYASSETS_BRANCH_CRYPTO_KEYRING`. Retire-legacy tasks 2.3a and 4.0 plus its STATUS dependency already preserve both `publish_version` and `approve_source_code`; any future retirement owner must accept those gates before implementation. The prompt owner must hand off its landed text and exact-handle invariant rather than be overwritten. No current `broad-test` owner/lane exists as of 2026-07-25.
3. Claim exact runtime/test files after those owners release them; write failing contract, authority, idempotency, pagination, guidance, and load tests first.
4. Implement the canonical router, shared patch/publication owners, catalog migration/backfill, keyring integration, and packaged-runtime parity.
5. Deploy through the normal pipeline only after the exact-branch projection is visibility-safe; run exact-seven canary, the rendered chatbot journey, and post-fix organic-use check.
6. After a separately reviewed serialized/locked wiki patch boundary exists, apply live wiki corrections one page at a time with dry-run and hash-precondition evidence.
7. Reconcile the two changes' concurrent `Canonical Advertised Handle Set` modifications, then sync this delta together with the legacy-retirement delta without dropping either requirement set. Archive only after implementation and acceptance land. Rollback restores the prior image; any rollback reopens the onboarding, guidance, publication, and retirement gates.

## Open Questions

- Which private-data custody mode and trust boundaries should a future private branch route select? Host-machine, private-brain, vault, and platform-held modes remain open research; none is ruled in or out by V1.
- The active universe-visibility lane must either supply a reusable visibility-safe related-wiki projection or explicitly accept a separate prerequisite fix; catalog rollout does not proceed without one.
- The load contract is frozen at p99 below three seconds for the declared 500-client/1,000-operation fixture; the implementation evidence must name hardware and topology rather than weakening the threshold.
