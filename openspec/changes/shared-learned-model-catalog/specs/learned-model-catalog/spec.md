# Public Model Lists

## Purpose

Let a newly released model reach every user of a source kind with no release and no
per-provider code, while a model id a user typed themselves never leaves them.

## Requirements

### Requirement: A typed model id is personal forever
A model id an owner supplied and successfully used SHALL be recorded for that owner and
SHALL remain available on that owner's own candidate list. It SHALL NOT be shared with
any other user, published, aggregated, or counted across owners by any mechanism. Two
universes of the same owner SHALL be one owner. The record SHALL be classified as that
owner's data and removed with their account.

#### Scenario: An account-bearing selector
- **WHEN** an owner uses a model selector that embeds their own account or deployment
- **THEN** it stays on their own list however often it is used
- **AND** no other user can see it, because no mechanism exists to share it

#### Scenario: The id stops being declared
- **WHEN** an owner's accepted model access no longer names an id that previously worked
- **THEN** it is still offered on their own list, marked as their own history

### Requirement: Sharing is a reviewed list, per source kind
For a source kind whose sources cannot enumerate their own models, the platform SHALL
read candidate ids from a tracked file per source kind. The file SHALL hold only the
source kind and a sorted, duplicate-free list of well-formed model identifiers, and no
user, universe, credential, URL or price. A malformed file SHALL be refused rather than
read as empty. Additions SHALL arrive by ordinary pull request with no automatic merge
path and no additional authority; a check SHALL refuse a malformed file in CI.

#### Scenario: A newly released model
- **WHEN** a pull request adding its id to the source kind's list is merged
- **THEN** every universe on that source kind offers it on the next read, with no release

#### Scenario: A malformed list
- **WHEN** a list file is invalid JSON, unsorted, duplicated, or holds a bad identifier
- **THEN** the read raises rather than silently offering fewer models
- **AND** the CI check names the file and the reason

#### Scenario: A source that lists its own models
- **WHEN** a source can call its provider's list endpoint
- **THEN** its ids arrive through discovery and need no entry in any file

### Requirement: A listed id is evidence, never permission
A candidate contributed by a public list or by an owner's own history SHALL NOT be an
admitted candidate and SHALL NOT enter the routing order until that universe's accepted
model access includes it. Each SHALL carry an availability basis distinguishing it from
the source's own verified models, and a reason stating that access is required. Only the
newest model of each class SHALL be offered from a list, derived from the identifier's
own shape with no vendor or model names in platform code.

#### Scenario: Before the grant
- **WHEN** a listed id is not in the universe's accepted model access
- **THEN** it is visible, not admitted, carries a needs-access reason, and is absent
  from the routing order

#### Scenario: After the grant
- **WHEN** the owner grants access to that id
- **THEN** it becomes an admitted candidate and a turn can run on it

#### Scenario: Two versions of one line are listed
- **WHEN** a list holds both an older and a newer id of the same class
- **THEN** only the newer is offered, and the older remains in the file
