## Context

The live connector advertises seven canonical handles. `read_page` currently
routes exact reads, lexical search, and changed-since enumeration, but its
public schema omits:

- `scope`, even though the wiki handler already supports
  `discovery|coordination|all`;
- `offset` and `max_chars`, even though exact reads already produce
  `next_offset`; and
- any continuation input for a changed-since result capped at 100.

The wiki handler reports `total_matches` and `truncated_count`, so it truthfully
admits that the result is partial but gives a connector-only client no way to
finish it. `read_graph target=goals` has the same structural gap: it accepts a
limit and returns a count, but no total, continuation, or completeness claim.
The canonical site reader exposed this as a live retirement-audit blocker, but
the contract is broader than the site: Tier-1 chatbot users, daemons, and
external MCP clients all need a complete public read path without a web app.

The root wiki is a public-by-definition commons. Wiki audience scope is a
relevance classifier, not authorization; universe ACL and per-page visibility
remain the disclosure boundary. The earlier
archived `openspec/changes/archive/2026-07-25-scope-wiki-discovery` change
intentionally deferred public scope advertisement
until the `universe_server.py` owner released the schema seam. That seam is
still actively claimed, so this lane specifies the contract but does not edit
runtime files.

The current Goal surface leaks non-public data through empty-query listing,
ranked search, and exact lookup. Listing also applies only the first tag
approximately, accepts no actor, and defines no per-principal read policy.
Gate-independent slice 0A first applies the exact-public allowlist to all three
canonical public modes; later pagination defines `goal-public-commons` as the
exhaustive public-only catalog. Non-public Goals never enter rows, totals,
ranked results, or exact public results. No accepted active change currently
defines actor-owned private-Goal read authority; `per-user-goal-canonicals`
owns canonical bindings, not read authority. A future authority change must
specify identity, ownership, non-disclosure, and cursor-partition behavior
before any public surface can expose a private Goal.

An older completeness finding,
`docs/design-notes/proposed/2026-05-08-brain-update-003-completeness-cursor-enumeration-fallback.md`,
established the applicable integrity rule: search ranking cannot prove absence;
clients need cursor/enumeration evidence and must fail closed on a gap or
version mismatch.

## Goals / Non-Goals

**Goals:**

- Make the complete visible wiki inventory and Goal catalog traversable through
  the existing canonical handles.
- Make partial windows mechanically distinguishable from complete results.
- Preserve authority-first filtering and prevent a cursor from widening access.
- Give exact large-page reads a hash-bound continuation contract.
- Keep response sizes bounded and ordering deterministic.
- Specify concurrency behavior that never silently claims completeness across
  a detected collection change.
- Preserve connector-only users as the primary acceptance surface.

**Non-Goals:**

- A new MCP handle, action family, compatibility alias, REST-only surface, or
  web-app/Village architecture.
- Making lexical wiki or Goal search a completeness proof.
- Changing wiki authority or defining owner access/custody for private Goals;
  the exhaustive public catalog only closes the shipped leak by excluding
  private-marked rows.
- Moving commons content into PostgreSQL.
- Implementing runtime while `universe_server.py` and broad tests are claimed
  by other providers.
- Solving ranked node discovery, remix, convergence, or realtime presence in
  this change.

## Decisions

### The existing handles gain parameters; the handle set stays at seven

`read_page` gains public `scope`, `cursor`, `offset`, `max_chars`, and
`expected_sha256` inputs. Its connector-facing exact-read default is 4,000
characters and its public cap is 32,000 characters, keeping the normal payload
below the known ChatGPT large-result failure zone while allowing bounded
opt-in windows. `read_graph` gains a public `cursor` input used by
`target=goals`. Every advertised parameter supplied outside a mode that
defines it returns zero results and a structured error naming both the
parameter and mode; nothing is silently ignored. This includes enumeration
`cursor` in an exact-page chunk mode and exact-chunk
`offset`/`max_chars`/`expected_sha256` inputs in search or enumeration modes.
Exact reads retain their shipped `changed_since` ambient-feed behavior and
their defined `query`/`scope`/`category` ambient-feed filters. Without an exact
page, non-empty `query` selects ranked search and conflicts with
`changed_since` or enumeration cursor; the structured error replaces the
shipped branch that silently dropped the enumeration discriminator. A
redundant
caller-supplied `changed_since` accompanying a
wiki cursor is compared to the cursor's decoded normalized inclusive boundary,
not its raw text spelling.

