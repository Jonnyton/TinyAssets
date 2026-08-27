## MODIFIED Requirements

### Requirement: Default discovery scope separates commons knowledge from coordination history
Wiki search and changed-since feeds SHALL trim scope and resolve an omitted, empty, or whitespace-only value to `discovery`; an exact-read ambient relevance feed SHALL instead resolve that unset scope to the source page's audience class. The core handler and canonical public `read_page` SHALL accept only `discovery`, `coordination`, or `all`; any other value SHALL return a structured error naming those values and no page results. Every search, changed-since, and exact-read response with an ambient feed SHALL report the applied scope, and an omitted scope whose audience filtering removes one or more candidates that would otherwise have entered the result set SHALL include a non-fatal scope note explaining intentional coordination/all access. Invalid-scope errors SHALL NOT claim an applied scope, and unchanged list responses SHALL remain unscoped.

Frontmatter `audience: discovery|coordination` SHALL be authoritative. An `audience` key that is absent, empty, or whitespace-only SHALL be treated as unset. A page with an unset audience SHALL classify as coordination when its category is `notes`, `plans`, `bugs`, `feature-requests`, `design-proposals`, or `patch-requests`, and SHALL classify as discovery otherwise, including custom categories and pages with no category component. The audience value SHALL be compared after trimming surrounding whitespace and casefolding; a set value that is still neither `discovery` nor `coordination` SHALL classify as coordination and SHALL NOT fall back to a discovery category.

Audience scope SHALL remain a relevance boundary, not access control. The existing universe ACL gate and page-listing visibility requirements SHALL be evaluated before audience and category filtering, and `all` SHALL NOT bypass them. Exact page-body reads SHALL remain addressable and unfiltered by audience; list behavior SHALL remain unchanged; no page SHALL be moved, rewritten, deleted, or migrated.

#### Scenario: default onboarding search excludes coordination history
- **WHEN** a caller searches a mixed visible corpus without supplying scope
- **THEN** the response contains a non-empty discovery result set
- **AND** untagged notes, plans, bugs, feature requests, design proposals, and patch requests are absent

#### Scenario: changed-since defaults to discovery
- **WHEN** a caller requests changed pages from a mixed visible corpus without supplying scope
- **THEN** the response reports applied scope `discovery`
- **AND** contains discovery-classified results only

#### Scenario: explicit coordination returns preserved history
- **WHEN** a canonical public or in-process caller searches with `scope=coordination`
- **THEN** the response contains coordination-classified results at their unchanged paths
- **AND** excludes discovery-classified results

#### Scenario: explicit all returns both audience classes
- **WHEN** a canonical public or in-process caller searches with `scope=all`
- **THEN** the response contains both discovery and coordination results that pass existing authority checks

#### Scenario: invalid scope fails without results
- **WHEN** a caller supplies a scope other than discovery, coordination, or all
- **THEN** the handler returns a structured error naming all three valid scopes
- **AND** returns no page results

#### Scenario: explicit discovery metadata overrides a coordination category
- **WHEN** a page under `pages/plans/` declares `audience: discovery`
- **THEN** the page is eligible for default discovery retrieval

#### Scenario: explicit coordination metadata overrides a discovery category
- **WHEN** a page under `pages/workflows/` declares `audience: coordination`
- **THEN** the page is excluded from default discovery retrieval

#### Scenario: unrecognized audience fails toward coordination
- **WHEN** a page in a discovery category declares a non-empty unsupported audience value
- **THEN** the page classifies as coordination without falling back to its category

#### Scenario: audience is trimmed and case-insensitive
- **WHEN** a page under `pages/plans/` declares a padded, mixed-case `audience: Discovery `
- **THEN** it normalizes to `discovery` and is eligible for default discovery retrieval

#### Scenario: custom and category-less pages default to discovery
- **WHEN** a page with no audience lives in a custom category or directly under the pages or drafts root
- **THEN** it classifies as discovery

#### Scenario: exact coordination read keeps coordination recommendations
- **WHEN** a caller exactly reads a coordination-classified page without supplying scope
- **THEN** the requested page body is returned unchanged
- **AND** its ambient feed applies coordination scope and may return visible coordination siblings

#### Scenario: exact discovery read excludes coordination recommendations
- **WHEN** a caller exactly reads a discovery-classified page without supplying scope
- **THEN** the requested page body is returned unchanged
- **AND** its ambient feed applies discovery scope and excludes coordination siblings

#### Scenario: unrecognized source audience drives coordination ambient scope
- **WHEN** a caller exactly reads a source page with a set but unrecognized audience value and omits scope
- **THEN** the requested page body is returned unchanged
- **AND** its ambient feed applies coordination scope rather than falling back to the source category

