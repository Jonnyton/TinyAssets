## MODIFIED Requirements

### Requirement: Converse relays bounded turn input provenance
The founder-only `converse` handle SHALL accept one optional `input_method` field with the closed values `typed`, `spoken`, `app_action`, and `unknown`, default it to `unknown` when omitted, and relay it to the universe writer as a fact about the specific current turn that cannot expand authority or alter the canonical founder message. The handle SHALL NOT expose or accept the replaced `voice_active` field.

#### Scenario: Reported input method reaches the universe writer
- **WHEN** an authorized founder calls `converse` with an allowed reported `input_method`
- **THEN** the writer receives plainly labeled context identifying how that specific turn entered the calling client
- **AND** the context is distinct from founder-authored message text

#### Scenario: Client cannot report input provenance
- **WHEN** an authorized caller omits `input_method`
- **THEN** the writer receives explicit `unknown` input-method context
- **AND** the system does not guess from the message wording or Voice-session state

#### Scenario: Replaced Voice-state field is rejected
- **WHEN** a caller supplies the removed `voice_active` field
- **THEN** the public tool boundary rejects it rather than translating or accepting it as an alias

#### Scenario: Input provenance cannot grant authority
- **WHEN** any caller supplies an allowed `input_method`
- **THEN** founder authentication, universe access, interlocutor tier, and effect consent remain unchanged
- **AND** conversation storage and learning extraction preserve only the original founder message and canonical reply