This follows PLAN's minimal-primitive rule. A standalone list-pages,
continue-page, or list-goals tool would add names without adding an irreducible
capability.

Alternative rejected: keep pagination inside the site or another client. A
client cannot recover rows the server never exposes, and connector-only users
are first-class.

The parameter name `scope` is intentionally reused only across different
handles: this change defines `read_page.scope=discovery|coordination|all`,
while the relay lane defines write-side `write_page.scope=commons`. Their
enums and routing are disjoint, and `connector-tool-selection-accuracy` must
retain handle-qualified descriptions so a chatbot never transfers values
between them.

### Public wiki scope is relevance, not privilege

The public `read_page` schema accepts `discovery`, `coordination`, and `all`.
Omitted or blank scope retains the current `discovery` default for search and
changed-since enumeration. An exact read retains the source page's audience as
the default for its ambient feed.

Anonymous callers may request `scope=all` on the root commons because the root
is already public by definition. The handler still applies universe ACL and
page-listing visibility before audience/category filtering. For a universe
wiki, `scope=all` only means “both audience classes among pages this caller may
list”; it never means “all pages regardless of authority.”

Alternative rejected: require operator authority for coordination/all. That
would incorrectly turn relevance classification into privacy and make public
commons history unavailable to connector-only contributors.

### Enumeration responses use one completeness receipt

Every paginated changed-since or Goal-catalog response returns:

- the applied normalized filters and scope where applicable;
- `snapshot_revision`, identifying the authority/filter/actor-context result
  manifest captured by the retained snapshot without exposing an unfiltered
  source revision;
- `snapshot_captured_at` and `snapshot_expires_at`, separating freshness from
  completeness;
- `count`, the number of emitted retained events in this response, including a
  pathless redacted wiki removal signal;
- `withheld_count`, the number of retained rows suppressed in this response
  because current visibility or withdrawal checks failed;
- `total_matches`, counted at capture after authority and filters;
- `truncated_count`, the retained rows not yet processed after this window;
- `has_more`;
- `next_cursor`, non-empty exactly when `has_more=true`; and
- `complete`, true exactly when all retained rows were emitted or withheld.

Only a terminal wiki enumeration window returns non-null
`next_changed_since`, an opaque actor/visibility-bound token carrying the
source-view watermark for the next inclusive poll. Non-terminal/error windows
cannot advance the poll.

An error response returns no items and `complete=false`. A non-terminal window
is never called complete, even if every returned item is valid. Search
responses continue to report `search_complete=false` and a completeness
warning; they do not issue enumeration cursors.

The existing `truncated_count` name is retained and sharpened rather than
adding a synonymous `remaining_count`. On a continuation page it is the number
of retained rows still unprocessed after that page, whether those future rows
will be emitted or withheld.

Alternative rejected: infer completeness from `count < limit`. Filters,
server-side caps, and concurrent changes make that inference brittle, and it
cannot explain an exact full final page.

### Cursors are versioned, query-bound continuation state, never authority

A cursor is an opaque, bounded, versioned, unguessable reference to:

- contract version and enumerator (`wiki_since` or `goal_catalog`);
- normalized query/filter hash, including scope, category, changed-since,
  universe, author, and tags that apply;
- visibility partition: `root-public` for the root wiki,
  `<universe_id>:granted|ungranted` for a universe wiki, and the constant
  `goal-public-commons` for the public Goal catalog;
- actor presentation context for every snapshot: authenticated principal or a
  server-derived anonymous requester partition, separate from the owning
  visibility partition;
- retained snapshot identifier, public authority-filtered `snapshot_revision`,
  `snapshot_captured_at`, and `snapshot_expires_at`;
- deterministic ordering version; and
- the next immutable manifest ordinal to process.

The server validates token shape and length before use, recomputes normalized
inputs, re-evaluates current authority, and rejects malformed, unsupported,
cross-query, cross-universe, cross-principal/presentation-context,
missing-snapshot, or expired-snapshot tokens with zero results and a restart
instruction. A cursor never proves identity and never bypasses a visibility
check. A valid wiki cursor alone selects changed-since continuation because it
binds the bootstrap/poll boundary and filters; a redundant caller-supplied
`changed_since` must match the decoded normalized inclusive boundary rather
than reroute the call.

