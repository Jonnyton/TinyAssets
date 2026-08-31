# Cancel is advisory, and the run timeout is quietly doing cancellation's job

**Found 2026-08-31**, following the founder's statement that a borrowed
workflow is bounded by the owner being able to stop it:

> "the agent can always edit or cancel the workflow and an agent wouldnt use an
> uninspected workflow it didnt test and come to trust first"

With the credential vault absolute, **cancellation is what bounds a borrowed
workflow's live blast radius** — the vault stops theft, not use. So cancel
being real is load-bearing, not a convenience.

It is not real.

## What cancel actually does

`cancel_run` sets a flag. The flag is read **between nodes**:

* `runs.py:2795-2796` — `if is_cancel_requested(...): raise RunCancelledError(
  f"Run {run_id} cancelled between nodes.")`
* `runs.py:3701-3703` — "`cancel_run` flips the flag, the next inter-node
  `event_sink` check unwinds the graph."

And the sandbox never hears about it: **`tinyassets/node_sandbox.py` contains
no reference to cancellation at all.** The running child is not signalled, not
killed, not told.

So a node 25 minutes into `ws.run(["make", "-j8"])` keeps going. The owner
pressed cancel; nothing stopped.

## The consequence that nearly cost us the only working stop

The single mechanism that actually terminates a runaway node today is
`MAX_WORKSPACE_TIMEOUT_SECONDS = 1800` (`node_sandbox.py:153`) — the timeout
path is the only one that kills the child.

`openspec/changes/script-authoring-surface` proposed deleting that ceiling once
per-tenant quota replaced the host-wide slot, on the grounds that run length is
the user's business. **That ordering was wrong.** Quota bounds a tenant's
*share*; it does not stop one stuck run. Removing the timeout before
cancellation is real would leave nothing able to stop a run at all.

Correct order:

1. make cancellation reach the child,
2. then replace the host-wide slot with per-tenant arbitration,
3. **then** the ceiling can go, because the user now has a real stop and the
   platform has real arbitration.

This is the same chain pattern as before, one layer deeper: a hard-coded
ceiling is silently substituting for a capability that was never built, so the
ceiling looks like policy and is actually load-bearing.

## What "real" has to mean

* The flag must reach the running child, not just the inter-node boundary.
* Killing the child must kill the **whole jail** — a workspace node can start
  128 processes, and the existing timeout path already terminates the process
  group, so reuse it rather than inventing a second kill.
* It must be prompt from the surface the owner is actually holding (the app),
  while the run is in flight.
* Cleanup must still run: lease wipe, ledger reconcile, lock release. A cancel
  that leaks a lease is a cancel that costs the next run.

## How to prove it

Not a unit test on the flag. Start a run whose node sleeps well past any
inter-node boundary, cancel it from the app, and assert the child process is
gone from `/proc` and the lease and lock are released — on the Linux oracle,
where the jail is real.

Related: `2026-08-31-hard-coded-policy-that-should-be-user-composable.md`
(the ceiling as policy), and
`openspec/changes/script-authoring-surface/design.md` (why cancellation became
load-bearing once the vault settled secrecy).
