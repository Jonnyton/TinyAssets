## Context

The approved V1 custom-agent demo needs durable conversation state before an
app adapter can deliver a message to an agent and return its reply. Public
`AgentDefinition` records and private `AgentBinding` records deliberately reject
conversation content, and no current owner provides an exportable conversation
store. Letting Slack, another app adapter, or provider output become canonical
would couple private history to a transport and make portability depend on that
provider.

This change establishes only the user-selected `private_universe` custody mode.
The first consumer will be the separately admitted app-conversation service.
That successor must authenticate app installation, organization, interlocutor,
agent binding, and custody selection before minting an opaque operation grant.
Neither matching identifiers nor possession of a filesystem path authorizes a
custody operation.

The selected universe placement remains a trust choice: cloud-hosted
`private_universe` custody trusts that universe host and its backup policy. It
does not claim vault encryption or protection from a privileged host
administrator. Host-resident, external-vault, and platform-held providers
remain separate future user-selectable modes.

## Goals / Non-Goals

**Goals:**

- Define a versioned, custody-mode-declared conversation contract independent
  of Slack, another app schema, an agent archetype, or a provider SDK.
- Require a one-use, action-bound grant from the future authenticated owner;
  owner/universe/binding equality remains necessary but never sufficient.
- Bind `private_universe` storage to the authority-registered, selected universe
  path and reject caller-selected, symlinked, or reparse-point placement.
- Persist immutable threads and append-only, ordered messages; provide exact
  reads, deterministic private export, and explicit live-store deletion.
- Bound and canonicalize arbitrary portable JSON payload members without
  silently dropping unknown fields.
- Make retries and concurrency deterministic, including post-deletion retries.
- Keep canonical and packaged runtime implementations byte-identical.

**Non-Goals:**

- No MCP action, public catalog field, Slack handler, organization mapping,
  interlocutor authentication, grant issuer, persona rendering, provider call,
  effect, or production construction path.
- No host-resident, external-vault, or platform-held implementation and no
  claim that `private_universe` is a universal default.
- No credential, app-installation authority, raw provider identity, provider
  response, runtime/workflow state, goal, or public remix lineage.
- No search, analytics, semantic indexing, mutation of accepted messages, or
  cross-thread/cross-owner listing.
- No claim of immediate forensic erasure from historical backups, filesystem
  snapshots, storage-device remanence, or copies already returned to a caller.

## Decisions

### 1. A consumed authority grant, not matching IDs, admits each operation

The internal facade accepts a one-use opaque grant minted by the future
app-conversation authority owner. Consuming the grant returns detached trusted
evidence binding:

- operation kind and normalized request digest;
- owner, universe, agent binding, and selected custody mode;
- custody-selection generation, authority-registered absolute universe path,
  and trusted platform data-root identity;
- a digest of a server-issued high-entropy idempotency key for mutations;
- grant nonce, issue time, and expiry.

The consumer must live-check the selection, binding, and registered path when it
consumes the grant. The facade compares every normalized request field and
digest with that evidence before opening storage. A grant is single-use and
cannot be serialized as a bearer token. Raw storage methods remain private and
the change ships with no production issuer or construction path; tests use an
explicit test-only issuer.

This keeps persistence scoped without pretending that caller-authored IDs are
authentication. A context with matching strings but no valid grant is refused.

### 2. The first provider derives its path only from registered grant evidence

The provider identifier is the open contract string `private_universe`; it is
not a closed enum. On every operation, the facade derives the database path only
from freshly consumed evidence. The registered path must be absolute, must
resolve strictly to an existing directory, and must match the current registry
association for the evidence's universe and custody-selection generation.

The registered path and each existing ancestor up to its filesystem anchor are
checked with `lstat`; POSIX symbolic links and Windows reparse points are
refused. The final resolved path must equal the registered canonical path and
must not equal the trusted platform data root bound into the grant evidence.

Before and immediately after SQLite opens or creates `.tinyassets.db`, the
provider `lstat`s the database and any present `-wal`/`-shm` sidecars. Each path
present at either check must be a regular file with one hard-link count and no
symbolic-link or Windows reparse attribute. An existing primary database's
device/file identity must be unchanged across open. WAL/SHM identity continuity
is deliberately not required because SQLite may create, delete, or replace
sidecars as part of normal WAL lifecycle; every sidecar that exists at a check
must still pass the alias checks. The same alias checks run before
cleanup/checkpoint completion. A caller cannot supply any of these paths.

These checks reject request-layer path substitution and stable filesystem
aliases. They cannot make Python's pathname-based SQLite API race-free against
another process running as the same OS account. Same-account mutation between
validation and open, privileged host administration, filesystem snapshots, and
storage-media behavior are explicitly inside this mode's host trust boundary.
Vault custody remains the alternative for a different threat model.

