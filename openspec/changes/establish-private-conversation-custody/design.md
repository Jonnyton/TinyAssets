## Context

The approved V1 custom-agent demo needs durable conversation state before an
app adapter can deliver a message to an agent and return its reply. Public
`AgentDefinition` records and private `AgentBinding` records deliberately reject
conversation content, and no current owner provides an exportable conversation
store. Letting Slack, another app adapter, or provider output become canonical
would couple private history to a transport and would make portability depend on
that provider.

This change establishes only the user-selected `private_universe` custody mode.
Its files live inside the selected universe directory, so the same universe
placement and backup boundary that keeps the user's cloud universe available
while their devices are off also owns the conversation database. This does not
assert that private-universe custody is appropriate for every user or use case.
Host-resident, external-vault, and platform-held implementations remain separate
future custody providers selected by the user.

The first consumer will be the separately admitted app-conversation service. It
will authenticate app installations, organizations, interlocutors, and agent
bindings before calling this internal contract. This change therefore stores
only internal identity references and never treats raw Slack or other provider
identifiers as authority.

## Goals / Non-Goals

**Goals:**

- Define a versioned, custody-mode-declared conversation contract that is not
  tied to Slack, another app schema, an agent archetype, or a provider SDK.
- Persist one immutable thread identity and append-only, ordered message
  envelopes inside a single selected private universe.
- Enforce exact owner, universe, and agent-binding scope on every read, append,
  export, and deletion operation.
- Provide deterministic private export plus irreversible owner-requested or
  retention-expiry deletion with a content-free receipt.
- Bound and canonicalize every stored envelope, make retries idempotent, and
  preserve arbitrary portable message payload shapes without silently dropping
  unknown fields.
- Keep canonical and packaged runtime implementations byte-identical.

**Non-Goals:**

- No MCP action, public catalog field, Slack handler, organization mapping,
  interlocutor authentication, persona rendering, provider call, effect, or
  production activation.
- No host-resident, external-vault, or platform-held storage implementation and
  no claim that `private_universe` is the universal default.
- No credential, app-installation authority, raw provider identity, provider
  response, runtime state, workflow state, goal, or public remix lineage.
- No search, analytics, semantic indexing, mutation of accepted messages, or
  cross-thread/cross-owner listing.

## Decisions

### 1. Custody providers are an open interface; the first provider is bound to one universe directory

The public contract carries a versioned custody-mode identifier, while the
implementation class represents the selected provider. The first provider uses
the stable identifier `private_universe` and is constructed with one exact
`universe_id` and universe directory. It opens that directory's existing
`.tinyassets.db`, never the platform data-root database, and refuses records for
another universe.

This makes placement an explicit construction decision and leaves future modes
free to use a host directory, vault client, or platform database behind the same
domain contract. A closed enum or one global conversation table was rejected:
both would silently settle the PLAN's deliberately open custody question.

### 2. Upstream authority supplies normalized internal identity references

Every operation receives an immutable `ConversationCustodyContext` containing
the authenticated owner, universe, and agent-binding identifiers. Thread
creation additionally receives an internal interlocutor reference. Message
creation receives internal participant and source-event references. These
values are bounded opaque identifiers; they are not Slack workspace, member,
channel, or event IDs and cannot themselves prove app authority.

The future app-conversation owner must construct this context only after its
organization/interlocutor/binding checks succeed. This store then enforces the
same exact context on every row lookup. Accepting raw app identities or a
caller-authored role/owner shortcut was rejected because it would move
authentication into the persistence layer without the required owners.

### 3. Immutable thread identity and append-only canonical message envelopes

A thread freezes its conversation ID, custody contract version/mode, owner,
universe, agent binding, interlocutor, retention boundary, and creation time.
There is no update operation. Messages receive a store-assigned contiguous
ordinal under `BEGIN IMMEDIATE`; accepted message rows are never updated. Each
message freezes a bounded message kind, internal participant reference,
internal source-event reference, optional reply-to message ID, canonical JSON
payload, payload digest, and creation time.

