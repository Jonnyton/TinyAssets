## 1. Inventory and runtime boundary

- [ ] 1.1 Re-run the provider-call and injected-callable inventory across the canonical runtime and packaged Claude-plugin mirror, including router-internal auth-health probes, async judge-ensemble fan-out, and direct `provider.complete(...)` calls; classify every production call site into exactly one authority route and make the inventory an executable CI check.
- [ ] 1.2 Select the existing transactional store behind `ProviderWorkAuthorityStore`, prove authority transactions close before assignment admission, enforce the global authority-store → assignment-admission → credential-lock order, and prove BranchTask JSON, public payloads, environment variables, and logs remain non-authority.
- [ ] 1.3 Define conservative server-owned operation, role, depth, lifetime, invocation, token, and cost ceilings for universe work and maintainer maintenance; reject caller-controlled widening.

## 2. Authority domain and durable store

- [ ] 2.1 Add failing domain tests for the closed binding, receipt, execution-claim, invocation-reservation, and handoff types, including unknown variants and invalid state transitions.
- [ ] 2.2 Implement `ProviderWorkBinding`, the two receipt variants, `ProviderWorkExecutionClaim`, `ProviderInvocationReservation`, and secret-free identifiers and errors with no provider behavior enabled.
- [ ] 2.3 Add failing transactional tests for concurrent receipt claims, post-worker-selection one-use process handoffs, unique invocation ordinals, first-terminal-wins transitions, cancellation races, worst-case budget reservation/settlement, and budget exhaustion.
- [ ] 2.4 Implement the authority store's atomic issue, claim, heartbeat, reserve, launch-start, complete, cancel, revoke, expire, and fence operations until the transactional tests pass.
- [ ] 2.5 Add crash/restart tests for live claims, dead claims with no reservation or only durable `cancelled_before_launch`, dead-owner `reserved`, expired receipts, unreadable evidence, and ambiguous launches; implement conservative reconciliation that preserves or fences uncertainty.

## 3. Binding and issuance roots

- [ ] 3.1 Add failing tests proving TinyAssets `Middleware.on_call_tool` creates an inert single-message binding draft from the exact current `request_ctx.get().request` after target authorization but before tool await/dispatch augmentation, and that missing this boundary creates no provider authority.
- [ ] 3.2 Implement transactional draft consumption for registered background-capable connector work and just-in-time receipt issuance with principal, actor, universe, branch, run, operation, physical-work, assignment-generation/digest, provider-binding, revocation, runtime, and budget revalidation.
- [ ] 3.3 Land or consume `harden-background-branch-execution-authority` before enabling schedule/subscription issuance; add tests that caller-controlled `owner_actor`, kwargs, schedule identity, and legacy synthetic actors cannot create a provider-work binding.
- [ ] 3.4 Add failing tests for schedule, subscription, run, resume, daemon-cycle, and child-work issuance, including stale/revoked bindings and no-broader child/retry/fallback constraints.
- [ ] 3.5 Implement the remaining server-owned binding roots and fresh per-attempt issuance without treating queue, lease, run, schedule, actor, or serialized receipt identity as authority.

## 4. Provider carrier and invocation accounting

- [ ] 4.1 Add failing sink tests proving every background route holds before provider, credential, outbound-proxy, auth-health, or quota access when its exact receipt, claim, operation, role, assignment, or reservation is absent or stale.
- [ ] 4.2 Thread the non-serializable receipt and active claim into the existing provider carrier; reserve and durably arm `launch_started` before acquiring assignment admission, then have the parent sequence revalidate the exact expected assignment tuple and armed reservation without adding a second provider-routing sink.
- [ ] 4.3 Add retry, fallback, cancellation, timeout, failure, dead-owner `reserved`, ambiguous-transport, and reverse-lock-order tests proving each armed attempt consumes its slot and every later attempt needs a fresh valid slot.
- [ ] 4.4 Add judge-ensemble tests proving N launches reserve N ordinals and worst-case budgets atomically before fan-out, with all-or-none hold when authority cannot fund the full ensemble.
- [ ] 4.5 Implement post-admission result settlement that refunds only proven unused token/cost budget and retains full reservation on absent or ambiguous usage, plus secret-free receipt, claim, reservation, hold, and fence observability.

## 5. Daemon and graph call-site closure

- [ ] 5.1 Convert branch-task workers, schedules, subscriptions, run/resume, selectors, cloud workers, and autonomous daemon cycles to claim exact background receipts independently of queue claims and leases.
- [ ] 5.2 Convert universe intelligence, compiled provider nodes and routers, async judge-ensemble fan-out and its direct provider calls, editorial, ingestion, entity extraction, community evaluation, retrieval, RAPTOR, and reflexion paths to propagate the exact receipt through direct, task, and thread bridges.
- [ ] 5.3 Implement atomic opaque process handoffs with one-use nonces and worker/runtime audiences; add replay, expiry, wrong-audience, worker-death, and cross-process load tests.
- [ ] 5.4 Update the packaged Claude-plugin mirror for every affected provider bridge and make canonical/mirror authority parity part of the call-site closure gate.
- [ ] 5.5 Run the inventory gate and prove that every production provider-capable caller and injected callable has exactly one authority classification with no unowned sink; keep attested host-request and accepted-market classes empty until their named successor owners land.

## 6. Isolated maintenance authority

- [ ] 6.1 Add failing tests for the exact `_AUTH_PROBE_PROMPT` digest, host/operator principal, invoking runtime/daemon, provider, executor/transport, opaque credential reference/digest, separate maintenance budget, ambient `CODEX_HOME`/PATH rejection, and rejection of user content, graph work, child work, or requester quota.
- [ ] 6.2 Under V2, make ordinary router auth-health consume cached state only and implement the universe-less maintenance path through `ProviderExecutor`'s closed maintenance entrypoint without ordinary universe work, `call_provider`, ambient credential resolution, or a second provider sink.
- [ ] 6.3 Prove `get_status` and other public reads never launch the probe and that unavailable maintenance authority records a held health state without borrowing requester or universe authority.

## 7. Rollout and complete-system proof

- [ ] 7.1 Keep V2 behavior observational while dark; add server-owned per-universe and default-empty exact operation-plus-runtime maintenance-canary configuration with isolated credential binding/budget that caller data cannot select or widen.
- [ ] 7.2 Run isolated universe-work and maintenance canaries and the Section 14 concurrent claim, reserve, launch, cancellation, restart, and cross-process load proof with no duplicate or authority-free launch.
- [ ] 7.3 Verify every Tier-1 connector, run, schedule, subscription, daemon, retrieval, ingestion, and maintenance loop either remains live under valid authority or produces an explicit recoverable hold; do not require Agent Village or any web application.
- [ ] 7.4 Obtain independent review of the exact implementation head, run focused and full quality gates, then perform rendered chatbot connector acceptance and post-fix clean-use monitoring for affected public behavior.
- [ ] 7.5 Sync the three delta specs into canonical specs, archive this change, update the living coordination files, and retire the implementation lane only after the reviewed implementation lands.