The token is an unguessable reference to a bounded record in the shared
ephemeral snapshot store. That record owns the normalized query binding,
visibility partition, immutable ordered result manifest, public snapshot
revision, internal canonical source revision, capture/expiry times, and wiki
visibility fence. It has no mutable continuation pointer. Each cursor selects
a fixed contiguous manifest-ordinal window and names the next start ordinal;
processing advances across every selected ordinal even when a current
withdrawal check withholds its row. With unchanged current withdrawal inputs,
replaying an identical cursor therefore reproduces the same emitted/withheld
window and the same `next_cursor` without mutating server state or consuming
quota; a newly withdrawn row can only reduce disclosure within the same
processed range. The record is not canonical content:
expiry or rebuild loses no wiki page or Goal. Token validation never
substitutes for recomputing the current visibility partition and applying the
owning handler's authority checks.

Alternative rejected: a raw integer offset. Offset pagination can duplicate or
skip rows when ordering changes and does not bind the continuation to its
filters or authority context.

### Retained snapshots make completeness relative, durable, and traversable

Wiki changed-since enumeration orders by server-assigned
`(inventory_committed_at DESC, path_sort_key ASC, partition_sequence DESC)`.
Path-bearing events use tagged `path_sort_key=(1,path)`; pathless events use
`(0,"")`. The canonical commons store assigns that UTC inventory clock, a
stable opaque globally unique `inventory_event_id`, and a globally unique
monotonically increasing `inventory_sequence` atomically in the same
serialization that moves a
revision or inventory-relevant ordinary-discovery transition to
durable/read-visible state. The global sequence is server-internal and is
never emitted or included in a public digest. Each visibility partition
instead receives at event commit a stable, monotonically increasing,
contiguous `partition_sequence` over only events whose frozen commit-time
membership includes that partition; hidden events create no gap in an
unfiltered partition inventory, though changed-since/scope/category filters
or current withholding can produce harmless emitted gaps. Initial backfill
creates one current event per current path with deterministic path-ordered
contiguous numbering independently within each partition. Later widening
never retroactively admits older events: every page/moderation/
declared-universe-visibility membership change commits a fresh
withdrawal/restoration event in each affected partition even when content is
unchanged.
Non-destructive withdrawal/restoration therefore
commits a fresh event even when content is unchanged. Accepted-but-pending
revisions/transitions have no committed clock/event identity/sequence and
receive all three
when they become visible, with the clock no earlier than the last visible
source-view watermark.
Page-controlled frontmatter `updated`
remains display metadata and cannot affect changed-since membership or order.
Goal catalog enumeration orders by
`(updated_at DESC, goal_id ASC)`. The first request materializes the entire
authority-filtered, normalized-filter result manifest in stable order;
continuation reads the retained manifest rather than re-querying a changing
canonical store. Enumeration windows contain at most 100 retained ordinals;
the existing smaller defaults remain unchanged, and values outside 1–100 fail
with no rows rather than silently expanding work. Before each row is emitted,
the owner rechecks only the
current withdrawal predicate: wiki listing visibility and universe authority,
or Goal public visibility (`private|deleted` are withdrawn). A row that no
longer passes is suppressed and counted, but its processed ordinal still
advances so later visible rows cannot duplicate or stall.
`complete=true` means every retained row has been emitted exactly once or
explicitly withheld **as of** `snapshot_revision`, not that no later canonical
mutation exists.

An identical first-window retry for the same actor context, normalized query,
ordering version, and authority-filtered public manifest digest reuses the
existing snapshot and initial cursor without consuming another quota unit.
Hidden-only source changes that leave the public manifest digest unchanged
must reuse that snapshot even when an internal source revision changed. An
identical continuation retry replays the same immutable ordinal window and,
when current withdrawal inputs are unchanged, the same next cursor and
emitted/withheld result without advancing a server pointer or consuming quota.
A newly withdrawn row is suppressed within that same positional range. This keeps
connector `readOnlyHint` and `idempotentHint` truthful even though the server
maintains ephemeral read state.

