## MODIFIED Requirements

### Requirement: The shared app reports each turn's input method
The shared app SHALL derive the input method of each canonical founder turn from the path that submitted that specific message and SHALL pass `typed`, `spoken`, or `app_action` with the `converse` call without modifying the founder's authoritative message text.

#### Scenario: Composer turn is typed while Voice is active
- **GIVEN** Voice capture is active
- **WHEN** the founder submits a turn through the message composer
- **THEN** the app sends `input_method=typed`
- **AND** it does not substitute ambient Voice-session state for the turn's origin

#### Scenario: Browser speech turn is spoken
- **WHEN** browser speech recognition commits a founder utterance
- **THEN** the app sends `input_method=spoken`

#### Scenario: Realtime Voice turn is spoken
- **WHEN** the realtime Voice bridge commits its canonical `converse` tool call
- **THEN** the app sends `input_method=spoken`

#### Scenario: Request-rail turn reports its actual origin
- **WHEN** the founder types a request-rail reply
- **THEN** the app sends `input_method=typed`
- **WHEN** the founder selects an app action that creates a conversation line
- **THEN** the app sends `input_method=app_action`

#### Scenario: Input method survives a retry or queue
- **WHEN** an app turn is queued or retried
- **THEN** the eventual `converse` call carries the input method recorded at the original submission
- **AND** the app does not infer it from the message words or current Voice state
