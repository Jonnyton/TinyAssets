## ADDED Requirements

### Requirement: Authorized terminal failures persist atomically
The platform SHALL retain an admitted owner's original message verbatim and a
typed safe platform-failure notice atomically in the existing principal-scoped
conversation store, without creating a successful answering execution receipt.

#### Scenario: Failed provider turn followed by another successful turn
- **WHEN** an admitted turn ends in an observed provider failure and storage succeeds
- **THEN** both original message and platform notice survive refresh and later messages
- **AND** the next authorized model can read the notice as untrusted conversation history
- **AND** no answering-model receipt is attributed to that notice

#### Scenario: Unowned or unauthenticated request
- **WHEN** authentication or owner/interlocutor admission fails
- **THEN** no conversation pair is persisted by this failure-history path

#### Scenario: Identical requests are distinct
- **WHEN** the owner explicitly sends the same message twice
- **THEN** failure persistence does not collapse them by text equality

### Requirement: Failure history contains only bounded safe diagnostics
The platform SHALL use a versioned allowlisted failure code and platform-authored
notice rather than raw provider text, exception strings, attempts or credentials.

#### Scenario: Unknown failure or native sign-in clue
- **WHEN** evidence does not establish a specific cause or only suggests sign-in trouble
- **THEN** the retained notice expresses that uncertainty without inventing a diagnosis
- **AND** it does not claim that the turn performed no actions

#### Scenario: Exception contains a secret-like sentinel
- **WHEN** a failing provider includes private payload text in its exception or attempts
- **THEN** that text does not enter durable failure metadata or the platform notice

### Requirement: Readers preserve type and principal isolation
The platform SHALL expose retained failure notices through existing authorized
history, lossless retrieval and agent-memory readers without treating them as
owner instructions, consent or successful model replies.

#### Scenario: Shared and automation context readers
- **WHEN** an authorized shared-self or owner automation reads conversation context
- **THEN** platform notices retain their speaker label and untrusted status
- **AND** conversation rows are scoped to the persisted owner principal, not an arbitrary session

#### Scenario: Two principals access conversation history
- **WHEN** each owner reads conversation state
- **THEN** each sees only the conversation rows authorized for their own principal and universe

#### Scenario: Legacy or corrupt optional metadata
- **WHEN** a read-only caller opens a legacy store or invalid failure metadata
- **THEN** no schema mutation occurs and legacy text remains readable
- **AND** platform text is not labelled as owner speech or an answering-model receipt

### Requirement: Persistence and retry state remain honest
The platform SHALL distinguish saved terminal failure, unsaved failure and
unknown transport outcome, and SHALL never automatically replay a failed turn.

#### Scenario: Failure write cannot complete
- **WHEN** a failure-pair write fails
- **THEN** no partial pair is committed and the owner receives an unsaved-history indication
- **AND** the original failure remains usable with explicit recovery

#### Scenario: Optional metadata column unavailable
- **WHEN** a writable legacy store cannot add the optional failure metadata column
- **THEN** the atomic pair can retain fixed safe notice text labelled by speaker platform
- **AND** no structured metadata is falsely reported as persisted

#### Scenario: Refresh after saved failure
- **WHEN** the owner refreshes after a saved terminal failure
- **THEN** the original message and a platform-labelled notice render without duplicate owner speech
- **AND** retry requires an explicit user action and warns that prior side effects are not ruled out

#### Scenario: Original request is not fully loaded
- **WHEN** the adjacent original request is missing or truncated in the history peek
- **THEN** the app does not resend guessed or partial text and requires the full original first

#### Scenario: Existing retention or deletion applies
- **WHEN** existing conversation retention or authorized universe/account deletion runs
- **THEN** failure rows and metadata follow the same data boundary as ordinary history
- **AND** the feature introduces no separate indefinite copy
