# universe-seats (delta)

## ADDED Requirements

### Requirement: A seat is one in-flight agent call, and the tier sets how many a universe holds at once

The platform SHALL bound how many agent calls one universe executes
concurrently by a per-universe count of **seats** taken from its account tier,
and SHALL hold one seat for the whole of each agent call rather than for each
provider attempt within it. Everything that runs a model SHALL hold a seat: a
`converse` chat turn, an agent node inside a graph run, an automation run, an
`event` wake, a `once` wake, and an `app_event` wake. The seat bound SHALL be
per universe and SHALL be enforced by a predicate keyed on `universe_id`, so no
universe's occupancy can consume or reveal another's. Seats SHALL NOT replace or
duplicate the host-wide provider-subprocess bound
(`tinyassets.provider_admission`), which is a memory bound on shared hardware
and SHALL continue to apply underneath the seat layer. Seats SHALL NOT bound
the size, depth or breadth of what a user builds.

#### Scenario: Four agents on a three-seat account
- **WHEN** an owner on a tier with 3 seats starts a graph with 4 agent nodes
- **THEN** 2 run concurrently (the background ceiling), the other 2 wait for a seat, and all 4 complete

#### Scenario: Seats are per universe
- **WHEN** one universe holds every seat its tier allows
- **THEN** another universe's agent call acquires a seat immediately and is not affected

#### Scenario: One agent call is one seat, whatever it costs in provider attempts
- **WHEN** an agent call falls back across sources and retries, making several provider attempts
- **THEN** it holds exactly one seat from start to finish

### Requirement: Over the limit, work queues longest-owed-first and is never refused or dropped

An agent call that finds no seat available SHALL be enqueued and SHALL start
when a seat frees. It SHALL NOT be refused and SHALL NOT be dropped. The queue
SHALL be ordered by priority class and then by a monotone ticket, so that among
equal-priority waiters the longest-owed starts first. A caller that finds a
seat free while another waiter is already owed one SHALL join the queue behind
that waiter rather than take the seat.

#### Scenario: Queue order is longest-owed first
- **WHEN** three background agent calls wait for one seat, enqueued in order A, B, C
- **THEN** they start in the order A, B, C as seats free

#### Scenario: An arriving call does not overtake an owed waiter
- **WHEN** a seat frees while a waiter is already enqueued, and a new call of the same class arrives in the same instant
- **THEN** the enqueued waiter takes the seat and the new call is enqueued behind it

#### Scenario: Queued work is not lost
- **WHEN** a wake, automation run or agent node is enqueued for a seat
- **THEN** it runs once a seat frees, and no path reports it as refused, rate-limited or skipped for want of a seat

### Requirement: Background work can never take the last seat, so the owner's chat is never blocked by it

Waiters SHALL be classified `interactive` (a chat turn) or `background`
(everything else). Background work SHALL occupy at most `seats - interactive_reserve`
seats; interactive work MAY occupy all `seats`. An interactive waiter SHALL
never be ordered behind a background waiter, whatever their tickets. The
fairness rule SHALL be documented where the tier values are defined.

#### Scenario: A background runaway cannot starve the chat
- **WHEN** two automations wake each other continuously for a sustained period on a universe whose every background seat is occupied
- **THEN** concurrent seat holders never exceed the background ceiling, and an interactive chat turn arriving at any point acquires a seat within the bounded wait

#### Scenario: Interactive work jumps the background queue
- **WHEN** background waiters are already enqueued and a chat turn asks for a seat
- **THEN** the chat turn is ordered ahead of every background waiter

### Requirement: A blocking nested agent call inherits its parent's seat

An agent call made while its caller is BLOCKED waiting for it SHALL re-enter
the caller's seat rather than take a second one, tracked by a depth count on
the seat, and the seat SHALL be released when the outermost holder releases it.
A non-blocking (asynchronous, or by-version) invocation SHALL take its own
seat, because its parent continues to execute. A chain of blocking nested agent
calls SHALL NOT be able to deadlock against its own universe's seat limit.

