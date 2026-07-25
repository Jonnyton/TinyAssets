## Context

The public connector advertises exactly seven handles. `read_graph(target="branch")` delegates to exact `get_branch` and therefore requires a caller to already know a `branch_def_id`; `write_graph(target="branch")` delegates only to `patch_branch`. The internal branch adapter already has visibility-filtered list and atomic full-definition build seams, but they are not safe to publish unchanged: listing is unbounded, author/approval fields are caller-influenceable, fork visibility is not checked first, validation can echo the submitted definition, and branch creation has no transactional idempotency.

The four registered MCP prompts also predate the canonical handle fold. They teach `extensions`, `goals`, `gates`, `wiki`, and `community_change_context`, while the active retirement change removes those hidden registrations. Live wiki pages require a separate exact-path correction manifest and existing compare-and-swap writes; repository prompt corrections cannot be treated as proof that live content changed.

Runtime files are owned by the active universe-creation, universe-visibility, broad-test, and legacy-retirement lanes. This change therefore produces the contract and review packet only.

## Goals / Non-Goals

**Goals:**

- Make branch discovery and first complete branch creation possible through the existing seven handles.
- Publish closed, bounded, non-enumerating request/result/error contracts.
- Bind branch and node provenance to verified request authority, never environment identity or caller-supplied ownership fields.
- Make create retries transactionally idempotent and validation failures atomic.
- Make registered first-contact guidance truthful for canonical handles and current source-code isolation limits.
- Define scale and rendered-chatbot proofs before runtime landing.

**Non-Goals:**

- No eighth MCP tool, hidden compatibility registration, magic default branch, or parallel authoring substrate.
- No runtime edit, canonical-spec sync/archive, deployment, live wiki write, or rollout in this lane.
- No repair of the existing exact-branch related-wiki projection leak; the universe-visibility owner must provide or accept the reusable safe projection before runtime integration.
- No platform custody of private branch content. Hosted private creation remains unavailable unless a user-controlled host/storage route satisfying PLAN exists.
- No compute, provider, execution, purchasing, or market authority follows from listing or creating a branch.

## Decisions

### 1. Extend targets, not tools

`read_graph(target="branches")` becomes the branch catalog. `read_graph(target="branch")` remains exact inspection. `write_graph(target="branch")` becomes a closed create-or-patch union. This preserves the exact seven handles and uses established branch ownership instead of re-advertising the legacy `extensions` surface.

Alternative rejected: add `list_branches` or `build_branch` tools. They are conveniences over the canonical graph handles and would permanently increase the public tool budget.

### 2. Use closed, versioned DTOs

Create accepts `BranchCreateDefinitionV1` in `definition_json`. It has a fixed allowlist and `schema_version="branch-definition-v1"`; identifiers, authorship, approval, publication, timestamps, statistics, ownership/ACL, universe/tenant, and related-wiki fields are server-owned and rejected if supplied. Node author/approval/registration fields are likewise rejected. A one-MiB total body cap plus numeric collection/string caps bounds validation and storage work.

Creation requires no `branch_id` or `changes_json`; patching requires both and forbids `definition_json`. Mixed or incomplete inputs fail before a handler runs. The adapter maps the create definition to the existing internal build seam only after authority and shape validation.

Alternative rejected: overload `changes_json` for both create and patch. That makes mode selection ambiguous and invites accidental partial creation.

### 3. Authority is verified and non-enumerating

The server derives the branch author and every node author from the authenticated request principal. `UNIVERSE_SERVER_USER`, caller-supplied author fields, graph membership, and a branch name are never positive authority.

`fork_from` resolves only a public active-published version or a caller-owned private version reachable through an eligible user-controlled host. Missing and unauthorized sources return the same `branch_not_found` envelope. Validation and filtering happen after ACL admission, so query, pagination, and derived projections cannot reveal excluded rows.

### 4. Catalog scope is `published` or `mine`

The default `published` scope returns public branches with an active published version. Authenticated `mine` returns branches authored by the verified actor and admitted by the canonical storage boundary. There is no public `all`, `visible`, `include_private`, or universe-membership shortcut.

Results use stable keyset ordering `(updated_at DESC, branch_def_id ASC)`, an opaque cursor bound to actor, scope, and normalized filters, default limit 25, and maximum 100. The response exposes no hidden total count. Summaries are deliberately smaller than exact branch reads and never carry node bodies, prompts, source, wiki metadata, gate/custody data, or execution authority.

