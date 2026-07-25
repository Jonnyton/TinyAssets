## 1. Ownership and review gates

- [ ] 1.1 Refresh current main and obtain explicit accept/adapt from the active `universe-creation` and `universe-visibility` owners before claiming runtime or test files. Re-check `retire-legacy-live-mcp-tools` at claim time; it is unclaimed as of 2026-07-25, so any later owner must receive and record the replacement-first dependency.
- [ ] 1.2 Obtain Claude Opus 5 opposite-provider review of the exact spec/evidence head; resolve every Critical/Important or ADAPT item and re-review.
- [ ] 1.3 Keep V1 commons-only. Reject non-public visibility before persistence; any private authoring route requires a separate PLAN-approved user-controlled-storage change.
- [ ] 1.4 Treat a visibility-safe `read_graph(target="branch")` projection and every shared exact alias/helper as a hard runtime, create-mode, catalog, deploy, prompt, and rendered-acceptance prerequisite; obtain the universe-visibility owner's accept/adapt.
- [ ] 1.5 Re-run file-collision and provider-context checks and create a new runtime STATUS claim with exact canonical, migration, packaging, test, and load-fixture paths.

## 2. Failing public-contract tests

- [ ] 2.1 Add failing exact-surface tests for `read_graph(target="branches")`, closed `write_graph(target="branch")` create/patch discrimination, and no legacy/eighth registration.
- [ ] 2.2 Add failing positive-schema tests for every allowed top-level/node/edge/conditional-edge/state-field key, exact `str|int|float|bool|list|dict|any` compiler semantics, every protected/unknown nested key, body/collection/string/numeric/default-value caps, prompt-template-only enforcement, minimal success projection, and bounded errors.
- [ ] 2.3 Add failing authority tests proving verified-principal authorship, no environment fallback, no graph-membership authority, no caller-supplied/generated ID overwrite, V1 rejection of fork/Goal/source/private shapes, and existing patch rejection of author/approval fields with source approval cleared on mutation.
- [ ] 2.4 Add failing catalog tests for `published|mine`, closed shared-handle defaults, auth, exact query/tag/filter normalization, default 30/max 100, generation-stale pagination, encrypted actor/filter-bound cursors, expiry/rotation, bounded partial pages, authoritative published-version verification, and zero wiki/provider/gate/custody/private-store projection.
- [ ] 2.5 Add failing transaction tests for same-body replay, changed-body conflict, retention/expiry, rolling secret rotation with retained-version aliases, 100 concurrent identical retries, pre/post-commit crashes, validation rollback, one branch/idempotency/outbox transaction, stable-event replay, and downstream export failure.
- [ ] 2.6 Add a failing catalog/create-to-exact-read test proving a returned branch ID cannot disclose restricted related-wiki metadata through `get_branch`, `describe_branch`, or their shared helper; new create/catalog modes must stay unavailable while any exact path is unsafe.

## 3. Branch authoring and catalog owner

- [ ] 3.1 Implement the versioned closed request/result/error DTO boundary, RFC 8785 digests, exact compiler type vocabulary, numeric/default-value caps, prompt-template-only nested allowlists, and protected-field rejection before calling existing handlers.
- [ ] 3.2 Add the connection-accepting branch-save seam plus schema migration for unique actor/key fingerprint, key version, command digest, retained result, catalog projection/generation, and attribution outbox with stable `event_id`; commit them in one canonical database transaction with at least 24-hour disclosed retention.
- [ ] 3.3 Implement retained-key fingerprint lookup plus unique aliases across rolling secret rotation, same-body replay, changed-body conflict, pre/post-commit crash recovery, and stable outbox-event replay; keep any optional consumer idempotent by `event_id` and source-control/GitHub export downstream.
- [ ] 3.4 Harden full-definition staging to derive branch/node authorship, reject fork/Goal/source/private shapes, avoid attempted-definition echo, and return the minimal create result.
- [ ] 3.5 Harden existing patch staging so caller authorship/approval/IDs are rejected, new-node author is derived, and any admitted source mutation clears approval.
- [ ] 3.6 Implement and backfill the bounded canonical-database catalog projection for existing eligible commons rows, publication outbox/periodic reconciliation, capped candidate scanning with last-examined cursors, generation-stale encrypted pagination, normalized filters, read-only authoritative published-version verification, and minimal `BranchSummaryV1` without a hidden total.

## 4. Canonical MCP routing

