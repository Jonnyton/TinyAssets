## 1. Ownership and review gates

- [ ] 1.1 Refresh current main and obtain explicit accept/adapt from the `universe-creation`, `universe-visibility`, broad-test, and `retire-legacy-live-mcp-tools` owners before claiming runtime or test files.
- [ ] 1.2 Obtain Claude Opus 5 opposite-provider review of the exact spec/evidence head; resolve every Critical/Important or ADAPT item and re-review.
- [ ] 1.3 Resolve or preserve the hosted-private fail-closed gate: name the eligible user-controlled storage owner before enabling private create, while allowing reviewed public-commons creation to proceed independently.
- [ ] 1.4 Re-run file-collision and provider-context checks and create a new runtime STATUS claim with exact canonical, packaging, test, and load-fixture paths.

## 2. Failing public-contract tests

- [ ] 2.1 Add failing exact-seven tests for `read_graph(target="branches")`, closed `write_graph(target="branch")` create/patch discrimination, and no legacy/eighth registration.
- [ ] 2.2 Add failing closed-DTO tests for every accepted V1 field, every protected branch/node field, unknown fields, size/count/string caps, minimal success projection, and bounded error projection.
- [ ] 2.3 Add failing authority tests proving verified-principal authorship, no environment fallback, non-enumerating private/missing behavior, safe public fork lineage, and no graph-membership authority.
- [ ] 2.4 Add failing catalog tests for published/mine scopes, auth, stable tied-timestamp keyset pagination, opaque actor/filter-bound cursors, bounded limits, and zero wiki/provider/gate/custody projection.
- [ ] 2.5 Add failing transactional tests for same-body replay, changed-body conflict, 100 concurrent identical retries, validation rollback, and one branch/ledger/commit.

## 3. Branch authoring and catalog owner

- [ ] 3.1 Implement the versioned request/result/error DTO boundary, canonical digest, numeric caps, and protected-field rejection before calling existing branch handlers.
- [ ] 3.2 Implement actor-scoped transactional idempotency with same-body replay, changed-body conflict, and one atomic branch/ledger/commit result.
- [ ] 3.3 Harden full-definition staging to derive branch/node authorship, validate fork-source visibility before load, apply private-storage availability, avoid attempted-definition echo, and return the minimal create result.
- [ ] 3.4 Implement bounded `published|mine` catalog keyset pagination and the minimal `BranchSummaryV1` projection without a hidden total.

## 4. Canonical MCP routing

- [ ] 4.1 Add `read_graph(target="branches")` parameters and delegate only to the hardened catalog owner; preserve exact `target="branch"` behavior without broadening its related-wiki projection.
- [ ] 4.2 Add `definition_json` branch create mode to `write_graph`, reject mixed/incomplete modes before dispatch, and preserve existing transactional patch semantics without falsely claiming patch CAS.
- [ ] 4.3 Update canonical parameter descriptions, allowed-target errors, structured envelopes, and the packaged runtime through `python packaging/claude-plugin/build_plugin.py`; prove mirror parity.

## 5. Prompt, help, and repository guidance truth

- [ ] 5.1 Rewrite the four registered prompt bodies/docstrings in canonical sources so first contact starts with `converse` and branch discovery/create/inspect/run uses only supported seven-handle target shapes.
- [ ] 5.2 Remove or replace retired-tool advice from first-contact user-facing strings in `tinyassets/api/{prompts,branches,wiki,universe,market}.py` and `tinyassets/universe_server.py`; where no canonical equivalent exists, remove the advice instead of inventing one.
- [ ] 5.3 Correct or mark historical `WORKFLOW_DESIGN_HANDOFF_FOR_POLSIA.md`, regenerate the packaged runtime, and add drift tests scanning prompts/help for retired invocation syntax, stale “five tools” text, opaque-ID-only onboarding, and false OS-sandbox claims.

## 6. Focused and concurrent verification

- [ ] 6.1 Run the new first-contact contract suite plus existing branch read/edit/composite/authoring, handle metadata, exact-registration, anonymous-challenge, and public-canary suites.
- [ ] 6.2 Mutation-test author spoofing, foreign-private fork, altered cursor, removed caps, definition echo, mixed write mode, idempotency bypass, one reintroduced hidden registration, and one stale prompt invocation.
- [ ] 6.3 Run the declared 500-client/1,000-operation load fixture and record environment, p50/p95/p99, error distribution, exact-seven result, privacy assertions, stable pagination, and one-winner create evidence.
- [ ] 6.4 Run scoped Ruff, plugin build/parity, `git diff --check`, strict validation of this change, and the repository-required test gate; obtain independent whole-diff spec and quality review.

## 7. Deploy and rendered acceptance

- [ ] 7.1 Deploy the reviewed runtime, record source SHA/image/release receipt, and run `scripts/mcp_public_canary.py --assert-handles` against `https://tinyassets.io/mcp`.
- [ ] 7.2 Complete the real browser-rendered chatbot journey: browse published branches without a prior ID, create a small public branch, inspect its returned ID, and save prompt/result plus trace or screenshot to `output/user_sim_session.md`.
- [ ] 7.3 Check for post-fix organic use; if none is visible, say so and leave a concise STATUS monitoring item.

## 8. Live wiki compare-and-swap lane

- [ ] 8.1 Re-read every direct page in the evidence manifest, refresh the exact full SHA-256, and expand the lower-bound inventory with privileged `scope=all` or volume export before claiming exhaustive coverage.
- [ ] 8.2 For each direct page, run an exact-one-match dry-run patch with `expected_sha256`; historical pages receive a concise supersession banner rather than rewritten provenance.
- [ ] 8.3 After repository/runtime and opposite-provider gates pass, apply authenticated `dry_run=false` one page at a time, reread each page, and record post-image hashes; stop on any conflict.

## 9. Foldback

- [ ] 9.1 Sync implemented deltas intelligently into canonical `branch-authoring-and-catalog` and `live-mcp-connector-surface`, prove sync idempotence, and strict-validate the full OpenSpec tree.
- [ ] 9.2 Archive the completed change and retire its STATUS row only after runtime, load, deployed canary, rendered chatbot, and live-wiki evidence are truthful.
