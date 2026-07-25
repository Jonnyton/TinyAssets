## 1. Ownership and review gates

- [ ] 1.1 Refresh current main and obtain explicit accept/adapt from the active `universe-creation` and `universe-visibility` owners before claiming runtime or test files. Re-check `retire-legacy-live-mcp-tools` at claim time; it is unclaimed as of 2026-07-25, so any later owner must receive and record the replacement-first dependency.
- [ ] 1.2 Obtain Claude Opus 5 opposite-provider review of the exact spec/evidence head; resolve every Critical/Important or ADAPT item and re-review.
- [ ] 1.3 Keep V1 commons-only. Reject non-public visibility before persistence; any private authoring route requires a separate PLAN-approved user-controlled-storage change.
- [ ] 1.4 Treat a visibility-safe `read_graph(target="branch")` projection and every shared exact alias/helper as a hard runtime, create/publish-mode, catalog, deploy, prompt, and rendered-acceptance prerequisite; obtain the universe-visibility owner's accept/adapt.
- [ ] 1.5 Add `TINYASSETS_BRANCH_CRYPTO_KEYRING` to the deployment host-action lane with named rotation owner, current/prior retention, and validation receipt; no catalog/create/publish runtime claim proceeds without it.
- [ ] 1.6 Re-run file-collision and provider-context checks and create a new runtime STATUS claim with exact canonical, `tinyassets/branch_versions.py`, `tinyassets/api/{branches,evaluation,selector_dispatch}.py`, secret-catalog, migration, packaging, test, and load-fixture paths.

## 2. Failing public-contract tests

- [ ] 2.1 Add failing exact-surface tests for `read_graph(target="branches")`, closed `write_graph(target="branch")` create/patch/publish discrimination, target-scoped idempotency docs, and no legacy/eighth registration.
- [ ] 2.2 Add failing duplicate-member and positive-schema tests for every typed top-level/node/edge/conditional-edge/state-field key, exact `str|int|float|bool|list|dict|any` compiler semantics, null-versus-omitted defaults, every protected/unknown nested key, body/collection/string/numeric/output caps, prompt-template-only enforcement, minimal projections, and exact error enums.
- [ ] 2.3 Add failing authority tests proving verified-principal authorship/publisher identity, no environment fallback or MCP `force` bypass, no graph-membership authority, no caller/generated-ID overwrite, V1 rejection of fork/Goal/source/private shapes, and shared patch-helper rejection of author/approval fields with source approval cleared on mutation.
- [ ] 2.4 Add failing catalog tests for `published|mine`, actionable anonymous-mine error, commons predicate, exact query/tag/filter normalization, default 30/max 100, immutable non-starving pagination under unrelated writes, closed AES-GCM envelope/multi-instance nonce leases/tag/expiry/rotation/tampering, bounded last-examined pages, active version+publication revision verification, and zero restricted/private-store projection.
- [ ] 2.5 Add failing transaction tests for same-body replay, actor/key publish replay before state lookup after patch/public→private/rollback/deletion, changed-branch key conflict, retention/expiry, rolling secret aliases, missing/malformed keyring across all three modes, 100 concurrent identical create/publish retries, pre/post-commit crashes, UUID collision retry, validation rollback, one branch/idempotency/outbox transaction, crash-after-effect-before-ack dedupe, and downstream export failure.
- [ ] 2.6 Add failing deliberate-publication tests proving stored-row public eligibility, create starts unpublished, patch/evaluation/selector snapshots create no publication record, explicit publish is owner/idempotency-bound, operational metadata is preserved, revisions supersede monotonically, delayed events cannot regress the pointer, rollback removes eligibility, `set_published` is rejected canonically, and publication outbox delivery is exact.
- [ ] 2.7 Add a failing catalog/create/publish-to-exact-read test proving a returned branch ID cannot disclose restricted related-wiki metadata through `get_branch`, `describe_branch`, or their shared helper; all three new modes stay unavailable while any exact path is unsafe.

## 3. Branch authoring and catalog owner

- [ ] 3.1 Implement the versioned closed request/result/error DTO boundary, RFC 8785 digests, exact compiler type vocabulary, numeric/default-value caps, prompt-template-only nested allowlists, and protected-field rejection before calling existing handlers.
- [ ] 3.2 Add the connection-accepting branch-save seam plus canonical-branch schema migration for unique actor/key aliases, command digest, retained result, immutable-order catalog projection, nonce-prefix leases, and unique UUIDv4 outbox event; commit create state in one transaction with configured retention of at least 24 hours.
- [ ] 3.3 Implement `TINYASSETS_BRANCH_CRYPTO_KEYRING` parsing/HKDF/catalog docs, retained-key aliases across rolling rotation, same-body replay, changed-body conflict, pre/post-commit crash recovery, collision retry, and stable outbox-event replay; optional consumers transact effect+dedupe by `event_id` or use inherently idempotent effects.
- [ ] 3.4 Harden full-definition staging to derive branch/node authorship, reject fork/Goal/source/private shapes, avoid attempted-definition echo, and return the minimal create result.
- [ ] 3.5 Harden the shared patch/node-spec staging reached by canonical and retained aliases so caller authorship/approval/IDs and MCP `force` bypass are rejected, new-node author is derived, any admitted source mutation clears approval, and `set_published` directs canonical callers to publish mode.
- [ ] 3.6 Add a version-store migration and connection-accepting transaction seam for `branch_catalog_publications`, per-branch revision/current state, publish idempotency aliases/results, and revisioned projection outbox; route `branches.py`, `evaluation.py`, and `selector_dispatch.py` through `publish_branch_version` without overwriting operational snapshot metadata, and make rollback emit the next ineligible revision.
- [ ] 3.7 Implement and backfill the bounded catalog projection for reviewed eligible commons rows, immutable `created_at` ordering, capped last-examined scanning, non-starving encrypted pagination, normalized filters, read-only active version/publication verification, compare-and-advance revision consumption, rollback reconciliation, and minimal `BranchSummaryV1` without a hidden total.

