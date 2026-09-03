## ADDED Requirements

### Requirement: Realtime voice authority is universe-scoped, compatible, and ephemeral
The voice capability check and session broker SHALL resolve only a compatible resource explicitly bound to the authenticated owner's universe. The initial OpenAI adapter SHALL recognize only that universe's deposited OpenAI API credential, use it only to create a short-lived client credential, and SHALL NOT expose, log, persist, or return the long-lived credential. A Codex/ChatGPT subscription binding SHALL NOT be reinterpreted as Realtime API authority unless OpenAI documents and TinyAssets implements that route.

#### Scenario: Compatible owner resource mints an ephemeral client secret
- **GIVEN** both host adapter gates are enabled and the authenticated owner's universe has a deposited OpenAI API credential
- **WHEN** the owner requests a voice session
- **THEN** the broker uses that credential server-side to request a scoped short-lived client secret
- **AND** the response contains no long-lived credential

#### Scenario: Ambient credential is present but compatible owner resource is absent
- **GIVEN** a process-global OpenAI credential exists but the authenticated owner's universe has no deposited OpenAI credential
- **WHEN** the owner requests a voice session
- **THEN** the capability is reported as locked and the broker fails with an actionable compatible-resource response before an OpenAI request
- **AND** it does not use the ambient credential or another universe's credential

#### Scenario: Universe has Codex subscription authority only
- **GIVEN** a universe is powered by its owner's Codex subscription and has no separately bound Realtime-compatible resource
- **WHEN** the app checks Voice capability
- **THEN** Voice is reported as locked because the public API does not document that subscription session as Realtime authorization
- **AND** TinyAssets does not request a new key, substitute a platform credential, or disturb the subscription writer

#### Scenario: Secret-bearing paths are non-observable
- **WHEN** credential minting succeeds or fails
- **THEN** application logs, traces, exceptions, and conversation history contain neither the long-lived key nor the short-lived client secret
- **AND** the HTTP response is marked not cacheable