#### Scenario: authority denial wins under every audience scope
- **WHEN** an existing universe ACL or page-listing visibility rule denies an ambient, search, or feed candidate
- **THEN** discovery, coordination, and all omit its path, title, excerpt, body, and metadata before relevance scoring

#### Scenario: default filtering is self-auditing
- **WHEN** omitted scope filters one or more otherwise-visible candidates
- **THEN** the response reports its applied scope and a non-fatal scope note
- **AND** an explicit scope response reports its applied scope without claiming privacy

#### Scenario: list remains an unscoped inspection surface
- **WHEN** an in-process caller lists the wiki
- **THEN** the existing visibility-filtered page and draft listing behavior is unchanged

#### Scenario: concurrent defaults are request-local and deterministic
- **WHEN** 256 default discovery searches execute concurrently against a fixed mixed corpus
- **THEN** every response is byte-identical to the non-empty single-threaded reference and excludes coordination paths
- **AND** the proof claims only request-local single-process determinism while the full-platform §14 load suite remains open

## ADDED Requirements

### Requirement: Canonical public wiki inventory is completely traversable
The capture-time candidate rule in this requirement SHALL be read together with the current-withdrawal fallback below: a partition-member candidate may be dropped only when an emitted superseding transition explains it; otherwise its ordinal remains withheld-and-counted.

The wiki commons SHALL expose visibility-filtered changed-since enumeration through canonical `read_page` with relevance `scope` values `discovery`, `coordination`, and `all`; omitted or blank scope SHALL retain the existing `discovery` default. Universe ACL and page-listing visibility SHALL execute before scope/category filtering, `scope=all` SHALL NOT widen authority, and exact totals SHALL count only visible matching inventory events. The existing smaller enumeration-window default SHALL remain unchanged, public `max_results` SHALL accept only the inclusive range 1 through 100, and an out-of-range value SHALL return zero page results with `invalid_window_limit`. The in-process wiki helper's existing silent clamp to the inclusive range 1 through 100 SHALL remain unchanged for non-connector callers; strict rejection belongs to the canonical public wrapper.

The canonical commons store SHALL assign every page revision and inventory-relevant ordinary-discovery transition a server-controlled `inventory_committed_at` UTC timestamp, stable opaque globally unique `inventory_event_id`, and server-internal globally unique monotonically increasing `inventory_sequence` atomically in the same serialization step that makes the revision or transition durable and visible to the enumeration source view. The commit SHALL evaluate and freeze the set of visibility partitions in which that event is inventory-visible. For every partition in that commit-time set, the canonical projection SHALL atomically assign a stable monotonically increasing `partition_sequence` that preserves internal causal order and is contiguous across only events committed visible to that partition; hidden events create no public sequence gaps. Partition membership for an existing event SHALL NOT be widened retroactively. Any later change to the set of partitions in which a page is inventory-visible SHALL instead commit a fresh withdrawal or restoration transition in every affected partition, including changes caused by moderation, page-listing visibility, or declared-universe visibility even when canonical content does not change; a widening transition carries the current authority-safe page evidence, and pre-membership events remain excluded from the newly eligible partition's manifest. The clock SHALL be monotonically non-decreasing and none of these fields can be selected or backdated by page content; accepted-but-not-yet-durable revisions/transitions SHALL have no committed inventory timestamp/event identifier/internal or partition sequence and SHALL receive all applicable values no earlier than the last source-view watermark when they become visible. The global `inventory_sequence` SHALL never be emitted or included in public revision evidence. Before complete enumeration is enabled, one current canonical event per current page path SHALL receive the same server-selected migration-commit timestamp plus its own stable event identifier, deterministic contiguous path-ordered internal sequence, and deterministic contiguous path-ordered `partition_sequence` within each applicable visibility partition through an atomic backfill; historical revisions retained by a successor store SHALL NOT be retroactively imported as separate bootstrap events. That timestamp SHALL NOT derive from page content or file mtime and SHALL be no later than the first post-backfill commit timestamp. No event may enter a partition manifest without the inventory clock, event identity, internal sequence, and that partition's sequence. Frontmatter `updated` SHALL remain returned display metadata only. Changed-since enumeration SHALL filter and deterministically order solely by `(inventory_committed_at DESC, path_sort_key ASC, partition_sequence DESC)`, where `path_sort_key` is the tagged tuple `(1, path)` for a path-bearing event and `(0, "")` for a pathless event; unique-within-partition `partition_sequence` makes the public order total and carries causal order without exposing hidden events. Each emitted row SHALL report `inventory_committed_at`, display `updated` where applicable, `inventory_event_id`, and `partition_sequence`, never global `inventory_sequence`. A bounded, versioned, opaque, unguessable cursor SHALL reference a retained immutable snapshot. The snapshot SHALL be derived from one committed source view of the canonical commons store, SHALL contain only candidates whose frozen commit-time membership includes the caller's current authority partition and that remain currently authorized, and SHALL apply normalized `changed_since`, scope, and category filters after authority filtering. The visibility partition SHALL be `root-public` for the root commons and `<universe_id>:granted|ungranted` for a universe wiki; the separate actor presentation context SHALL be the authenticated principal or a server-derived anonymous requester partition that caller input cannot select.