Wiki runtime planning depends on reconciling `build-brain-canonical-store`,
but the behavioral requirement names the canonical commons store rather than
an in-flight change. Snapshot creation consumes one committed source view,
whether the eventual commons topology is a physical OKF bundle or a union
view, filters its inventory through current universe authority first, then
scope/category/changed-since, and persists only visible result metadata. Its
public `snapshot_revision` is a deterministic digest of the
authority-filtered ordered manifest, using only domain-separated typed
`inventory_event_id`, `partition_sequence`, `inventory_committed_at`, and
capture-time disposition. It excludes path, content hash, and
display/relevance metadata entirely, so post-capture redaction cannot leave a
suppressed identifying value in the preimage.
The unfiltered source revision stays server-side.
Hidden pages do not
enter the manifest,
digest, totals, or public revision evidence, so a hidden-only source change
produces the same public revision and reuses an otherwise-identical live
first-window snapshot. The retained snapshot is an ephemeral projection of
the canonical commons store, not a second content store.

A canonical deletion is a new inventory revision rather than an absent fact.
Its durable commit receives a new `inventory_committed_at`,
`inventory_event_id`, and `inventory_sequence`, records
`supersedes_inventory_event_id`, and retains only
the authority-safe removal evidence needed by an incremental mirror: `path`,
`deleted=true`, the last canonical `source_sha256`, and the prior visibility
partition/audience/category required for authority and relevance filtering.
It retains no title, excerpt, body, or other page metadata. Only actor contexts
that could list the page immediately before deletion may receive the
tombstone. Its distinct event identity prevents it from deduplicating against
the live row even when both clocks are equal. Before emission, current
universe authority is rechecked against the retained prior partition; revoked
authority withholds the event. Operational-redaction and accepted moderation
predicates then run again; a block replaces identifying fields with a pathless
removal signal containing only the new/superseded event IDs,
applicable public `partition_sequence`, deletion/redaction flags, and commit
clock. A secrets-class
deletion omits the recoverable content hash from both durable and emitted tombstone state,
matching PLAN.md redaction ordering.
Clients that ingested the prior event can remove it without rediscovering its
identity. Tombstones participate in changed-since snapshots and exact totals
until a future explicitly specified compaction checkpoint; they are never
silently discarded. If deletion occurs after an older snapshot captured the
live row, that row is withheld by the old snapshot and the next inclusive poll
returns the authority-filtered ordinary, secrets-safe, or redacted deletion
tombstone.

Non-destructive ordinary-discovery withdrawal is likewise an inventory event
with a fresh clock/event ID/sequence, `withdrawn=true`, and the superseded visible event ID; its removal form
uses the same authority/redaction/moderation/secrets-safe rules. Restoration
commits `restored=true`, a fresh clock/event ID/sequence, the current
authority-safe path/hash/metadata, and the withdrawal event it supersedes. This makes a
moderation dismissal or other unhide visible to the next poll without
pretending the old content-revision clock changed.

Wiki completeness is event-based: each retained `inventory_event_id` is
processed exactly once, and `total_matches` equals emitted event rows
(including pathless redacted removal signals) plus withheld positions. A path
may legitimately recur when multiple revision/deletion events for it match the
same changed-since range. Stable per-partition `partition_sequence` makes the
newest-first public wire order total even for same-clock/same-path or pathless
events without revealing hidden activity; the server-internal global sequence
records causal serialization without crossing the public boundary.

Wire order is not reducer order. A mirror collects the completed snapshot and
applies events in ascending `(inventory_committed_at, partition_sequence)`
order, or equivalently reduces `supersedes_inventory_event_id` chains to their
greatest applicable partition sequence. It never applies the descending stream
naively; therefore a newer restoration wins over an older withdrawal even
across windows.

Changed-since polling accepts an explicit inclusive ISO bootstrap boundary or
the opaque `next_changed_since` token from a completed poll. At source-view
start, under the same durability/read-visibility serialization, the canonical
store captures a server-clock visibility fence. The fence is no earlier than
the decoded incoming boundary and every revision/visibility event visible in
the view, advances monotonically with source-view time even when no row
matches, and is no later than the clock assigned to any accepted-pending or
future revision/transition when it becomes visible. Only the terminal
`complete=true` window exposes a bounded authenticated self-contained poll
token binding that fence to enumerator/version, universe, visibility
partition, and actor context; abandoning a traversal cannot advance the next
poll past unread rows. If the visibility partition changes, the server returns
`poll_rebaseline_required` plus its explicit earliest supported ISO
`rebaseline_changed_since`, forcing a safe bootstrap so newly granted
authority cannot reuse an old watermark and miss pre-existing pages. If only
the actor presentation context changes while the visibility partition remains
the same, the server returns `poll_context_rebound` plus a
`rebound_changed_since` token carrying the same visibility fence rebound to
the new actor context; the caller retries from that fence without a full-epoch
rebaseline. Clients reuse the resulting terminal token and
deduplicate repeated boundary rows by globally unique `inventory_event_id`,
never content hash; each ordinary emitted inventory row carries the canonical
raw-text hash. Because frontmatter
`updated` is never the poll clock, a backdated page still appears after its
commit. The watermark is derived from source-view start, not hidden membership,
an unfiltered revision, or later `snapshot_captured_at`. Therefore hidden-only
changes do not create an activity oracle, visibility restorations receive a
fresh event, and time spent materializing the snapshot cannot create a polling
gap.

