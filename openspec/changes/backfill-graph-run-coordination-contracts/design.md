## Context

The runs SQLite database already persists two coordination stores that the
canonical OpenSpec inventory omitted:

- `run_receipts` records normalized acquisition, claim-lineage, and revision
  evidence for an existing run; and
- `teammate_messages` records installation/data-root-local run-to-node
  messages and one global acknowledgement bit.

Both are reachable through legacy `extensions` actions and have focused tests.
The active `distributed-execution` change instead owns authenticated remote
owner-daemon execution and signed authority. External-effect receipts own
idempotent outside-system effects. Neither is the semantic owner of these
local run-database records.

## Goals / Non-Goals

**Goals:**

- Give both shipped stores one canonical as-built owner.
- Specify the validation, normalization, ordering, filtering, and
  authorization behavior that current source and tests prove.
- Preserve security and consistency limitations visibly so future hardening
  changes cannot mistake them for guarantees.
- Sync the reviewed requirements into `graph-execution-substrate` without
  changing existing requirement text.

**Non-Goals:**

- No runtime, database, MCP tool, permission, or deployment change.
- No signed authority, truth scoring, external-effect idempotency, remote
  transport, or claim of cross-universe isolation.
- No claim that `send_message_spec` or `receive_messages_spec` executes from a
  compiled graph; those tests remain strict expected failures.
- No stronger sender, recipient, reply-target, or acknowledgement identity
  than the current functions enforce.

## Decisions

### 1. Extend `graph-execution-substrate`

The records live in the run database and coordinate runs/nodes. The graph
substrate therefore owns their local as-built behavior. This avoids creating a
capability for two small stores and avoids colliding with the signed remote
authority owned by `distributed-execution`.

Alternative: extend `external-effect-receipts`. Rejected because run evidence
does not reserve or finalize an external effect and deliberately assigns no
truth rank.

Alternative: extend `development-coordination-runtime`. Rejected because that
capability owns repository/provider coordination, not universe run/node state.

### 2. Add requirements rather than modify broad run lifecycle text

The canonical run lifecycle requirements are true but do not imply either
store. New requirements keep the ownership explicit and let sync preserve all
existing graph requirements byte-for-byte.

### 3. Specify public routing only where it changes domain behavior

The delta records the receipt actions' per-run read/write filtering and the
mailbox action results because those are observable domain behavior. Generic
hidden-tool registration and tool-level authentication remain owned by
`live-mcp-connector-surface` and `identity-auth-and-access-control`.

### 4. Treat limitations as normative as-built boundaries

The receipt foreign key is declarative because SQLite foreign-key enforcement
is not enabled. Receipt IDs are not caller-idempotency keys. Unknown payload
keys round-trip without validation or truth status.

Mailbox send validates the source run but not destination node or reply
existence. All message actions use the installation's shared
`TINYASSETS_DATA_DIR` runs database and perform no `_current_actor`,
`universe_access_allows`, or per-run read/write check. Reads with no node
enumerate that data-root mailbox. Ack authorization compares a caller-supplied
node string, broadcast ack is global, and the returned acknowledgement time is
not persisted. These facts must remain visible until a separately reviewed
hardening change replaces them.

## Risks / Trade-offs

- **[Risk] Backfill language accidentally upgrades local evidence into
  authority.** → State that receipts preserve caller data without truth rank,
  signature, or external-effect semantics.
- **[Risk] Mailbox wording implies graph execution wiring.** → Name the strict
  expected-failure tests and state the compiler primitives are unwired.
- **[Risk] A future distributed transport duplicates local semantics.** → Keep
  `distributed-execution` as a read-only dependency and require it to compose
  or explicitly replace this local owner.
- **[Risk] Canonical sync overwrites unrelated graph requirements.** → Use only
  ADDED requirements, compare the pre-sync file as an exact prefix, and run
  full-tree strict validation.

## Migration Plan

1. Strictly validate and independently review the delta against current source
   and focused tests.
2. Run the receipt, mailbox, and receipt-visibility evidence suites.
3. Sync only the added requirements into
   `openspec/specs/graph-execution-substrate/spec.md`.
4. Prove existing canonical content is preserved, validate the full tree,
   archive the completed change, and publish through a reviewable PR.

Rollback is documentation-only: revert the sync/archive commit. Runtime and
stored data are unchanged.

## Open Questions

None for this as-built backfill. Authentication, graph wiring, per-recipient
broadcast acknowledgements, foreign-key enforcement, and caller idempotency are
future behavior changes requiring their own OpenSpec proposals.