### 3. Threads are immutable; messages have explicit identity and lineage

A thread freezes a server-generated `conversation_id`, contract version/mode,
owner, universe, agent binding, normalized interlocutor reference, retention
boundary, and canonical UTC creation time. There is no update operation.

Each message freezes a globally unique server-generated `message_id`, a
store-assigned contiguous ordinal, bounded message kind, normalized participant
and source-event references, optional reply-to ID, canonical payload, payload
digest, and creation time. `BEGIN IMMEDIATE` allocates the ordinal. A reply must
target an already-committed message in the same thread whose ordinal is lower
than the new ordinal. Concurrent reply/target attempts resolve in transaction
order: target-first succeeds; reply-first fails without consuming an ordinal.
Accepted messages have no update operation.

All owner, universe, binding, conversation, message, interlocutor,
participant, and source-event identifiers/references are already-normalized
opaque ASCII: 1 through 256 bytes, matching
`^[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}$`. They are never trimmed, case-folded, or
Unicode-normalized; input outside the grammar is rejected. Message kind is 1
through 64 lowercase ASCII characters matching
`^[a-z][a-z0-9_.:-]{0,63}$`. These grammars describe portable internal refs,
not authorization and not raw transport IDs.

Every stored/exported time uses exactly `YYYY-MM-DDTHH:MM:SS.ffffffZ`: a valid
Gregorian UTC date/time, literal `T` and `Z`, and exactly six fractional-second
digits. Offset spellings, omitted/shorter/longer fractions, leap seconds, and
naive timestamps are rejected. `retention_until` is either that grammar or
JSON null.

### 4. `tinyassets-canonical-json/v1` fixes portable payload and digest semantics

Message payload input is an in-memory mapping, never raw JSON text. Duplicate
keys are therefore impossible at this boundary. The canonicalizer rejects
non-string keys and accepts only null, booleans, NFC-normalized strings,
signed-64-bit integers, lists, and mappings. Floats, bytes, custom objects, and
non-NFC strings are rejected rather than coerced.

The structural bounds are: maximum node depth 16, 128 members per mapping, 256
items per list, 4,096 total value nodes, 256 UTF-8 bytes per key, 32,768 UTF-8
bytes per string, and 65,536 canonical UTF-8 bytes for the complete payload.
The root mapping is one value node at depth 0. Every mapping value and list item
is one child node at its parent's depth plus one. Mapping keys are not nodes.
No node may have depth above 16. Unknown member names within those limits are
preserved.

Strings and keys must contain Unicode scalar values; surrogate code points
U+D800 through U+DFFF are rejected. Canonical bytes use UTF-8, NFC strings,
object keys sorted by Unicode code point, no insignificant whitespace,
lowercase JSON literals, base-10 integers without leading zeroes, and unescaped
solidus/non-ASCII text. Quotation mark encodes as `\"`, reverse solidus as
`\\`, U+0008/0009/000A/000C/000D as `\b`/`\t`/`\n`/`\f`/`\r`, and every
other U+0000 through U+001F scalar as six ASCII bytes `\u00xx` with lowercase
hexadecimal digits. No alternative escape spelling is canonical.

The payload digest is lowercase `sha256:<64 hex>` over those exact bytes.
`conversation-custody/v1` export is the same canonical encoding of exactly:

```text
{
  "canonical_json": "tinyassets-canonical-json/v1",
  "custody_mode": "private_universe",
  "messages": [
    {
      "created_at": <canonical UTC timestamp>,
      "kind": <string>,
      "message_id": <string>,
      "ordinal": <integer>,
      "participant_ref": <string>,
      "payload": <canonical mapping>,
      "payload_digest": <sha256 string>,
      "reply_to_message_id": <string or null>,
      "source_event_ref": <string>
    }
  ],
  "schema": "conversation-custody/v1",
  "thread": {
    "agent_binding_id": <string>,
    "conversation_id": <string>,
    "created_at": <canonical UTC timestamp>,
    "interlocutor_ref": <string>,
    "owner_user_id": <string>,
    "retention_until": <canonical UTC timestamp or null>,
    "universe_id": <string>
  }
}
```

No other top-level/thread/message member is accepted in this version. Messages
are ordered by ordinal. The export result returns these canonical bytes plus a
separate digest formatted exactly as lowercase `sha256:<64 hex>` over all and
only those bytes; the digest is not embedded recursively. There is no
export-time timestamp, so unchanged exports are byte-for-byte stable.

### 5. Idempotency has an exact namespace and an explicit deletion transition

