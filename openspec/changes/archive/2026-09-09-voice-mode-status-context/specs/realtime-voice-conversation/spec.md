## ADDED Requirements

### Requirement: Voice transport status does not obscure conversation progress
The shared app SHALL render Voice transport state independently from canonical conversation/session progress and SHALL describe the observed effect of stopping Voice without claiming that an in-flight reply was canceled.

#### Scenario: Voice changes state while the universe is thinking
- **GIVEN** a canonical conversation turn is still pending
- **WHEN** Voice moves through startup, listening, speaking, error, or stopped states
- **THEN** the conversation status remains visibly "thinking" until the turn settles
- **AND** Voice status changes independently without replacing the conversation status

#### Scenario: Voice is stopped during a pending reply
- **WHEN** the founder stops Voice while a canonical conversation turn is pending
- **THEN** microphone capture, recognition, and speech output stop
- **AND** the app says the text reply is still running and will not be spoken
- **AND** it does not claim cancellation without a cancellation receipt

#### Scenario: Pending reply settles after Voice is stopped
- **WHEN** the pending turn completes after Voice was stopped
- **THEN** conversation progress clears normally and the canonical text reply remains rendered
- **AND** Voice status says whether the reply arrived or failed

### Requirement: The shared app reports Voice state without message inference
The shared app SHALL derive an invocation-time `voice_active` boolean from its actual Voice state and SHALL pass it with every canonical `converse` call without modifying the founder's authoritative message text.

#### Scenario: Turn begins while Voice is active
- **WHEN** a typed or spoken turn invokes `converse` while Voice capture is active
- **THEN** the app sends `voice_active=true`

#### Scenario: Turn begins while Voice is off
- **WHEN** a typed turn invokes `converse` after Voice is disabled
- **THEN** the app sends `voice_active=false`
- **AND** it does not infer Voice state from words in the message
