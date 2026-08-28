# A turn holding a provider slot can starve the work it spawns

**Severity:** P2 · **Filed:** 2026-08-28 from a cross-family review of the admission bound
**Surface:** `tinyassets/provider_admission.py`, `tinyassets/providers/router.py`

## The finding

The admission bound holds a slot for the lifetime of a provider subprocess. That
subprocess is an agent, and it can call back into the engine over MCP — `run_graph`,
notably — which executes nodes that make their own provider calls needing their own
slots.

So with the default limit of 6, six simultaneous served turns that each trigger a
`run_graph` hold every slot while their children queue behind them. The 20-second
admission wait means this is not a permanent deadlock — the children fail and the slots
eventually free — but the workload starves, and it starves in exactly the situation the
bound exists to survive.

## Why it is not simply fixed

The obvious answer is to reserve headroom: let user-facing turns take at most `limit - k`
and keep `k` for nested work. The difficulty is *recognising* nested work. The child call
does not run on the parent's thread — it arrives as a fresh MCP request from the parent's
subprocess — so a thread-local or ContextVar marking "already holding a slot" does not
propagate to it. Distinguishing the two requires threading a depth or an originating-turn
id through the engine MCP boundary, which is a design change rather than a tuning change.

## What holds until then

- The 20-second wait bounds the damage to a failed child rather than a hung box.
- `get_status.provider_admission` reports `refused` and `peak_concurrent`, so this
  becomes observable rather than theoretical the moment it happens in production: a
  rising `refused` with `peak_concurrent` pinned at the limit is this pattern's signature.
- The approved 4 vCPU / 8 GB resize raises the limit, which widens the margin without
  changing the shape.

## Related

`docs/design-notes/2026-08-28-capacity-measured-for-1000-users.md` carries the
measurements the bound is sized from.