The future authority supplies each mutating operation a cryptographically
random 32-byte value encoded as exactly 43 unpadded base64url characters with
the prefix `ik_`. The complete 46-character ASCII key must match
`^ik_[A-Za-z0-9_-]{43}$`, its suffix must decode without padding to exactly 32
bytes, and raw provider event IDs are never keys. The persisted key digest is
lowercase `sha256:<64 hex>` over the UTF-8/ASCII bytes of the complete `ik_...`
string, not over the decoded random bytes. Test-only vector
`ik_AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA` decodes to 32 zero bytes and
hashes to
`sha256:7c02713014568e7c6a23ccce8e98f0d6e165f7f779f274859610460060faf803`;
production issuers must never use that zero-entropy value.

The logical mutating namespace is `(universe_id, owner_user_id,
operation_kind, idempotency_key_digest)`, where operation kind is
`create_thread`, `append_message`, or `delete_thread`. Each provider database is
bound to exactly one universe and enforces the remaining tuple locally; no
cross-universe uniqueness claim is made. High-entropy issuance prevents
accidental collision, while deliberate reuse in another universe is an
independent operation. The authority/action domain additionally contains
`read_thread` and `export_thread`, which have request digests but no key or
ledger row.

Every operation request digest is lowercase `sha256:<64 hex>` over the exact
`tinyassets-canonical-json/v1` bytes of one domain-separated mapping:

```text
create_thread = {
  "agent_binding_id", "custody_mode": "private_universe",
  "domain": "conversation-custody/create-thread/v1", "interlocutor_ref",
  "owner_user_id", "retention_until", "universe_id"
}
append_message = {
  "agent_binding_id", "conversation_id",
  "domain": "conversation-custody/append-message/v1", "kind",
  "owner_user_id", "participant_ref", "payload", "reply_to_message_id",
  "source_event_ref", "universe_id"
}
read_thread = {
  "agent_binding_id", "conversation_id",
  "domain": "conversation-custody/read-thread/v1", "owner_user_id",
  "universe_id"
}
export_thread = {
  "agent_binding_id", "conversation_id",
  "domain": "conversation-custody/export-thread/v1", "owner_user_id",
  "universe_id"
}
delete_thread = {
  "deleted_target_digest",
  "domain": "conversation-custody/delete-thread/v1", "reason"
}
```

The braces above name exact member sets; no member is optional except that
`retention_until` and `reply_to_message_id` carry JSON null when absent. Grant
evidence binds the operation kind, this request digest, and the separately
carried idempotency-key digest where the operation is mutating.

Normative vector values are: owner `owner_1`, universe `universe_1`, binding
`agent_binding_1`, conversation `conversation_1`, interlocutor
`interlocutor_1`, participant `participant_1`, source event `event_1`, message
kind `text`, payload `{"text":"hello\nworld"}`, null reply, retention
`2030-01-02T03:04:05.000006Z`, delete reason `owner_request`, and the deleted
target digest from the vector below. Their request digests are:

```text
create_thread  sha256:2e16d89e186ea01130b06c77c544394f1bdc84159d7fd816419acd65826dd78f
append_message sha256:03d0dce3eba96d9efa1c8bf8ab383c90a2724c6c6e4a935201653649805fc3d5
read_thread    sha256:6b9114c5a4161548e7bca566a340d73f7ddab83c21527f53a375c2c47531b143
export_thread  sha256:f0d5c9697fbac581b93f42a4c52750388e1cb8c825fe653d52d2e91b902bef42
delete_thread  sha256:a326ce1489645ec9083d739e9a27bfb2c88870a63cf7e833877b77a59acb00be
```

For active create/append operations, the ledger retains the canonical request
digest and result identity. Identical concurrent or later retries return the
exact result; a changed request conflicts. Creation and append allocation occur
in the same transaction as the ledger row.

Deletion converts every create/append ledger row for that conversation to a
content-free tombstone: request digest, result identity, conversation
association, and any source-derived value are cleared while operation kind and
high-entropy key digest remain. Any post-deletion reuse of such a key returns
`conversation_deleted` without distinguishing identical from changed input and
never recreates content. A fresh create key may create a new thread; any append
to the deleted conversation fails.

The deletion-reason domain is exactly `owner_request` or `retention_expired`.
The caller never supplies a retention boundary: `retention_expired` reads and
checks the immutable stored boundary. The store retains a
`deleted_target_digest` under a unique index. Its preimage is exactly the
`tinyassets-canonical-json/v1` bytes of this mapping and no other members:

```json
{"agent_binding_id":"<binding>","conversation_id":"<conversation>","domain":"conversation-custody/deleted-target/v1","owner_user_id":"<owner>","universe_id":"<universe>"}
```

The digest is lowercase `sha256:<64 hex>` over those bytes. Normative vector:
with values `agent_binding_1`, `conversation_1`, `owner_1`, and `universe_1`,
the exact preimage is
`{"agent_binding_id":"agent_binding_1","conversation_id":"conversation_1","domain":"conversation-custody/deleted-target/v1","owner_user_id":"owner_1","universe_id":"universe_1"}`
and the digest is
`sha256:1720128239c73ade4c587c137126e013dde5617751676294b5029815154cc1f5`.
It contains no message/content-derived value and supplies target-only
correlation after active rows are gone.

