## ADDED Requirements

### Requirement: Converse relays bounded client interaction state
The founder-only `converse` handle SHALL accept an optional boolean `voice_active` interaction-state field, default it to false when omitted, and relay it to the universe writer as informational context that cannot expand authority or alter the canonical founder message.

#### Scenario: Voice-active context reaches the universe writer
- **WHEN** an authorized founder calls `converse` with `voice_active=true`
- **THEN** the writer receives explicit context that Voice was active when this turn began
- **AND** the context is distinct from founder-authored message text

#### Scenario: Existing client omits Voice state
- **WHEN** an authorized existing client calls `converse` without `voice_active`
- **THEN** the writer receives Voice-inactive context
- **AND** the call remains valid without a compatibility alias or migration

#### Scenario: Interaction state cannot grant authority
- **WHEN** any caller supplies either value for `voice_active`
- **THEN** founder authentication, universe access, interlocutor tier, and effect consent remain unchanged
- **AND** conversation storage and learning extraction preserve only the original founder message and canonical reply
