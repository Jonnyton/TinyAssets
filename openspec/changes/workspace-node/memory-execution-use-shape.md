# Derived execution-use lifetime: bounded review question

2026-09-19 UTC. Proposal only; no shared primitive modification. Owner primitive
is f68a9db8, integrated af3156ba. Root requested this concrete race be reviewed.

## Observed source facts

- `storage/run_execution_lock.py:RunExecutionGuard.require_held` validates active
  registry, PID, acquiring thread and exact DB. Do not weaken this check.
- `runs.py:_managed_execution_scope` holds the OS lock through invocation and
  provider settlement. Start/terminal mutations use that owner receipt.
- Actual installed LangGraph `BackgroundExecutor.__exit__` waits pending Futures
  and shuts down its executor, even on exception. `submit` copies ContextVars.
  Read with `python -c "import inspect; from langgraph.pregel.executor import
  BackgroundExecutor; print(inspect.getsource(BackgroundExecutor))"` on Windows.
- However `graph_compiler.py:_build_code_node` copies context into NodeSandbox's
  stdout RPC drain thread. `node_sandbox.py:run_sync` joins drains for only2s;
  a callback may still be executing after the graph node returns. This is an
  actual escape from assuming compiled graph return means every worker is done.
- `_run_with_timeout` (graph_compiler.py) also leaves timed-out provider callbacks
  running. It does not copy ContextVars. Only resource-operation use is in this
  slice, not a claim that every external provider process stops with the graph.

## Proposed smallest contract

1. Owner may mint a nonserializable `RunExecutionUse` only while its exact guard
   passes require_held. Receipt binds original guard object/PID/DB/run and cannot
   satisfy owner start/terminal/release APIs. It is not persisted/new authority.
2. Worker `with use.hold(conn)` atomically checks original guard active/not
   closing under a guard-owned condition and registers this *actual scoped
   operation*. It rechecks current same-process identity and DB/run, rejects
   forged/unissued, retired and forked copies. Nested uses are scoped, not TTLs.
3. Pin the whole concrete code-node acquisition/launch/reap/release scope; pin
   the actual RPC callback separately because its drain may outlive the node.
   Provision/acquisition/broker scopes likewise pin through exact process reap.
   No bare validate-then-launch method: kernel admission needs a live hold plus
   fresh FamilyFence/current epoch/lease. Membership cannot replace byte authority.
4. On owner context exit, atomically close new holds, then **retain original OS
   guard** until all registered operation contexts actually finish their finally
   blocks. Wait without a family fence or SQL writer lock. Do not transfer guard
   ownership, set an independent alive flag, or release by timeout. A stuck
   callback retains ownership/cleanup debt; Stop/OOM still closes epoch promptly
   without this guard, preventing new resource launches and killing owned groups.
5. Existing LangGraph Future completion supplies normal node quiescence; the
   separate RPC-use scope covers the proven2s drain-join gap. A callback starting
   after owner exit begins is denied before effects. If an already-held callback
   attempts a new launch after closure, fresh epoch admission refuses it.

No second execution manager, lock, lease table, guessed root or database queue.
One condition/counter is bookkeeping on the existing guard lifetime, tied to
actual entered/exited work scopes—not a substitute for process/kernel emptiness.
Registry membership and pin creation/owner retirement are synchronized together;
otherwise validate-only races owner release and is insufficient.

## Red-first concrete tests / reviewer question

- Real pool-thread use succeeds while ordinary require_held on that thread still
  refuses; owner-only settlement/release remains unavailable to derivative.
- Pause a worker after pin/before launch; owner return attempts to finish. A
  separate process still cannot acquire OS guard until worker completion; late
  unpinned task is refused after closing begins.
- Real NodeSandbox RPC callback intentionally outlives its2s drain joins and node
  return. Guard remains held until callback finally exits. Concurrent Stop closes
  promptly; callback's post-close family admission refuses/no child starts.
- Real parallel LangGraph exception/cancel waits active node use and reaps its
  sandbox. Registry/condition retirement is tested, not inferred from Futures.
- Forged, wrong DB/run, owner-retired, fork-inherited receipt refuses; callback
  exception releases only its pin, not OS guard or sibling pins.

Question: AGREE/ADAPT this minimal derivative + actual-use scope lifetime, or cite
the exact remaining owner-return/launch race. Do not reopen cgroup/bootstrap
shape or request general provider shutdown. No implementation before disposition.

## Fable85986 ADAPT disposition (2026-09-19)

Full unchanged receipt: memory-execution-use-review.md. Frozen review9199697e,
exit0 after529s, verdict ADAPT (not integrated-code approval). Coordinator read
and accepted both required corrections before implementation:

- Closing and pin-drain wait live in the existing owning OS-lock context's
  finally, before registry removal, FD close or mutex release. Exceptional waits
  must not bypass pins. Nested nullcontext neither mints nor closes another use.
- Mint once owner-side immediately after ownership; carry by ContextVar. Actual
  drain-thread RPC pin brackets permission counting and invocation, using its own
  read connection for identity. This includes the trailing-line callback path.

Clarification to proposed item5: **terminal FamilyFence is the effect boundary**,
not owner exit. A pin admitted after terminal status but before close may exist,
but fresh family authority refuses effects. Existing terminal/provider settlement
ordering remains; owner lifetime wait does not rewrite completed-parent semantics.
Tests add actual resume contention during late drain and success afterward,
committed cancellation before pin wait returns, late dispatch creates no child,
sibling exception pins, wrong DB, forged and forked receipts. Optional rpc closed
flag/atfork are deferred unless needed by a concrete basic-safety test. Production
allocator/AS/bootstrap activation remains separately gated.
