## ADDED Requirements

### Requirement: A turn that recorded its own lesson does not pay for a second pass

When a founder turn has recorded what it was taught — settling its conversation's
learned cursor — `converse` SHALL return the reply with no further model
round-trip. When the cursor is NOT settled at turn end, the existing synchronous
extraction SHALL still run, so no lesson is ever lost. No turn SHALL become slower
than it was before this requirement.

#### Scenario: the settled turn returns immediately
- **WHEN** a founder turn records its lesson in-turn and its cursor is settled at turn end
- **THEN** `converse` returns the reply without any further model round-trip

#### Scenario: the unsettled turn keeps the guaranteed pass
- **WHEN** the cursor is still unsettled when the turn ends
- **THEN** the existing extraction runs synchronously, as before, and the lesson is persisted

#### Scenario: learning still never breaks a turn
- **WHEN** any part of the learning path fails, at any stage
- **THEN** the founder's reply is unaffected and the failure is logged, never raised

### Requirement: An unsettled learned-watermark is the record of work owed

Each conversation SHALL carry a durable cursor naming the last founder turn whose
lesson is settled. Pending lessons SHALL be derived as the founder turns after that
cursor, read from the retained turns verbatim. The cursor SHALL advance only when a
lesson has actually been recorded, so a crash or a failure leaves it unsettled —
the retry state — and never the reverse.

#### Scenario: the cursor advances only on a real write
- **WHEN** a lesson is recorded into the universe's brain
- **THEN** the cursor advances past that turn
- **WHEN** recording fails, is skipped, or the process dies first
- **THEN** the cursor is unchanged and that turn is still pending

#### Scenario: a burst of turns is one span, not one job each
- **WHEN** several founder turns arrive before any lesson is settled
- **THEN** they are pending as one span after the cursor, settled together

#### Scenario: existing conversations are not re-extracted
- **WHEN** the cursor is created for a conversation that already has history
- **THEN** it starts at the latest turn, so past turns are never re-extracted

### Requirement: The turn records its own lesson in-turn, at no extra cost

A founder turn SHALL be told whether it has yet recorded what it was taught, and
SHALL record it with the brain-write tool it already holds, inside the round-trips
it is already paying for. Telling it SHALL add no model call and SHALL grant no new
authority: the brain-write gate, the honesty floor and the "only clear, direct,
stable facts the founder actually gave me" rule are unchanged.

Recording SHALL NOT be deferred to a later turn, because a founder who never sends
another message would lose the fact.

#### Scenario: the turn is told what it has not recorded
- **WHEN** a founder turn is assembled for a conversation with an unsettled cursor
- **THEN** the turn is told the lesson is unrecorded and has the exchange available to it
- **AND** no extra model round-trip is made to tell it

#### Scenario: recording in-turn settles the cursor
- **WHEN** the turn writes the founder-taught fact to its brain
- **THEN** the cursor advances and nothing further is owed for that turn

#### Scenario: nothing waits for a turn that may never come
- **WHEN** the founder sends no further message after a turn
- **THEN** that turn's lesson is already recorded, or was persisted by the synchronous fallback before the turn ended

### Requirement: The deferred path, when it exists, re-derives its authority

DEFERRED to its own change (lead, 2026-09-26): this change ships the in-turn
recording plus the existing synchronous fallback, and stage 2 is designed against
the cursor-settle rate this produces. The requirement is stated here because it is
the constraint that change inherits, and because D1 is settled.

A cursor unsettled past its bound SHALL be settled by a deferred extraction that
runs outside any founder request. Its authority SHALL be RE-DERIVED at that moment
from durable ownership — owner, universe, serving binding and revision — under its
own named operation, and SHALL NOT come from a request lease that outlived its
request. A binding that has since been revoked, a changed home, or a deleted
universe SHALL fail the deferred work closed.

#### Scenario: a revoked binding stops the deferred work
- **WHEN** the deferred extraction reaches a universe whose serving binding was revoked, rebound, or whose home changed since the turn
- **THEN** it is refused and nothing is called on the owner's credential

#### Scenario: no lease outlives its request
- **WHEN** a founder request completes
- **THEN** its provider request lease is revoked as before, and no deferred work holds or depends on it

#### Scenario: the deferred path can only do this one thing
- **WHEN** the deferred extraction runs
- **THEN** it is pinned to the learning operation and cannot select another operation, mint authority for one, or reach a model outside the owner's own binding

### Requirement: The foreground turn keeps budget priority

The deferred extraction SHALL be refused while the universe has any in-flight
foreground provider reservation, and SHALL reserve budget only if a full foreground
turn's allowance still remains afterwards. It SHALL remain marked as a secondary
call, so its rate-limit refusal never writes the shared cooldown a founder's next
turn reads, and it SHALL never sleep.

#### Scenario: a turn in flight defers the deferred work
- **WHEN** the drain considers a universe with an in-flight foreground reservation
- **THEN** it does not reserve, does not call, and leaves the cursor for the next tick

#### Scenario: it cannot leave the next turn short
- **WHEN** reserving would drop the remaining allowance below one foreground turn
- **THEN** the deferred extraction is refused rather than reserved

#### Scenario: its refusal costs the founder nothing
- **WHEN** the deferred extraction is rate-limited or exhausted
- **THEN** the shared cooldown is untouched, nothing sleeps, and the cursor stays pending

### Requirement: One path for every account

The cursor, both stages, the bound and the budget floor SHALL be identical for
every account, plan, tier, provider, source and universe. The only per-account input
SHALL be the owner's own serving binding.

#### Scenario: no per-account variation
- **WHEN** the learning path runs for any universe on any source
- **THEN** the same stages, bound and floor apply, with no plan, tier or provider branch
