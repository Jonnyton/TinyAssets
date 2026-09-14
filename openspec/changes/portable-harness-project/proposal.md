## Why

A developer should be able to export a harness, inspect and edit its source in
ordinary development tools, and continue using it without the hosted app.
TinyAssets already has canonical agent definitions, private bindings, and an
interchange pipeline. The next step is to prove that these carry a runnable
software project, including its required files and dependency identities.

This is a proposal-only change. Requirements below are targets, not claims of
shipped behavior. It does not change PLAN.md, storage, runtime activation, or
the public tool catalog.

## Refinement: the fundamental toolset

The source project is the portable unit of a broader composition contract.
[primitives.md](primitives.md) maps Node, Edge, State, Scope, Run and Trigger to
replaceable context, memory, loop, tool and evaluator components, with concrete
interfaces, runtime boundaries and an evidence ladder. [research.md](research.md)
records primary sources, existing compiler integration, alternatives and the
implementation review handoff.

Companion [UI proposal #3841](https://github.com/Jonnyton/TinyAssets/pull/3841)
uses the same substrate for presentation, inputs, state projections and actions.
Packaging proof alone does not establish that this complete toolset works.

## What Changes

- Specify a portable project representation around the existing
  `agent-definition/v1` contract, preserving native definition fingerprints.
- Separate public source and intentional seed assets from private installation
  bindings and run state.
- Define inspection-only import, integrity checks, compatibility reporting,
  and an explicit activation boundary.
- Define one acceptance fixture that round-trips through an empty installation
  and runs without the hosted app.
- Keep harness strategies replaceable compositions; use the existing governed
  runtime for execution and external effects.

## Capabilities

### New Capabilities

- `portable-harness-project`: An inspectable source project with a locked file
  inventory, explicit runtime requirements, and a reproducible offline fixture.

### Modified Capabilities

- None in this proposal. Existing `universe-custom-agents` behavior is retained.
  Any implementation that needs to change its public envelope or storage must
  first add the corresponding reviewed delta.

## Impact

Expected implementation integration points are `tinyassets/custom_agents.py`,
`tinyassets/agent_interchange.py`, and `tinyassets/api/custom_agents.py`.
These are integration candidates, not a mandate to modify each module.

Owner: tiny, working through Codex. One intent: prove source-project portability
for one ordinary harness. Delivery: one draft PR; implementation tasks remain
unchecked. Cross-family shape review precedes implementation. The scope covers
local developers and browser users receiving the same project artifact through
a governed workspace and existing delivery channels.