The JSON payload is deliberately extensible rather than text-only: a future
adapter can preserve typed parts or attachment references without changing the
custody primitive. Canonical JSON, an explicit byte limit, finite nesting, and
exact allowed envelope fields prevent ambiguous or unbounded records. Unknown
payload members are preserved because they are private content, not execution
authority.

### 4. Idempotency is owner-scoped and request-bound

Thread creation, message append, and deletion each require a bounded
idempotency key. The store persists both the key and a canonical request digest
under an owner-scoped unique constraint. An identical retry returns the exact
stored result; reusing a key for different input fails with a conflict. Message
append allocates its ordinal in the same transaction as the idempotency check,
so concurrent retries produce one row and concurrent distinct messages produce
distinct contiguous ordinals.

### 5. Export is deterministic and private; deletion physically removes content

Export returns one canonical `conversation-custody/v1` JSON-compatible bundle
containing the immutable thread and messages ordered by ordinal. The method
requires the full owner/universe/binding context and exact conversation ID. It
does not publish, register, or attach the bundle to public definition lineage.

Deletion runs in one transaction. An owner request may delete at any time; a
retention-expiry request succeeds only after the stored retention boundary. The
transaction physically deletes the thread and cascading message rows, then
inserts an immutable receipt containing identity, reason, deletion time, and
message count but no payload, payload digest, source-event reference,
interlocutor reference, or reply lineage. Exact deletion retries return that
receipt. Retaining append-only rows with content hashes was rejected because
small or predictable private messages could be guessed after deletion.

### 6. Integrity is checked on every reconstruction

Typed domain records reconstruct from canonical row content and compare every
duplicated indexed column, digest, ordinal, and serialized envelope. A mismatch
raises an integrity error instead of returning partially trusted history.
SQLite foreign keys, WAL mode, parameterized statements, bounded busy timeout,
and transactions follow existing runtime-store practice. No external
dependency is added.

## Risks / Trade-offs

- **[Risk] A cloud-hosted private universe still requires user trust in that
  selected host.** -> The mode is named in every record/export and remains
  exportable and replaceable; other custody providers remain open.
- **[Risk] A compromised upstream adapter could pass forged internal refs.** ->
  This implementation is kept dark and internal until the separately reviewed
  organization/interlocutor/app-authority owner constructs the context.
- **[Risk] Physical deletion sacrifices append-only audit detail.** -> A
  content-free deletion receipt retains proof of scope, reason, time, and count
  without retaining guessable content-derived material.
- **[Risk] Arbitrary JSON payloads can be large or pathological.** -> Enforce
  canonical JSON, finite depth, string/key/list limits, and a 64 KiB canonical
  payload limit before any write.
- **[Risk] Per-universe SQLite does not by itself provide encryption.** -> This
  mode inherits the selected universe's filesystem/volume protections and does
  not claim vault semantics; a vault provider remains a separate mode.
- **[Trade-off] No listing or search in the first contract.** -> Exact thread
  operations are sufficient for app delivery and materially reduce accidental
  cross-tenant disclosure surface.

## Migration Plan

1. Add the domain and per-universe SQLite owner dark, with no existing caller.
2. Verify canonical/package parity, race behavior, deletion, export, and
   cross-scope refusal.
3. Hand the authenticated context and store interfaces to the future
   `connect-custom-agent-app-conversations` change.
4. That successor selects `private_universe` only after the user chooses it and
   only after organization/interlocutor/app authority is authenticated.

Rollback is additive: before a consumer lands, remove the new modules and
tables. After a consumer lands, export or delete its private threads before
removing this provider; never silently fall back to a different custody mode.

## Open Questions

- What authenticated organization/interlocutor owner mints the normalized
  internal references? The app-conversation successor must name that owner.
- Which alternate custody providers are offered and how users compare them?
  This change deliberately leaves that product/research decision open.
