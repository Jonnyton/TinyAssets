## ADDED Requirements

### Requirement: Voice is a rendering of the canonical universe turn, not a second author
The voice surface SHALL relay each committed founder utterance through the existing `converse` operation and SHALL treat the exact returned text as the universe's canonical reply; Realtime SHALL NOT independently answer as, rename, or add facts for the universe.

#### Scenario: Voice relay returns a universe reply
- **WHEN** `converse` returns successfully for a spoken founder turn
- **THEN** the app renders that exact text in the canonical conversation history
- **AND** any speech output is treated only as an audio rendering of that reply

#### Scenario: Speech renderer differs from canonical text
- **WHEN** the speech renderer's output transcript differs materially from the canonical `converse` reply
- **THEN** the canonical stored and displayed reply remains unchanged
- **AND** the client records content-free mismatch evidence and does not replace history with the renderer output
