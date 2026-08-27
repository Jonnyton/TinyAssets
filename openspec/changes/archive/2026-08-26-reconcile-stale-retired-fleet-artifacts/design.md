## Context

Epoch-2 tasks and daemon runtime instances share the canonical host SQLite database, but their mutations already belong to separate lifecycle owners. The retirement plan requires a temporary on-demand operator tool after fixed cloud workers are fenced: it must identify artifacts that can no longer make progress, let an operator review the exact set, and refuse a changed plan rather than guessing.

The task adapter already owns epoch-2 integrity classification and the legacy operational matcher distinguishes `awaiting_compatible_capacity` from invalid, disabled, policy-parked, or runnable work. `RequestAdmissionStore.request_v2_cancel` already maintains task/admission/request/event lifecycle state. `daemon_server.retire_runtime_instance` already owns runtime retirement.

## Goals / Non-Goals

**Goals:**

- Produce a deterministic, read-only plan for stale valid cloud-class epoch-2 tasks and stale provisioned cloud-worker runtimes.
- Make dry-run the CLI default and require a reviewed digest plus both exact counts before apply.
- Recheck each planned row under `BEGIN IMMEDIATE` before invoking its existing lifecycle transition.
- Preserve every task payload, admission, event, daemon definition, runtime history, and attribution row.

**Non-Goals:**

- No queue consumer, scheduler, compose fence, worker denylist, watchdog rewire, background serving authority, deployment, automatic reconciliation, or production invocation.
- No schema migration, SQL `DELETE`, payload compaction, or generalized cleanup framework.

## Decisions

### One canonical plan with stable time semantics

The CLI computes one UTC cutoff truncated to the current hour and subtracts `older-than-hours`. Hour truncation makes an inspected plan applicable during a bounded review window despite the CLI intentionally exposing no caller-chosen cutoff. The plan digest is SHA-256 of canonical JSON containing the cutoff and sorted selected task/runtime IDs. Full plan entries also carry their CAS evidence.

Alternative: hash an exact wall-clock instant. Rejected because a second CLI invocation could never reproduce the first digest. Alternative: accept an arbitrary cutoff argument. Rejected because it is outside the approved CLI contract.

### Read-only planning, lifecycle-owned mutation

Planning opens the existing canonical database in SQLite read-only/query-only mode and reads heartbeat/config files without initializing or migrating storage. Apply first recomputes this same plan and compares digest and counts before opening a mutation path. Task cancellation and runtime retirement then use the existing lifecycle logic through connection-local helpers so their new CAS wrappers do not duplicate state transitions.

Alternative: call ordinary storage initialization/list APIs during dry-run. Rejected because those paths may create/migrate a database or change journal state. Alternative: update status columns directly from the CLI. Rejected because it would bypass lifecycle events and aggregate state.

### Conservative task and runtime membership

A task is eligible only when its joined admission/request/task aggregate passes the existing epoch-2 integrity classifier, its policy tier is enabled, the current legacy capacity matcher says no compatible capacity, its executor class is exactly `cloud`, it remains enabled/pending, and its queued timestamp is at or before the cutoff. Its CAS evidence includes queued timestamp, admission grant generation, admission body digest, and an integrity-row digest.

A runtime is eligible only when it remains `provisioned`, has exact `runtime_registration=cloud_worker`, has a nonempty worker identity, its trusted `updated_at` heartbeat is at or before the cutoff, no matching live heartbeat exists, and no running/cancel-requested task is owned by that worker. Treating even expired or malformed ownership rows as active is the conservative fail-closed interpretation of the no-current-claim/unexpired-lease requirement. Its CAS evidence includes `updated_at` and a canonical runtime-row digest.

Malformed, incomplete, or unreadable evidence fails closed by exclusion or a loud planning error; it is never treated as stale merely because evidence is absent.

### Guard scope

Digest/count mismatches abort before any lifecycle call. Per-row CAS protects the interval between planning and each mutation; a CAS miss is an explicit nonzero apply failure. The existing SQLite lifecycle transactions remain the mutation authority rather than introducing a cross-subsystem transaction coordinator in this bounded slice.

## Risks / Trade-offs

- **[Risk] The hourly cutoff changes during a long review.** → Apply fails its digest guard; the operator must inspect a new dry-run.
- **[Risk] Filesystem heartbeat and database evidence disagree.** → Any live matching heartbeat excludes the runtime; malformed evidence fails closed.
- **[Risk] A row changes after the global plan check.** → Its `BEGIN IMMEDIATE` CAS refuses the transition and the CLI exits nonzero.
- **[Risk] A later per-row CAS fails after earlier reviewed rows were transitioned.** → Apply is not atomic across task and runtime lifecycles; the operator must run a fresh dry-run and reconcile the remaining plan. Digest or count mismatches still abort before every mutation.
- **[Risk] Private legacy matcher dependencies drift.** → Focused tests pin qualifying and non-qualifying behavior; this tool is intentionally retired with the fleet migration rather than generalized.
