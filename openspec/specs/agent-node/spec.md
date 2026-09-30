# agent-node Specification

## Purpose
An agent is a node: a workflow step that runs the universe's conversation turn with
the tools its owner grants, pinned to the owner's own universe. Code nodes reach the
same served tools under the same grant.

## Requirements
### Requirement: An agent node runs the conversation turn as a workflow step
A prompt node whose `tools_allowed` holds the `agent` marker SHALL run the same
agent loop, persona assembly and pinned engine tools as
`converse`, in foreground and background runs, with its rendered prompt as the
turn's direction and its final answer written to its output key; `universe_self`
is the legacy spelling of the marker. A branch MAY
hold any number of agent nodes alongside ordinary prompt and code nodes. Only an
agent node's own calls SHALL become agent turns. The run session SHALL resolve
the calling node from its own admitted immutable snapshot, never from call
arguments.

#### Scenario: agent step in a background run on a private universe
- **WHEN** a background run on the owner's private universe executes an agent node
- **THEN** the agent node's turn reads and writes the universe's brain and calls `write_graph` on that same universe

#### Scenario: plain and agent steps in one workflow
- **WHEN** a run executes a branch with an ordinary prompt node and two agent nodes with different grants
- **THEN** the ordinary node makes one plain model call and each agent node sees exactly its own grant

#### Scenario: another author's prompt never drives the owner's tools
- **WHEN** the branch snapshot's author is not the run principal
- **THEN** the agent node refuses before any model round or tool call

#### Scenario: an invoked child never borrows its parent's agent grant
- **WHEN** a blocking `invoke_branch` child (another user's public branch) holds an agent node named like the parent's agent node
- **THEN** the child's call refuses before any model round or tool call, and the parent's brain is untouched

#### Scenario: an undeclared node cannot claim an agent turn
- **WHEN** a provider call names an `agent_node_id` that is not an agent node in the admitted snapshot
- **THEN** the call is refused

### Requirement: An agent node's saved output is bound to its universe
Every run that executes an agent node SHALL be bound to the run's universe, so
another user's `get_run`, `get_run_output`, `list_runs` and `query_runs` are
refused on it, in foreground and background runs alike.

#### Scenario: a second user reads an agent-node run
- **WHEN** another signed-in user asks for an agent-node run on the owner's private universe
- **THEN** none of the four reads returns the run or its output, and the owner still reads it

### Requirement: Node tool grants
The other entries of an agent node's `tools_allowed` SHALL be a grant over the served
engine tools. A marker with no other entry SHALL mean every served tool, and a non-empty grant SHALL expose
exactly the listed tools on every provider surface. A name that is not a served
tool SHALL refuse loudly. Every granted tool SHALL be pinned to the run's own
universe and current owner.

#### Scenario: a narrowed grant
- **WHEN** an agent node grants only `read_brain`
- **THEN** its turn sees only `read_brain`, and a call to any other tool is refused

### Requirement: An agent turn runs until finished
An agent node SHALL be bounded by the converse turn's runaway backstop, not by
the node's slot timeout.

#### Scenario: long agent step
- **WHEN** an agent node's turn outlasts the default node timeout
- **THEN** the node is not failed while its turn is still running within the backstop

### Requirement: Code nodes reach their granted served tools
A code node's `invoke_mcp_action` SHALL accept any served engine tool name and
call that tool as the run's owner, pinned to the run's universe. Owner and
universe SHALL come from the run's immutable execution context, only for a
branch that owner authored. The served names in the node's `tools_allowed` SHALL
be its grant, and naming none SHALL grant the whole served set. The existing
action aliases SHALL keep working.

#### Scenario: a code node outside its owner's own run
- **WHEN** the run's provenance is foreign, the definition author is not the owner, or the owner is missing
- **THEN** the served-tool call is refused before any tool route is opened