- [ ] 4.1 Repair `read_graph(target="branch")`, internal `get_branch`, `describe_branch`, and their shared related-wiki projection so restricted pages contribute no item, path, title, summary, boolean, or count; keep new create/catalog modes unavailable until verified.
- [ ] 4.2 Add `definition_json` branch create mode to `write_graph`, reject mixed/incomplete modes before dispatch, and preserve all-or-none patch staging without falsely claiming patch idempotency or CAS.
- [ ] 4.3 Add `read_graph(target="branches")` scope/domain/cursor parameters without changing existing target defaults; reject unrelated non-default shared-handle fields and delegate only to the hardened catalog owner.
- [ ] 4.4 Update canonical parameter descriptions, allowed-target errors, structured envelopes, and the packaged runtime through `python packaging/claude-plugin/build_plugin.py`; prove mirror parity.

## 5. Prompt, help, and repository guidance truth

- [ ] 5.1 Rewrite the four registered prompt bodies/docstrings in canonical sources so first contact starts with `converse` and prompt-template-only V1 branch discovery/create/inspect/run uses only supported canonical target shapes.
- [ ] 5.2 Remove or replace retired-tool advice from first-contact user-facing strings in `tinyassets/api/{prompts,branches,wiki,universe,market}.py` and `tinyassets/universe_server.py`; where no canonical equivalent exists, remove the advice instead of inventing one.
- [ ] 5.3 Remove source-code/fork/Goal-binding instructions from first-contact guides; broader source guidance must disclose the missing canonical approval route and current non-OS-isolated execution boundary.
- [ ] 5.4 Correct or mark historical `WORKFLOW_DESIGN_HANDOFF_FOR_POLSIA.md`, regenerate the packaged runtime, and add drift tests scanning prompts/help for retired invocation syntax, stale "five tools" text, opaque-ID-only onboarding, excluded V1 shapes, and false OS-sandbox claims.

## 6. Focused and concurrent verification

- [ ] 6.1 Run the new first-contact contract suite plus existing branch read/edit/composite/authoring, handle metadata, exact-registration, anonymous-challenge, and public-canary suites.
- [ ] 6.2 Mutation-test branch/node author spoofing, self-approval patch, caller/generated-ID overwrite, private/fork/Goal/source create, altered/cross-context cursor, stale catalog generation, false publication projection, removed caps, definition echo, mixed write mode, idempotency bypass, one reintroduced hidden registration, and one stale prompt invocation.
- [ ] 6.3 Run the declared 500-client/1,000-operation 800-read/200-create fixture under production SQLite settings and record hardware, p50/p95/p99, error distribution, exact-surface result, restricted-data assertions, cursor-stale behavior, and one-winner create evidence.
- [ ] 6.4 Run scoped Ruff, plugin build/parity, `git diff --check`, strict validation of this change, and the repository-required test gate; obtain independent whole-diff spec and quality review.

## 7. Deploy and rendered acceptance

- [ ] 7.1 Deploy only after the visibility-safe exact branch projection and fail-closed create/catalog gates pass; record source SHA/image/release receipt and run `scripts/mcp_public_canary.py --assert-handles` against `https://tinyassets.io/mcp`.
- [ ] 7.2 Complete the real browser-rendered chatbot journey: browse published branches without a prior ID, create a small public prompt-template V1 branch, inspect its returned ID, and save prompt/result plus trace or screenshot to `output/user_sim_session.md`.
- [ ] 7.3 Check for post-fix organic use; if none is visible, say so and leave a concise STATUS monitoring item.

## 8. Live wiki serialized hash-guard lane

- [ ] 8.1 Re-read every direct page in the evidence manifest, refresh the exact full SHA-256, and expand the lower-bound inventory with privileged `scope=all` or volume export before claiming exhaustive coverage.
- [ ] 8.2 Add or identify a separately reviewed serialized/locked single-writer boundary; the current read/check/write SHA precondition alone is race-prone and does not authorize live writes.
- [ ] 8.3 For each direct page, fill audience and exact replacement, then run an exact-one-match dry-run with `expected_sha256`; historical pages receive a concise supersession banner rather than rewritten provenance.
- [ ] 8.4 After repository/runtime, opposite-provider, and serialized-writer gates pass, apply authenticated `dry_run=false` one page at a time, reread each page, and record guarded-write and post-image hashes; stop on any conflict.

## 9. Foldback

- [ ] 9.1 Do not sync this connector delta while canonical truth still contains the legacy-registration requirement. Once implemented, sync this change together with `retire-legacy-live-mcp-tools`, preserving the canonical exact-handle requirement, this journey-composition requirement, the replacement-first approval prerequisite, and every surviving retirement requirement; prove sync idempotence and strict-validate the full OpenSpec tree.
- [ ] 9.2 Archive the completed change and retire its STATUS row only after runtime, load, deployed canary, rendered chatbot, and live-wiki evidence are truthful.
