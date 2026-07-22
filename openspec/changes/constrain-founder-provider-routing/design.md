## Context

The router already distinguishes preference from authority: a preferred writer
is tried first while fallback remains available, whereas `allowed_providers`
filters every relevant route and hard-fails when no permitted provider remains.
The `set_engine` paths currently persist an engine source and optional
preference but no eligibility ceiling. A deposited Anthropic key can try Claude
first and then continue through Codex or local hardware; persistence-only
self-hosted, market, and host-daemon choices can run the ordinary chain before
their selected destination exists.

The previously landed host-credential isolation is also incomplete: host API
keys survive explicit-universe calls when global API-key opt-in is enabled, and
non-`ValueError` vault failures return an environment with inherited host
subscription auth. Provider eligibility and credential isolation are
independent necessary constraints; neither alone establishes request execution
authority. Host reachability must never widen either constraint.

## Goals / Non-Goals

**Goals:**

- Make every successful engine assignment replace the provider ceiling.
- Make a complete BYO API-key assignment name exactly one eligible provider;
  incomplete source types name none.
- Reject contradictory service/provider input before any vault or config write.
- Strip all ambient provider auth for explicit-universe calls and fail on vault
  errors.
- Quarantine cross-file assignment updates before any secret mutation.
- Gate rollout on explicit migration of historical assignments.
- Reuse the router's existing allowlist boundary and fail-closed diagnostics.
- Prove the assigned provider cannot fall through to another registered route.

**Non-Goals:**

- No change to normal `preferred_writer` fallback semantics outside a strict
  `set_engine` assignment.
- No new provider, key type, auth flow, router global, or receipt mechanism.
- No implementation of self-hosted, market-rented, or host-daemon authority;
  their persisted ceiling is empty until those resolvers exist.
- No duplicate of the `universe-creation` request authority resolver or R2-1b
  provider receipts.
- No claim that `run_graph` or other provider call sites already thread an
  explicit universe context; that remains in the #1582 authority work.

## Decisions

### Treat allowed_providers as a replace-only eligibility ceiling

The executable BYO destination mapping is exact: `anthropic` uses `claude-code` and
`openai` uses `codex`. The broader vault alias table is not execution proof
because only those two CLI providers receive per-universe key overlays.
`set_engine` SHALL infer the executable provider when omitted and reject a
different explicit writer or unroutable alias before writing.

Every successful assignment replaces, never unions, the prior ceiling:

| Source | Persisted provider-destination ceiling now |
|---|---|
| BYO `anthropic` | `["claude-code"]` |
| BYO `openai` | `["codex"]` |
| `self_hosted_endpoint` | `[]` until endpoint/provider binding is executable |
| `market_rented` | `[]` until an accepted compute/model grant is bound |
| `host_daemon` | `[]` until a daemon and its authority are bound |

Silently overriding contradictory input was rejected because the response
would claim to honor a choice it discarded. Accepting the mismatch was rejected
because the stored key cannot authenticate the named provider and could make a
host/local fallback appear to work.

### Compose the persistent ceiling with request authority

The router already applies the explicit universe context, preference, and
allowlist across the role chain, policy route, and judge ensemble. This change
uses that boundary instead of teaching the router that every preference is an
allowlist. Globally reinterpreting `preferred_writer` would break existing
configs whose canonical contract deliberately retains fallback.

The persistent ceiling does not grant execution. The target architecture's
eventual effective set is the intersection of the `set_engine` ceiling, the
request authority bundle's `eligible_providers`, and runtime registration/
policy/health filters. #1582 already owns the normative authority-bundle delta,
implementation, and tests; this change does not claim that intersection is
built. A key deposit, selected provider, or non-empty allowlist never replaces
that future request decision.

For the boundary this lane does own, every normal, policy, and judge provider
attempt for an explicit universe takes the assignment lock long enough to
re-read the non-secret on-disk config immediately before the attempt. Only a
fresh `engine_assignment_state="ready"`, a valid `list[str]` ceiling, and a
candidate inside that ceiling may continue. This makes lock acquisition the
attempt's provider-eligibility linearization point: a non-CLI call admitted
before a later assignment may finish, while a call reaching the check after
`pending` is written waits and observes the committed or restored state. CLI
credential materialization performs its own second locked revalidation. No
secret-vault query participates in the routing decision itself.