Goal snapshot behavior is storage-engine neutral. Snapshot creation runs over
one transactional source view, uses an index covering
`(updated_at DESC, goal_id ASC)` plus exact author/tag/public-visibility
predicates,
and persists immutable ordered matching rows in the shared ephemeral snapshot
store. Public 1–100 limit rejection belongs to the canonical catalog wrapper;
the in-process Goal helper's lack of an upper clamp and internal
`production_only` overfetch formula remain unchanged. The target Postgres
control plane remains a host-gated substrate
decision rather than a SHALL in this capability. The visibility partition
remains `goal-public-commons`, while the cursor and snapshot are also bound to
the authenticated principal or anonymous presentation context so actor-aware
canonical fields cannot cross users. Deduplication never crosses that actor
context. Only `visibility=public` enters the catalog; every other or
unrecognized visibility is non-public. The public `snapshot_revision` is a
deterministic server-keyed digest over domain-separated typed stable Goal ID,
public `updated_at`, manifest ordinal, normalized filters, ordering version,
and actor-context partition. A caller without the dedicated key cannot compute
or forge a valid digest; author/tag/text, every other Goal field, and all
non-public rows are not directly encoded. An ordinary public edit can
indirectly change it only through public `updated_at`, membership, or ordinal.
The cursor binds the digest-key version.
Keys are provisioned through the accepted credential-vault/control-plane path,
never reused from identity or request-idempotency, and an old version remains
available for at least 30 minutes and until no live snapshot/cursor binds it.
The database source marker remains server-side. Non-public-only mutations that
leave the public manifest
digest unchanged reuse an otherwise-identical live first-window snapshot
rather than consuming quota. This lane must reconcile
`per-user-goal-canonicals` before implementation.

The wiki/Goal digest asymmetry is deliberate. Wiki revision evidence is
unkeyed because its typed preimage contains only opaque or already emitted
public event fields; the Goal digest is keyed because its stable ID and public
clock are caller-predictable and snapshot reuse must not expose excluded-row
influence.

Snapshots live for 15–30 minutes. Each serialized manifest is capped at
64 MiB. Combined across wiki and Goal snapshots, one actor/anonymous requester
partition may hold at most four live snapshots and 256 MiB, and may create at
most six snapshots per rolling minute.
The combined wiki-and-Goal service holds at most 4,096 live snapshots and
16 GiB. Anonymous contexts collectively stop at 2,048 snapshots or 8 GiB, so
the other 2,048 snapshots/8 GiB remain reserved for authenticated contexts
when otherwise free. Anonymous partitions come from trusted transport
metadata, never caller input. New creation beyond any per-context, anonymous
class, or global bound fails with zero results, `snapshot_capacity_exceeded`,
bounded retry guidance, and no partial snapshot; existing valid continuations
are not retroactively rejected at capacity.

The deployed front door must first make that requester key trustworthy:
Cloudflare overwrites caller `X-Forwarded-For` with `CF-Connecting-IP`; the
origin accepts it only with authenticated tunnel/front-door provenance and
derives a keyed privacy-safe partition without persisting raw addresses.
Direct-origin or caller-selected forwarding metadata cannot create a partition.

