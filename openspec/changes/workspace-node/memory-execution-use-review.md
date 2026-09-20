I'll read the frozen shape note at 9199697e first, then trace the runtime paths it references.

Now tracing the runtime the note cites. Fetching the guard, the owner scope, the code-node builder, the sandbox drain, and the LangGraph executor in parallel.

Now the sandbox `run_sync` body, the RPC invoker, terminal settlement ordering, and every guard consumer in the tree.

**AGREE**, with two narrow adaptations required before code. The shape answers the question correctly: a same-process, non-serializable pin on the existing guard's lifetime can hold the same OS lock across LangGraph pool threads and the RPC drain thread without granting authority. Evidence from the frozen tree:

- **Authority stays owner-only by construction.** Both sinks type-check the receipt (`type(execution_guard) is not RunExecutionGuard`, runs.py:1804 and :3601) and `require_held` binds the acquiring thread (run_execution_lock.py:37). A use object of another type cannot pass either, and no change to `require_held` is needed.
- **Worker reachability of the guard is pre-existing, not new.** The guard already reaches every pool thread and the drain thread by reference through the ContextVar (runs.py:3611, then `copy_context` in `BackgroundExecutor.submit` and graph_compiler.py:2118). Those copies are refused by thread ident today. The pin only adds a lifetime count.
- **The only in-process escape is the RPC callback.** LangGraph 0.4.10 `BackgroundExecutor.__exit__` waits every started future, so the code-node acquire/launch/reap/release block (graph_compiler.py:2140-2210) cannot outlive `app.invoke` on the owner thread. The drain thread's `on_line` path (node_sandbox.py:2767-2796, joins at 2864-2866) is the real gap, including the trailing-line `finally` at 2445-2452. `_run_with_timeout` workers run with an empty context, hold neither guard nor use, and are out of slice.
- **Terminal ordering needs no rework.** The terminal write runs on the owner thread inside the scope (runs.py:4290 through the nested nullcontext), so family close, `chain.settle()`, and the outbox enqueue all precede the proposed wait. A late `dispatch` is refused by `validate_in_transaction` (parent not `running`, or root closing, workspace_family.py:340-368) and it serializes with the terminal write under the same fence. Cancel is polled and kills on the pool thread (node_sandbox.py:2840-2850), so the root closes with `cancelled` before the owner waits. Orphan marking already ignores managed runs (runs.py:187-190), so no timeout path can take the guard.
- **Resume during a drain is refused truthfully.** `resume_run` writes RESUMED through a fresh `try_run_execution_lock` on the request thread (runs.py:5445), gets contention, and raises before any status write (runs.py:3607-3609). That is the correct outcome and belongs in the red-first list.

## Blockers (adapt before implementation)

1. **Release ordering inside `try_run_execution_lock`.** The closing flag and the `while count: cond.wait()` loop must run in the existing `finally` before `_active.discard`, `os.close(fd)`, and `mutex.release()` (run_execution_lock.py:96-103). The close path must be unreachable while the count is nonzero, even if an exception lands during the wait. Nested `_managed_execution_scope` entries (nullcontext) must neither mint a second use nor close the outer one.
2. **Mint once, carry by ContextVar, pin on the drain thread.** Mint immediately after `_owns_managed_execution` enters, where `require_held` passes, and publish through a ContextVar so both `copy_context` sites carry it. Never expose it as workflow payload. The RPC pin must bracket `rpc_permit()` plus `invoke_mcp_action` inside `_invoke` on the drain thread and open its own read connection for the database identity check. Keep the code-node pin as well, though it is redundant with the executor wait.

Item 5 of the note should be restated: the effect boundary is the family fence at the terminal write, not owner exit. A hold admitted between the terminal write and owner exit is harmless because the fence refuses effects, and the family stays open only if the child was admitted while the parent was still running.

## Red-first proof

- Pool-thread `use.hold` succeeds while `require_held` on that thread raises. Passing the use as `execution_guard` or `provided` raises at the type check.
- A drain callback outliving node return by more than the join timeout. A second `try_run_execution_lock` from another thread yields None until the callback's `finally`. `resume_run` raises `RunExecutionAuthorityLost` during the drain and succeeds after it.
- Cancel while a callback is stuck. Observe from a second connection that the root's closing reason is committed before the owner's wait returns.
- Late `dispatch` after the terminal write raises `FamilyRefused` from `assign_in_transaction`, and no child row or jail appears.
- Forged, wrong-database, and forked receipts refuse. Run the fork case on the Linux oracle.
- A callback exception decrements only its own pin. A sibling pin keeps the OS lock held.

## Optional hardening

- `EffectChain.rpc_permit` should refuse once `closed` is set (effectors/__init__.py:681-690). Today it only counts, so a post-settlement round-trip is refused by the fence rather than at the RPC layer.
- Register an `os.register_at_fork` hook that clears `_active` and per-guard conditions in the child.
- Note for the other lane: the frozen `WORKSPACE_LAUNCHER_FACTORY` is built without a `cgroup_admission` (the parameter at node_sandbox.py:1995 is the only reference). The fresh-admission seam this proposal relies on is present but not yet wired in production.

VERDICT: ADAPT

Checked: the listed dispatches belong to the builder's session, and this review's hard constraints forbid re-dispatching (no `peer_agent.py`), dropping them (no edits), or waiting on the running one. My deliverable is complete and unchanged above.

VERDICT: ADAPT
