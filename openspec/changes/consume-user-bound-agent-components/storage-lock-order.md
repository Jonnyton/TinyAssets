# Bounded storage lock order (2026-09-19)

Before implementation, inspected every intended helper: account_deletion
delete_account:912-922 acquires provider-assignment exclusive, writes the author
DB tombstone, releases admission, then stages home; write_tombstone:582-606
commits in author DB. ProviderAssignmentAdmission._file_lock:961 mkdirs, so it
is deliberately NOT called by delayed canonical projection.

Canonical bounded path: existing shared reset maintenance barrier -> read-only
recovery-clean check -> open existing author DB in rw mode -> BEGIN IMMEDIATE ->
check_current_home + admin + existing plain home -> one runs transaction at a
time -> close runs writer -> conversation pair transaction -> close it -> runs
projection flag transaction -> release author writer. No network/provider/work
execution and no bulk filesystem streaming occurs in this section. Source/home
metadata is checked before runs writer, not by opening another author connection
under it. `_insert_run_in_transaction:1468` is transaction-local SQL only;
`named_principal` is pure. Schema migrations execute before this path.

Projection uses only conversation_store._connect (local SQLite schema/migration),
fixed terminal normalization helpers and local SQL; none acquires provider
admission. It never invokes record_exchange's best-effort retry layer. The author
writer excludes tombstone commit; deletion holding provider exclusive cannot
deadlock because projection never asks for that lock. Conversely a tombstone
committed first refuses projection before any home path is opened or created.
All SQLite waits are bounded (the new path uses five-second connection timeout).

The two-process regression pauses before pair write while the author writer is
held, starts real account deletion in another process, proves deletion waits,
then releases and requires both to finish. Additional delayed-after-delete proof
requires no recreated home. No consumer launch guard or general lock manager is
introduced. Integration must retain this order; audit any newly invoked helper.

Scoped reset integration takes the SAME exclusive maintenance barrier before its
author operations. Post-witness expiry occurs without an author transaction open,
using one bounded runs transaction; recovery does the same before cleanup. The
consumer always obtains the shared barrier before any author writer, never in
reverse order. Nested process-wide and request-scoped shared leases are covered
on Windows (distinct shared byte slots) and Linux; a separate process attempting
exclusive reset while projection holds a shared lease is refused. A dirty reset
journal/operation refuses consumer scope before home access; only existing
startup/operator recovery may repair it. No provider admission lock is added.

Source checks during new admission use metadata-only runs read then visibility
through the held author connection before the runs writer; pin/hash/status and
snapshot checks run in that writer. At shared prepared-start integration the
file lane supplies its existing author_conn/runs_conn fences, permitting the same
checks without opening another writer or connection. Its run guard and start CAS
remain the only execution-start truth; this storage module never dispatches.
