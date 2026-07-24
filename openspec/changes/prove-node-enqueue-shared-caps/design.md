## Context

Production deploys have enabled `TINYASSETS_NODE_ENQUEUE_ENABLED=on` since
2026-06-03. The primitive appends an epoch-1 `owner_queued`/`branch_run`
`BranchTask` from an approved source node and relies on the daemon dispatcher
to execute it later.

The existing count/check/append operation is correctly serialized by the
per-universe cross-process file lock. The missing §14 boundary proof exposed
two separate lineage defects:

1. a trusted root run with no parent or origin falls back to each new child
   task ID, so siblings do not share an origin; and
2. the lineage count reads only the live queue, so garbage collection forgets
   terminal descendants after moving them to the archive.

Independent security review then exposed four older containment gaps: the
documented per-run budget was allocated per source node, the dispatcher trusted
the queue row's mutable universe field instead of the physical queue, private
target authorization inherited process-global identity, and an existing blank
history file was treated as an empty list.

The active `operator-request-trigger-contract` change designs a future queue
epoch. This change repairs the production epoch-1 bridge and records invariants
that any later queue migration must preserve; it does not decide that
migration.

## Goals / Non-Goals

**Goals:**

- Give every trusted root execution one stable, server-owned lineage origin.
- Enforce the lineage cap across both live and archived descendants.
- Keep global active-cap and lineage count/check/append decisions under the
  existing cross-process universe lock.
- Prove exact cap boundaries through compiled graph threads and the storage
  seam through spawned processes.
- Fail loudly when persisted history cannot support a safe admission decision.
- Share one atomic successful-enqueue budget across every source node in a run.
- Bind enqueue universe authority to the physical queue consumed by dispatch.
- Refuse private targets until request-scoped actor authority is durable.

**Non-Goals:**

- Change public MCP/API shapes, queue epoch, dispatcher selection, cap defaults,
  or production feature flags.
- Introduce a separate lineage ledger or migrate existing queue files.
- Claim organic post-fix use before production evidence exists.

## Decisions

### Derive the root origin at the run boundary

`execute_branch` already creates the authoritative `run_id` before compiling
the graph. When a trusted enqueue universe exists, it will pass
`supplied_origin or supplied_parent or "run:" + run_id` as the context origin.
Queued descendants keep their persisted origin, and a queued root keeps its
task ID through the parent fallback.

Deriving the origin once at the run boundary is preferred to the current
per-child fallback because every source node in the run receives the same
trusted value. Requiring callers to invent a root task is rejected because the
soul-loop path is a real run without a parent `BranchTask`.

### Share one atomic budget across the compiled run

`compile_branch` will allocate one small lock-protected budget object and pass it
to every source-node MCP invoker. A contender reserves a slot immediately
before the atomic queue append and releases it if append fails, so only
successful enqueues consume the run budget. Compilation occurs once per
production run, keeping the counter run-scoped rather than process-global.

### Bind universe authority to the consumed queue

The dispatcher will compare `claimed_task.universe_id` with the canonical name
of the `universe_path` whose queue supplied the row. A mismatch fails before
branch execution. After that check, the physical queue name—not row metadata—is
passed as trusted enqueue context.

### Keep epoch-1 private targets fail closed

The current queue row does not carry request-scoped authenticated actor
authority. Therefore epoch-1 in-node enqueue will accept only public target
branches, even when the process-global actor string happens to match a private
branch author. The active epoch-2 admission design owns durable tenant/actor
evidence; private targets may be reconsidered only when that evidence is
carried end to end.

### Count lifetime lineage across live queue and archive

`append_task_capped` will read the live queue and, only when a lineage cap and
origin are present, the existing archive under the same universe lock. The
global cap continues to count only live `pending` and `running` rows. The
lineage cap counts distinct non-empty `branch_task_id` values across live and
archived rows with the same origin; matching rows without IDs are counted
conservatively. Garbage collection also avoids re-appending a task ID already
present in the archive.

Reusing the archive is preferred to a new counter file because a separate
ledger would need crash-consistent multi-file commits and historical backfill.
The archive already contains the necessary immutable task records. A crash
between the archive replace and live-queue rewrite can leave one row in both
files; ID-based de-duplication prevents false exhaustion, and a later GC run
converges the archive without duplicating that task again.

### Make archive corruption fail closed

Once archived rows participate in admission truth, garbage collection cannot
replace an unreadable archive with a fresh one. Both capped admission and
collection will surface the decode/read failure without appending or
overwriting. Existing zero-byte or whitespace-only queue/archive files are
invalid JSON and fail the same way; only a missing file means empty history.
This aligns the queue path with the project's fail-loud storage rule and
prevents silent budget reset.

### Prove both semantic and cross-process boundaries

Compiled-and-invoked graph tests will synchronize concurrent producers and
assert exact winner/refusal counts for distinct-origin global contention and
same-origin lineage contention. A small spawn-based process test will exercise
the real Windows/POSIX sidecar lock directly. Existing compile/invoke coverage
continues to prove source-node wiring, per-run budgets, and loss-free queue
writes.

## Risks / Trade-offs

- **Large archives make capped enqueue O(history).** → Read the archive only
  for lineage-capped enqueues; a future queue epoch may replace this with a
  transactional indexed counter while preserving the requirement.
- **A legacy row without an ID can be double-counted after a mid-GC crash.** →
  Identified rows are de-duplicated; unidentified rows remain conservative,
  and future transactional storage can remove the ambiguity.
- **Spawn tests can be slow on Windows.** → Keep the cohort and cap small,
  enforce join timeouts, and terminate only test-owned processes on failure.
- **The future queue-epoch change may touch the same semantics.** → Treat these
  stable-root, run-wide-budget, physical-universe, lifetime-lineage, and
  fail-closed rules as required transactional migration invariants. In-node
  enqueue remains epoch-1-only until v2 implements them.

## Migration Plan

No data migration is required. Existing live and archived task rows already
carry `origin_branch_task_id`; empty historical origins do not count toward a
named lineage. Deploy the code normally, then use post-deploy evidence before
claiming clean real-user use. Rollback is the ordinary prior-image rollback;
the change creates no new storage artifact.

## Open Questions

None for this repair. Indexed lineage accounting belongs to the future queue
epoch design.
