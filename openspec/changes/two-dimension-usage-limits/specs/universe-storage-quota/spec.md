# universe-storage-quota (delta)

## ADDED Requirements

### Requirement: A universe's cloud footprint is accounted as measured bytes plus bytes admitted since

The platform SHALL account one number per universe — the total bytes it
occupies in the cloud — as the logical size of every regular file under that
universe's own directory, EXCLUDING bytes attributed to scratch leases, which
belong to the shared pool and SHALL be charged to no universe. The accounted
value SHALL be the sum of a cached full measurement and a per-universe ledger
of bytes admitted since that measurement was taken, so that many small writes
between measurements cannot evade the quota. The pending ledger SHALL be reset
transactionally with the measurement that supersedes it, so a write concurrent
with a remeasurement is counted once and never dropped. Accounting SHALL be
keyed on `universe_id` alone; no universe's footprint SHALL be derived from, or
charged to, another's.

#### Scenario: Many small writes cannot slip the quota between measurements
- **WHEN** a universe near its quota performs many small writes without a remeasurement occurring
- **THEN** their bytes accumulate in the pending ledger and the quota is reached

#### Scenario: Scratch is not charged to the universe
- **WHEN** a run checks out a large repository into a scratch lease
- **THEN** those bytes are not counted against the universe's storage quota

#### Scenario: A remeasurement does not lose a concurrent write
- **WHEN** a write is admitted while a remeasurement is being committed
- **THEN** the universe's accounted total includes that write exactly once

### Requirement: At the quota new writes are refused with a visible, actionable failure, and reads never break

A byte-adding write SHALL be refused once the universe's accounted footprint
has reached its tier's storage quota. The refusal SHALL be structured and
visible to the owner, naming the bytes used, the quota, how to free space, and
an inline clickable upgrade link — the same wording and link used for a seat
wait, and absent for an account already on the highest tier. No read, list,
status or delete path SHALL consult the quota, so a full universe remains
fully readable and can be emptied. A quota refusal SHALL be distinguishable
from an unmeasurable footprint and SHALL NOT be reported as one.

#### Scenario: A write at the quota is refused with the numbers and a link
- **WHEN** a universe at its storage quota attempts a byte-adding write
- **THEN** the write is refused with a message naming bytes used, the quota, how to free space, and an inline upgrade link

#### Scenario: A full universe still reads
- **WHEN** a universe is at its storage quota
- **THEN** reading its graph, pages, runs and status all succeed unaffected

#### Scenario: A full universe can be emptied
- **WHEN** an owner deletes run outputs or workspaces from a universe at its quota
- **THEN** the deletions succeed and subsequent writes are admitted

### Requirement: An unmeasurable footprint admits work loudly rather than refusing it

A failed footprint measurement SHALL fall back to the last good measurement plus the pending ledger, and where there has never been a good measurement the write SHALL be admitted, the failure SHALL be logged loudly, and the owner's usage surface SHALL report the footprint as unmeasured rather than reporting a number it does not have. A measurement failure SHALL NEVER be presented as a quota refusal, and a partial or bounded scan SHALL NEVER be presented as a total.

#### Scenario: A measurement failure does not break a working universe
- **WHEN** the footprint measurement raises and no prior measurement exists
- **THEN** the write is admitted, the failure is logged, and the owner's usage surface says the footprint is unmeasured

#### Scenario: An unmeasured footprint is not a quota story
- **WHEN** the footprint cannot be measured
- **THEN** no surface reports a storage quota refusal or a fabricated used-bytes figure

### Requirement: Tier values are defined in exactly one place

The seat count, the interactive reserve and the storage quota for each account tier SHALL be defined in a single module, keyed by the tier strings the subscription store already owns. An unrecognized tier SHALL resolve to the lowest tier and log loudly; it SHALL NEVER resolve to "no limit". The free tier SHALL have both a smaller storage quota and fewer seats than a paid tier. The free tier's seat count SHALL be large enough that a four-agent graph completes by queueing without an upgrade, and that the interactive reserve leaves more than one background seat.

#### Scenario: An unknown tier is the most restrictive, not unlimited
- **WHEN** a universe's stored tier string is not recognized
- **THEN** the free tier's seats and quota apply and the mismatch is logged

#### Scenario: Both test accounts work on free
- **WHEN** a free universe runs a four-agent village, chats while it runs, and writes its outputs within the free quota
- **THEN** every surface works and nothing requires an upgrade
