# Universe Lifecycle and Soul

## MODIFIED Requirements

### Requirement: Clean-slate reset is the only lifecycle-end

There SHALL be no MCP, API, or user-facing per-universe delete operation; the only production
teardown is a confirm-gated clean-slate reset (`tinyassets.reset.reset`) that removes every universe
directory, the `.active_universe` marker, and the universe-scoped and hosted-daemon tables at once,
returning the platform to "no universe, no daemon." Without `confirm` the reset SHALL only plan
(mutating nothing), and it SHALL be idempotent when run repeatedly. The reset SHALL preserve the
branch commons (`branch_definitions`, `branch_versions`, `goals`, `gate_claims`,
`canonical_bindings`), the entire `.runs.db` run history, and the `wiki/` commons.

A separate host-operator test-maintenance command MAY return one allowlisted external test principal
to first-contact state, but SHALL NOT be registered as an MCP tool or API route and SHALL NOT accept a
caller-selected or non-allowlisted principal. It SHALL plan before apply, bind apply to the reviewed
plan, acquire a durable process-shared fenced affected-scope maintenance lease, and derive the
candidate home only from that principal's exact `founder_home` binding. An admin ACL SHALL NOT confer
deletion ownership. The
command SHALL use an explicit reviewed deletion graph across every database and filesystem store;
unclassified, path-escaping, shared, foreign-bound, foreign-granted, or otherwise ambiguous state
SHALL block apply. It SHALL preserve all other principals' content and bindings, the commons, wiki,
run history, immutable audit/market/billing records, global daemon identities, and all maintainer or
provider credentials. Credential-bearing homes, pending external-write receipts/consents, or active
run/daemon/market obligations SHALL block until their normal lifecycle closes. The plan SHALL bind the
roster and inventory revisions, principal fingerprint, exact binding/grant row versions, and resolved
paths. Interrupted filesystem/database work SHALL recover before traffic resumes from a durable
content-free journal plus a commit-witness row written atomically with the database deletion, without a
long-lived full-content backup.

As-built limitation until this change is implemented: reset is all-or-nothing across every universe;
a single test principal cannot yet be returned to first-contact state.

#### Scenario: a dry run reports but deletes nothing
- **WHEN** `reset` runs with `confirm=False`
- **THEN** it returns a plan listing the universe directories, marker presence, and row counts to clear
- **AND** no directory, marker, or table row is actually removed

#### Scenario: a confirmed reset clears universes and daemons but preserves the commons
- **WHEN** `reset` runs with `confirm=True`
- **THEN** every universe directory, the `.active_universe` marker, and the universe-scoped and daemon tables are cleared
- **AND** `branch_definitions`, `goals`, `.runs.db`, and the `wiki/` directory survive

#### Scenario: reset is idempotent
- **WHEN** `reset(confirm=True)` runs a second time after a first successful reset
- **THEN** it reports no universe directories, no rows to clear, and no marker, without error

#### Scenario: Scoped test reset has no public route

- **WHEN** an MCP or API client enumerates or invokes the public surface
- **THEN** no scoped-reset, account-delete, or per-universe-delete operation is available
- **AND** only an operator shell can plan or apply test-principal maintenance.

#### Scenario: Scoped plan is reviewed and revalidated before apply

- **WHEN** an operator plans reset for an allowlisted test principal
- **THEN** the command reports the exact resettable and preserved state plus a stable plan ID without
  mutating anything
- **AND** apply acquires the affected-scope lease and refuses if the plan changed.

#### Scenario: Scoped apply leaves every other principal untouched

- **WHEN** an operator applies a still-valid plan for one unshared, unambiguous test home
- **THEN** that home, its explicitly resettable state, the founder-home binding, and that subject's ACL
  grants are removed
- **AND** every other principal's home, universe content, binding, grant, run history, and shared commons
  remain byte-for-byte and row-for-row unchanged.

#### Scenario: Unknown and ambiguous principals fail safely

- **WHEN** the alias is unknown or non-allowlisted, or the candidate home is shared, foreign-bound,
  foreign-granted, credential-bearing, path-escaping, or contains unclassified or active obligated
  state
- **THEN** plan or apply fails closed without mutation
- **AND** an allowlisted test principal with no state returns an idempotent no-op plan.

#### Scenario: Interrupted scoped apply converges safely

- **WHEN** the process stops before or after the database commit boundary
- **THEN** the next recovery pass uses the journal to restore the pre-commit state or complete
  post-commit cleanup deterministically
- **AND** it never leaves database rows claiming a deleted live directory or exposes a reusable content
  backup.
