## ADDED Requirements

### Requirement: Public Goal read modes expose only public Goals
Every canonical public `read_graph` Goal mode SHALL expose only Goals whose visibility is exactly `public`: empty-query `target=goals` listing, non-empty ranked `target=goals` search, and exact `target=goal` lookup by ID. Every other or unrecognized visibility, including `private` and `deleted`, SHALL return no Goal ID or fields and no count contribution. Exact lookup of a non-public Goal SHALL return the same non-disclosing result as a missing Goal. This gate-independent requirement SHALL NOT invent per-principal private-Goal authority; any future owner-scoped read capability SHALL modify this requirement and its identity/authority evidence before exposing a private Goal.

#### Scenario: public Goal listing excludes every non-public visibility
- **WHEN** public, private, deleted, and unrecognized-visibility Goals are eligible for empty-query `target=goals`
- **THEN** only exactly `visibility=public` Goals enter rows or totals
- **AND** no filter or actor context can expose the non-public IDs or fields

#### Scenario: ranked Goal search excludes every non-public visibility
- **WHEN** public, private, deleted, and unrecognized-visibility Goals match one non-empty `target=goals` query
- **THEN** ranked results contain only exactly `visibility=public` Goals
- **AND** ranking, author, tags, query text, or actor context cannot expose non-public IDs or fields

#### Scenario: exact public Goal lookup is non-disclosing
- **WHEN** canonical public `read_graph target=goal` requests the ID of a private, deleted, unrecognized-visibility, or missing Goal
- **THEN** each case returns the same non-disclosing missing-result shape with no Goal ID or fields
- **AND** exact lookup grants no private-Goal read authority

### Requirement: Canonical Goal catalog reads are completely traversable
For this requirement, actor presentation context SHALL mean an authenticated principal or a server-derived anonymous requester partition that caller input cannot select.

The shared Goal surface SHALL expose deterministic public-catalog enumeration through canonical `read_graph target=goals` when `query` is empty. The exhaustive catalog SHALL be one public-only visibility partition identified as `goal-public-commons`; only Goals with `visibility=public` SHALL enter rows or `total_matches`, while every other or unrecognized value (including `private` and `deleted`) SHALL be treated as non-public, and this change SHALL NOT invent per-principal private-Goal read authority. The enumerator SHALL preserve the canonical author filter, SHALL treat every supplied normalized tag as an exact-match intersection rather than SQL wildcard input, and SHALL order by `(updated_at DESC, goal_id ASC)`. The internal Python `production_only` approximation SHALL remain outside this canonical exact-count contract. The existing smaller catalog-window default SHALL remain unchanged, public `limit` SHALL accept only the inclusive range 1 through 100, and an out-of-range value SHALL return zero Goals with `invalid_window_limit`. Strict rejection SHALL occur only in the canonical public catalog wrapper; the in-process Goal helper's absence of an upper clamp and the internal `production_only` overfetch `max(requested_limit * 10, 100)` SHALL remain unchanged.

