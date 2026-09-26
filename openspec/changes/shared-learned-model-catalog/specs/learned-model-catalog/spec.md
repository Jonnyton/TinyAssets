# Learned Model Catalog

## Purpose

Platform-wide verified model facts, contributed by successful calls and surfaced
newest-per-class per source kind, so new model availability reaches every user
with no release and no per-provider code.

## Requirements

### Requirement: The catalog carries no user data
The catalog SHALL store exactly three fields per row: source kind, model id, and
the time the id was first verified platform-wide. It SHALL NOT store a user id, a
universe id, a connection id, a prompt, a reply, a credential, or any count of how
many users verified an id. A repeat verification of a known id SHALL be a no-op.

#### Scenario: A row is recorded
- **WHEN** a model id is verified through a source and recorded
- **THEN** the stored row names only the source kind, the model id and the first-verified time
- **AND** no user id, universe id, prompt or credential appears anywhere in the store

#### Scenario: The same id is verified again by another user
- **WHEN** an id already in the catalog is verified again
- **THEN** the existing row is unchanged and nothing accumulates

### Requirement: Only verified success enters the catalog
A model id SHALL enter the catalog only from a call that succeeded through the
source. A refusal, a capacity hold, an unconfirmed transport outcome, and an
owner-declared id SHALL record nothing. Failing to record SHALL NOT fail the call
that succeeded.

#### Scenario: A turn succeeds
- **WHEN** a call completes through a source with a known model id
- **THEN** that id is recorded for the source's kind

#### Scenario: A turn is refused, held, or unconfirmed
- **WHEN** the call did not succeed
- **THEN** the catalog is unchanged

#### Scenario: The catalog cannot be written
- **WHEN** recording fails
- **THEN** the call that succeeded still returns its result

### Requirement: Class and newest are derived with no vendor knowledge
Model class SHALL be derived by removing version tokens from the model id, where a
version token is a run of digits, a dotted run of digits, or a date stamp. Every
other token, including a named suffix, SHALL be part of the class. Newest SHALL be
the highest version tuple, tie-broken by the earlier first-verified time. An id
whose shape cannot be parsed SHALL be its own class. Platform code SHALL contain no
vendor or model names.

#### Scenario: Two versions of one line
- **WHEN** two ids differ only in their numeric version tokens
- **THEN** they share a class and only the higher version is contributed

#### Scenario: A named suffix
- **WHEN** two ids share a stem but differ by a named suffix
- **THEN** they are different classes and both are contributed

#### Scenario: An unparseable id
- **WHEN** an id carries no recognisable version token
- **THEN** it is its own class and is always contributed

### Requirement: The catalog adds candidates and never removes a user's own
For each source kind on a universe's connections, the newest model of each class
SHALL be contributed to that universe's model options, unioned with the ids the
universe already had. A contributed row SHALL carry an availability basis
distinguishing it from this connection's own verified models, and SHALL grant no
access: serving still requires that universe's accepted model access. The
currently-saved model SHALL remain marked as current even when the union does not
contain it and even when it is not usable.

#### Scenario: A newer sibling is verified elsewhere
- **WHEN** the catalog learns a newer model in the same class as one a user already has
- **THEN** the user's own id remains on their list and the newer one is added

#### Scenario: A source that cannot enumerate
- **WHEN** a source cannot enumerate its own catalogue
- **THEN** its options include the catalog's newest-per-class for that source kind

#### Scenario: The saved model is unusable
- **WHEN** the saved default is absent from the union or is not usable
- **THEN** it is still shown as the current choice and is not offered as a fresh pick
