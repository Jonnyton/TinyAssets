> **Planning-only gate:** every task below is intentionally unchecked. Tasks
> 1.3-7.5, including the first isolated baseline execution, SHALL NOT start
> until task 1.1 returns a fresh Claude verdict and task 1.2 records accepted
> re-review of every required adaptation.

## 1. Review And Authority Gates

- [ ] 1.1 Obtain a fresh Claude opposite-provider review against current `origin/main`, deployed topology evidence, active owner changes, and draft PR #1670; require an explicit APPROVE, ADAPT, or REJECT verdict with source citations.
- [ ] 1.2 Incorporate every required Claude adaptation and obtain accepted opposite-provider re-review, or stop and revise/close the change without implementation or baseline execution. Record separate host/product-owner decisions only for PLAN or product-boundary changes, budgets, production access/effects, first-write/activation, and numerical public-launch SLOs.
- [ ] 1.3 Name the authority that accepts each first workload profile, numerical gate, repetition count, freshness window, topology fingerprint field, and access-controlled raw-evidence home. The host/product owner accepts public-launch SLOs and budgets unless PLAN assigns a narrower owner. Preserve historical Track J numbers as `historical_target` unless that named authority explicitly reaccepts them.
- [ ] 1.4 Wait for the active broad `tests/` owner (`test-identity-and-reset` / R2 lane) to release or narrow its claim. Then re-run OpenSpec, STATUS, worktree, claim-file, and provider-context collision checks and create narrow implementation claims for `tinyassets/testing/capacity/`, focused capacity tests, isolated fixtures, and only the separately approved CI/evidence paths. Do not claim or edit any test path while the broad owner remains active.
- [ ] 1.5 Confirm every participating MCP/SSE/session, commons/discovery/collaboration, webhook/external-ingress, export/GitHub-projection, storage/retention, moderation/abuse, operator-request, paid-market, live-price, universe, identity/reset, visibility, provider/executor, and uptime owner has an accepted driver/assertion contract; mark absent owner paths `unknown` rather than substituting generic fixtures.

## 2. Contracts And Deny-By-Default Safety

- [ ] 2.1 Add failing contract tests for complete topology manifests, feature probes, unsupported-operation reporting, exact topology fingerprints, isolated namespaces, and rejection of contradictory or incomplete adapters.
- [ ] 2.2 Implement versioned topology-adapter, workload-profile, run-packet, raw-artifact, threshold-provenance, and envelope-cell types under `tinyassets/testing/capacity/` until the contract tests pass.
- [ ] 2.3 Add failing tests proving ambient provider/auth homes, production targets, provider/model calls, market/payment/wallet routes, external effects, destructive production faults, secret-bearing evidence, and unscoped teardown all fail before or during a run.
- [ ] 2.4 Implement scrubbed load-generator environments, isolated run namespaces, forbidden-route sentinels, path containment, secret/private-payload redaction, and idempotent scoped teardown until every safety test passes.
- [ ] 2.5 Add a deterministic synthetic adapter and prove unsupported features become `unknown`, required unavailable dependencies fail visibly, and no skipped result can become a pass.

## 3. Scenario, Evidence, And Envelope Core

- [ ] 3.1 Add failing tests for steady, burst, saturation, topology-failure/recovery, noisy-neighbor, cross-tenant, hot-key, zero-host, reconnect/replay, backlog-recovery, and mixed-authority scenario orchestration.
- [ ] 3.2 Implement the versioned scenario catalog and bounded orchestrator so every scenario consumes one accepted profile, one adapter, and only registered owner drivers/assertions.
- [ ] 3.3 Add failing evidence-validation tests covering exact commands/fingerprints, raw digests, counts, p50/p95/p99/max, throughput, error/failure distributions, resource/pool/queue occupancy, fairness, catch-up/recovery, repetition, sentinels, caveats, and review metadata.
- [ ] 3.4 Implement immutable evidence-packet validation and access-controlled raw-artifact writing; prove incomplete telemetry, missing raw samples, secret-bearing output, or digest mismatch invalidates the affected claim.
- [ ] 3.5 Add failing envelope-projection tests for `verified`, `failed`, and `unknown`, including stale evidence, changed fingerprints, historical targets, unapproved hypotheses, incomplete repetitions, missing reviews, unsupported faults, and unrelated-path separation.
- [ ] 3.6 Implement the deterministic conservative envelope projector and prove it publishes only measured reviewed lower bounds without DAU/vendor-limit extrapolation.

## 4. Dated `412a876a` Single-Origin Baseline