The cursor SHALL be bound to the enumerator, normalized filters, universe, visibility partition, actor presentation context, ordering version, snapshot identifier, internal committed source revision, and next immutable manifest ordinal to process. It SHALL NOT reference a mutable server continuation pointer or merely the last emitted row. Every request SHALL process one fixed contiguous manifest-ordinal window; a row withheld by a current authority check SHALL still advance its processed ordinal. The resulting `next_cursor` SHALL identify the next unprocessed ordinal. Snapshot deduplication SHALL NOT cross actor presentation contexts. The public `snapshot_revision` SHALL instead be a deterministic digest over the authority-filtered ordered manifest using only domain-separated typed encodings of each row's `inventory_event_id`, public `partition_sequence`, `inventory_committed_at`, and capture-time disposition (`live`, `withdrawn`, `restored`, or `deleted`). It SHALL NOT consume global `inventory_sequence`, path, source hash, title, excerpt, body, returned display/relevance metadata, or a superseded value, so hidden activity and post-capture redaction cannot alter or leak through the digest preimage. The unfiltered source revision SHALL remain server-side. Each ordinary emitted inventory row SHALL expose its event identity/partition sequence plus canonical raw-text hash as `inventory_event_id`, `partition_sequence`, and `source_sha256`. Every successful window SHALL return the applied filters, public `snapshot_revision`, `snapshot_captured_at`, `snapshot_expires_at`, per-window emitted `count`, per-window `withheld_count`, capture-time visibility-filtered `total_matches`, retained rows unprocessed after the window as `truncated_count`, `has_more`, nullable `next_cursor`, nullable `next_changed_since`, and `complete`. Per-window `count` SHALL include every emitted retained event, including a pathless redacted removal signal. `complete` SHALL be true exactly when every retained event has been either emitted or explicitly withheld, and `next_cursor` SHALL be non-empty exactly when unprocessed retained rows remain. One path MAY appear more than once when distinct revision/deletion/visibility-transition events for it match the same range; uniqueness and no-gap proofs SHALL use `inventory_event_id`, not path.

An identical first-window retry within the same actor presentation context, normalized filters, ordering version, and authority-filtered public manifest digest SHALL reuse the existing retained snapshot and initial cursor rather than allocate or charge another snapshot. A hidden-only committed-source change that leaves that digest unchanged SHALL reuse the same live snapshot and SHALL NOT alter cursor validity, quota use, totals, or public revision evidence. Retrying an identical continuation cursor with unchanged current withdrawal inputs SHALL reproduce the same emitted rows, withheld count, and `next_cursor` without advancing mutable server state or consuming quota; a newly withdrawn row SHALL instead be withheld without changing the cursor's processed ordinal range. This internal allocation SHALL remain semantically read-only and idempotent.

Snapshots SHALL remain available for at least 15 minutes and SHALL expire no later than 30 minutes after capture. One serialized manifest SHALL be capped at 64 MiB. Combined across the wiki and Goal snapshot services, each actor presentation context SHALL be limited to four concurrent snapshots, 256 MiB retained bytes, and six new snapshots per rolling minute. The combined wiki-and-Goal snapshot service SHALL be limited to 4,096 concurrent snapshots and 16 GiB retained snapshot bytes; anonymous contexts collectively SHALL use no more than 2,048 snapshots or 8 GiB, reserving the remaining 2,048 snapshots and 8 GiB for authenticated contexts when that reserved capacity is otherwise free. Anonymous requester partitions SHALL derive from trusted transport metadata rather than caller-supplied fields. A new-snapshot request exceeding any creation, class, count, or byte bound SHALL return zero page results, `complete=false`, `snapshot_capacity_exceeded`, and bounded retry guidance; it SHALL NOT leave a partial snapshot. Existing valid continuations remain governed by their advertised expiry and withdrawal checks and SHALL continue at anonymous or global capacity.

