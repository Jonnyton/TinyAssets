## 1. Lock the fail-open behavior test-first

- [x] 1.1 Run the focused assignment/allowlist/credential/context baseline and record its current pass count; no test may use a real provider, network, key, quota, or compute. (`30 passed`, 2026-07-22, local fake-only pytest suite.)
- [ ] 1.2 Add failing table-driven tests for Anthropic/OpenAI singleton ceilings, replace-not-union reassignment, mismatched/unroutable services with zero mutation, and empty ceilings for persistence-only engine sources.
- [ ] 1.3 Add a failing real-`set_engine` to fake-router proof where the assigned provider fails and every provider outside the persisted ceiling remains uncalled.
- [ ] 1.4 Add failing explicit-universe environment tests for host API-key opt-in, unrelated ambient subscription auth, and injected vault/import/materialization errors; add a deterministic pause after router admission but before auth materialization, write pending and mutate the vault, then prove the second locked revalidation returns no partial/new auth and launches no subprocess.
- [ ] 1.5 Add failing success/failure transaction tests: successful key replacement preserves unrelated social/VCS/subscription records; failures exactly restore a prior vault or remove a newly created vault; injected restore failure reports both errors and retains `engine_assignment_state="pending"` with `allowed_providers=[]`.
- [ ] 1.6 Add failing shared pre-invocation tests for normal/policy/judge routes: preload an old context, pause reassignment after pending and after vault mutation, then prove fresh locked state blocks every attempt; also reject missing/invalid state plus `None`, scalar, and mixed-entry ceilings without provider/quota/auth-health access.
- [ ] 1.7 Add a deterministic same-universe concurrent-assignment test with an overlap probe: one transaction succeeds and one fails, final vault/provider/ceiling/state belong to one complete winner, and stale rollback cannot overwrite it.

## 2. Implement the minimum fail-closed boundary

- [ ] 2.1 Add one canonical credential-service to executable-provider resolver for the two wired per-universe BYO routes; do not treat the broader env-var alias table as execution support.
- [ ] 2.2 Validate BYO service/provider input before mutation and make successful BYO assignment initialize `preferred_writer` plus a singleton `allowed_providers` ceiling while replacing only prior engine API-key records and preserving unrelated vault records.
- [ ] 2.3 Make `self_hosted_endpoint`, `market_rented`, and `host_daemon` replace the ceiling with `[]` until their source-specific authority becomes executable and bound.
- [ ] 2.4 Serialize every `set_engine` source with the same per-universe cross-process `.engine-assignment.lock` held from snapshot through commit/rollback; snapshot the prior config/vault, atomically store `engine_assignment_state="pending"` with `allowed_providers=[]` before vault mutation, restore vault then config on failure, and store `ready` only after complete commit; restoration failure must leave the pending empty-ceiling quarantine and surface both errors.
- [ ] 2.5 For explicit universes, remove all ambient API-key and subscription auth regardless of host opt-in; reacquire the assignment lock during CLI auth materialization, require fresh ready state plus provider membership, read the vault and freeze the child env under that lock, then release before execution; propagate every helper failure before subprocess launch while preserving host-local behavior.
- [ ] 2.6 Add one shared pre-invocation guard used by normal calls, policy routing, and judge ensembles: for an explicit universe, acquire the assignment lock, load fresh non-secret config, and require `engine_assignment_state="ready"`, a valid `list[str]` ceiling, and the candidate inside it before provider/quota/auth-health access; never inspect the vault.
- [ ] 2.7 Add the exact `UniverseConfig.engine_assignment_state` contract (`pending`/`ready`) and clarify `allowed_providers`: `None` is legacy/unassigned, `[]` is assigned-but-held/quarantined, and non-empty is the provider-destination ceiling.

## 3. Prove isolation and scope boundaries

- [ ] 3.1 Extend explicit-context concurrency coverage with two distinct BYO keys/ceilings, a synchronization barrier proving overlap, and globals pinned to a third wrong universe; selected-provider failure must never cross a key or ceiling.
- [ ] 3.2 Retain existing pin, policy, judge-ensemble, host-local, and provider-preference tests; mutation of singleton to union, `[]` to `None`, or ambient stripping must make focused tests red.
- [ ] 3.3 Keep `run_graph` and provider call sites that do not thread `UniverseContext` explicitly tracked under #1582; do not claim this lane proves those paths.

## 4. Mirror, verify, and fold back

- [ ] 4.1 Regenerate the bundled `tinyassets/` package mirror with `packaging/claude-plugin/build_plugin.py` and prove canonical/mirror parity.
- [ ] 4.2 Run the focused assignment, engine-source, credential-vault, fail-closed, allowlist, and per-universe context suites plus `ruff check` on touched Python and `git diff --check`.
- [ ] 4.3 Run strict validation for this change and all OpenSpec content, then obtain independent security and diff APPROVE verdicts.
- [ ] 4.4 Before rollout, version-fence or quiesce legacy `set_engine` writers, then run an idempotent inventory/migration under that fence: confirmed BYO mappings become reviewed singleton/`ready` assignments, ambiguous/incomplete assignments become empty-ceiling/`ready` holds, and zero unclassified/unmigrated assignments remain. Production inventory or writer-fence unavailability blocks rollout.
- [ ] 4.5 After implementation/review land, sync deltas into `provider-routing` and `credential-vault`, archive the change, and unblock R2-1b without claiming provider receipts or uncovered run paths.
