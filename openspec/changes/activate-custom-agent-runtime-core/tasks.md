## 1. Review and Exact Owner Handoff

- [ ] 1.1 Run strict OpenSpec and bounded-flow checks, fold an independent exact-head architecture/security review, then obtain exact current-main activation, provider-work, continuation, grant-resolver, health, packaged-mirror, and test handoffs before broadening STATUS Files; explicitly fence the Branch-only background-attempt owner out of agent invocation.

## 2. Immutable Subject, Manifest, and Compilation

- [x] 2.1 Test-first, add the shared typed execution subject to canonical activation, derive the sole agent automation key from `(universe_id, agent_binding_id)`, and prove concurrent aliases cannot create a second row while every Branch CAS/epoch/executor/lease guard remains unchanged. Completed 2026-08-01 in PR #2082: canonical and packaged activation/admission/task owners now use `ExecutionSubject(kind, ref, digest)`; generic creation cannot enter the reserved agent namespace and activation/rebind/claim enforce kind-to-namespace coupling; the reserved agent key is deterministically derived from the binding within the universe; legacy stopped rows migrate transactionally while active legacy rows fail closed; Branch admission refuses agent subjects; eight-way alias/migration races, 383 broader authority regressions, Ruff, strict OpenSpec, and 301-file mirror parity pass. Exact-head opposite-provider review gates landing.
- [x] 2.2 Test-first, add immutable agent runtime manifest persistence with exact binding/definition/adapter/reference/budget pins, canonical digest, atomic failure, owner-scoped idempotency, private reads, and no credentials/conversations/outputs/effects/runtime state. Completed 2026-08-01 in #2091 with canonical and packaged manifest/store owners, source-truth revalidation, tamper refusal, concurrent single identity, and private bounded persistence; the capability remains dark and does not activate or execute the manifest.
- [ ] 2.3 Test-first, add the governed component-adapter registry and deterministic exhaustive component compiler with explicit runtime modes, descriptive-only data, unsupported/type/confinement refusal, and complete deterministic diagnostics.
- [ ] 2.4 Test-first, add governed plan-adapter compilation with adapter-declared topology/entry/coverage semantics and one bounded provider-turn plan/component pair; prove no universal DAG, single-entry, fixed taxonomy, or silent component omission.

## 3. Delegated Requester-Owned Execution

- [ ] 3.1 Test-first, derive the immutable agent runtime principal and live-check current delegated capability/resource/provider grants on activation, invocation, and resume without accepting caller-authored actors or owner/maintainer/ambient authority.
- [ ] 3.2 Test-first, atomically consume a live authenticated provider-work binding draft into one linked `ProviderWorkBinding`, server-authored `AgentInvocationCommand`, and append-only invocation root; prove exact replay, changed-input conflict, concurrent single winner, missed-boundary/no-write behavior, bearer-free recovery provenance, and helper/dispatcher/queue bypass refusal.
- [ ] 3.3 Test-first, admit only that command/invocation lineage into canonical provider-work reservation/claim/launch with requester-owned credential routing, conserved budgets, typed non-authoritative output, and unchanged Branch authority guards.

## 4. Single-Active Recovery and Health

- [ ] 4.1 Test-first, compose agent invocation with canonical cloud continuation and restart reconciliation under the same subject/command/invocation/provider identities; prove no `BackgroundBranchAttempt`, replacement identity, graph/effect/app, or public-control path is reached.
- [ ] 4.2 Test-first, add the private useful-progress projection over canonical owner records with exact subject/epoch/lease/grant/budget revalidation, stale-executor fencing, and no-progress alarms.

## 5. Dark Verification and Foldback

- [ ] 5.1 Run focused/regression/security/fault/type/lint/mirror suites, cross-process identity races, §14 production-shaped load, worker-restart recovery, existing Branch authority regressions, and dark deployment health using only requester-owned authority; verify seven public handles and app/workflow/effect routes remain unchanged.
- [ ] 5.2 Obtain independent exact-head code/security review, sync `custom-agent-runtime-core` plus both modified owner deltas, archive this change, retire its STATUS claim, and hand immutable manifest/principal/activation/invocation/health seams to the separately admitted app, workflow, and control successors.