- [ ] 4.1 Build an isolated production-shaped clone of the single-origin/shared-volume topology observed at `origin/main` `412a876a`, with synthetic tenants/data, deterministic provider fakes, no mounted provider auth homes, no production network access or mutation, and a reproducible dated manifest.
- [ ] 4.2 Implement the dated `412a876a` baseline fixture plus run-time source/deployment/topology probes. Prove the adapter accepts only a matching one-origin, shared-volume/process-local shape; classifies fixed shared-auth workers as ineligible; reports no requester-authorized public executor or usable OS-isolating `SandboxBackend`; and refuses any changed topology pending a new dated fixture.
- [ ] 4.3 Execute the accepted steady/burst/saturation/recovery/isolation profiles against the exactly matched isolated baseline; record exact source/image/config plus bounded live observation `519fb2ea` only as separately authorized context, never as capacity evidence.
- [ ] 4.4 Obtain independent evidence review and publish the result only under the isolated-clone topology/environment ID, with every unproved replica, durable-queue, PostgreSQL, failover, and public-executor dimension explicitly `unknown`. Keep corresponding public-deployment cells `unknown` unless every capacity-relevant image/configuration, hardware/resource, contention, gateway/region/network, and storage fingerprint matches through separately safe evidence.

## 5. Domain-Owned Composition

- [ ] 5.1 Add owner plug-in contract tests proving the harness cannot create identity, select/reset a principal, widen visibility, admit operator priority, construct a market transition, invent a price, grant provider/executor authority, or activate recovery.
- [ ] 5.2 Consume only owner-published test-identity/reset and identity-auth plug-ins for repeatable synthetic tenants; prove raw subjects, bearers, provider credentials, and another principal's reset scope never enter evidence. Any owner-file change requires that owner's separate claim and review.
- [ ] 5.3 Consume the owner-published operator-request workload/assertion plug-in and run its literal Section 14 and zero-compatible-capacity cases without changing epoch, admission, claim, or provider-authority semantics. This lane edits only harness-side registration/orchestration.
- [ ] 5.4 Consume owner-published paid-market workflow and live-price plug-ins; run their stricter conservation, quote-freshness, isolation, reconnect, contention, recovery, and zero-host assertions without direct harness mutation or purchase. Domain-driver changes stay with their owners.
- [ ] 5.5 Consume owner-published universe-authority and visibility plug-ins; exercise concurrent birth, hot-universe access, and cross-tenant reads while preserving founder binding, lifecycle, and existence/metadata/content/page grants. Owner changes require separate claims.
- [ ] 5.6 Consume owner-published distributed-execution/provider-authority and uptime plug-ins; prove unsupported public execution remains `unknown` and that harness evidence cannot authorize executor or serving-topology activation. This lane does not implement those owners' drivers.
- [ ] 5.7 Consume owner-published MCP/SSE/session, commons/discovery/collaboration, webhook/external-ingress, export/GitHub-projection, storage-growth/retention, and moderation/abuse plug-ins. Missing owner suites remain explicit `unknown` cells, and every owner-file change requires a separate claim and review.

## 6. PostgreSQL Adapter Consumption By PR #1670

- [ ] 6.1 Publish the PostgreSQL adapter interface and acceptance checklist for the #1670 owner. Require a separately claimed and reviewed #1670 adaptation before that lane implements an adapter over its approved baseline, roles, migration runner, transactions, Realtime, recovery, and stock-PostgreSQL exit; this task authorizes no edits to #1670.
- [ ] 6.2 Add harness-side adapter conformance tests, then consume the #1670-owner-published adapter evidence for the accepted Supabase-shaped environment and supported stock PostgreSQL. Absent queue/realtime/executor features remain `unknown`; database feature implementation and integration tests remain #1670-owned.
- [ ] 6.3 Through #1670 owner consent and review, verify that its separately claimed adaptation consumes the common catalog/evidence contract instead of publishing parallel generic Section 14 machinery, while retaining its stricter migration, role/RLS, pool, transaction, backup/restore, exit, cutover, and domain gates.
- [ ] 6.4 After the owner-published adapter is accepted, execute the accepted PostgreSQL profiles through the shared harness and publish only reviewed exact-topology cells; database success SHALL NOT imply queue, realtime, failover, domain, or executor capacity.

## 7. CI, Review, And Foldback

- [ ] 7.1 Add focused CI contract/synthetic runs that require dependencies to fail rather than skip and that never require production credentials, provider accounts, market funds, or production mutation.
- [ ] 7.2 Add separately approved isolated capacity jobs with concurrency cancellation, artifact retention/redaction, cost/runtime bounds, and no deploy or activation side effect.
- [ ] 7.3 Run focused tests, strict OpenSpec validation, safety/secret checks, each accepted topology profile, and independent code-to-requirement plus evidence review against the exact landing SHA.
- [ ] 7.4 For any public capacity/status presentation added by a dependent change, run the required public canary, rendered chatbot acceptance, and post-fix clean-use check without claiming unknown dimensions.
- [ ] 7.5 Sync `public-capacity-envelope` into canonical specs and archive this change only after implementation, reviewed isolated baselines, and all required owner proofs are complete; otherwise leave tasks unchecked and the change active.