An ordinary canonical write after capture does not abort a valid continuation;
it appears in a later snapshot.
A wiki restriction, authority loss, operational redaction tombstone, or Goal
transition from exactly `visibility=public` to any other or unrecognized value
takes effect at the next row-emission check and increments
`withheld_count` without leaking the row. Wiki checks follow the read-serving
path and consult the operational redaction block before a durable bundle body,
matching PLAN's redaction-before-physical-deletion ordering. A later canonical
deletion tombstone carries no page body or descriptive metadata and consults
the same operational-redaction plus accepted moderation predicates before
choosing its ordinary identifying form or pathless removal form. A future accepted
moderation capability may extend the Goal withdrawal predicate. An invalid,
wrong-query/partition/actor-context, missing, or expired snapshot returns zero
results and `complete=false`.
Responses carry `snapshot_captured_at` and `snapshot_expires_at`, so a client
can judge freshness separately from completeness.

Two owner-local pagination scenarios use the same per-surface envelope, one
registered to `wiki-commons` and one to `shared-goals-and-convergence`. Each
surface independently uses a 10,000-record corpus and 1,000 concurrent
connector clients distributed across 1,000 distinct authoritative
actor/requester rate partitions for five minutes: 100 full traversals, 900
ordinary first-page or continuation reads, and 20 relevant canonical
writes/second.
Each SHALL return zero false-complete receipts, keep cold
snapshot-plus-first-page latency below 2 seconds at p99 and continuation
latency below 500 ms at p99, and complete at least 99 of its 100 traversals
within five minutes and before snapshot expiry.
Each surface also runs a single-partition adversarial fan-out phase that varies
filters past the creation/count/byte budgets and proves hard rejection,
bounded aggregate storage, cleanup by 30 minutes, and valid existing
continuations. A coordinated multi-partition anonymous phase then reaches the
anonymous aggregate sub-cap and proves further anonymous rejection,
authenticated first-window success from the reserved class, and valid existing
continuations at class/global capacity.

Alternative rejected: per-window source rescans or global write invalidation.
They either miss out-of-band ordering changes on today's filesystem or make a
100-window traversal mathematically unable to finish under the required write
rate.

### Exact page chunks are hash-bound and contain only source content

The first exact read returns the existing `source_read_proof.sha256`,
`truncated`, and `next_offset`. A continuation supplies both `offset` and
`expected_sha256`. If the canonical page hash changed, the read fails with no
content and the read-side error `stale_read`, then instructs the caller to
restart at offset zero. `expected_sha256` deliberately reuses the write-side
CAS parameter name and the same hash basis, but read mismatch is not a write
`conflict`.

At the owning handler layer for both in-process and canonical exact reads, the
hash, offsets, and `content` are all defined over the raw canonical file text,
including frontmatter. Draft state is reported by the existing `is_draft`
sibling field; the current synthetic `[DRAFT] ` prefix moves out of
exact-read `content` so drafts obey the same hash/offset contract as promoted
pages. Ranked-search draft title labeling remains unchanged.
Truncation explanation likewise stays in structured fields/caveats rather than
being appended to the source body. Offsets are server-issued Python Unicode
code-point positions over that raw text, never byte or UTF-16 indexes; callers
advance only with `next_offset` and do not calculate offsets themselves.

The 4,000-character default and 32,000-character cap apply at canonical
`read_page`; the in-process core handler keeps its current 128,000-character
default and 256,000-character clamp for internal callers. The wrapper rejects
malformed/range-invalid values before dispatch and invokes the owning handler
with an internal strict-window flag so `offset > total_chars` is checked
against canonical source length before slicing. Public `offset < 0`,
`offset > total_chars`, malformed offset, `max_chars < 1`, or
`max_chars > 32_000` returns `invalid_read_window` with no content.
`offset == total_chars` is a valid empty terminal window.

Alternative rejected: unguarded offset continuation. It can silently combine
the first half of one revision with the second half of another.

### Goal completeness applies to catalog listing, not ranked search

`read_graph target=goals` with an empty query is the complete catalog
enumerator. Its cursor binds author, tags, the constant
`goal-public-commons` partition, and ordering inputs. The internal
`production_only` approximation is not advertised by canonical `read_graph`
and is outside this exact-count contract. `target=goals` with a non-empty query
remains a ranked/best-effort search and reports that it is not a completeness
proof.

Comma-separated tags normalize to distinct trimmed tokens and use all-tags
intersection semantics. Each token matches an exact JSON tag value; SQL
wildcards in user input are data, not pattern operators. The receipt returns
the normalized applied tag list.

Exact `target=goal` remains the path for reading one known Goal. This separates
enumeration integrity from search relevance without creating another target.

### Concurrent connector deltas reconcile before sync

