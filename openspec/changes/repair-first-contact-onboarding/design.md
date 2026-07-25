## Context

The public connector advertises exactly seven handles. `read_graph(target="branch")` delegates to exact `get_branch` and therefore requires a caller to already know a `branch_def_id`; `write_graph(target="branch")` delegates only to `patch_branch`. The internal branch adapter already has visibility-filtered list and atomic full-definition build seams, but they are not safe to publish unchanged: listing is unbounded, author/approval fields are caller-influenceable, fork visibility is not checked first, validation can echo the submitted definition, and branch creation has no transactional idempotency. Freshness check on 2026-07-25 found no `UNIVERSE_SERVER_USER` configuration in `deploy/` or `.github/workflows/`; production therefore cannot treat that environment fallback as authenticated authority.

The four registered MCP prompts also predate the canonical handle fold. They teach `extensions`, `goals`, `gates`, `wiki`, and `community_change_context`, while the active retirement change removes those hidden registrations. The retirement change cannot safely remove those tools until the canonical branch equivalents, migrated prompt consumers, and rendered proof land. Live wiki pages require a separate exact-path correction manifest. The current SHA-256 precondition is a useful stale-write guard but is not atomic compare-and-swap because the read/check/write sequence has no lock; repository prompt corrections cannot be treated as proof that live content changed.

Runtime files are owned by the active universe-creation and universe-visibility lanes. The legacy-retirement change is present but unclaimed, and no `broad-test` lane exists as of 2026-07-25. This change therefore produces the contract and review packet only.

## Goals / Non-Goals

**Goals:**

- Make branch discovery and first complete branch creation possible through the existing seven handles.
- Publish closed, bounded, non-enumerating request/result/error contracts.
- Bind new branch ownership and new-node authorship to verified request authority while preserving inherited remix provenance.
- Make durable branch creation body-bound idempotent, make validation failures atomic, and reconcile attribution through an idempotent outbox instead of pretending multiple stores share one transaction.
- Make registered first-contact guidance truthful for canonical handles and current source-code isolation limits.
- Define scale and rendered-chatbot proofs before runtime landing.

**Non-Goals:**

- No eighth MCP tool, hidden compatibility registration, magic default branch, or parallel authoring substrate.
- No runtime edit, canonical-spec sync/archive, deployment, live wiki write, or rollout in this lane.
- This lane does not itself repair the existing exact-branch related-wiki projection leak. New catalog/create runtime, deployment, prompts, and rendered inspection remain hard-blocked until the universe-visibility owner lands or accepts safe canonical/internal exact-branch projections and their shared helper.
- No private-branch authoring or catalog proxy in V1. A later private route requires a PLAN-approved user-controlled host/storage contract; this packet adds no platform private row or `is_private` substitute.
- No compute, provider, execution, purchasing, or market authority follows from listing or creating a branch.

## Decisions

### 1. Extend targets, not tools

`read_graph(target="branches")` becomes the branch catalog. `read_graph(target="branch")` remains exact inspection. `write_graph(target="branch")` becomes a closed create-or-patch union. This preserves the exact seven handles and uses established branch ownership instead of re-advertising the legacy `extensions` surface.

Alternative rejected: add `list_branches` or `build_branch` tools. They are conveniences over the canonical graph handles and would permanently increase the public tool budget.

### 2. Use closed, versioned DTOs

Create accepts `BranchCreateDefinitionV1` in `definition_json`. It has a fixed top-level allowlist and `schema_version="branch-definition-v1"`. V1 is deliberately a prompt-template starter format: it positively specifies the allowed node, edge, conditional-edge, and state-field objects and excludes `source_code`, `node_ref`, invoke/await references, effects, skills, arbitrary metadata, and per-node/provider policies until canonical approval, authority, and provenance paths exist. Identifiers, caller-authored provenance, approval, publication, timestamps, statistics, ownership/ACL, universe/tenant, and related-wiki fields are server-owned and rejected in the structural locations where those fields could grant authority. A one-MiB total body cap plus numeric collection/string caps bounds validation and storage work.

Creation requires no `branch_id` or `changes_json`; patching requires both and forbids `definition_json`. The existing top-level `write_graph.visibility` parameter must remain at its `"public"` default for both V1 create and patch and is not duplicated inside the definition. Create accepts only `target`, `definition_json`, and `idempotency_key` beyond defaults; patch accepts only `target`, `branch_id`, and `changes_json`. Any non-default goal/request/universe/visibility field, a patch idempotency key, mixed payload, or incomplete mode fails before a handler runs. The adapter maps the create definition to the existing internal build seam only after authority and shape validation.