#### Scenario: A two-deep blocking chain runs on one seat
- **WHEN** an agent node blocking-invokes a sub-branch containing another agent node, on a universe with one background seat
- **THEN** both execute and neither waits for the other's seat

#### Scenario: An async invoke pays its own seat
- **WHEN** an agent node invokes a sub-branch asynchronously and continues
- **THEN** the sub-branch's agent call acquires its own seat

### Requirement: A seat is a lease, released on every terminal path and reaped when it expires

Seats SHALL be recorded in a durable store under the canonical data-dir
resolver, never in process memory alone, because engine MCP runs in a child
process and a deploy recreates the container. A seat SHALL be released on
success, on failure, on cancellation and on timeout. A seat SHALL carry an
absolute expiry, SHALL be refreshed on a cadence shorter than that expiry while
its work is live, and SHALL be reaped by any subsequent acquisition once it has
expired, so a crashed or restarted holder cannot strand capacity. Reaping SHALL
happen on the acquisition path and SHALL NOT depend on a timer or background
sweeper being alive. A seat store that is a symlink or resolves outside its
data directory SHALL be refused rather than trusted, because a tampered seat
store is a cross-universe concurrency escape. A live long-running agent call
SHALL keep its seat for as long as it runs; the lease SHALL bound only how long
a DEAD holder's seat survives.

#### Scenario: A crashed holder's seat is reclaimed
- **WHEN** a process holding a seat dies without releasing it
- **THEN** the next acquisition for that universe reaps the expired seat and admits waiting work

#### Scenario: Seats survive a deploy restart correctly
- **WHEN** the container is recreated while seats were held
- **THEN** the first acquisition after restart reaps the stale rows and the seat count reflects only live work

#### Scenario: A long run keeps its seat
- **WHEN** an agent call runs for many multiples of the lease period while refreshing it
- **THEN** its seat is never reaped and no second holder is admitted in its place

#### Scenario: Every terminal path releases
- **WHEN** an agent call ends in success, in failure, by cancellation, or by timeout
- **THEN** its seat is released immediately and the next waiter starts

### Requirement: The per-agent lease is resolved before a seat is requested

A per-agent overlap fence SHALL be resolved by the automation's own overlap policy BEFORE the run joins the seat queue, so a run its own policy would skip does not occupy a queue position it will abandon. The fence is the existing per-agent lease, which keeps one automation's runs from overlapping themselves; the seat layer sits above it and neither replaces it.

#### Scenario: A skip-policy automation does not hold a queue position
- **WHEN** an automation whose overlap policy is `skip` becomes due while its previous run is still going, and the universe's seats are full
- **THEN** it is skipped by its overlap policy without ever entering the seat queue

### Requirement: The waiting state is visible to the owner with an inline upgrade link

Whenever work waits for a seat, the owner SHALL be able to see that it is
waiting and how many seats are running, on the chat turn's own reply, in
`read_graph`, and in the app's status for queued runs and wakes. The waiting
message SHALL name the number running and SHALL contain a clickable upgrade
link inline within the message itself; it SHALL NOT be presented as a separate
banner, button, card or modal. The link SHALL point at an existing route that
opens the deployment's real upgrade flow; no new or invented URL SHALL be used.
An account already on the highest tier SHALL see the fact without an upgrade
link. The prompt SHALL be informative and SHALL NOT block: the work still runs
when a seat frees.

#### Scenario: A waiting chat turn says so rather than hanging
- **WHEN** a chat turn cannot get a seat within the bounded wait
- **THEN** the owner receives a message naming the number of seats running with an inline upgrade link, the turn keeps its queue position, and its reply arrives when the seat frees

#### Scenario: The upgrade link resolves to the real upgrade flow
- **WHEN** the waiting message's upgrade link is followed
- **THEN** it resolves to an existing served route which opens the same checkout flow as the app's own upgrade control

#### Scenario: The top tier is not asked to upgrade
- **WHEN** a universe on the highest tier waits for a seat
- **THEN** the message names the waiting state and carries no upgrade link

#### Scenario: read_graph shows the queue
- **WHEN** an owner reads a universe with seats held and work waiting
- **THEN** the response reports the tier's seat count, how many are running, and how many are waiting
