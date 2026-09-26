## ADDED Requirements

### Requirement: The founder's reply never waits on learning

`converse` SHALL return the reply as soon as the writer turn produces it. No
learning extraction, persistence or bookkeeping call SHALL run between the reply
existing and `converse` returning it, because the HTTP response is the delivery and
anything before it is the founder's wall clock.

#### Scenario: a served turn makes no bookkeeping round-trip
- **WHEN** a founder turn completes its writer call, with or without tool steps
- **THEN** `converse` returns the reply without any further model round-trip
- **AND** the number of model round-trips for a turn with one tool step is exactly two

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

### Requirement: The turn records its own lesson first, at no extra cost

A founder turn whose conversation has an unsettled cursor SHALL be told so, and
SHALL be able to record the lesson with the brain-write tool it already holds,
inside the turn it is already paying for. This path SHALL NOT add a model call.

#### Scenario: the turn is told what it has not recorded
- **WHEN** a founder turn is assembled for a conversation with an unsettled cursor
- **THEN** the turn is told a lesson from the earlier turn is unrecorded, and that earlier exchange is available to it
- **AND** no extra model round-trip is made to tell it

#### Scenario: recording in-turn settles the cursor
- **WHEN** the turn writes the founder-taught fact to its brain
- **THEN** the cursor advances and nothing further is owed for that span

### Requirement: The deferred fallback runs off the founder's clock, with re-derived authority

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
