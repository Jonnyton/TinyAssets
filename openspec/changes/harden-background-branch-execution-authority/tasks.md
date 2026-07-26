## 1. Inventory and Stable Interfaces

- [ ] 1.1 Inventory every schedule, subscription, soul/`PROGRAM.md` loop, Request admission, goal-pool/paid-market producer, `BranchTask`, graph-enqueue, live/frozen `invoke_branch`, resume/recovery, `_current_actor`, daemon, cloud-worker, and distributed-worker call site that can execute a branch after its authorizing request ends; add a CI closure assertion for the inventory.
- [ ] 1.2 Record the canonical identity, ACL, branch, daemon, run, request/admission, goal-subscription, paid-market contract, queue, B2, provider-work, and provider-attempt read interfaces consumed by target authority without duplicating their truth.
- [ ] 1.3 Define typed `BackgroundBranchBinding`, `BackgroundBranchAttempt`, source-kind, target-mode, lifecycle, hold-reason, and provenance contracts with strict validation and lossless round trips.
- [ ] 1.4 Define the `BackgroundBranchAuthorityStore` protocol, transaction/CAS primitives, lock order, and bounded query seams without exposing storage tables to callers.
- [ ] 1.5 Add a deterministic logical-attempt-key builder for schedule due instants, subscription events, soul cycles, claimed task generations, and graph child ordinals.
- [ ] 1.6 Obtain host approval for the `PLAN.md` reconciliation that assigns one live scheduling/task-claim mutation authority; block production persistence integration and activation until it lands while allowing model, inventory, dark-mode, and test work.

## 2. Authority Store and Recovery Core

- [ ] 2.1 Implement binding persistence with opaque IDs, canonical principal/target/source fields, digests, generations, revocation, limits, and explicit child-delegation policy.
- [ ] 2.2 Implement attempt persistence with unique logical keys, exact branch snapshot, source generation, executor audience, lineage, limits, and monotonic lifecycle transitions.
- [ ] 2.3 Implement server-owned binding create/rotate/pause/revoke/exhaust transitions that reject stale generations and caller-controlled identity or authority fields.
- [ ] 2.4 Implement just-in-time attempt issuance that revalidates principal, ACL, physical universe, branch, source, daemon/runtime eligibility, lineage, limits, and prior-attempt state before any downstream access.
- [ ] 2.5 Implement single-winner attempt claim/renew/release/reclaim with audience and claim-generation fencing; lease expiry alone must not prove predecessor death.
- [ ] 2.6 Implement typed `target_authority_held` queue transitions, equivalent source-owned target holds, and non-secret projections for missing, stale, revoked, exhausted, unauthorized, source-mismatched, and indeterminate authority.
- [ ] 2.7 Implement prepared-pair reconciliation for cross-store create/rotate/revoke operations using exact source/binding digests and idempotent recovery.
- [ ] 2.8 Add model/store tests for malformed records, replay, unique-key concurrency, stale CAS, generation fences, bounded reads, and crash recovery.

## 3. Authenticated Trigger, Request, and Producer Lifecycle

- [ ] 3.1 Change schedule/subscription handlers to derive the canonical request principal and exact universe/branch authorization; remove `owner_actor` from every authority decision and durable identity field.
- [ ] 3.2 Create schedules/subscriptions and their bindings in one transaction or one recoverable prepared pair, including atomic per-principal active-limit reservation.
- [ ] 3.3 Make list, pause, unpause, unschedule, and unsubscribe principal/admin gated with no unauthorized existence oracle and no admin ownership transfer.
- [ ] 3.4 Change due-schedule processing to create/follow one freshly revalidated attempt per schedule generation and due instant while preserving interval catch-up and cron non-backfill semantics.
- [ ] 3.5 Change event delivery to commit one subscription-generation/event attempt or explicit denial/hold with the deduplication record instead of marking delivery before authority resolution.
- [ ] 3.6 Persist separate authorizer, exact target snapshot, trigger, attempt, and executing daemon/runtime provenance on scheduled/event runs.
- [ ] 3.7 Add handler, restart, duplicate-tick, duplicate-event, rate-limit, ACL-revocation, source-rotation, no-oracle, and crash-boundary tests.
- [ ] 3.8 Merge the `demand-side-signals` timezone, DST, missed-tick-policy, and schedule-period-identity contract into scheduler implementation before adding authority; enforce the declared sync order so neither active delta can overwrite the other.
- [ ] 3.9 Extend authenticated protocol-v2 Request admission so its Request, admission, task, event, and exact target binding commit as one aggregate and the task carries only the binding reference/digest.
- [ ] 3.10 Replace goal subscriptions with authenticated principal/universe target delegations; put the anonymous fresh-install maintenance default in `reauthorization_required` until a founder authorizes it through the connector.
- [ ] 3.11 Bind accepted paid-market producer work to its canonical requester, contract, subscriber universe, exact target policy, and contract generation without treating a market row as execution authority.
- [ ] 3.12 Change goal-pool and paid-market producer emission to derive one exact prepared child/task binding per source-item/subscription-or-contract generation before queue pickability; reject `posted_by`, pool YAML, and producer identity as authority.
- [ ] 3.13 Add Request-transaction, goal-subscription, default-maintenance, market-contract, duplicate producer-pump, cross-universe, source-revision, and connector reauthorization tests.