Ordinary content and metadata writes committed after capture SHALL NOT invalidate or reorder an in-progress traversal; callers continue over retained as-of rows. Immediately before emitting each retained row, however, the server SHALL re-evaluate current universe authority and page-listing visibility through the owning read-serving path. Operational redaction/tombstone blocks SHALL be consulted before any durable bundle body, so a redaction takes effect as soon as reads are blocked even if physical body deletion follows later. A missing, newly restricted, or operationally blocked page SHALL emit no path, title, excerpt, body, or metadata from that older retained live row and SHALL increment that window's `withheld_count`. Capture-time `total_matches` SHALL not shrink, and terminal completeness SHALL mean that every retained row was emitted or withheld, not that restricted data was disclosed. A malformed, unsupported, cross-query, cross-universe, cross-partition, cross-actor-context, missing, or expired cursor SHALL return zero page results, `complete=false`, and a structured restart error. Candidates hidden at capture SHALL be excluded before snapshot materialization, so their activity cannot alter that snapshot, its totals, or its public revision evidence. Every capture-time exclusion of a candidate whose frozen membership includes the caller's visibility partition SHALL correspond to a retained, emitted ordinary-or-pathless superseding withdrawal/deletion transition in that same partition; if no such superseding event exists, the excluded candidate's ordinal SHALL instead remain in the manifest and be withheld-and-counted rather than dropped. Therefore any public `partition_sequence` gap caused by capture exclusion is explained by an event the same partition receives and cannot reveal an otherwise hidden event. A cursor SHALL NOT grant identity or access.

Canonical page deletion SHALL commit a durable inventory tombstone with a new `inventory_committed_at`, `inventory_event_id`, internal `inventory_sequence`, and applicable public `partition_sequence`, plus `supersedes_inventory_event_id` naming the deleted live revision. The ordinary tombstone SHALL retain only those fields, `path`, `deleted=true`, the last canonical `source_sha256`, and the prior visibility partition, audience, and category needed to reproduce authority-first relevance filtering; it SHALL retain no title, excerpt, body, or other page metadata. A secrets-class deletion SHALL omit `source_sha256` from durable and emitted tombstone state, matching PLAN.md redaction-before-physical-deletion ordering; no secrets-class tombstone or removal signal SHALL emit a content hash, and durable tombstone state SHALL retain none. A superseded live event MAY retain its prior hash until the owning redaction/deletion lifecycle physically removes it, but current authority and operational-redaction checks SHALL prevent that event or hash from being emitted after secrets classification. A tombstone SHALL be eligible for changed-since enumeration and `total_matches` only in visibility partitions where the page was listable immediately before deletion. Immediately before emission, the server SHALL re-evaluate current universe authority against the retained prior visibility partition; revoked authority SHALL withhold the entire event and increment `withheld_count`. It SHALL then consult the current operational-redaction and accepted moderation withdrawal predicates. If either blocks ordinary discovery, the response SHALL suppress `path`, `source_sha256`, and prior descriptive/relevance metadata and emit only a pathless removal signal containing `deleted=true`, `redacted=true`, `inventory_event_id`, public `partition_sequence`, `supersedes_inventory_event_id`, and `inventory_committed_at`; this lets a client discard a previously ingested event without rediscovering the artifact identity. A tombstone event SHALL never deduplicate against the live event it supersedes, including when their committed clocks are equal. Deletion tombstones SHALL remain durable inventory metadata until a future explicitly specified compaction checkpoint; no implementation may silently age them out. If deletion happens after an older snapshot captured the live row, that older row SHALL be withheld under the current-read check and the next inclusive poll SHALL expose the authority-filtered ordinary, secrets-safe, or redacted deletion tombstone.

An ordinary-discovery withdrawal that does not delete content SHALL commit a new inventory event with `withdrawn=true`, a fresh clock/event ID/internal sequence/applicable partition sequence, and `supersedes_inventory_event_id`; its emitted removal form SHALL apply the same authority, operational-redaction, moderation, and secrets-safe field rules as a deletion tombstone. A later restoration SHALL commit a distinct event with `restored=true`, a fresh `inventory_committed_at`/`inventory_event_id`/internal sequence/applicable partition sequence, the current authority-safe path/hash/metadata, and `supersedes_inventory_event_id` naming the withdrawal event, even when canonical content has not changed. Thus a mirror polling after restoration observes the page again through a fresh event rather than depending on its older content-revision clock.