Alternative rejected: overload `changes_json` for both create and patch. That makes mode selection ambiguous and invites accidental partial creation.

### 3. Authority is verified and non-enumerating

The server derives the new branch owner and every newly authored node's author from the authenticated request principal. V1 excludes fork, copy, node-reference, Goal binding, and source-code creation, so it neither fabricates nor erases inherited provenance. A future remix contract must preserve immutable source author/provenance separately from current branch ownership. `UNIVERSE_SERVER_USER`, caller-supplied author fields, graph membership, and a branch name are never positive authority.

The same protection applies to the existing patch mode: protected author/approval/identifier fields are rejected before staging, newly added inline nodes derive their author from the verified principal, and any admitted source mutation clears approval. The legacy source-approval action cannot retire until a canonical approval route exists or source-code patching is separately migrated away.

### 4. Catalog scope is `published` or `mine`

The default `published` scope returns commons branches with an authoritative active published version. Authenticated `mine` returns platform-commons branches authored by the verified actor and never indexes or proxies user-controlled private content. There is no public `all`, `visible`, `include_private`, or universe-membership shortcut.

Results preserve the handle's existing unset/default limit of 30 and cap explicit limits at 100. A canonical-database catalog projection gives bounded filtering and keyset ordering `(updated_at DESC, branch_def_id ASC)`. Its generation changes with projection mutations, so a mutation between pages returns `branch_cursor_stale` rather than a false stability claim. The cursor is a ten-minute, versioned AES-256-GCM envelope carrying the generation, last tuple, and a digest of the normalized actor/scope/query/sorted-tags/domain/goal filters; it hides catalog activity while rejecting alteration, expiry, unknown keys, and cross-context replay. Because published versions currently live outside the branch-definition transaction, a `published` result verifies each candidate against the authoritative version store and omits stale candidates instead of trusting `branch_definitions.published`; publication outbox consumers and periodic maintenance reconcile drift without mutating state from the read-only handle. The response exposes no hidden total count. Summaries use exact typed fields, split ordinary and conditional edge counts, and report structural validation rather than ambiguous execution readiness. They are deliberately smaller than exact branch reads and never carry node bodies, prompts, source, wiki metadata, gate/custody data, or execution authority.

Alternative rejected: expose the internal `published/all/mine` scopes directly. `all` is ambiguous at a public boundary and risks turning an internal host option into an enumeration contract.

### 5. Create is body-bound idempotent

Creation requires a printable-ASCII 16–128 character `idempotency_key`. The raw key is HMAC-fingerprinted under a versioned server secret and actor scope, and the command is bound to an RFC 8785 canonical digest. Retry lookup and unique alias reservation cover every retained secret version, preventing rotation or rolling servers from creating a duplicate. A new connection-accepting storage seam commits the canonical branch row, catalog projection/generation, succeeded idempotency result, and branch-creation outbox row with a stable `event_id` in one database transaction; it does not nest the current branch save's independent connection. Same-key/same-body replay within the disclosed minimum 24-hour retention returns the original minimal result; changed-body reuse conflicts. Concurrent identical submissions create one durable branch result. The outbox is V1's concrete durable attribution record; any optional future at-least-once consumer must deduplicate by `event_id`. Source-control/GitHub export is downstream and is not part of the create-success transaction.

Alternative rejected: deduplicate on branch name. Branch names are intentionally non-unique and part of the user-designed commons.

### 6. V1 creation is commons-only

Public creation can land in the platform commons. V1 rejects any non-public visibility before persistence and does not query, proxy, or index a private user store. This avoids resolving the open PLAN private-data decision locally. A later private-authoring change must name the user-controlled storage/routing contract and receive the required design approval.

### 7. Guidance has one canonical vocabulary

The registered `control_station`, `meet_universe`, `extension_guide`, and `branch_design_guide` prompts must describe workflows using only the seven handles and their supported targets. The first-contact path starts with `converse`; starter-branch examples compose `read_graph(target="branches"|"branch")`, `write_graph(target="branch")`, and `run_graph`. V1 guidance is prompt-template-only. Advanced source-code authoring stays out of the first-contact path until a canonical approval route exists; any broader guide must disclose that the current compiled path is not OS-isolated rather than promising sandbox execution.