## 4. Soul-Loop Authority Lifecycle

- [ ] 4.1 Add normalized loop-target comparison and pinned `soul.md` version/content-digest inputs to universe creation and governed soul-edit planning.
- [ ] 4.2 Thread the canonical authorizing principal/authority object into `apply_soul_edit` and implement the binding prepare/edit-snapshot/commit-old-revoke protocol under the existing soul compare-and-swap and per-universe lock.
- [ ] 4.3 Permit narrow carry-forward only when the normalized target is unchanged; require fresh authenticated or explicit exact delegated authority for target changes.
- [ ] 4.4 Implement exact-digest soul-transition recovery: commit the candidate, abort against the old state, or quarantine every third state.
- [ ] 4.5 Change daemon and cloud-worker loop dispatch to require the current soul binding/attempt and remove `PROGRAM.md`, `UNIVERSE_SERVER_USER`, prior-generation, and daemon-ownership authority fallbacks.
- [ ] 4.6 Persist soul version, loop target, authorizer, daemon executor, cycle key, binding, and attempt provenance on each loop run.
- [ ] 4.7 Add creation, governed-edit, unchanged-target, changed-target, concurrent-edit, crash-point, stale-worker, restart, and legacy-loop hold tests.

## 5. Graph Child Derivation and Queue Append

- [ ] 5.1 Create a non-serializable root/parent child-delegation context from current request, resume attempt, or parent target authority and inject it into trusted graph execution context.
- [ ] 5.2 Implement atomic child-binding derivation for enqueue and direct live/frozen invocation that resolves the exact same-universe target and transfers—not copies—the parent's remaining depth/count/cost/retry envelope.
- [ ] 5.3 Enforce public same-universe delegation by default and exact authenticated allowlists for private targets; reject branch-authored actor, principal, universe, source, lineage, and binding overrides.
- [ ] 5.4 Extend epoch-1/epoch-2 `BranchTask` with only opaque binding reference/digest and required generations plus persisted non-pickable `target_authority_held`; implement fenced pending/running-to-held, authenticated held-to-pending, cancellation, validation, and transition-table semantics without compatibility parsing.
- [ ] 5.5 Coordinate child-binding creation, shared run/global/lineage cap admission, and queue append without nesting authority and queue locks; reconcile every prepared pair before pickability.
- [ ] 5.6 Preserve stable root origin, run-wide budget, physical universe, depth, global-active, lifetime-lineage, archive-integrity, and corrupt-history fail-closed behavior; exclude held rows from active capacity, count them once against lifetime lineage, and revive the same row without a second lineage charge.
- [ ] 5.7 Gate epoch-2 enqueue until all pre-authority rows are linked, boundedly drained, or held and the unclassified count is zero.
- [ ] 5.8 Add public/private target, dynamic escalation, concurrent transfer, shared-cap, append-crash, corrupt-history, and epoch-1/epoch-2 boundary tests.
- [ ] 5.9 Make live and frozen child-definition validation reject `child_actor`; inventory affected definitions and require republish without the insecure field instead of retaining a compatibility identity path.
- [ ] 5.10 Gate every live blocking/async initial invocation and retry on a stable parent/node/invocation/retry key, exact freshly pinned child attempt, and debited parent envelope before direct `execute_branch`.
- [ ] 5.11 Gate every frozen blocking/async initial invocation and retry on the exact stored branch version/content digest and the same attenuated attempt/ordinal rules before queue or execution.
- [ ] 5.12 Add live/frozen blocking, async, retry, timeout, mutable-live-target, frozen-version, invalid-`child_actor`, stale-parent, and authority-budget tests.

## 6. Claimed Task, Distributed, and Provider Composition