`changed_since` SHALL accept either an explicit inclusive ISO `inventory_committed_at` bootstrap boundary or the opaque versioned `next_changed_since` token returned by a completed prior poll. Under the same serialization that defines read visibility, the source view SHALL capture a server-clock visibility fence as the candidate watermark. That fence SHALL be no earlier than the decoded incoming boundary and the maximum `inventory_committed_at` of every revision/visibility event visible in the source view; every accepted-but-not-yet-visible or future revision/transition SHALL receive `inventory_committed_at` no earlier than the fence when it becomes visible. The fence SHALL advance monotonically with serialized source-view time even when no matching row exists, and SHALL not be derived from hidden membership or an unfiltered revision. Only the terminal `complete=true` window SHALL return non-null `next_changed_since`; that value SHALL be a bounded opaque authenticated self-contained token binding the fence, enumerator/version, universe, visibility partition, and actor presentation context. A visibility-partition mismatch SHALL return zero page results, `complete=false`, `poll_rebaseline_required`, and `rebaseline_changed_since` set to the server's explicit earliest supported inclusive inventory epoch (no later than the atomic initial-backfill timestamp); the caller SHALL restart with that returned ISO boundary rather than decode the opaque token or reconstruct a boundary from observed rows. An actor-presentation-context mismatch while the recomputed visibility partition is unchanged SHALL instead return zero page results, `complete=false`, `poll_context_rebound`, and `rebound_changed_since` containing the same fence re-authenticated for the new actor context; the caller SHALL retry with that rebound token and SHALL NOT re-enumerate the corpus from the inventory epoch. Neither token grants authority. Every other non-terminal or error response SHALL return `next_changed_since` as null or omit it, and callers SHALL NOT advance their next poll until traversal completes. Callers SHALL pass the terminal or rebound token as the next request's `changed_since` and deduplicate rows repeated at the inclusive boundary by globally unique `inventory_event_id`, never by content hash alone. Because the fence precedes later snapshot-materialization work, neither hidden-only activity, accept-to-durable projection delay, restoration delay, nor source-to-snapshot delay creates an observable mutation signal or a polling gap.

The wire order is newest-first for discovery, but it is not mutation-application order. A mirror SHALL collect the completed retained snapshot and apply its events in ascending `(inventory_committed_at, partition_sequence)` order, or equivalently reduce each `supersedes_inventory_event_id` chain so the greatest partition sequence determines the final disposition. It SHALL NOT apply the descending emission stream naively. This rule holds across window boundaries and makes a restoration newer than its withdrawal win deterministically without exposing global activity.

If a future authority change makes wiki page-listing visibility differ by principal within one current visibility partition, that change SHALL revise the partition definition, cursor/poll-token binding, actor-rebound rule, snapshot deduplication, tombstone eligibility, and load proofs before exposing different catalogs. Actor presentation context alone SHALL NOT silently carry per-principal listing authority under this contract.

Lexical search SHALL remain best-effort, SHALL report `search_complete=false` with a completeness warning, and SHALL NOT issue a cursor that claims complete enumeration.

#### Scenario: anonymous root-commons caller requests every audience class
- **WHEN** an anonymous caller enumerates the public root commons with `scope=all`
- **THEN** the response includes both discovery- and coordination-classified pages that pass existing visibility checks
- **AND** the response does not imply that scope granted authority

#### Scenario: universe visibility denial wins under public all scope
- **WHEN** a caller enumerates a universe wiki with `scope=all` and lacks visibility for one matching page
- **THEN** that page's path, title, excerpt, body, metadata, and contribution to `total_matches` are absent

#### Scenario: first partial inventory window carries a continuation
- **WHEN** a changed-since query has more visible matches than its bounded result window
- **THEN** the response reports `has_more=true`, `complete=false`, and a non-empty `next_cursor`
- **AND** `truncated_count` equals the retained rows not yet processed after that window

#### Scenario: terminal inventory window proves completion
- **WHEN** a valid continuation returns the final visible matching window
- **THEN** the response reports `has_more=false`, `next_cursor=null`, `truncated_count=0`, and `complete=true`

#### Scenario: enumeration window above the public cap fails closed
- **WHEN** a caller supplies `max_results` outside the inclusive range 1 through 100
- **THEN** the response returns zero page results with `invalid_window_limit`
- **AND** it does not allocate a snapshot or normalize the value into range

#### Scenario: identical continuation replay is immutable
- **WHEN** a caller retries the same valid continuation cursor and one retained ordinal is withheld by a current authority check
- **THEN** both attempts return the same emitted rows, `withheld_count`, and `next_cursor`
- **AND** the withheld ordinal is processed exactly once in traversal position without mutating a server-side pointer or consuming quota

#### Scenario: an all-withheld window remains positional
- **WHEN** every retained ordinal in a non-terminal 100-ordinal window fails its current emission check
- **THEN** the response reports `count=0`, `withheld_count=100`, `has_more=true`, and the cursor for the next unprocessed ordinal
- **AND** it does not scan ahead to backfill the window with later emitted rows

#### Scenario: an exact full final page is still terminal
- **WHEN** the final result window contains exactly the requested maximum number of items and no visible match remains
- **THEN** the response reports `complete=true` rather than inferring incompleteness from `count == max_results`

#### Scenario: cursor cannot cross query or authority context
- **WHEN** a caller reuses a cursor with a different scope, category, changed-since value, universe, visibility partition, or actor presentation context
- **THEN** the server returns no page results, `complete=false`, and a structured restart error

