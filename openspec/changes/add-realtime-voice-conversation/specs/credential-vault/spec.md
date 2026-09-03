## ADDED Requirements

### Requirement: Realtime voice credential use is owner-scoped, explicit, and ephemeral
The voice-session broker SHALL resolve only the authenticated universe owner's deposited OpenAI credential after the dedicated Realtime voice API allowance is enabled, SHALL use it only to create a short-lived client credential, and SHALL NOT expose, log, persist, or return the long-lived credential.

#### Scenario: Owner credential mints an ephemeral client secret
- **GIVEN** both voice allowances are enabled and the authenticated owner's universe has a deposited OpenAI credential
- **WHEN** the owner requests a voice session
- **THEN** the broker uses that credential server-side to request a scoped short-lived client secret
- **AND** the response contains no long-lived credential

#### Scenario: Ambient credential is present but owner credential is absent
- **GIVEN** a process-global OpenAI credential exists but the authenticated owner's universe has no deposited OpenAI credential
- **WHEN** the owner requests a voice session
- **THEN** the broker fails with an actionable missing-credential response before an OpenAI request
- **AND** it does not use the ambient credential or another universe's credential

#### Scenario: Secret-bearing paths are non-observable
- **WHEN** credential minting succeeds or fails
- **THEN** application logs, traces, exceptions, and conversation history contain neither the long-lived key nor the short-lived client secret
- **AND** the HTTP response is marked not cacheable
