# graph-execution-substrate (delta)

## ADDED Requirements

### Requirement: An agent node holds a seat while it executes, and a blocking nested invoke inherits it

Each agent node execution SHALL acquire one of its universe's seats before it
runs a model and SHALL release it on every terminal path. A node that cannot
get a seat SHALL wait rather than fail, and its run SHALL report the waiting
state to the owner rather than appearing stalled. A sub-branch invoked
BLOCKINGLY SHALL re-enter its caller's seat, because a blocked caller is not
executing a model; an asynchronous or by-version invocation SHALL take its own
seat. The seat bound SHALL NOT limit how many agent nodes a graph may contain,
how deep branches may nest, or how many effects a branch may declare.

#### Scenario: A graph wider than its seats completes
- **WHEN** a graph with more concurrent agent nodes than the universe has background seats runs
- **THEN** the nodes run in waves as seats free and the run completes successfully

#### Scenario: A waiting node is visible, not stalled
- **WHEN** an agent node is waiting for a seat
- **THEN** the run's status names it as waiting for a free seat and how many are running

#### Scenario: Graph shape is still unbounded
- **WHEN** a user builds a graph with many more agent nodes than their tier has seats
- **THEN** authoring, saving and starting the graph all succeed