The first window SHALL materialize an immutable, ordered, filter-specific snapshot from one transactional source view using an index that covers `(updated_at DESC, goal_id ASC)` and exact author/tag/public-visibility predicates. This behavioral contract SHALL remain storage-engine neutral; adopting a successor control plane requires its own accepted substrate gate. A bounded, versioned, opaque, unguessable cursor SHALL reference that snapshot and bind the normalized filters, `goal-public-commons` visibility partition, actor presentation context (authenticated principal or anonymous), ordering version, snapshot identifier, internal source marker, snapshot-digest key version, and next immutable manifest ordinal to process. It SHALL NOT reference a mutable server continuation pointer or merely the last emitted Goal. Every request SHALL process one fixed contiguous manifest-ordinal window; a Goal withheld by the current public-visibility check SHALL still advance its processed ordinal, and `next_cursor` SHALL name the next unprocessed ordinal. Snapshot deduplication SHALL NOT cross actor presentation contexts. The public `snapshot_revision` SHALL be a deterministic server-keyed digest over domain-separated typed encodings of stable Goal ID, public `updated_at`, manifest ordinal, normalized filters, ordering version, and actor-context partition. A caller without the dedicated snapshot-digest key SHALL NOT be able to compute or forge a valid digest. Author/tag/text payload, every other Goal field, and non-public rows SHALL NOT be directly encoded; an ordinary public Goal edit MAY indirectly change the digest only through its public `updated_at`, membership, or ordinal. The dedicated key SHALL be provisioned through the accepted credential-vault/control-plane secret path and SHALL NOT reuse an unrelated request-idempotency or identity key. Rotation SHALL retain each prior key version for at least the 30-minute maximum snapshot TTL and until no unexpired snapshot or cursor binds that version, so identical retries and quota continuity remain valid across rotation. Every successful window SHALL return the applied filters, `snapshot_revision`, `snapshot_captured_at`, `snapshot_expires_at`, per-window emitted `count`, per-window `withheld_count`, exact capture-time public-catalog `total_matches`, retained rows unprocessed after the window as `truncated_count`, `has_more`, nullable `next_cursor`, and `complete`. `complete` SHALL be true exactly when every retained row has been emitted or explicitly withheld, and `next_cursor` SHALL be non-empty exactly when unprocessed retained rows remain.

An identical first-window retry within the same actor presentation context, normalized filters, ordering version, and public manifest SHALL reuse the existing retained snapshot and initial cursor rather than allocate or charge another snapshot. Server-internal dedup lookup SHALL recognize that live manifest independently of which digest-key version is currently active and SHALL return the retained snapshot's original `snapshot_revision`, key-version-bound cursor, and quota identity. A non-public-only source mutation that leaves that manifest unchanged SHALL reuse the same live snapshot and SHALL NOT alter cursor validity, quota use, totals, or public revision evidence. Retrying an identical continuation cursor with unchanged current withdrawal inputs SHALL reproduce the same emitted Goals, withheld count, and `next_cursor` without advancing mutable server state or consuming quota; a Goal that is no longer exactly `visibility=public` SHALL instead be withheld without changing the cursor's processed ordinal range. This internal allocation SHALL remain semantically read-only and idempotent.

Snapshots SHALL remain available for at least 15 minutes and SHALL expire no later than 30 minutes after capture. One serialized manifest SHALL be capped at 64 MiB. Combined across the wiki and Goal snapshot services, each actor presentation context SHALL be limited to four concurrent snapshots, 256 MiB retained bytes, and six new snapshots per rolling minute. The combined wiki-and-Goal snapshot service SHALL be limited to 4,096 concurrent snapshots and 16 GiB retained snapshot bytes; anonymous contexts collectively SHALL use no more than 2,048 snapshots or 8 GiB, reserving the remaining 2,048 snapshots and 8 GiB for authenticated contexts when that reserved capacity is otherwise free. Anonymous actor contexts SHALL derive from trusted transport metadata rather than caller-supplied fields. A new-snapshot request exceeding any creation, class, count, or byte bound SHALL return zero Goals, `complete=false`, `snapshot_capacity_exceeded`, and bounded retry guidance; it SHALL NOT leave a partial snapshot. Existing valid continuations remain governed by their advertised expiry and withdrawal checks and SHALL continue at anonymous or global capacity.

Ordinary Goal mutations committed after capture SHALL NOT invalidate or reorder an in-progress traversal; callers continue over retained as-of rows. Immediately before emitting each retained row, however, the server SHALL re-check that current visibility is exactly `public`. A Goal changed to any other or unrecognized visibility SHALL emit no Goal fields and SHALL increment that window's `withheld_count`; capture-time `total_matches` SHALL not shrink. A future accepted moderation capability MAY extend this withdrawal predicate without weakening the exact-public allowlist. A malformed, unsupported, cross-filter, wrong-partition, wrong-actor-context, missing, or expired cursor SHALL return zero Goals, `complete=false`, and a structured restart instruction. A cursor SHALL NOT grant identity or Goal access. If a future authority change introduces per-principal Goal visibility, that change SHALL modify this requirement and cursor partition before exposing different catalogs.

