## ADDED Requirements

### Requirement: A selected governed consumer uses one canonical conversation path
The canonical turn path SHALL retain its authenticated principal, home,
interlocutor policy, receiver-scoped conversation history, current model
preferences and execution receipts when an explicitly installed governed
consumer handles the turn. The default persona/writer path SHALL remain the
default when no handler is selected; a selected handler SHALL NOT also run that
default writer or its cognitive/learning pipeline behind the user's back.

#### Scenario: A custom graph handles an ordinary app or connector message
- **WHEN** a founder sends a message with a valid selected Branch-backed handler
- **THEN** the trusted shell admits that immutable handler under the receiver's current execution authority
- **AND** it renders one terminal canonical reply selected by the adapter's declared output contract
- **AND** history and current input method remain associated with the same receiver conversation

#### Scenario: A user changes model for the current turn
- **WHEN** the user chooses an authorized model or ordered fallback policy for that turn
- **THEN** writer calls in the selected handler respect that current choice and ordinary eligibility checks
- **AND** the app reports the actual executing provider/model, not the creator's suggested default

#### Scenario: A slow or cancelled custom turn has not completed
- **WHEN** the underlying run is pending, running, cancelled, interrupted or uncertain
- **THEN** the shell exposes that run's actual progress/outcome through existing turn/run evidence
- **AND** it neither fabricates a terminal reply nor launches a replacement writer automatically
- **AND** cancellation uses the existing governed run control rather than deleting private state

#### Scenario: A turn response is lost or an installation changes during execution
- **WHEN** an admitted custom turn already has a run identity and a client reconnects, or the installation revision subsequently changes
- **THEN** observation resolves that existing attempt and selection revision
- **AND** automatic transport recovery does not admit a duplicate graph or append a second canonical reply
- **AND** an explicit new user send remains a distinct request, not falsely advertised as exactly-once replay

#### Scenario: A handler tries to recursively become the same conversation writer
- **WHEN** descendant work re-enters the current canonical handler for the same admitted turn
- **THEN** the trusted boundary rejects the recursive writer admission using run/turn ancestry
- **AND** ordinary separately authorized graph work remains governed by existing rules

### Requirement: Canonical custom requests reserve one existing run
Custom-consumer turns SHALL require the versioned keyed request object and SHALL
atomically bind owner/universe/session-scoped stable caller intent and captured
installation/context to one existing runs-database run. They SHALL reuse the
common run-owned start/dispatch mechanism, not add a conversation execution queue,
launch claim or provider authority. Status SHALL remain owner-scoped and truthful.

#### Scenario: Transport reconnect follows changed history and saved defaults
- **WHEN** the same scoped key and original caller request return after history or saved model defaults changed
- **THEN** the original admission and run are returned using their captured server context
- **AND** current history/defaults are not recomputed into replay conflict detection
- **AND** explicitly changed message, model choice or installation intent conflicts without execution

#### Scenario: Custom request protocol is absent or races with installation
- **WHEN** a selected custom handler receives no keyed request object, or a new keyed request names a stale installation revision
- **THEN** it refuses before either writer executes and reports the protocol or selection prerequisite
- **AND** it does not silently fall back to unkeyed default chat
- **AND** unkeyed default chat remains unchanged when no custom handler is selected

#### Scenario: A repeated request follows handler disable
- **WHEN** an existing admitted key is observed after its installation is disabled
- **THEN** current owner/home authorization precedes lookup and the original run remains observable
- **AND** the request neither changes its selected definition nor starts another run

### Requirement: Terminal history is a mandatory idempotent projection
A custom turn's immutable terminal envelope SHALL be frozen from its admitted run
and projected as one founder/reply or founder/platform-notice pair. A durable
per-admission projection record SHALL be committed atomically with that pair in
the existing conversation database. Reconciliation SHALL never rerun effects.

#### Scenario: Owner observes unknown or ambiguous admitted execution
- **WHEN** the owner reads a nonterminal custom turn with an unknown, legacy or invalid origin, or a queued run carrying either durable start-marker component
- **THEN** the common metadata-only admission classifier exposes held state, phase, `automatic_replay=false` and whether actions may have occurred without changing persisted run status
- **AND** unavailable origin reports `origin_unavailable` and queued started work reports `recovery_required`, not proven healthy waiting work
- **AND** terminal history projection retains its existing guarded repair; observation never loads execution input bodies or dispatches effects

#### Scenario: Crash occurs between conversation commit and runs projection flag
- **WHEN** the terminal pair exists but the admission has not recorded its projection completion
- **THEN** repair finds the matching projection digest and original row numbers
- **AND** it repairs only the admission flag without adding a second pair or provider call

#### Scenario: Pair storage fails or the terminal result is uncertain
- **WHEN** projection cannot commit or the run lacks a validated terminal output
- **THEN** status reports held/pending and no successful canonical reply is fabricated
- **AND** trusted recovery and the same run identity remain available

#### Scenario: The terminal callback is lost before history projection
- **WHEN** the exact run completed but its callback did not project the canonical pair
- **THEN** ordinary owner-authorized turn status converges that same terminal projection idempotently
- **AND** no provider invocation, execution dispatch or second history pair occurs

#### Scenario: Detailed history expires
- **WHEN** ordinary retention removes old conversation text or terminal details
- **THEN** durable scoped admission/projection identity prevents replay or reappend
- **AND** an expired observation reports expired rather than rebuilding or rerunning the turn
