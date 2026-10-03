# Agent node and owner-granted node tools

Founder-approved plan, 2026-09-27, items 1 and 2 of 6. An agent is just a node,
and its access is whatever context and tools its owner gives it.

## Why

A user cannot build an agent step, a background agent, several sub-agents in one
workflow, or a custom agent that executes. The model-with-tools loop that
answers `converse` does exist as a node, but only behind a magic marker
(`tools_allowed: ["universe_self"]`, #3836). It is allowed on exactly one node,
which must also be the branch's only prompt node, and it always gets the whole
served tool set. The founder's universe could not set itself loose for exactly
this reason.

## What changes

- **`agent` node.** A prompt node whose `tools_allowed` holds the `agent` marker
  runs the converse turn as a node. It uses the same persona and brain assembly, the same shared agent loop
  (`AgentTurnCoordinator`), the engine tools pinned to the run's own universe,
  and the owner's model preferences, with the node's `llm_policy` as a per-node
  override. Its prompt is the node's own instructions rendered with its input
  state, and its final answer is written to graph state. A branch may hold any
  number of agent nodes alongside ordinary prompt and code nodes, in foreground
  and background runs. `universe_self` keeps working as a legacy spelling.
- **Tool grants.** The rest of an agent node's `tools_allowed` is a grant over
  the served tools. The marker alone means everything the owner's chat has. A list narrows
  the node to exactly those tools. A name that is not a served tool refuses
  loudly.
- **Code nodes (second slice).** `invoke_mcp_action` on a code node reaches any
  served tool the node is granted, pinned the same way. The existing aliases
  keep working.

## Not changing

- The cross-user floor. Every tool stays pinned to the run's own universe and
  its current owner, and a branch another user authored can never start an
  agent turn.
- Metering. Each agent round is admitted and settled against the run's existing
  provider work receipt and reservation. No cap is added.
- `agent_runtime*`. The design names which parts become redundant; deleting
  them is a later lane.