`read_graph target=goals` with a non-empty query SHALL remain ranked/best-effort search, SHALL include only Goals with exactly `visibility=public`, SHALL explicitly report that it is not a completeness proof, and SHALL NOT issue a catalog cursor. Every other or unrecognized visibility SHALL fail closed in ranked search just as it does in empty-query catalog enumeration.

#### Scenario: first partial Goal window carries a continuation
- **WHEN** a filtered visible Goal catalog has more matches than its bounded result window
- **THEN** the response reports `has_more=true`, `complete=false`, and a non-empty `next_cursor`
- **AND** `total_matches` counts capture-time matching public-catalog Goals while `truncated_count` counts retained rows not yet processed

#### Scenario: terminal Goal window proves completion
- **WHEN** a valid continuation returns the final visible matching Goal window
- **THEN** the response reports `has_more=false`, `next_cursor=null`, `truncated_count=0`, and `complete=true`

#### Scenario: Goal window above the public cap fails closed
- **WHEN** a caller supplies `limit` outside the inclusive range 1 through 100
- **THEN** the response returns zero Goals with `invalid_window_limit`
- **AND** it does not allocate a snapshot or normalize the value into range

#### Scenario: identical Goal continuation replay is immutable
- **WHEN** a caller retries the same valid continuation cursor and one retained ordinal is no longer exactly `visibility=public`
- **THEN** both attempts return the same emitted Goals, `withheld_count`, and `next_cursor`
- **AND** the withheld ordinal is processed exactly once in traversal position without mutating a server-side pointer or consuming quota

#### Scenario: exact full final Goal window is complete
- **WHEN** the final Goal window contains exactly the requested limit and no visible match remains
- **THEN** the response reports `complete=true` rather than treating a full window as proof of truncation

#### Scenario: filters and global partition are bound to the Goal cursor
- **WHEN** a caller reuses a cursor with different author, tags, or a partition other than `goal-public-commons`
- **THEN** the server returns zero Goals, `complete=false`, and a structured restart error

#### Scenario: Goal mutation does not disturb a retained snapshot
- **WHEN** an ordinary non-withdrawal Goal mutation commits after a catalog snapshot is captured
- **THEN** the caller continues over the same retained ordered snapshot without reorder or restart
- **AND** the terminal receipt identifies the original `snapshot_revision` and does not claim to include later mutations

#### Scenario: post-capture Goal withdrawal is withheld immediately
- **WHEN** a retained Goal changes to any non-public or unrecognized visibility before its row is emitted
- **THEN** that window emits no fields for the Goal and increments `withheld_count`
- **AND** terminal `complete=true` means all capture-time rows were emitted or withheld

#### Scenario: Goal snapshot remains usable through the minimum lifetime
- **WHEN** a caller presents a valid continuation immediately before 15 minutes after `snapshot_captured_at`
- **THEN** the retained snapshot remains available and returns its ordinary deterministic window
- **AND** capacity pressure or key rotation cannot shorten that minimum lifetime

#### Scenario: expired Goal snapshot fails without partial results
- **WHEN** a caller continues after the retained Goal snapshot's advertised expiry
- **THEN** the server returns zero Goals, `complete=false`, and `cursor_expired`
- **AND** the error instructs the caller to begin a new catalog snapshot

#### Scenario: retained Goal catalog has no duplicates or gaps
- **WHEN** a caller follows every server-issued cursor across a retained filtered snapshot
- **THEN** each matching Goal ID appears exactly once
- **AND** capture-time `total_matches` equals combined unique emitted Goal IDs plus the sum of per-window `withheld_count`

#### Scenario: equal Goal update clocks remain stable across a page boundary
- **WHEN** multiple public Goals share the same `updated_at` and their `(updated_at DESC, goal_id ASC)` order crosses a retained-window boundary
- **THEN** continuation preserves ascending `goal_id` order within that equal-clock group
- **AND** no Goal duplicates, disappears, or changes position on identical replay

