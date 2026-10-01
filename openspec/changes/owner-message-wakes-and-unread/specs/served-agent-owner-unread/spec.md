# served-agent-owner-unread (delta)

## ADDED Requirements

### Requirement: Every served JSON tool result carries the owner's unread count

Every served engine tool result that is a JSON object SHALL carry `owner_unread`: the number of the pinned owner's messages in their own thread of the pinned universe, recorded at or after the counter's epoch, that the universe has not read. Raw content tools SHALL carry none. A result for a server without current serving authority SHALL carry none. The count SHALL never include another principal's messages.

#### Scenario: A new message shows at the next tool boundary
- **GIVEN** a running agent with nothing unread
- **WHEN** the owner's message is stored and the agent calls any JSON tool
- **THEN** the result carries `owner_unread: 1`

#### Scenario: Another user's thread is never counted
- **WHEN** another principal's messages are stored in the same universe's conversation store
- **THEN** the owner's count is unchanged and that principal's own engine reports only its own thread

### Requirement: Only a delivered message is marked read

A message SHALL be marked read only when a served `read_graph target="conversation"` returns that owner message's text through its end, and only for ids that payload carried. A catalogue page SHALL mark nothing, a middle chunk SHALL mark nothing, and reading a newer message SHALL leave older unread ones unread.

#### Scenario: A message arriving during a read stays unread
- **WHEN** the owner's message is stored while the agent's conversation read is in flight
- **THEN** after the read the count still includes that message
