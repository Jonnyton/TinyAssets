# Stale-fleet reconcile cancels and retires without platform admission

**Filed:** 2026-09-23
**Verified:** 2026-09-23 UTC, worktree `wf-cloud-authority-remaining` at baseline `16e6f0bf`
(deployed runtime `042cdce8`), by reading `tinyassets/runtime_reconcile.py` end to end.
**Severity:** P2 — authority surface, not a serving or execution bypass.

## Source (verbatim)

From the independent Claude Opus read-only audit at HEAD `e389505b`, retained in
the lead checkout as `docs/reviews/2026-09-23-cloud-recovery-coverage-opus.md`
(not a file shipped with this candidate):

> | `tinyassets/runtime_reconcile.py:182-196, 220-256` (stale retirement/recovery) | **Ungated, but
> direction-safe.** No admission call in the module. `--apply` is CAS-fenced on digest+counts
> (L289-312) and only *cancels* pending tasks and *retires* runtimes. It removes capacity; it cannot
> grant serving or execute. Residual: an unadmitted host with the data dir can cancel a live
> universe's pending work — an authority concern, **not** a serving bypass. | A test that
> `_apply_plan` from a non-cloud process is refused (or explicitly documented as host-maintenance,
> not platform runtime). | File as a `docs/concerns/` row under this change; decide gate-vs-document
> before spec sync. |

## Re-verification at `16e6f0bf`

The finding holds; two citations moved.

- **Confirmed:** the module contains no reference to `platform_runtime_provenance`,
  `resolve_process_cloud_admission`, `cached_process_is_cloud_admitted` or
  `require_process_cloud_admission`. Grep over the whole file returns nothing.
- **Corrected:** `_apply_plan` is at `:220-256` (unchanged). The CAS fence the audit cited as
  `L289-312` is in `main()` at **`:289-312`** — `--expected-plan-digest` / `--expect-task-count` /
  `--expect-runtime-count` must all be supplied and must match the freshly rebuilt plan, else
  `ReconcileGuardError`.
- **Confirmed direction-safe:** the only two writes are
  `RequestAdmissionStore.cancel_pending_v2_task_if_stale` (`:225`) and
  `daemon_server.retire_runtime_instance_if_stale` (`:241`). Both are row-digest-fenced and both
  only remove capacity. Neither mints a runtime row, publishes a descriptor, claims a lease or
  reaches a provider. There is no path from this module to `router.call_sync`.

## Why it is still open

The cloud-only principle treats an existing row as a record, never permission.
The audited *granting* sites in this candidate derive from the process verdict — runtime
registration (`daemon_registry.py:515`), descriptor publication and refresh
(`daemon_registry.py:568`, added 2026-09-23), the assigned-consumer claim
(`branch_tasks_v2.py:487`/`:1232`), the Epoch2 cloud-activation claim (`branch_tasks_v2.py:450`/
`:1156`, added 2026-09-23) and the provider-authority `executor_class` derivation
(`agent_runtime_provider_execution.py:1235`, added 2026-09-23).

This module is an audited *revoking* site with no process check. An unadmitted
process can cancel and retire matching rows in a data root it can write. No path
from the personal desktop to writable production state has been demonstrated;
a copied fixture/data root is not a live universe. This is an unresolved
maintenance-authority boundary, not a proved production denial or execution bypass.

## Decision owed before full boundary closeout

Gate or document. Both are defensible and the choice is not mine to make unilaterally:

- **Gate** — add `require_process_cloud_admission(surface="stale fleet reconciliation")` at the top
  of `main()` (it holds no transaction there, so a resolve is safe). An unobserved
  process would resolve then; only a refused process needs a restart to resolve
  again. This would also close any legitimate off-cloud maintenance use.
- **Document** — declare the module host-maintenance tooling that is explicitly outside platform
  runtime admission, and say so in `openspec/specs/cloud-only-runtime-admission/`. Cost: the
  "removes capacity only" argument has to stay true, so any future write added here re-opens this.

If a guard is added, prove its refusal red-first at `_apply_plan` or the actual
apply entrypoint. If retained as scoped maintenance, prove its capacity-removing
contract without claiming an admission refusal it does not implement. Partial
spec sync for the separately reviewed granting guards does not close this concern.

## Not addressed here

The same audit's watchdog row asks for an ops note that the refusal → no heartbeat →
`heartbeat_stale` → restart loop is *intentional fail-closed behaviour*, not silent serving
(`deploy/daemon-watchdog.sh:22-39,100-119`). No code change; it belongs with this decision. See
[[cloud-only-runtime-admission]] task 8.