#### Scenario: Goal cursor cannot cross actor presentation context
- **WHEN** an authenticated principal or anonymous caller presents a cursor captured for a different actor context
- **THEN** the server returns zero Goals, `complete=false`, and a structured restart error
- **AND** this binding does not redefine the catalog's `goal-public-commons` visibility partition

#### Scenario: snapshot digest key rotation preserves live traversal
- **WHEN** the active snapshot-digest key rotates while an earlier-version retained Goal snapshot remains unexpired
- **THEN** its cursor continues to validate against the bound retained key version through the advertised snapshot expiry
- **AND** identical retry, snapshot reuse, and per-actor quota accounting remain unchanged

#### Scenario: adversarial Goal snapshot fan-out is bounded
- **WHEN** one actor or anonymous requester context varies filters to create snapshots beyond its rate, count, or retained-byte budget
- **THEN** excess creation requests return zero Goals and `snapshot_capacity_exceeded`
- **AND** global snapshot count, retained bytes, and expiry remain within the declared hard bounds

#### Scenario: anonymous Goal Sybil fan-out cannot consume authenticated reserve
- **WHEN** many anonymous requester contexts collectively reach the anonymous snapshot-count or byte sub-cap
- **THEN** further anonymous creation fails without a partial snapshot while existing continuations remain valid
- **AND** an authenticated first-window request can still use otherwise-free reserved authenticated capacity

#### Scenario: tags are exact all-tag predicates
- **WHEN** a caller supplies multiple tags containing SQL wildcard characters
- **THEN** a Goal matches only when every normalized tag is present as an exact tag value
- **AND** `%` and `_` are treated as ordinary tag characters rather than wildcard operators

#### Scenario: soft-deleted Goal remains absent from ordinary enumeration
- **WHEN** a Goal becomes soft-deleted before a new catalog scan
- **THEN** ordinary enumeration omits it and excludes it from `total_matches`
- **AND** no cursor value can make the deleted Goal visible

#### Scenario: private Goal is never part of the public catalog
- **WHEN** a Goal is marked `visibility=private` before public enumeration
- **THEN** its ID, fields, and contribution to `total_matches` are absent
- **AND** no author/tag filter, actor context, or cursor can make it enter `goal-public-commons`

#### Scenario: non-public-only activity does not consume public snapshot quota
- **WHEN** Goals with any non-public or unrecognized visibility mutate while an otherwise-identical public-catalog first-window snapshot remains live
- **THEN** a retry reuses the same public manifest digest, snapshot, totals, and initial cursor
- **AND** the internal source-marker change does not consume another quota unit or reveal hidden activity

#### Scenario: Goal search remains explicitly incomplete
- **WHEN** `read_graph target=goals` receives a non-empty query
- **THEN** the response identifies the result as ranked/best-effort and not an absence proof
- **AND** it does not return a catalog `next_cursor`

#### Scenario: ranked Goal search never returns non-public Goals
- **WHEN** public, private, deleted, and unrecognized-visibility Goals all match the same non-empty ranked query
- **THEN** `read_graph target=goals` returns only the exactly `visibility=public` matches
- **AND** no author, tag, query, actor context, or ranking score can expose the non-public Goal IDs or fields

#### Scenario: Goal pagination meets the owning concurrency proof
- **WHEN** the Goal surface alone serves a 10,000-Goal catalog to 1,000 concurrent connector clients distributed across 1,000 distinct actor/requester rate partitions for five minutes, comprising exactly 100 full traversals and 900 ordinary first-or-continuation reads while 20 relevant mutations commit per second
- **THEN** retained snapshots have no duplicate or omitted Goal IDs and zero false-complete receipts
- **AND** cold snapshot creation plus its first window remains below two seconds at p99, continuation windows remain below 500 milliseconds at p99, and at least 99 of the 100 full traversals finish within five minutes
- **AND** an implementation that misses the bound optimizes or materializes the shared retained-snapshot projection rather than weakening `complete`
