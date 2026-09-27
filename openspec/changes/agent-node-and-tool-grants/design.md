# Design

## As-built starting point (origin/main f4417205)

`shared_self.shared_self_requested(snapshot)` decides per **branch** whether a
provider call is an agent turn. Both run sessions branch on it:
`foreground_run_provider._call` and `background_served_provider._call`. When it
is true, they call `prepare_shared_self_turn` (persona, founder history, the
sandboxed engine-MCP `ModelConfig`), then `workflow_agent._call_work_agent`.
That runs the shared `AgentTurnCoordinator` with a per-round
`_authorize_attempt` against the run's own work receipt. Because the decision
is per branch, a marked branch may contain only one prompt node: the session
cannot tell which node is calling.

## D0. The kind is a marker in `tools_allowed`, not a new field

An agent node is a prompt node whose `tools_allowed` holds `agent` (legacy:
`universe_self`). A new dataclass field would serialize into every node's
`to_dict`, so republishing an unchanged branch would mint a new content hash.
The marker needs no schema change, and every create path (canonical and served)
already carries `tools_allowed`. The served `update_node` edit contract is
unchanged: it still refuses `tools_allowed`. Grants are set when the node is
created (served or connector), or changed through the connector's canonical
updater.

## D1. The calling node is named by the compiler and resolved from the snapshot

The compiler sets `ModelConfig.agent_node_id` on the config it passes for an
agent node. The session never
trusts that config for authority. It resolves the id against its own admitted
immutable snapshot with `shared_self.agent_node(snapshot, node_id, principal)`,
which returns the node definition or raises:

- an id that is not an agent node in the snapshot → `PermissionError`;
- the snapshot's `author` is not the run principal → `PermissionError`, so
  another user's authored prompt can never drive the owner's tools. Foreground
  admission already requires this; background now checks it too;
- an agent node must be a writer prompt node with no `source_code`.

Calls with no `agent_node_id` take the ordinary path, even in a branch that also
has agent nodes. `shared_self_requested` keeps its branch-level meaning ("this
branch has at least one agent node"). That meaning is used for tool readiness
and for the invocation allowance at admission, which stays shared by the whole
run.

## D2. Grants narrow one config field that every tool surface honours

`served_tools.granted_engine_tools(tools_allowed)` maps a node's list to a
tuple: the markers (`universe_self`) are dropped, an empty list means the whole
served set, and an unknown name raises. `prepare_shared_self_turn` puts the
result in `ModelConfig.engine_tool_grant`. It is read in three places:

- the HTTP agent loop (`AgentTurnCoordinator` → `open_engine_tools(enabled_tools=…)`),
  where `EngineToolSession.call` already refuses unlisted names;
- the codex native turn (`enabled_tools=[…]`);
- the claude native turn: the allowed list is narrowed, and ungranted
  `mcp__tinyassets__*` names are added to the denylist.

The route stays pinned by (principal, universe) from the work receipt, as today.

## D3. The turn runs until finished

A node slot wall clock (default 300s) used to fail an agent node while its turn
kept running. An agent node's slot is now the converse turn's own runaway
backstop, `universe_intelligence.served_absolute_cap_s(universe config)`
(3600s, with a per-universe override). The node's `timeout_seconds` does not
shorten an agent turn. There is one bound and it matches converse.

## D4. Code nodes reach granted served tools (slice 2)

`invoke_mcp_action(name, **args)` with `name` in the served set opens the
pinned engine tool route for that one tool. Owner and universe come from the
run's immutable `BranchExecutionContext`, never from the node. The call is
allowed only when provenance is `own` and the definition author is the owner,
and the route read rechecks current serving-owner authority. The grant is
exactly the served names in the node's `tools_allowed`. If it names none, the
node gets the whole served set, which is what the owner's chat has. The alias
table is unchanged for its existing names.

## D5. What an agent node saves stays bound to its universe

Widening what a run may read also widens what its saved output contains. The run
read gate only protects rows bound to a universe, either by a `universe:<id>`
actor or by `queue_universe_id`. Every agent turn is structurally bound:
- the foreground session rechecks, before each round, that its run's actor is
  `universe:<session universe>`;
- a background task records its universe in `queue_universe_id`.

The agent node writes no conversation transcript. Its turn journal is keyed by
(owner, universe) and is not served. Tests read an agent-node run as a second
user through `get_run`, `get_run_output`, `list_runs` and `query_runs`, and
expect a refusal on both paths.

## Custom agents become configurations

A custom agent is an agent node's stored configuration: instructions
(`prompt_template`), grant (`tools_allowed`), model (`llm_policy`), and inputs
and outputs. It is published or remixed as a branch like any other. That makes
the following redundant, to be removed in a later lane:

- `agent_runtime_compiler` / `agent_runtime_plan_compiler` (a second graph
  compiler);
- `agent_runtime_invocation` / `agent_runtime_provider_execution` /
  `agent_runtime_provider_outcome` (a second provider loop);
- `agent_runtime_grants` (a second grant model).

`custom_agents` definitions and bindings stay: they store and share
configurations.

## Risks, and what bounds them

- **Cross-user reach.** The route is pinned from the work receipt and rechecked
  each round. There is the author check (D1), and no tool takes a universe
  parameter.
- **Runaway cost.** Each round admits against the run's existing receipt, so a
  loop ends when the receipt's invocation and token allowance is spent.
  Nested `run_graph` calls admit on their own.
- **Grant escalation within the owner's universe.** A node granted both
  `write_graph` and `run_graph` can build and run a node with any grant, so the
  pair is equivalent to the full grant. It is documented, not enforced: it is
  owner-to-owner, and the floor is cross-user only (lead ruling 2026-09-27).
- **Prompt injection.** A turn can read untrusted text (commons, channels, run
  outputs). The grant is how the owner narrows what an injected instruction
  could reach. Foreign content stays wrapped as untrusted.
