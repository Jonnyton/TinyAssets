## Context

The canonical background binding and attempt records already share one SQLite database and transaction boundary. PR #2162 introduced typed queue/source owner records and lifecycle validation, but left persistence as `BackgroundBranchAuthorityOwnerStore.compare_and_swap`; its tests provide only an in-memory implementation. The service can consequently return a pending owner that references a recovered or replacement attempt never committed to the canonical store.

## Goals / Non-Goals

Goals:

- persist owner records with integrity-checked canonical JSON;
- validate current owner and every applicable binding/attempt fence or exact expected absence in one SQLite transaction;
- commit recovery attempt CAS and owner CAS atomically;
- commit reauthorization attempt insertion/replay and owner CAS atomically;
- make every conflict, malformed row, and injected failure roll back the whole transition.

Non-goals:

- no BranchTask table/status integration;
- no queue/source adapter wiring, dispatch, provider execution, or activation;
- no new reauthorization semantics or caller-facing surface;
- no second authority database or prepared-pair protocol while all records share SQLite.

## Decisions

### 1. One database is one transaction

The concrete owner store extends the existing SQLite background authority store and adds an owner table to the same schema. A transition uses one `BEGIN IMMEDIATE` transaction. A prepared-pair protocol would add failure states without value while binding, attempt, and owner records share one database.

### 2. Owner records serialize canonically

The typed owner record gains strict `to_dict` / `from_dict` support. The owner table stores canonical JSON plus a record digest and indexed identity/generation/state fields. Reads reject malformed JSON, non-canonical encodings, digest mismatches, and index mismatches before any authorization decision.

### 3. The store derives the atomic write from fenced records

The service API remains unchanged. The concrete store inspects the current and replacement owner fences:

- hold-only transitions validate referenced canonical rows and change only the owner, except that a closed missing-authority reason proves the applicable row is absent and preserves any non-authorizing fence only for audit;
- recovery is available only when both owner records fence the same present attempt; it requires the same binding and attempt identity, applies the existing monotonic attempt CAS, then updates the owner;
- queue-owner reauthorization requires the current fenced rows and an already-committed newer binding; before updating the owner it re-applies transaction-local issuance admission, including deterministic attempt identity, first-generation reserved state, exact logical-key ownership, canonical target/source facts, and the binding's canonical attempt-count limit, then inserts or exactly replays the attempt;
- source-owner reauthorization may exit without a replacement attempt only after validating the newer canonical binding and any previous attempt fence; binding rotation leaves that old attempt stale/non-runnable and the owner never revives or mutates it.

Any missing/conflicting row or write outcome aborts the transaction. Resolver output is evidence to validate, never an independently authoritative record.

### 4. Dark means non-pickable

No production queue or runtime imports the owner store in this change. Task 5.3 remains the sole owner of BranchTask persistence and pickability. This correction only makes the dark prerequisite truthful and safe to wire later.

## Risks / Trade-offs

- Import direction: the SQLite adapter needs the owner record types currently defined in the service module. The service does not import the storage adapter, so this remains acyclic; a later model cleanup may move the types without changing behavior.
- Transaction duration: canonical row decoding adds bounded local work under `BEGIN IMMEDIATE`; the dark store favors integrity over throughput.
- Existing databases: `CREATE TABLE IF NOT EXISTS` adds the owner table lazily without migrating live queue state because no runtime owner records exist yet.

## Migration Plan

1. Add the table and typed serialization with no runtime consumers.
2. Prove atomic recovery/reauthorization and rollback under injected failures.
3. Keep task 2.6 partial until this correction lands; task 5.3 remains open afterward.

## Open Questions

None. If a future owner store is separated from the authority database, it must implement the existing digest-bound prepared-pair requirement rather than reuse this same-database transaction.