Delete keys retain a request digest derived only from that target digest and
reason. Same-key changed requests conflict. A different delete key for the same
target and reason is linked to and returns the first receipt; a different reason
for the same target conflicts. This makes competing deletion requests
deterministic without retaining message-derived material.

### 6. All operations have a SQLite serialization point

Create, append, exact read, export, and delete use `BEGIN IMMEDIATE` against the
per-universe database. Their transaction commit is the linearization point.
Distinct concurrent appends receive contiguous ordinals. Append versus delete
and read/export versus delete resolve in lock order: an operation serialized
before delete may finish normally; one serialized after delete observes the
tombstone and fails. Data already returned by an earlier or overlapping read
cannot be revoked.

Integrity reconstruction compares canonical envelopes with every duplicated
indexed identity column, digest, message ID, ordinal, and reply edge. A mismatch
raises an integrity error without partial output. Deletion intentionally does
not reconstruct payloads, so corrupt message content can still be deleted when
the authoritative scope columns remain intact; corrupt scope columns fail
closed for repair rather than risking cross-tenant deletion.

### 7. Deletion guarantees active-store removal, not universal forensic erasure

Deletion first serializes and verifies scope/reason. Owner-requested deletion
may run at any time; retention deletion requires the stored boundary to have
passed. With SQLite `secure_delete=ON`, one transaction deletes thread/message
rows, clears create/append request digests and result refs, and records a
content-free deletion intent. That commit is the logical deletion point.

After commit, the store checkpoints and truncates its WAL. Only after quiescent
live-store cleanup succeeds does it finalize and return an immutable receipt.
A crash or busy checkpoint leaves a content-free pending intent; an authorized
retry completes cleanup and returns the receipt without restoring content. The
receipt contains scope IDs, reason, logical deletion time, cleanup completion
time, deleted-message count, `deletion_scope=active_private_universe_sqlite`,
and an explicit historical-backup-retention caveat. It contains no payload,
payload/request digest, message/result ID, interlocutor, participant,
source-event, reply edge, credential, or provider identifier.

Quiescent tests scan the SQLite primary and sidecars for unique private
sentinels after successful cleanup. This is evidence for the active store only;
historical backups, snapshots, media remanence, and external copies follow
separate universe/provider retention and deletion policies and are explicitly
not covered by this receipt.

## Risks / Trade-offs

- **[Risk] A cloud private universe still trusts its host and backup policy.** ->
  Every export/receipt names the mode and deletion scope; alternate providers
  remain open and the successor must surface the backup caveat.
- **[Risk] The future grant owner could be implemented incorrectly.** -> No
  production issuer ships here; app activation stays blocked on independent
  review of organization/interlocutor/binding/custody authority.
- **[Risk] Filesystem checks cannot defeat a privileged host administrator.** ->
  State that threat boundary explicitly and offer vault custody later rather
  than implying encryption or host isolation.
- **[Risk] WAL cleanup can be busy or interrupted.** -> Persist a content-free
  deletion intent, return no completed receipt until cleanup succeeds, and make
  retry recovery deterministic.
- **[Risk] Arbitrary JSON can be pathological.** -> Enforce exact type,
  normalization, structural, and byte limits before authorization or storage.
- **[Trade-off] `BEGIN IMMEDIATE` serializes reads and writes.** -> Conversation
  threads are low-throughput in V1; a simple auditable total order is preferred
  to weaker deletion and reply semantics. The §14 proof will measure the cost.
- **[Trade-off] No listing/search in the first contract.** -> Exact operations
  satisfy app delivery while minimizing accidental disclosure surface.

## Migration Plan

1. Add the domain, grant-consumer seam, and per-universe SQLite owner dark, with
   no production issuer or caller.
2. Verify authority refusal, canonical/package parity, races, corruption,
   export, live-store deletion, and byte-residue cleanup.
3. Hand the grant-evidence and facade interfaces to
   `connect-custom-agent-app-conversations`.
4. That successor selects `private_universe`, resolves the registered path, and
   mints grants only after its organization/interlocutor/binding checks pass.

Rollback is additive before a consumer lands. After use begins, export or
delete active threads and honor the universe's historical-backup policy before
removing the provider; never silently fall back to another custody mode.

## Open Questions

- Which exact organization/interlocutor owner will implement the production
  grant consumer, platform-root authority, and custody-selection registry? The
  app successor must name them.
- What retention/deletion propagation will each backup provider promise? The
  app successor must surface the active-store scope until that is specified.
- Which alternate custody providers are offered and how users compare them?
  This change deliberately leaves that product/research decision open.
