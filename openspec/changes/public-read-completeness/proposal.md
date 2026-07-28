## Why

Tier-1 users and other connector-only clients cannot currently prove that they
have read the complete visible wiki inventory or Goal catalog: the canonical
handles cap results without a continuation cursor, `read_page` does not expose
the already-supported audience scope or large-page continuation inputs, and
Goal listings do not report whether more visible rows exist. This blocks
trustworthy discovery, retirement audits, collaboration, and any client that
must distinguish “no more results” from “the server stopped returning them.”

## What Changes

- Extend canonical `read_page` without adding an MCP handle:
  - publicly expose `scope=discovery|coordination|all`, with `discovery` as the
    default for ranked search and changed-since enumeration, the source page's
    audience as the exact-read ambient-feed default, and existing
    visibility/ACL checks always applied first;
  - expose bounded `offset`/`max_chars` plus `expected_sha256` continuation for
    exact page bodies, forward exact-read `category`, and align in-process and
    canonical exact-read `content` with raw source by removing synthetic draft
    and truncation prose from the body;
  - preserve exact-page `changed_since`/`query`/`scope`/`category` ambient
    filtering, route no-page `changed_since` to enumeration, and replace the
    shipped silent drop of enumeration state on no-page `query` conflicts with
    a structured fail-loud result;
  - add a visibility-safe, query-bound cursor for changed-since inventory
    enumeration over a retained snapshot captured from one committed canonical
    commons source view, while exposing only an authority-filtered snapshot
    revision plus capture/expiry/completeness and safe next-poll evidence;
  - base changed-since filtering and order on server-assigned
    `inventory_committed_at`, leaving page-controlled frontmatter `updated` as
    display metadata so backdating cannot evade a later poll, and retain
    uniquely identified authority-safe deletion tombstones so incremental
    mirrors can remove deleted paths without confusing them with live rows;
  - commit fresh inventory events for non-destructive visibility withdrawal
    and restoration, and bind terminal poll tokens to actor/visibility context
    so restored or newly granted history cannot fall behind a stale watermark;
  - keep lexical search explicitly best-effort and never present it as an
    absence/completeness proof.
- Extend canonical `read_graph target=goals` without adding an MCP handle:
  - add deterministic cursor pagination over the visible, filtered Goal
    catalog;
  - report whether the returned window is complete and provide a continuation
    cursor when it is not;
  - preserve author filtering, replace the current first-tag/SQL-LIKE
    approximation with exact all-supplied-tag intersection, include only
    exactly `visibility=public` in rows and totals, and define the exhaustive
    public partition as `goal-public-commons`; ranked search and the internal
    `production_only` approximation remain outside the exact-count contract,
    but gate-independent slice 0A immediately applies the same exact-public
    allowlist to empty-query listing, ranked search, and exact `target=goal`
    lookup so canonical public reads cannot return non-public Goal fields while
    pagination gates remain unresolved.
- Define one self-auditing read receipt vocabulary for both enumerations:
  applied filters/scope, snapshot revision, capture/expiry time, returned
  count, current-withdrawal `withheld_count`, `total_matches`,
  `truncated_count`, `has_more`, `next_cursor`, and `complete`, plus
  terminal-only actor/visibility-bound `next_changed_since` for wiki polling.
  Cursors are opaque immutable positional references to retained snapshots,
  never credentials or authority grants; identical retries replay without
  mutable server progress, while invalid, expired, or
  cross-query/actor-context cursors and poll tokens fail closed.
- Require deterministic total wire ordering with a globally sequenced causal
  reducer, no duplicate/omitted events within an unchanged snapshot,
  redaction-stable payload-free revision digests, concurrent-reader isolation,
  hard per-snapshot/actor/service
  creation and retained-byte quotas with 15–30 minute expiry, a hard 100-row
  enumeration-window cap, hidden-activity-safe snapshot deduplication, a
  numeric snapshot-backed pagination-under-mutation and adversarial
  fan-out envelope, public canary coverage, rendered connector acceptance, and
  the full-platform §14 load proof appropriate to each owning lane.
- Keep Agent Village/web-app behavior out of scope. Connector-only users are
  the primary acceptance surface.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `wiki-commons`: make visible changed-since enumeration and exact large-page
  reads completely traversable through the canonical public handle while
  preserving audience-as-relevance and authority-first filtering.
- `shared-goals-and-convergence`: make filtered Goal catalog reads completely
  traversable with deterministic cursor semantics and truthful completeness
  evidence.
- `live-mcp-connector-surface`: advertise the new parameters and
  self-auditing response contract under the existing `read_page` and
  `read_graph` handles, with no new handle or legacy alias.

## Impact

Because the repository is public and the live visibility defect is not yet
closed, this exploit-sensitive planning lane SHALL remain local/unpublished
until slice 0A is deployed and its self-contained requirement is synced, unless
the host explicitly acknowledges publication first. The eventual public
history SHALL describe the closed class of defect without retaining
exploit-ready shipped predicate or file-line instructions.

Planning affects the three capability specs above. Later implementation is
expected to touch the canonical wrappers in `tinyassets/universe_server.py`,
wiki enumeration/indexing in `tinyassets/api/wiki.py` and the canonical Brain
store, Goal listing/storage in `tinyassets/api/market.py`,
`tinyassets/daemon_server.py`, and the host-approved Goal storage substrate, a
shared ephemeral read-snapshot store, their focused tests, plugin parity
generation in every landable slice, the Cloudflare front-door forwarding
header overwrite and origin provenance seam, public canaries, and
rendered-chatbot acceptance evidence. Every runtime slice waits for its exact active
canonical/mirror/test claims to release or provide a non-overlapping handoff.
Slice 1A exact chunks has no Brain, Goal-substrate, scope, or load-harness
dependency. Slice 1B waits only on the public-scope host decision plus its file
claims. Wiki snapshot slice 2 waits on `build-brain-canonical-store` topology
and the host-approved quota envelope. Goal snapshot slice 3 waits on resolution
of `establish-postgres-control-plane`, reconciliation with
`per-user-goal-canonicals`, provisioning of a dedicated versioned
snapshot-digest key through the accepted credential-vault/control-plane secret
path, and the host-approved quota envelope. Load execution
waits on the not-yet-created `implement-production-load-harness` and isolated
traffic/substrate approval. Wiki inventory-transition/tombstone emission must
reconcile the accepted operational withdrawal **and restoration** predicates
and every partition-membership change from `moderation-and-abuse-response` and
`universe-visibility`, including pathless redacted removal signals, before
slice 2 lands. This change must also
reconcile before sync with the concurrent
`live-mcp-connector-surface` deltas in
`connector-tool-selection-accuracy`, `operator-request-trigger-contract`,
`reconcile-external-connector-manifests`, and
`retire-legacy-live-mcp-tools`; removal of the legacy `wiki` tool must not land
before canonical exact-page continuation is available. Public scope slice 1B
is a new MCP exposure and is independent of legacy removal.
`reconcile-external-connector-manifests` carries a competing full-body
modification of `Cloudflare Worker Public Front Door`. This change SHALL NOT
sync until that owner records a reciprocal dependency and both owners agree
one merged requirement body containing that lane's accepted manifest behavior
plus this change's intentional normalization to the shipped non-hop-by-hop
request-header boundary, exact XFF overwrite exception, missing-header
strip/proxy, and origin in-band denial clauses, while preserving every clause and scenario of the
then-canonical requirement not explicitly modified by either accepted change.