Live wiki corrections are enumerated separately with exact paths, pre-image hashes, replacement text, dry-run evidence, and post-image hashes. The current hash precondition is documented as race-prone; no live mutation occurs until a wiki owner supplies serialized/locked atomic patching or another reviewed single-writer boundary. A repository prompt change never implies a live wiki mutation.

### 8. Acceptance includes concurrency and a rendered user journey

Before runtime landing, a deterministic fixture exercises 500 logical clients and 1,000 mixed operations (800 catalog reads and 200 creates) under the production SQLite journaling/busy-timeout configuration, including tied timestamps, 100 concurrent identical retries, unsupported-private requests, authoritative publication checks, catalog-generation invalidation, and cross-actor cursor replay. It must show no 5xx, restricted metadata leak, duplicate/partial create, silent pagination duplicate/skip, or extra advertised handle, with p99 under three seconds on declared hardware.

Final acceptance then uses a real browser-rendered chatbot through `https://tinyassets.io/mcp`: discover a branch without an ID, create a new complete public branch, inspect the returned ID through the visibility-safe exact projection, and preserve the exact seven-tool listing. Neither the new catalog nor create mode can deploy while canonical `read_graph(target="branch")`, internal/legacy `get_branch`, `describe_branch`, or their shared related-wiki helper can reveal restricted page metadata. Post-fix organic use is checked separately or left as a STATUS watch.

## Risks / Trade-offs

- **[Risk] The internal build seam accepts unsafe ownership/provenance fields.** → Validate positive nested V1 DTOs, preserve inherited provenance, and mutation-test every excluded authority field.
- **[Risk] Pagination can skip, duplicate, or accept forged context.** → Use two-column keyset ordering and an authenticated versioned cursor bound to normalized filters and actor.
- **[Risk] Validation responses disclose prompts/source.** → Return bounded field paths and codes only; never echo `definition_json`.
- **[Risk] Private creation conflicts with commons-first PLAN.** → Keep V1 commons-only; any private route remains a separately approved user-controlled-storage design.
- **[Risk] Catalog or create IDs amplify the existing exact-get wiki leak.** → Hard-block both new modes, deployment, prompts, and rendered inspection until every exact branch path and shared helper provides a visibility-safe projection.
- **[Risk] Active owners land incompatible seams.** → Keep this lane spec-only, obtain explicit owner accept/adapt, then rebase and rerun current-main review before runtime claim.
- **[Risk] Corrected prompts coexist with stale live wiki pages.** → Keep an exact two-surface manifest and require a serialized/locked patch boundary before any live mutation.

## Migration Plan

1. Land this strict-valid spec/review packet as a blocked draft after Claude Opus 5 review.
2. Obtain accept/adapt from the current universe-creation and universe-visibility owners. At runtime claim time, re-check whether the unclaimed legacy-retirement change has acquired an owner; that owner must record canonical-equivalent deployment, prompt migration, and rendered proof as removal prerequisites. No current `broad-test` owner/lane exists as of 2026-07-25.
3. Claim exact runtime/test files after those owners release them; write failing contract, authority, idempotency, pagination, guidance, and load tests first.
4. Implement the canonical router and branch adapter changes plus packaged-runtime parity.
5. Deploy through the normal pipeline only after the exact-branch projection is visibility-safe; run exact-seven canary, the rendered chatbot journey, and post-fix organic-use check.
6. After a separately reviewed serialized/locked wiki patch boundary exists, apply live wiki corrections one page at a time with dry-run and hash-precondition evidence.
7. Sync this delta together with the legacy-retirement delta without dropping either requirement set, then archive only after implementation and acceptance land. Rollback restores the prior image; any rollback reopens the onboarding, guidance, and retirement gates.

## Open Questions

- Which concrete user-controlled host/storage route is the first supported private branch target? It is intentionally outside V1 and does not block commons creation.
- The active universe-visibility lane must either supply a reusable visibility-safe related-wiki projection or explicitly accept a separate prerequisite fix; catalog rollout does not proceed without one.
- The load contract is frozen at p99 below three seconds for the declared 500-client/1,000-operation fixture; the implementation evidence must name hardware and topology rather than weakening the threshold.
