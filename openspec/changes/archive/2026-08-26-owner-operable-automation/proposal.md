## Why

An owner watched their own automation sit dead for five hours and could do
nothing about it. Every observation below comes from a rendered chatbot session
against live production on 2026-08-05 (`output/user_sim_session.md`), typed as a
normal user with the installed connector — not from reading source.

The automation reported `desired_state: active` while `activation.state` stayed
`stopped`, epoch 0, `terminal_receipts: []`. The owner's assistant diagnosed it
correctly and then said the honest thing:

> I can request state changes (resume, pause, rebind), but I can't spin up or
> assign a worker myself — that's infrastructure on TinyAssets' side, not
> something the graph API exposes a control for.

That is the gap. Every control on `target=automation` sets **desired** state and
waits for convergence. When convergence never happens, the owner has no move.
The platform's whole premise is that a power user can build, run, and repair
their own long-running work; here the owner could not perform the single most
basic repair — "run it now".

Worse, the surface filled the vacuum with fiction. Health advertised
`next_action: "run_once"`, an operation the API does not accept. The assistant
read it and invented a queued job, a claiming worker, and a causal story for why
it was stuck — a confident false statement about live system state. With no real
action to offer, it then sent the owner to a dashboard and a support channel
that do not exist.

## What Changes

- Give the owner a way to make their own automation do work now, without
  desktop, filesystem, or CLI access. This is the missing primitive; the exact
  shape is a design decision (see `design.md`), because the obvious verb was
  already rejected once as redundant with `run_graph`.
- Make `next_action` a contract, not a hint: it must name an operation this
  surface actually accepts, and that guarantee must be enforced by a test that
  fails when the two drift apart. A label that names a non-existent verb is
  worse than an empty field — it manufactures false state downstream.
- Make `resume` honest. Today it returns success while changing nothing when
  `desired_state` is already `active`. Success that changes nothing is
  indistinguishable from success that works.
- Expose Trigger as a user primitive so a scheduled workflow is *composed* from
  Branch + Trigger rather than only obtainable by adopting the whole opinionated
  `automation` lane. Neither `read_graph` nor `write_graph` exposes `trigger`
  today.
- Let an owner attach an effect to an existing node. `update_node` cannot patch
  `effects`, so the only route is `remove_node` + `add_node`, which silently
  drops that node's edges and forces a rewire the tool description never
  mentions.
- Say plainly that a remix cannot be bound to an existing automation. `rebind`
  requires the same `branch_def_id`; `operation=remix` mints a new one — so the
  natural "fork it and improve it" path produces a version the owner's
  automation can never adopt.
- Enforce `timeout_seconds` on a node, or stop accepting it. A node declaring
  300s ran past 50 minutes; in a 300s-cadence loop a stuck node has no ceiling.

## Capabilities

### Modified Capabilities

- `user-owned-cloud-automation`: owner-operable repair, an honest `next_action`
  contract, and a non-silent `resume`.
- `graph-execution-substrate`: Trigger as a first-class user primitive, effects
  patchable on an existing node, remix/rebind lineage stated in the contract,
  and node timeout enforcement.

## Impact

No new top-level MCP handle. Everything here rides existing canonical handles
(`read_graph`, `write_graph`, `run_graph`) and existing owner-scoped fences —
principal derived from authenticated request context, revision-fenced writes,
and no widening of provider or destination authority.

The guiding constraint from the host: *"the more that is user buildable, custom
made however the user wants, the more we ensure the power users still use our
platform."* And its diagnostic form: **if you cannot fix it as a user, the
primitives are not powerful enough.** Each item above is a place where that test
failed against live production, with the transcript to prove it.