## 4. Canonical MCP routing

- [ ] 4.1 Repair `read_graph(target="branch")`, internal `get_branch`, `describe_branch`, and their shared related-wiki projection so restricted pages contribute no item, path, title, summary, boolean, or count; keep new create/catalog/publish modes unavailable until verified.
- [ ] 4.2 Add `definition_json` create and explicit `publish=true` modes to `write_graph`, reject mixed/incomplete modes before dispatch, and preserve all-or-none patch staging without falsely claiming patch idempotency or CAS.
- [ ] 4.3 Add `read_graph(target="branches")` scope/domain/cursor parameters without changing existing target defaults; reject unrelated non-default shared-handle fields and delegate only to the hardened catalog owner.
- [ ] 4.4 Re-scope the `idempotency_key` docstring/metadata to create and publish only, update publish/definition parameter descriptions, allowed-target errors, structured envelopes, and the packaged runtime through `python packaging/claude-plugin/build_plugin.py`; prove mirror parity and add drift coverage.

## 5. Prompt, help, and repository guidance truth

- [ ] 5.1 Rewrite the four registered prompt bodies/docstrings in canonical sources so first contact starts with `converse`; prompt-template V1 discovery/create/inspect/publish/rediscovery uses canonical target shapes; any run first requires requester BYOC/market authority and never maintainer quota.
- [ ] 5.2 Remove or replace retired-tool advice from first-contact user-facing strings in `tinyassets/api/{prompts,branches,wiki,universe,market}.py` and `tinyassets/universe_server.py`; where no canonical equivalent exists, remove the advice instead of inventing one.
- [ ] 5.3 Remove source-code/fork/Goal-binding instructions from first-contact guides; broader source guidance must disclose the missing canonical approval route and current non-OS-isolated execution boundary.
- [ ] 5.4 Correct or mark historical `WORKFLOW_DESIGN_HANDOFF_FOR_POLSIA.md`, regenerate the packaged runtime, and add drift tests scanning prompts/help for retired invocation syntax, stale "five tools" text, opaque-ID-only onboarding, excluded V1 shapes, and false OS-sandbox claims.

## 6. Focused and concurrent verification

- [ ] 6.1 Run the new first-contact contract suite plus existing branch read/edit/composite/authoring, handle metadata, exact-registration, anonymous-challenge, and public-canary suites.
- [ ] 6.2 Mutation-test branch/node/publisher spoofing, stored-row visibility bypass, self-approval patch, `force` bypass, caller/generated-ID overwrite, private/fork/Goal/source create, duplicate JSON members, multi-instance nonce-lease/tag/ciphertext tampering or reuse, cursor starvation, false/out-of-order/rolled-back publication, removed caps, definition echo, mixed write mode, idempotency/keyring bypass, one reintroduced hidden registration, and one stale/BYOC-unsafe prompt.
- [ ] 6.3 Run the declared 500-client/1,000-operation 750-read/200-create/50-publish fixture under production SQLite settings and record hardware, p50/p95/p99, error distribution, exact-surface result, restricted-data assertions, completed pagination during concurrent writes, cross-instance nonce uniqueness, monotonic deliberate-publication evidence, and one-winner create/publish results.
- [ ] 6.4 Run scoped Ruff, plugin build/parity, `git diff --check`, strict validation of this change, and the repository-required test gate; obtain independent whole-diff spec and quality review.

## 7. Deploy and rendered acceptance

- [ ] 7.1 Deploy only after the visibility-safe exact branch projection, provisioned keyring, and fail-closed create/catalog/publish gates pass; record source SHA/image/release receipt and run `scripts/mcp_public_canary.py --assert-handles` against `https://tinyassets.io/mcp`.
- [ ] 7.2 Complete the real browser-rendered chatbot journey: browse without a prior ID, create and inspect a public prompt-template V1 branch, explicitly publish it, rediscover it, and save prompt/result plus trace or screenshot to `output/user_sim_session.md`; any run uses requester-owned BYOC/market authority.
- [ ] 7.3 Check for post-fix organic use; if none is visible, say so and leave a concise STATUS monitoring item.

## 8. Live wiki serialized hash-guard lane

- [ ] 8.1 Re-read every direct page in the evidence manifest, refresh the exact full SHA-256, and expand the lower-bound inventory with privileged `scope=all` or volume export before claiming exhaustive coverage.
- [ ] 8.2 Add or identify a separately reviewed serialized/locked single-writer boundary; the current read/check/write SHA precondition alone is race-prone and does not authorize live writes.
- [ ] 8.3 For each direct page, fill audience and exact replacement, then run an exact-one-match dry-run with `expected_sha256`; historical pages receive a concise supersession banner rather than rewritten provenance.
- [ ] 8.4 After repository/runtime, opposite-provider, and serialized-writer gates pass, apply authenticated `dry_run=false` one page at a time, reread each page, and record guarded-write and post-image hashes; stop on any conflict.

## 9. Foldback

- [ ] 9.1 Do not sync this connector delta while canonical truth still contains the legacy-registration requirement. Reconcile baseline plus both changes' concurrent MODIFIED `Canonical Advertised Handle Set` text, preserving the existing goal write/read scenario, exact handles, shared-owner hardening, journey composition, `publish_version`/approval replacement-first prerequisites, and every surviving retirement scenario; prove sync idempotence and strict-validate the full OpenSpec tree.
- [ ] 9.2 Archive the completed change and retire its STATUS row only after runtime, load, deployed canary, rendered chatbot, and live-wiki evidence are truthful.