#### Scenario: root-public cursor cannot cross requester context
- **WHEN** a principal or anonymous requester partition presents a root-commons cursor captured for another actor presentation context
- **THEN** the server returns zero page results and `complete=false`
- **AND** the constant `root-public` visibility partition does not make cursors transferable

#### Scenario: writes do not disturb a retained inventory snapshot
- **WHEN** canonical pages are created, modified, or deleted after an inventory snapshot is captured
- **THEN** the caller continues over the same retained ordered snapshot without reorder or restart
- **AND** the terminal receipt identifies the original `snapshot_revision` and does not claim to include later writes

#### Scenario: post-capture restriction is withheld immediately
- **WHEN** a retained page becomes missing or fails current page-listing visibility before its row is emitted
- **THEN** that window omits every identifying or content field for the page and increments `withheld_count`
- **AND** terminal `complete=true` means all capture-time rows were emitted or withheld

#### Scenario: wiki snapshot remains usable through the minimum lifetime
- **WHEN** a caller presents a valid continuation immediately before 15 minutes after `snapshot_captured_at`
- **THEN** the retained snapshot remains available and returns its ordinary deterministic window
- **AND** capacity pressure cannot shorten that minimum lifetime

#### Scenario: expired snapshot fails without partial results
- **WHEN** a caller continues after the retained snapshot's advertised expiry
- **THEN** the server returns zero page results, `complete=false`, and `cursor_expired`
- **AND** the error instructs the caller to begin a new inventory snapshot

#### Scenario: hidden activity is not a cursor oracle
- **WHEN** a page outside the caller's authority partition is created, modified, or deleted
- **THEN** the caller's retained snapshot, totals, cursor validity, and revision evidence do not change
- **AND** an otherwise-identical first-window retry reuses the live snapshot without another quota charge

#### Scenario: deletion becomes an authority-safe incremental tombstone
- **WHEN** an authority-visible non-secrets-class page is canonically deleted after an earlier poll
- **THEN** the next inclusive changed-since snapshot returns `path`, `deleted=true`, the prior `source_sha256`, its new `inventory_event_id`, `supersedes_inventory_event_id`, and deletion `inventory_committed_at` only to previously authorized actor contexts
- **AND** it returns no title, excerpt, body, or other page metadata and includes the tombstone in exact totals

#### Scenario: deletion after capture is withheld then observable
- **WHEN** a live row is deleted after capture but before emission from the retained snapshot
- **THEN** the old snapshot withholds the row and advances its processed ordinal
- **AND** the next inclusive poll returns the durable authority-filtered deletion tombstone

#### Scenario: equal-clock deletion cannot deduplicate against its live row
- **WHEN** a live revision and its deletion tombstone have equal `inventory_committed_at` values at an inclusive boundary
- **THEN** their distinct `inventory_event_id` and public `partition_sequence` values give them a total causal order and cause the client to process both semantic events
- **AND** the tombstone's `supersedes_inventory_event_id` identifies the live event to remove

#### Scenario: moderation suppresses identifying tombstone fields
- **WHEN** an operational-redaction or accepted moderation predicate blocks an otherwise authority-visible deletion tombstone
- **THEN** enumeration emits only the pathless redacted removal signal with new and superseded event identifiers
- **AND** it exposes no path, source hash, title, excerpt, body, or prior relevance metadata

#### Scenario: secrets-class deletion tombstone never retains a recoverable hash
- **WHEN** a secrets-class page is canonically deleted
- **THEN** its ordinary or redacted tombstone omits `source_sha256` from durable and emitted state
- **AND** public inventory enumeration emits no content hash that could confirm the deleted content

#### Scenario: revoked grant withholds a captured tombstone
- **WHEN** a universe grant is revoked after a deletion tombstone is captured but before its event is emitted
- **THEN** the server emits none of the tombstone's ordinary or redacted fields and increments `withheld_count`
- **AND** its processed ordinal still advances within the immutable window

#### Scenario: moderation restoration commits a fresh inventory event
- **WHEN** a soft-hidden page returns to ordinary discovery without a content revision
- **THEN** the restoration atomically receives fresh `inventory_committed_at`, `inventory_event_id`, internal sequence, and applicable public `partition_sequence` values and names the superseded withdrawal event
- **AND** the next inclusive poll emits the restored authority-safe page rather than relying on its old content-revision clock

#### Scenario: visibility withdrawal is an incremental removal event
- **WHEN** a visible page becomes non-discoverable without deletion
- **THEN** the transition commits a fresh `withdrawn=true` inventory event naming the superseded visible event
- **AND** its emitted ordinary or pathless form follows the same authority, moderation, redaction, and secrets-safe rules as deletion removal