### Sanitize explicit-universe environments before vault overlay

Host-local calls retain the existing opt-in behavior. When `universe_dir` or an
explicit universe binding is present, environment construction starts by
removing every API-key and subscription-auth variable regardless of host
opt-in, then overlays only the selected universe's vault values. Any vault
load/import/materialization exception propagates before subprocess launch.

CLI auth materialization reacquires the same assignment lock and revalidates
fresh `ready` state plus candidate membership before reading the vault and
returning the immutable child environment. Thus a router attempt admitted just
before reassignment cannot resume during `pending` and consume a partial/new
credential. The lock is released after the environment snapshot is complete;
it is not held through the CLI/network execution.

The prior compare-before/after heuristic was rejected: one vault-supplied field
could leave unrelated host fields intact, and an exception skipped cleanup.

### Quarantine before mutation and roll back without exposing partial state

BYO input is fully validated first. Every `set_engine` source then takes the
same per-universe cross-process `.engine-assignment.lock`; the lock spans
snapshot through complete commit or rollback, so a stale transaction cannot
mix with or undo a newer assignment. The prior config and vault bytes/existence
are snapshotted. Before secret mutation, an atomic config write records
`engine_assignment_state="pending"` with `allowed_providers=[]`; every router
entry point's fresh locked pre-invocation check holds on that state. The vault write then replaces
the prior engine `llm_api_key` set while preserving unrelated social, VCS, and
subscription records. A final atomic config write commits the matching
preference, singleton ceiling, and `engine_assignment_state="ready"`.

On failure, restore the prior vault first and then the prior config. If exact
rollback succeeds, the previous assignment is restored. If vault restoration
or config restoration fails, the pending empty-ceiling config remains as a
durable quarantine and the action reports both the assignment and rollback
failure. `pending` changes to `ready` only after a complete commit, or returns
to the exact prior state after exact rollback. This
prevents a later normal, policy, or judge route from consuming partial state.

### Test the write and the route without any provider resource

The first red test asserts the current action leaves
`allowed_providers=None`. After the minimal write fix, an integration test uses
in-memory fake providers: the assigned provider raises and every non-allowed
provider must remain uncalled while the router raises
`AllProvidersExhaustedError`. No real key, network, personal quota, local model,
or platform compute participates.

## Risks / Trade-offs

- **Existing assignments remain unconstrained on disk** -> Block rollout;
  inventory every historical `set_engine` assignment and explicitly migrate a
  confirmed BYO mapping to its reviewed singleton or any ambiguous/incomplete
  assignment to `[]`. Absence of production inventory access blocks rollout.
- **Service/provider mapping can drift** -> Keep focused tests for both
  supported pairs and fail unsupported/mismatched input before mutation.
- **The singleton allowlist also constrains judge/extract routes** -> Accept
  fail-closed/degraded behavior rather than spending an unselected provider;
  the future request-authority design may admit additional explicit grants.
- **Rollback itself can encounter I/O failure** -> Fail loudly with both the
  assignment and rollback error and do not invoke a provider; independent
  review must verify no exception path returns inherited auth.

## Migration Plan

1. Add and witness the failing assignment/config assertion.
2. Validate provider/service agreement, persist source-specific ceilings, and
   make BYO mutation quarantine-first and rollback-safe while preserving
   unrelated vault records.
3. Sanitize explicit-universe auth and keep router preference/allowlist
   behavior unchanged.
4. Add fake-provider, ambient-auth, vault-error, and partial-state proofs.
5. Version-fence or quiesce every legacy `set_engine` writer, then run the
   idempotent inventory/migration under that fence: explicitly migrate confirmed
   BYO mappings, quarantine ambiguous/incomplete records, and assert zero
   unclassified/unmigrated assignments before rollout.
6. Sync both modified capabilities and archive the change when implementation
   and independent security review land.

Rollback is a normal code revert. It restores fallback for future assignments
and is therefore security-regressive; already-written singleton allowlists stay
fail-closed unless explicitly changed by the founder/operator.

## Open Questions

- Is production inventory access available to complete the required historical
  migration? Absence of access blocks rollout; it is not evidence of absence.
