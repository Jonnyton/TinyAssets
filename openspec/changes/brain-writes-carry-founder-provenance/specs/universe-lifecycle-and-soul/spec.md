## ADDED Requirements

### Requirement: Durable brain content carries server-verifiable founder provenance
The daemon SHALL persist soul and canon content only through the founder-only writer, whose
inputs are the founder's utterance for the turn and the agent's proposal; every committed edit
MUST record the turn id and a digest of the founder utterance that grounds it. The served
`write_brain` tool SHALL record a proposal and SHALL NOT persist directly.

#### Scenario: Founder states a durable fact
- **WHEN** the founder tells their universe a fact about themselves in a turn
- **THEN** the next turn's system prompt contains it, and `read_brain` shows the turn id and utterance digest for that section

#### Scenario: Agent proposes content the founder did not say
- **WHEN** the served agent calls `write_brain` with a section body whose claims are not in the founder's utterance for the turn
- **THEN** nothing of it is persisted, the drop is logged with a reason, and the next turn's system prompt is unchanged

#### Scenario: Turn with no founder utterance
- **WHEN** a proposal arrives during a turn that has no founder utterance (tool-initiated or scheduled)
- **THEN** the proposal is discarded and no brain file changes

### Requirement: The founder-only writer never sees tool or commons output
The extraction call that grounds brain writes SHALL receive only the founder's utterance and the
proposal; the reply, tool results, fetched pages and commons shapes SHALL NOT be part of its input.

#### Scenario: Reply carries laundered content
- **WHEN** the reply for a turn contains text copied from a commons shape and the founder's utterance does not
- **THEN** that text is not persisted to any brain file
