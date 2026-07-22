## 1. Lock the fail-open behavior test-first

- [x] 1.1 Run the focused assignment/allowlist/credential/context baseline and record its current pass count; no test may use a real provider, network, key, quota, or compute. (`30 passed`, 2026-07-22, local fake-only pytest suite.)
- [x] 1.2 Add failing table-driven tests for Anthropic/OpenAI singleton ceilings, replace-not-union reassignment, mismatched/unroutable services with zero mutation, and empty ceilings for persistence-only engine sources.
- [x] 1.3 Add a failing real-`set_engine` to fake-router proof where the assigned provider fails and every provider outside the persisted ceiling remains uncalled.
- [x] 1.4 Add failing explicit-universe environment tests for host API-key opt-in, unrelated ambient subscription auth, injected vault/import/materialization errors, both CLIs' default-home fallback, and failed vault-replace temp cleanup; add a writer-held-lock interleaving after router admission and prove auth materialization fails closed immediately with no partial/new auth or subprocess, while a later retry sees only complete state.
- [x] 1.5 Add failing success/failure transaction tests: successful key replacement preserves unrelated social/VCS/subscription records; failures exactly restore a prior vault or remove a newly created vault; injected restore failure reports both errors and retains `engine_assignment_state="pending"` with `allowed_providers=[]`.
- [x] 1.6 Add failing shared pre-invocation tests for normal/policy/judge routes: preload an old context, hold reassignment after pending/vault mutation, then prove the contended nonblocking try-lock fails every attempt immediately without provider/quota/auth-health access; also reject missing/invalid state plus `None`, scalar, and mixed-entry ceilings.
- [x] 1.7 Add deterministic same-universe concurrency tests: two assignment writers serialize with one complete winner; cross-process writer exclusion releases correctly; concurrent shared validation readers coexist while an assignment writer excludes them.

## 2. Implement the minimum fail-closed boundary

- [x] 2.1 Add one canonical credential-service to executable-provider resolver for the two wired per-universe BYO routes; do not treat the broader env-var alias table as execution support.
- [x] 2.2 Validate BYO service/provider input before mutation and make successful BYO assignment initialize `preferred_writer` plus a singleton `allowed_providers` ceiling while replacing only prior engine API-key records and preserving unrelated vault records.
- [x] 2.3 Make `self_hosted_endpoint`, `market_rented`, and `host_daemon` replace the ceiling with `[]` until their source-specific authority becomes executable and bound.
- [x] 2.4 Serialize every `set_engine` source with the same per-universe cross-process exclusive `.engine-assignment.lock` held from snapshot through commit/rollback, while validation/auth readers use nonblocking shared locks; snapshot the prior config/vault, atomically store `engine_assignment_state="pending"` with `allowed_providers=[]` before vault mutation, restore vault then config on failure, and store `ready` only after complete commit; restoration failure must leave the pending empty-ceiling quarantine and surface both errors.
- [x] 2.5 For explicit universes, remove all ambient API-key and subscription auth regardless of host opt-in; pin the selected CLI auth home to a validated universe-owned directory and require the matching key for ready BYO assignments; take a nonblocking assignment shared try-lock during auth materialization, read the vault and freeze the child env under that lock, then release before execution; contention and helper failures fail closed before subprocess launch while host-local behavior remains unchanged.
- [x] 2.8 Make vault replacement use a unique private temp file, flush/`fsync`, atomic replace, and unconditional temp cleanup so failed writes leave prior vault bytes and no new secret material.
- [x] 2.6 Add one shared nonblocking pre-invocation guard used by normal calls, policy routing, and judge ensembles: for an explicit universe, try-lock assignment, load fresh non-secret config, and require `engine_assignment_state="ready"`, a valid `list[str]` ceiling, and the candidate inside it before provider/quota/auth-health access; contention fails closed immediately and the guard never inspects the vault.
- [x] 2.7 Add the exact `UniverseConfig.engine_assignment_state` contract (`pending`/`ready`) and clarify `allowed_providers`: `None` is legacy/unassigned, `[]` is assigned-but-held/quarantined, and non-empty is the provider-destination ceiling.

## 3. Prove isolation and scope boundaries

- [x] 3.1 Extend explicit-context concurrency coverage with two distinct BYO keys/ceilings, a synchronization barrier proving overlap, and globals pinned to a third wrong universe; selected-provider failure must never cross a key or ceiling.
- [x] 3.2 Retain existing pin, policy, judge-ensemble, host-local, and provider-preference tests; mutation of singleton to union, `[]` to `None`, or ambient stripping must make focused tests red.
- [x] 3.3 Keep `run_graph` and provider call sites that do not thread `UniverseContext` explicitly tracked under #1582; do not claim this lane proves those paths.

## 4. Mirror, verify, and fold back

- [x] 4.1 Regenerate the bundled `tinyassets/` package mirror with `packaging/claude-plugin/build_plugin.py` and prove canonical/mirror parity.
- [x] 4.2 Run the focused assignment, engine-source, credential-vault, fail-closed, allowlist, and per-universe context suites plus `ruff check` on touched Python and `git diff --check`.
- [x] 4.3 Run strict validation for this change and all OpenSpec content, then obtain independent security and diff APPROVE verdicts.
- [x] 4.4a Build and independently review `scripts/migrate_engine_assignments.py`, its crash-resumable secret-free transaction journal, focused adversarial tests, and the durable deploy/recovery fence. Strict raw config/vault/ledger inventory emits a reviewed decision manifest; apply reclassifies under all universe locks, preserves unrelated bytes/keys and metadata, survives hard interruption, and requires zero unclassified/unmigrated assignments.
- [ ] 4.4b Execute the reviewed manifest against the live named `/data` volume with the new immutable image: drain legacy workflows, quiesce/mask every writer/recovery timer, prove zero mount users, migrate and verify twice, run daemon-only loopback canary before exposure, publish the receipt, and release the fence. Production access, missing evidence, or fence failure blocks merge/rollout; never auto-rollback to a pre-fence writer.
- [ ] 4.5 After implementation/review land, sync deltas into `provider-routing` and `credential-vault`, archive the change, and unblock R2-1b without claiming provider receipts or uncovered run paths.