`connector-tool-selection-accuracy`, `operator-request-trigger-contract`,
`reconcile-external-connector-manifests`, and
`retire-legacy-live-mcp-tools` also modify
`live-mcp-connector-surface`. This change reads them as dependencies rather
than assuming its delta will sync onto today's canonical file unchanged.
Before any implementation broadens the wrapper schema, it rebases against
their landed state; before sync/archive, it copies the exact then-canonical
requirements and resolves any overlap.

One overlap is an exact full-body collision, not a generic capability touch:
`reconcile-external-connector-manifests` also replaces `Cloudflare Worker
Public Front Door` while retaining the old blanket header-preservation text.
This lane cannot bind the other owner's task map, so it SHALL NOT sync until
that owner records the reciprocal edge and both owners agree one merged body
that preserves that lane's accepted manifest/front-door clauses and this
change's intentional normalization of the blanket request-header rule to the
shipped non-hop-by-hop boundary, unconditional authoritative-XFF overwrite,
missing-value strip and continued proxy, plus origin
`anonymous_partition_unavailable` denial. This lane also requires preservation
of every clause/scenario in the then-canonical
requirement not intentionally modified by either accepted change; its foldback
gate names the merged body so it cannot silently publish a one-sided promise.

The legacy `wiki` tool currently remains the only MCP-reachable route to
`offset`/`max_chars`; it does not advertise or forward `scope`. Slice 1A
replaces that exact-page route and therefore independently unblocks legacy
removal. Slice 1B is a new public MCP scope exposure, not compatibility for a
legacy route. No temporary alias is introduced.

The repository is public. Until slice 0A is deployed and its self-contained
as-built requirement is synced, this branch remains local and must not be
pushed or opened as a PR without explicit host acknowledgment. After closure,
public history describes the defect class and proof without exploit-ready
shipped predicates or file-line instructions.

### Runtime lands in vertical slices after claim release

The implementation sequence is:

1. **Slice 0A:** immediately close anonymous private-Goal leakage in both list
   and ranked search, independent of snapshot, key, substrate, Worker, scope,
   or quota gates;
2. **Slice 1A:** exact-page hash-bound chunks and exact-read category forwarding;
3. **Slice 1B:** after the host approves anonymous
   `scope=coordination|all`, expose public wiki scope across ranked search,
   changed-since enumeration, and exact-read ambient feeds;
4. **Slice 1C:** reconcile and deploy authoritative requester provenance at
   the Worker/origin boundary before anonymous snapshot quotas are enabled;
5. after `build-brain-canonical-store`, wiki retained-snapshot enumeration;
6. after the Goal storage substrate is host-approved and
   `per-user-goal-canonicals` is reconciled, Goal retained-snapshot
   enumeration;
7. canonical wrapper/plugin parity and canary coverage;
8. rendered connector acceptance and post-fix organic-use watch.

Each slice gets RED tests before production code and its own focused review.
Slice 1A is independently landable once its narrow files release; it waits on
neither the scope host decision nor either retained-snapshot substrate.
Removal of the legacy `wiki` tool must not land before slice 1A exposes
equivalent exact-page continuation through canonical `read_page`; it does not
wait on the independent new-scope decision.
The current spec-only branch does not claim runtime or broad tests; a later
lane must rerun `claim_check.py` and either wait for or receive a handoff from
the active owners.

## Risks / Trade-offs

- **Private-Goal authors temporarily lose connector read-back** → the shipped
  propose/update paths may still accept `visibility=private`, but slice 0A
  deliberately makes every current public read mode non-disclosing even to the
  author because no accepted owner-read authority exists. A future authority
  change must restore read-back with explicit identity/ownership proof; this
  hotfix must not guess.

- **Snapshots consume shared storage** → enforce the 64 MiB per-snapshot,
  combined wiki-and-Goal four/256 MiB per-actor, six-creations/minute, 2,048/8 GiB anonymous-class,
  4,096/16 GiB service-wide, authenticated-reserve, and 15–30 minute TTL
  bounds; deduplicate only within the same authority and actor-presentation
  context; adversarially load-test rejection and cleanup.
- **A caller mistakes snapshot completeness for latest-state freshness** →
  expose the filtered snapshot revision plus capture/expiry timestamps and
  define `complete` only relative to that retained revision.