Alternative rejected: expose the internal `published/all/mine` scopes directly. `all` is ambiguous at a public boundary and risks turning an internal host option into an enumeration contract.

### 5. Create is body-bound idempotent

Creation requires a 16–128 character `idempotency_key`. The transaction key is scoped to the verified actor and bound to a canonical digest of the accepted V1 definition plus effective visibility and lineage. Same-key/same-body replay returns the original minimal result; changed-body reuse conflicts. Concurrent identical submissions create one branch, one attribution/ledger record, and one storage commit.

Alternative rejected: deduplicate on branch name. Branch names are intentionally non-unique and part of the user-designed commons.

### 6. Private creation follows the storage boundary

Public creation can land in the platform commons. Private creation succeeds only when the request is routed to eligible user-controlled storage; otherwise it returns `branch_private_storage_unavailable` before persistence. The router does not add platform-side private rows or an `is_private` substitute.

### 7. Guidance has one canonical vocabulary

The registered `control_station`, `meet_universe`, `extension_guide`, and `branch_design_guide` prompts must describe workflows using only the seven handles and their supported targets. The first-contact path starts with `converse`; branch examples compose `read_graph(target="branches"|"branch")`, `write_graph(target="branch")`, and `run_graph`. Source-code guidance must disclose that the current compiled path is not OS-isolated rather than promising sandbox execution.

Live wiki corrections are enumerated separately with exact paths, pre-image hashes, replacement text, dry-run evidence, and post-image hashes. A repository prompt change never implies a live wiki mutation.

### 8. Acceptance includes concurrency and a rendered user journey

Before runtime landing, a deterministic fixture exercises 500 logical clients and 1,000 mixed catalog/create operations, including tied timestamps, concurrent identical retries, private-source probes, and cross-actor cursor replay. It must show no 5xx, private metadata leak, duplicate/partial create, unstable pagination, or extra advertised handle, with p99 under three seconds in the declared test environment.

Final acceptance then uses a real browser-rendered chatbot through `https://tinyassets.io/mcp`: discover a branch without an ID, create a new complete public branch, inspect the returned ID, and preserve the exact seven-tool listing. Post-fix organic use is checked separately or left as a STATUS watch.

## Risks / Trade-offs

- **[Risk] The internal build seam accepts unsafe ownership/provenance fields.** → Validate a closed V1 DTO and derive protected fields before delegation; mutation-test every protected field.
- **[Risk] Pagination can skip or duplicate tied updates.** → Use two-column keyset ordering and bind the opaque cursor to normalized filters and actor.
- **[Risk] Validation responses disclose prompts/source.** → Return bounded field paths and codes only; never echo `definition_json`.
- **[Risk] Private creation conflicts with commons-first PLAN.** → Fail before persistence unless an eligible user-controlled storage route exists; do not resolve the PLAN decision locally.
- **[Risk] Active owners land incompatible seams.** → Keep this lane spec-only, obtain explicit owner accept/adapt, then rebase and rerun current-main review before runtime claim.
- **[Risk] Corrected prompts coexist with stale live wiki pages.** → Keep an exact two-surface manifest and require independent CAS proof for every live page.

## Migration Plan

1. Land this strict-valid spec/review packet as a blocked draft after Claude Opus 5 review.
2. Obtain accept/adapt from universe-creation, universe-visibility, broad-test, private-storage, and legacy-retirement owners.
3. Claim exact runtime/test files after those owners release them; write failing contract, authority, idempotency, pagination, guidance, and load tests first.
4. Implement the canonical router and branch adapter changes plus packaged-runtime parity.
5. Deploy through the normal pipeline; run exact-seven canary, the rendered chatbot journey, and post-fix organic-use check.
6. Apply live wiki corrections one page at a time with dry-run and compare-and-swap evidence.
7. Sync deltas into canonical specs and archive only after implementation and acceptance land. Rollback restores the prior image; any rollback reopens the onboarding and guidance gates.

## Open Questions

- Which concrete user-controlled host/storage route is the first supported private branch target? Public commons creation does not wait on this answer.
- Will the active universe-visibility lane supply a reusable visibility-safe related-wiki projection, or will exact branch inspection need a separate follow-up?
- The final numeric latency threshold must be freshness-checked against the production/test topology at implementation time; correctness and non-leak assertions are not negotiable.