#### Scenario: authority partition change forces poll rebaseline
- **WHEN** a caller presents a terminal poll token captured while its universe partition was ungranted after that caller becomes granted
- **THEN** the server returns zero page results, `complete=false`, `poll_rebaseline_required`, and the explicit ISO `rebaseline_changed_since`
- **AND** the caller must restart from that server-provided earliest supported boundary to enumerate the newly visible pre-existing corpus

#### Scenario: actor-context rotation rebinds without corpus rebaseline
- **WHEN** an anonymous caller's presentation context changes while its visibility partition remains `root-public`
- **THEN** the server returns zero page results, `complete=false`, `poll_context_rebound`, and `rebound_changed_since` carrying the same fence for the new context
- **AND** the caller retries with that token rather than consuming a full-epoch snapshot series

#### Scenario: public ordering values reveal no hidden activity
- **WHEN** a caller completes an epoch-bootstrap traversal for one authority partition with `scope=all`, no category filter, no candidate excluded at capture by a current-authority or withdrawal check, and no row withheld at emission while hidden events commit between visible events, including across initial backfill
- **THEN** the emitted `partition_sequence` values are contiguous across that unfiltered retained partition manifest
- **AND** a traversal filtered by `changed_since`, scope, category, or current withholding MAY emit non-contiguous sequence values; such a filtered gap is not evidence of hidden activity
- **AND** no emitted field or revision evidence reveals the existence or count of events outside the visibility partition

#### Scenario: snapshot digest excludes redaction-sensitive payload
- **WHEN** a path-bearing tombstone captured in a retained manifest becomes redacted before emission
- **THEN** `snapshot_revision` remains a digest only of event identity, sequence, clock, and capture-time disposition
- **AND** it never consumes the current or superseded path/hash or other descriptive/relevance metadata

#### Scenario: supersession chains reduce in causal order
- **WHEN** one completed retained snapshot emits a restoration before its older withdrawal because the wire order is descending
- **THEN** the mirror applies events in ascending `(inventory_committed_at, partition_sequence)` order or reduces the supersession chain to its greatest partition sequence
- **AND** the restored event wins even when withdrawal/restoration straddle different windows

#### Scenario: retained corpus paginates without duplicates or gaps
- **WHEN** a caller follows every server-issued cursor across a retained visible snapshot
- **THEN** each retained `inventory_event_id` appears exactly once in the combined emitted rows or withheld positions
- **AND** capture-time `total_matches` equals all emitted rows, including pathless redacted removal signals, plus the sum of per-window `withheld_count`
- **AND** one path may appear in multiple emitted events when distinct revisions or deletion events match the range

#### Scenario: next poll uses an inclusive source watermark
- **WHEN** a caller finishes a snapshot and begins a later changed-since poll with the returned `next_changed_since`
- **THEN** no canonical update committed after the earlier source revision is omitted
- **AND** rows repeated at the inclusive boundary retain stable globally unique `inventory_event_id` evidence for client deduplication

#### Scenario: abandoned partial traversal cannot advance the poll
- **WHEN** a caller stops after any non-terminal inventory window
- **THEN** that response exposes no non-null `next_changed_since`
- **AND** a later poll cannot truthfully advance beyond the retained rows that were not processed

#### Scenario: backdated display metadata cannot evade polling
- **WHEN** a page commits after the prior watermark with frontmatter `updated` set earlier than that watermark
- **THEN** its server-assigned `inventory_committed_at` places it in the next inclusive poll
- **AND** the backdated frontmatter timestamp remains display metadata and cannot affect membership or ordering

#### Scenario: accepted pending revision cannot fall behind the watermark
- **WHEN** a revision is accepted before a source view starts but becomes durable/read-visible only after that view
- **THEN** it receives `inventory_committed_at` no earlier than the completed view's terminal watermark
- **AND** the next inclusive poll includes it rather than advancing past it

#### Scenario: initial inventory backfill leaves no canonical page unclocked
- **WHEN** complete enumeration is enabled over a pre-existing commons corpus
- **THEN** the current revision of every canonical page has a deterministic server-controlled `inventory_committed_at`, stable unique `inventory_event_id`, internal causal sequence, and deterministic contiguous `partition_sequence` in each applicable visibility partition
- **AND** historical revisions retained by a successor store receive no separate bootstrap event
- **AND** a changed-since poll spanning the backfill boundary can enumerate every authority-visible candidate

#### Scenario: adversarial snapshot fan-out is bounded
- **WHEN** one actor or anonymous requester partition varies filters to create snapshots beyond its rate, count, or retained-byte budget
- **THEN** excess creation requests return no results and `snapshot_capacity_exceeded`
- **AND** global snapshot count, retained bytes, and expiry remain within the declared hard bounds