- **A retained row is restricted or withdrawn after capture** → recheck only
  the owning visibility/withdrawal predicate before emission, suppress the
  row, and report `withheld_count`.
- **Filesystem writers bypass MCP/API hooks** → cursor implementation waits on
  the canonical Brain commit protocol; uncommitted files are not advertised as
  canonical bundle state.
- **A scope parameter is mistaken for authorization** → name it relevance
  scope in specs/responses and test that visibility denial wins under every
  value.
- **Exact wiki totals or revisions leak hidden activity** → build the retained
  manifest only after authority filtering; hidden pages affect neither its
  rows, digest, totals, nor cursor validity.
- **A deploy changes ordering while old cursors exist** → version the cursor
  and ordering contract; reject unsupported versions with zero results.
- **Cursor payload becomes an input attack surface** → cap token length, decode
  defensively, reject unknown fields/versions, and never interpolate cursor
  data into SQL or paths.
- **Chunk consumers concatenate server prose** → keep source `content` exact
  and carry truncation/caveats in sibling fields.
- **The change grows into general search/discovery** → keep ranked search
  explicitly incomplete and leave node discovery/remix to its existing target.
- **Spec work collides with active runtime owners** → keep this lane's Files to
  the change directory and coordination files until an explicit handoff.

## Migration Plan

1. Review and land this target OpenSpec without syncing it into canonical
   as-built specs.
2. After runtime claims release, claim exact implementation/test files and
   build the slices above test-first.
3. After the wiki topology and Goal substrate decisions land, implement the
   shared ephemeral retained-snapshot store, canonical-commons source-view
   adapter with server-assigned `inventory_committed_at` and unique
   `inventory_event_id`/server-internal causal `inventory_sequence` plus
   stable contiguous per-visibility-partition `partition_sequence`; perform an
   explicit atomic one-current-event-per-path initial-corpus backfill using one
   server-selected migration timestamp, distinct event IDs, deterministic contiguous internal
   sequences, and deterministic contiguous path-ordered sequences
   independently within each visibility partition (never content/mtime-derived
   and no later than the first live commit),
   storage-neutral Goal transactional snapshot adapter, covering Goal index,
   current-withdrawal checks plus durable moderation/page-listing/
   declared-universe-visibility withdrawal-and-restoration events,
   moderation-safe removal signals, TTL
   cleanup, and actor-scoped deduplication; no compatibility handle.
4. Audit packaged-plugin byte parity across the change. Every runtime slice
   regenerates all applicable packaged mirrors and proves parity in that same
   slice; this step is only the final cross-slice audit.
5. After `implement-production-load-harness` lands, register separate
   owner-local pagination-under-mutation registry entries for `wiki-commons`
   and `shared-goals-and-convergence`, each with scenario ID/version,
   applicability, required classification and justification, substrate
   requirements, adapter/oracle references, fault declaration, and threshold
   references.
   After the existing host decision authorizes an isolated environment and
   traffic envelope, run focused tests, strict full-tree validation, cursor
   fuzz/security tests, concurrent read/write proofs, and the owner-local load
   scenario through the shared protocol.
6. Deploy through the normal main pipeline; run the public canary, then
   browser-rendered Claude.ai **and** ChatGPT connector conversations that
   traverse multiple pages/chunks and prove the terminal receipt. If either
   host is unavailable, keep that matrix cell and public-completion claim open.
7. Look for post-fix clean organic use. If none is visible, leave the required
   monitoring row rather than calling the public surface proven.
8. Reconcile the four concurrent `live-mcp-connector-surface` changes against
   current canonical truth, then sync the three deltas and archive only after
   runtime and acceptance evidence land. Legacy `wiki` removal follows or
   lands atomically with exact-page slice 1A.

Rollback reverts the runtime/spec-sync commit and deletes only ephemeral
snapshot rows/index additions as one release. Existing wiki pages and Goals
remain canonical throughout; no content rollback or alias route is required.

## Open Questions

- The shared ephemeral snapshot table/cleanup shape belongs to its runtime lane
  and must be reconciled with the Brain successor, the host-approved Goal
  substrate, and `per-user-goal-canonicals` before implementation.
- Wiki enumeration `max_results` and Goal catalog `limit` retain their current
  smaller defaults and accept only 1–100; pagination correctness does not
  depend on page size. The proposed public exact-page default/cap are
  4,000/32,000 characters and remain subject to rendered-host evidence.
