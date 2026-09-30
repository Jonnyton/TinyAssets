## ADDED Requirements

### Requirement: A seat SHALL be reclaimed on its holder's proven death, never while its holder is proven alive
A seat's holder SHALL be the process-liveness owner token of the process holding it. A seat whose holder is provably dead SHALL be reclaimed by the next acquisition without waiting for its lease to expire. A seat whose holder is provably alive SHALL NOT be reclaimed, even after its lease has expired. The lease expiry alone SHALL reclaim a seat only when its holder's liveness is unknown, such as a holder that never registered a liveness lock.

#### Scenario: A killed holder's seat returns before its lease ends
- **WHEN** a process holding a seat is killed
- **THEN** the next acquisition for that universe reclaims the seat immediately

#### Scenario: A live holder that missed refreshes keeps its seat
- **WHEN** a live holder's seat lease expires because its refresher stalled
- **THEN** the seat is not reclaimed and no second holder is admitted in its place
