## ADDED Requirements

### Requirement: HTTP-protocol turns run as tasks in the execution owner
When the thin loop is selected, a served turn on an HTTP model protocol SHALL
run as an asyncio task on the execution owner's single event loop, with the
submitting caller's context, and SHALL call the model only through the
credential broker (`resolve_exact_scoped_proxy`). No model credential SHALL be
held by the loop or passed to the box. Cancelling the caller's wait SHALL
cancel the task.

#### Scenario: a cancelled wait cancels the turn
- **WHEN** the caller waiting on a thin-loop turn cancels its wait
- **THEN** the turn's task is cancelled and any box execution it started is
  cancelled in the box

#### Scenario: the caller's context reaches the turn
- **WHEN** two callers with different identities submit turns concurrently
- **THEN** each turn reads its own caller's context and never the other's

### Requirement: Box tools are forwarded to the turn's bound box by op_id
The tools `read`, `write`, `edit` and `bash` SHALL execute in the turn's
command-center box through the `BoxProvider` contract, on a handle bound once
at turn start for the turn's owner, command center and turn, and never looked
up per call. Each call SHALL carry an `op_id` derived from its journal
position. A lost reply SHALL be resolved only by asking again with the same
`op_id`; an outcome still unresolved SHALL be recorded as unknown, the turn
SHALL hold, and the operation SHALL NOT be re-issued. An `edit` SHALL write
only if the file still holds the bytes it read.

#### Scenario: a lost reply runs once
- **WHEN** the reply to a box tool's `start_exec` is lost
- **THEN** the loop asks again with the same `op_id` and the box runs the
  command once

#### Scenario: an unknown outcome holds the turn
- **WHEN** a box tool's outcome cannot be resolved
- **THEN** the journal records the call as unknown, the turn ends
  `held_tool_unknown`, and no further inference or tool call is made

#### Scenario: a granted box tool with no box is refused
- **WHEN** the thin loop is selected, a turn is granted a box tool and no box
  provider is configured
- **THEN** the turn is refused before its first inference and no tool runs
  anywhere else

### Requirement: Owner reads are served by the loop and never reach the box
The tools `history` and `activity` SHALL be answered by the loop, read-only,
for the turn's owner and command center only, through the same domain reads
and identity gates as the owner door. They SHALL NOT be forwarded to the box
and SHALL take no parameter naming an owner or command center.

#### Scenario: history is the founder's own
- **WHEN** a turn reads `history` for a command center its owner no longer
  holds as founder home
- **THEN** the read is refused and nothing is disclosed

### Requirement: Other served tools keep their engine route and gates
Every served tool other than the box tools and the owner reads SHALL keep its
existing engine route, so the owner's rules and the auto-review continue to
gate consequential actions where they are enforced today. With the thin loop
not selected, every turn SHALL behave exactly as before this change.

#### Scenario: switch off is today's path
- **WHEN** `TINYASSETS_AGENT_LOOP` is unset
- **THEN** the four tools are served by the engine route and no box is bound
