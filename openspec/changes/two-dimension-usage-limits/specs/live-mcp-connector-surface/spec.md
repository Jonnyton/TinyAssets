# live-mcp-connector-surface (delta)

## ADDED Requirements

### Requirement: read_graph reports the two usage numbers, and converse reports a waiting turn

`read_graph` SHALL report, for the universe it reads, the tier's seat count,
how many seats are running, how many callers are waiting, and the universe's
accounted storage against its tier quota — or an explicit unmeasured marker
where the footprint could not be measured. `converse` SHALL, when its turn
cannot obtain a seat within the bounded wait, reply with the waiting state
naming the number of seats running and carrying the inline upgrade link, and
SHALL keep the turn's queue position so its real reply arrives when a seat
frees. Neither surface SHALL report a per-hour or per-day usage notice, a
capacity-returns time, or a rate-limit reason, because none exists. A universe
on the highest tier SHALL receive no upgrade link. The seat and storage figures
SHALL be readable only by a caller already authorized to read that universe.

#### Scenario: read_graph shows seats and storage
- **WHEN** an authorized owner reads a universe with seats held and work waiting
- **THEN** the response reports seats running, seats total, waiters, and storage used against the quota

#### Scenario: A waiting turn answers instead of hanging
- **WHEN** a chat turn cannot obtain a seat within the bounded wait
- **THEN** `converse` replies with the number of seats running and an inline upgrade link, and the turn's real reply follows when a seat frees

#### Scenario: The removed meters are gone from every surface
- **WHEN** any connector surface reports usage
- **THEN** no per-hour write or total count, no per-day run count, no outbound dispatch or byte window, and no capacity-returns time appears

#### Scenario: Usage is private to the universe
- **WHEN** an unauthenticated or unauthorized caller reads a universe
- **THEN** no seat occupancy or storage figure is disclosed
