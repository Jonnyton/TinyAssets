# graph-execution-substrate — primitives the owner is missing

## ADDED Requirements

### Requirement: Trigger SHALL be a user primitive

An owner SHALL be able to create, inspect, fire, and cancel a Trigger bound to a
published immutable Branch version through canonical handles. A scheduled
workflow is then composed from Branch + Trigger by the user, rather than being
obtainable only by adopting the `automation` lane whole.

#### Scenario: Composing a scheduled workflow without the automation lane

- **GIVEN** an owner with a published Branch version
- **WHEN** they bind a Trigger to it with a cadence
- **THEN** it runs on that cadence
- **AND** they can fire or cancel it themselves

> Verified absent 2026-08-05: `write_graph` accepts `goal, request, branch,
> universe, automation, agent, agent_binding`; `read_graph` adds
> `runs/run/automations/connections/agents/...`. Neither exposes `trigger`.

### Requirement: An owner SHALL be able to attach an effect to an existing node

`update_node` SHALL be able to patch `effects`, or the surface SHALL document
the supported route and preserve the node's edges across it.

#### Scenario: Adding a GitHub pull-request effect to a delivery node

- **GIVEN** a published Branch whose delivery node declares no effects
- **WHEN** the owner attaches `github_pull_request` to that node
- **THEN** the effect is attached
- **AND** the node's existing edges survive without a manual rewire

> Live 2026-08-05: `_NODE_UPDATE_FIELDS` omits `effects`, so the only route was
> `remove_node` + `add_node`, which dropped both of that node's edges. The rewire
> succeeded only because the operator had read the source; the tool description
> does not mention it.

### Requirement: The remix/rebind lineage constraint SHALL be stated

Where a remix cannot satisfy `rebind`, the surface SHALL say so at the point of
use.

#### Scenario: Owner tries to improve an automation's workflow by remixing it

- **GIVEN** an automation bound to a Branch version
- **WHEN** the owner remixes that Branch to improve it
- **THEN** they are told the remix mints a new lineage their automation cannot
  bind to, and which operation to use instead

> `rebind` requires the same `branch_def_id`; `operation=remix` mints a new one.
> The natural "fork and improve" path yields a version the automation can never
> adopt, and nothing says so.

### Requirement: A node's declared timeout SHALL be enforced

`timeout_seconds` on a node definition SHALL bound that node's execution, or the
field SHALL be rejected at authoring time rather than accepted and ignored.

#### Scenario: A node exceeding its declared timeout

- **GIVEN** a node declaring `timeout_seconds: 300`
- **WHEN** it has been executing for materially longer
- **THEN** it is terminated and the run reports the timeout

> Live 2026-08-05: run `6d248abb9d4b4ee3` held `delivery_slice` for over 50
> minutes against a declared 300s. In a 300s-cadence loop, an unbounded node has
> no ceiling.