- [ ] 6.1 Change claimed-task dispatch to resolve the physical queue universe and atomically claim the exact target attempt for task, source, daemon/runtime/worker, and lease generations before branch resolution.
- [ ] 6.2 Carry a non-serializable claimed-attempt object only inside the live execution scope; reject serialized IDs/digests/envelopes as execution authority.
- [ ] 6.3 Replace environment-derived run actors, including `tinyassets/api/engine_helpers.py::_current_actor`, with canonical authorizer provenance and record daemon/runtime/worker separately as executors.
- [ ] 6.4 Require an independent B2 grant for distributed work without letting target authority mint B2 or B2 mint target authority.
- [ ] 6.5 Require a valid target attempt before background provider-work receipt issuance and preserve the separate provider-attempt gate at the provider call boundary.
- [ ] 6.6 Implement independent terminal settlement and generation-bound reconciliation across target, queue, B2, provider-work, and provider-attempt domains using the documented lock order.
- [ ] 6.7 Add missing/mismatched attempt, physical-universe mismatch, stale audience, lease race, B2 absence, provider-authority absence, worker crash, and cross-domain promotion tests.
- [ ] 6.8 Persist an exact durable run binding at initial authorized execution and make `resume_run` derive one single-winner target attempt from canonical request principal, run ACL/owner, checkpoint, stored branch version, cancellation, and resume generation.
- [ ] 6.9 Make `recover_in_flight_runs` fence stale execution and mark interruption without minting resume authority; provide resumed graph child delegation only from the claimed resume attempt.
- [ ] 6.10 Add concurrent resume, stored-actor spoof, ACL revocation, version/checkpoint mismatch, startup recovery, resume-plus-child-enqueue, and crash-boundary tests.

## 7. Legacy Migration and Rollout Controls

- [ ] 7.1 Build a read-only inventory/report command for legacy triggers, Request admissions, goal/market subscriptions/contracts and producer rows, soul/`PROGRAM.md` loops, live/archive tasks, graph enqueue/direct invocation, resume/recovery, `_current_actor`, and dispatch call sites with canonical-evidence classifications.
- [ ] 7.2 Add dark-mode would-allow/would-hold decisions and metrics without creating live authority or altering legacy execution.
- [ ] 7.3 Implement deterministic backfill only when canonical durable principal, ACL, exact target, source generation, and physical-universe evidence all prove the binding.
- [ ] 7.4 Preserve every ambiguous source/task in `reauthorization_required`; never backfill from `owner_actor`, environment, public visibility, queue possession, or daemon/worker identity.
- [ ] 7.5 Extend existing authenticated unpause/recreate/redeclare paths to rotate valid bindings without adding an Agent Village or web-app dependency.
- [ ] 7.6 Add activation counters and assertions for zero unclassified sources/tasks, zero unclosed prepared pairs, and zero legacy authority fallbacks.
- [ ] 7.7 Implement rollback that stops new issuance/claims, fences in-flight generations, retains history, and leaves work pending/held without restoring legacy authority.
- [ ] 7.8 Add migration idempotency, partial-evidence, stale-ACL, legacy-program, dark-row drain/hold, repeated rollback, and recovery tests.

## 8. Verification, Activation, and Foldback

- [ ] 8.1 Run focused authority, scheduler, soul, graph, queue, daemon, cloud-worker, distributed, provider, migration, and provenance test suites plus full `pytest` and `ruff`.
- [ ] 8.2 Run process/thread concurrency proof for duplicate schedule/event/soul/task/child attempts, parent-budget transfer, multi-host claim/reclaim, and shared queue caps.
- [ ] 8.3 Run failure injection at every binding/source, soul, event-delivery, child-append, attempt-claim, execution, and settlement prepare/commit boundary.
- [ ] 8.4 Produce the full-platform §14 concurrency/load evidence for sustained zero-host trigger recovery, multi-host contention, bounded backlog, and authority-store health.
- [ ] 8.5 Run strict targeted and repository-wide OpenSpec validation, independent diff review, security review, and exact call-site inventory closure.
- [ ] 8.6 Deploy dark mode, verify metrics and rollback, then activate one source class at a time only after its focused evidence passes.
- [ ] 8.7 Run public connector canaries and a rendered chatbot conversation that creates and observes unattended work with correct authorizer/executor provenance; save `output/user_sim_session.md` and trace/screenshot evidence.
- [ ] 8.8 Check fresh production traces for clean post-fix real-user use; if absent, add a dated `STATUS.md` watch item instead of claiming proven adoption.
- [ ] 8.9 After `demand-side-signals` and `operator-request-trigger-contract` have synced their owning deltas, sync this change's five merged capability deltas second, archive it, retire its `STATUS.md` row, and record the landing in git history only after every gate passes.