#### Scenario: anonymous Sybil fan-out cannot consume authenticated reserve
- **WHEN** many anonymous requester partitions collectively reach the anonymous snapshot-count or byte sub-cap
- **THEN** further anonymous creation fails without a partial snapshot while existing continuations remain valid
- **AND** an authenticated first-window request can still use otherwise-free reserved authenticated capacity

#### Scenario: search cannot prove absence
- **WHEN** lexical search returns zero or a capped ranked result set
- **THEN** it reports `search_complete=false` and directs completeness-sensitive callers to changed-since enumeration
- **AND** it does not return an enumeration `next_cursor`

#### Scenario: public inventory concurrency meets the owning load proof
- **WHEN** the wiki surface alone serves a 10,000-record corpus to 1,000 concurrent connector clients distributed across 1,000 distinct actor/requester rate partitions for five minutes, comprising exactly 100 full traversals and 900 ordinary first-or-continuation reads while 20 relevant content or visibility-transition events commit per second, including non-destructive withdrawal/restoration
- **THEN** retained snapshots have no duplicate or omitted visible `inventory_event_id`, preserve total sequence/reducer semantics, and return zero false-complete receipts
- **AND** cold snapshot creation plus its first window remains below two seconds at p99, continuation windows remain below 500 milliseconds at p99, and at least 99 of the 100 full traversals finish within five minutes
- **AND** an implementation that misses the bound optimizes or materializes the shared retained-snapshot projection rather than weakening `complete`

### Requirement: Exact canonical page reads support hash-bound chunks
Exact wiki reads through canonical `read_page` SHALL expose bounded `offset` and `max_chars` inputs with a connector-facing default of 4,000 and cap of 32,000 characters, return `truncated`, `next_offset`, and `source_read_proof.sha256`, and accept `expected_sha256` on continuation. The existing in-process wiki handler's 128,000-character default and 256,000-character clamp SHALL remain unchanged for non-connector callers. The canonical wrapper SHALL request strict public-window validation from the owning handler so an invalid window returns no content. For both in-process and canonical exact reads, the owning handler's hash, offsets, and `content` SHALL use the raw canonical file text, including frontmatter, for promoted pages and drafts. Draft state SHALL remain in the sibling `is_draft` field; neither a synthetic draft marker nor truncation explanation SHALL be appended to the owning exact-read handler's `content`; current draft labeling in ranked-search result titles remains unchanged.

A continuation whose `expected_sha256` differs from the current canonical page hash SHALL return no content and a structured `stale_read` restart-at-zero error. The parameter SHALL use the same raw-text hash basis as write-side compare-and-swap while retaining a read-specific failure envelope. Offsets SHALL be server-issued Python Unicode code-point positions over canonical source; callers SHALL advance with `next_offset` and SHALL NOT calculate byte or UTF-16 offsets.

#### Scenario: first large-page chunk exposes continuation evidence
- **WHEN** an exact page body exceeds the bounded `max_chars` window
- **THEN** the response returns source-only `content`, `truncated=true`, a non-null `next_offset`, and the canonical page SHA-256

#### Scenario: small page completes in one public window
- **WHEN** an exact page body fits within the connector's default 4,000-character window
- **THEN** the response returns the full canonical body with `truncated=false` and `next_offset=null`

#### Scenario: stable page chunks concatenate exactly
- **WHEN** a caller follows each `next_offset` while supplying the first chunk's SHA-256
- **THEN** concatenating each returned `content` value reproduces the canonical page body exactly once
- **AND** the final chunk reports `truncated=false` and `next_offset=null`

#### Scenario: draft chunks hash and concatenate over canonical text
- **WHEN** a caller reads every chunk of a draft page
- **THEN** concatenated `content` equals the raw canonical draft file whose SHA-256 is reported
- **AND** draft status appears only in `is_draft`, not as a synthetic prefix in `content`

#### Scenario: changed page blocks mixed-revision chunks
- **WHEN** the canonical page changes after one chunk and the caller continues with the earlier SHA-256
- **THEN** the server returns no content and instructs the caller to restart from offset zero

#### Scenario: invalid read window fails closed
- **WHEN** a caller supplies a malformed or negative offset, an offset beyond the canonical source length, or `max_chars` outside the inclusive range 1 through 32,000
- **THEN** the connector returns `invalid_read_window` with no content
- **AND** it never normalizes the value, reads outside the canonical page, or leaks adjacent content

#### Scenario: offset at end is a valid empty terminal window
- **WHEN** a caller supplies an offset exactly equal to the canonical source length
- **THEN** the connector returns empty `content`, `truncated=false`, and `next_offset=null`
