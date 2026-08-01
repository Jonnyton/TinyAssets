## Context

The active `universe-custom-agents` change already supplies immutable public
definitions, private universe bindings, canonical portable reads, local
fingerprint verification on import, and server-verified multi-parent component
lineage. Its implementation lives primarily in `tinyassets/custom_agents.py`
and `tinyassets/api/custom_agents.py`, routed through existing graph handles.

That substrate accepts only the canonical definition shape and immediately
publishes a successful import. It has no private inspection stage, foreign
adapter contract, conversion-loss report, or receipt tying a conversion to
the exact source and adapter. The existing lineage implementation does not
restrict parents by author, but the cross-user invariant needs explicit
acceptance coverage rather than being inferred.

The public/private boundary is load-bearing. Foreign sources can contain raw
credentials, local paths, channel addresses, conversations, or runtime state.
None can leak into public definitions, conversion evidence, exports, or logs.
Adapter code is also untrusted and cannot execute on managed cloud outside the
Engine OS admission boundary.

## Goals / Non-Goals

**Goals:**

- Make canonical `agent-definition/v1` import/export exactly round-trip.
- Stage every foreign import privately as a sanitized candidate plus an
  inspectable conversion report before separate publish and bind decisions.
- Let versioned adapters represent arbitrary source/target formats without a
  hardcoded format enum or new MCP handle.
- Preserve safe unknown data, report every normalization or loss, and scrub
  suspected secret/authority values before durable storage.
- Make every public definition from every user available as a remix parent,
  including blends across three or more creators.
- Produce immutable, content-bound conversion receipts and concurrency-safe
  idempotent stage/publish operations.

**Non-Goals:**

- Maintain platform starter agents, named archetypes, or a privileged commons
  publisher.
- Claim compatibility or feature parity with a named external project without
  the separate research and opposite-provider review gate.
- Execute imported code, activate an agent, deposit credentials, or connect an
  external channel as part of import.
- Make foreign conversions lossless when the source or target format cannot
  represent the same information.
- Add a top-level MCP tool or duplicate Branch, Engine OS, binding, evaluator,
  or attribution primitives.

## Decisions

### 1. Canonical interchange remains the only native guarantee

`agent-definition/v1` is the canonical public envelope. Native export returns
the exact normalized portable content whose fingerprint is calculated by the
existing custom-agent domain; native import revalidates it and reproduces that
content and fingerprint. Server-local IDs, timestamps, bindings, credentials,
conversations, effect payloads, and runtime state are excluded.

Portable lineage declarations are part of that immutable content but are not
the verified ledger itself. Each declaration carries the original source ID
for human provenance plus stable parent-definition and parent-component
content fingerprints. Import never rewrites an unresolved declaration into a
different field. Instead, publication projects only fingerprint-matched local
parents into the server-local verified lineage table. This changes the active
`universe-custom-agents` portability requirement and must archive after that
capability is canonical.

For a locally authored remix, the server resolves the caller-supplied local
parent IDs and enriches the portable declarations with both fingerprints
before calculating the child fingerprint. On cross-install import, a portable
declaration becomes verified only when exactly one local definition matches
both fingerprints; zero or multiple matches remain informational so a copier
cannot capture credit by republishing identical bytes.

Foreign formats are not added to the canonical validator. Keeping one native
shape avoids a growing format enum and makes every adapter replaceable.

### 2. Foreign imports are sanitized private stages, not publications

A foreign import creates an actor-owned `AgentImportStage`. The request's raw
source is bounded and processed without being written to the database or
application logs. Durable stage content contains only:

- the sanitized canonical candidate;
- source format/media metadata, a SHA-256 digest of sanitized source content,
  and an actor-private purpose-keyed HMAC commitment to the raw bounded input;
- adapter identity, semantic version, and immutable artifact digest;
- a structured `ConversionReport`;
- a content-bound private `ConversionReceipt` view;
- status, actor ownership, timestamps, and optional resulting definition ID.

The stage never contains recovered credential values or an executable runtime
snapshot. Items requiring private configuration become typed placeholders in
the candidate and `requires_private_binding` report entries. Publishing and
binding remain two explicit, independently authorized operations. Successful
conversion therefore cannot surprise a user by exposing or activating an
agent.

Persisting the raw foreign document was rejected because the current control
plane is not a general secret vault and inspection does not require retaining
the secret-bearing bytes. An unkeyed raw-source hash was also rejected because
small or low-entropy credentials could be guessed offline. The private
commitment requires `TINYASSETS_AGENT_INTERCHANGE_HMAC_KEY`, fails closed when
the key is unavailable, is never returned by public evidence, and expires with
the stage 24 hours after creation. Production accepts this deploy secret only
as canonical single-line base64 decoding to at least 32 random bytes, installs
it in a protected daemon-only env file, and validates it before the first
remote mutation. Rotation replaces the repository secret and deploys forward;
image rollback intentionally retains the new key so it cannot resurrect a
rotated-away authority. Deleting the repository secret only blocks later
deployments and is not a revocation mechanism: emergency revocation stops the
daemon before removing the protected file, while normal revocation rotates and
deploys. Durable receipts bind only sanitized
content. If the stage expires unpublished, its private receipt view expires
with it; explicit publish copies the same immutable receipt content into the
durable receipt ledger inside the publication transaction. Explicit export
writes its durable sanitized receipt immediately.

Canonical publication, staged imports, and foreign exports share one
conservative credential/private-runtime classifier. It rejects sensitive key
segments and suffixes plus embedded provider-token, bearer, and JWT-shaped
values. Import constants and final candidates are scanned; export inventory
must explicitly omit sensitive leaves and the final foreign output is scanned
again. This prevents adapter constants or legacy canonical rows from bypassing
source-only sanitization.

### 3. Reports are exhaustive and machine-readable

For JSON import and canonical JSON export, the trusted protocol runner
enumerates every scalar leaf and empty container as a canonical RFC 6901 JSON
Pointer before invoking the adapter. The adapter's inventory must cover that
core inventory exactly once; missing, duplicate, or extra paths fail the
conversion. Each covered item receives one terminal classification:
`preserved`, `normalized`, `unsupported`, `omitted_secret`,
`requires_private_binding`, or `requires_runtime`. Entries carry a stable
source path, optional canonical target path, safe reason code, and bounded
non-secret detail. The report also declares whether the conversion is
lossless; that flag is true only when every item is `preserved` and an
independent format verifier proves equality. Foreign adapter claims alone
cannot establish completeness or losslessness.

For opaque formats the report uses `inventory_verification=unverified` unless
an independently admitted format verifier supplies the source inventory. An
unverified inventory is explicitly non-exhaustive and can never claim
losslessness, even if every adapter-declared item is preserved. This makes the
unknown-loss boundary visible rather than pretending the core can understand
arbitrary bytes.

Safe unknown objects are retained under bounded namespaced extension keys.
Silently discarding an unknown field or collapsing it into prose was rejected
because it prevents honest round-trip and power-user editing.

### 4. Receipts bind source, adapter, output, and report

The receipt is canonical JSON containing a schema version, sanitized-source
digest, adapter identity/version/digest, direction, canonical candidate
fingerprint or foreign-output digest, report digest, and creation time. Its
receipt digest is SHA-256 over all preceding receipt fields. Any adapter
revision therefore produces distinct provenance even when output happens to
match. The actor-private raw-source HMAC remains on the expiring stage and is
not copied into the durable receipt.

Receipts contain hashes and safe identifiers only. They are evidence of what
ran, not an authority token, signature, execution attestation, or proof that a
foreign project endorses the conversion.

### 5. Adapters conform to a protocol and compose from governed primitives

`agent-interchange-adapter/v1` defines bounded JSON input/output envelopes for
`import` and `export`. Adapter references resolve immutable public artifact
versions. Where conversion requires executable code, the adapter runs only as
an admitted Engine OS workload with no ambient credentials, universe
authority, network entitlement, or provider access. Its output is untrusted
until the canonical validator and report validator pass. Source locators that
require network or repository access are resolved only inside the adapter's
explicit governed network entitlement; the API process never fetches them with
ambient authority.

The first end-to-end proof uses a non-executable declarative JSON mapping
adapter. Its immutable Branch version may contain only bounded JSON Pointer
copy, rename, constant, namespace-preserve, and classification rules—no
expressions, templates, code, network, filesystem, or secret lookup. The core
protocol runner may interpret that closed grammar in-process and validates the
result exactly like every adapter. A repository conformance fixture supplies a
foreign JSON manifest plus the mapping artifact for local and rendered tests;
it is evidence for the pipeline, not a named product integration or maintained
format catalog. All more expressive adapters wait for Engine OS admission.

The grammar binds operation to classification: copy/namespace operations may
only preserve or normalize, omission may only declare explicit loss, private,
or runtime categories, and constants cannot cover source inventory. Declared
target paths must be pairwise non-overlapping, including ancestor overlap, so
one rule cannot silently overwrite another while both claim successful
coverage.

The platform may ship the protocol runner and canonical native adapter, but
foreign adapters are ordinary public, remixable, evaluable commons artifacts,
preferably immutable Branch workflows. A registry table or built-in list of
named external formats was rejected.

### 6. Universal remix extends the existing verified lineage transaction

The existing definition publication logic remains the sole publisher, but its
transaction body is extracted to accept the stage transaction's existing
SQLite connection. It
resolves parent definition/component pairs without comparing parent author to
child author, validates shares and depth, and writes the child plus lineage
atomically. Interchange adds tests proving parents from independent actors can
be selected together, that newly authored residual content is credited to the
child author, and that unresolved imported origins remain informational.

Import stages do not create verified lineage. Only explicit publication can
resolve portable fingerprint declarations against the current local commons
and write verified edges. Stage status, definition publication, local lineage
projection, receipt link, and resulting definition ID commit in one SQLite
transaction; a crash cannot leave an unlinked published definition.

### 7. Existing graph handles carry explicit operations

The public surface continues to use `read_graph` and `write_graph` targets for
agents. Existing publish/remix/bind/get-agent operations remain unchanged. The
agent target adds only `stage_import`, `get_import_stage`, `publish_stage`, and
`convert_export`; private stage reads require the authenticated stage owner.
Responses are bounded structured documents suitable for chatbot inspection.

A new `agents` tool was rejected because interchange is a graph-artifact
operation and the canonical live surface must remain exactly seven handles.

### 8. Storage is additive and retry-safe

Add SQLite tables for import stages, immutable content-addressed conversion
receipts, and stage-to-receipt links beside the existing custom-agent tables.
The separate stage-link and export-owner tables are required because two
independently published stages or two actors' exports may legitimately produce
the same receipt digest. Receipt rows are content-addressed evidence rather
than ownership records; content deduplication must not erase any stage linkage
or actor ownership. `(actor_id, operation,
idempotency_key)` is
unique for every non-empty key and the row stores one canonical bound-request
digest covering direction, private source commitment, adapter digest, and
candidate fingerprint. Repeating an identical request returns the original
stage/receipt; reuse with different content fails. Publish-stage uses the
shared publication transaction described above.

Unpublished stages expire after 24 hours. Reads, publication attempts, and
subsequent staging writes deterministically prune expired rows and their
idempotency identities, so cleanup does not depend on the expired stage being
read successfully. Expiry deletes the sanitized
candidate, private raw-source HMAC, and actor-private inspection report; a
durable receipt is written only for a successful explicit publication or
export and binds sanitized content. Published definitions and bindings are not
deleted by stage expiry.

No data migration or compatibility shim is needed. Existing canonical import
continues as the native fast path, while foreign sources use the staged path.

## Risks / Trade-offs

- **[Secret detection is necessarily incomplete]** → reject known
  secret-bearing keys recursively, classify credential-shaped values and
  authority-bearing fields conservatively, never persist raw foreign input,
  and prove absence in database rows, reports, receipts, errors, and logs.
- **[A malicious adapter can lie about preservation]** → treat its report as
  untrusted, independently validate paths/categories/digests, recompute native
  fingerprints, require a declared source inventory, and reserve
  `lossless=true` for an independent format verifier. An adapter without such
  a verifier is always loss-aware/non-lossless even if it reports preservation.
- **[Namespaced extensions can become an opaque dumping ground]** → bound
  total canonical size, component count, nesting, keys, and per-entry report
  count under the existing definition limits.
- **[Adapter execution may not yet be available]** → the closed declarative
  JSON mapping grammar proves the protocol without executable code; every
  adapter outside that grammar returns `requires_runtime` until Engine OS is
  admitted, with no in-process code fallback.
- **[Stages can accumulate private metadata]** → expire every unpublished
  stage and its private source commitment after 24 hours, support bounded
  pagination, and never infer deletion of a published immutable definition.
- **[Concurrent publish can duplicate work]** → use SQLite transactions,
  uniqueness constraints, and the existing definition idempotency boundary.

## Migration Plan

1. Land `universe-custom-agents` and sync its canonical capability before this
   change archives.
2. Add red domain tests for native round-trip, cross-user blend, sanitization,
   report/receipt integrity, idempotency, and concurrency.
3. Add the additive staging/receipt schema, shared publication transaction,
   pure validators, and the closed declarative JSON mapping runner.
4. Add only the new stage/inspect/publish-stage/convert-export graph operations,
   preserving existing publish/remix/bind behavior and the seven handles.
5. Run a deployment-shaped test with 200 concurrent actors across eight
   processes: 1,000 mixed stage/import/remix/export requests in five minutes,
   including 256-KiB/64-component maxima and conflicting retries. Require p95
   below 2 seconds, p99 below 3 seconds, at least 3.33 requests/second, zero
   unhandled SQLite busy errors, zero partial writes or duplicate stages,
   zero secret/log leaks, and below 1% unexpected errors; expected idempotency
   conflicts are reported separately rather than counted as errors.
6. Admit executable adapters only through the Engine OS gate; ship no
   in-process code fallback.
7. Deploy, run focused/load/security gates and the public canary, then complete
   a rendered chatbot foreign-manifest import → inspect → blend → publish →
   bind → foreign export flow through the declarative proof adapter.

Rollback removes the new routing operations and adapter admission while
leaving additive stage/receipt rows inert for forward repair. It never deletes
published definitions or private bindings.

## Interface Schemas

Every interface document uses UTF-8 canonical JSON (sorted object keys,
compact separators, finite numbers only), rejects duplicate object keys before
canonicalization, and has maximum nesting depth 32. SHA-256/HMAC digests are
lowercase 64-hex values with their algorithm carried separately. Timestamps
are required finite Unix seconds. IDs/refs are non-empty UTF-8 strings of at
most 256 characters; semantic versions at most 64; media types at most 127.

- `AgentImportStage` (all fields required unless marked optional):
  `schema_version=1`, `stage_id`, `actor_id`, `status`
  (`staged|published|expired`), `direction` (`import|export`),
  `source_media_type`, `sanitized_source_digest_algorithm=sha256`,
  `sanitized_source_digest`, private
  `source_commitment_algorithm=hmac-sha256`, `source_commitment`,
  `adapter_ref`, `adapter_version`, `adapter_digest_algorithm=sha256`,
  `adapter_digest`,
  `candidate` (canonical JSON at most 256 KiB and 64 components), `report`,
  `created_at`, `expires_at`, and optional `published_definition_id` present
  only for `published`. A raw inline source is at most 1 MiB before parsing.
- `ConversionReport` (all required): `schema_version=1`, `direction`,
  `inventory_verification` (`core_json|format_verifier|unverified`),
  `exhaustive`, `lossless`, optional `verifier_id` required only for
  `format_verifier`, and at most 4,096 `items`. Each item requires a unique
  RFC 6901 `source_path` of at most 512 UTF-8 characters, optional
  `target_path` with the same bound, one terminal classification, a
  `[a-z][a-z0-9_]{0,63}` reason code, and optional non-secret `detail` of at
  most 256 characters. `lossless` requires `exhaustive=true`, verified
  inventory, and all items `preserved`.
- `ConversionReceipt` (all required unless conditional):
  `schema_version=1`, `direction`,
  `sanitized_source_digest_algorithm=sha256`, `sanitized_source_digest`,
  `adapter_ref`, `adapter_version`, `adapter_digest_algorithm=sha256`,
  `adapter_digest`, `output_kind` (`canonical_definition|foreign_bytes`),
  `output_digest_algorithm=sha256`, `output_digest`, optional
  `content_fingerprint` required only for `canonical_definition`,
  `report_digest_algorithm=sha256`, `report_digest`, `created_at`,
  `receipt_digest_algorithm=sha256`, and `receipt_digest`. It never contains
  `source_commitment`. `output_digest` covers canonical candidate JSON bytes
  or decoded foreign bytes; `receipt_digest` covers every preceding field.
- Adapter request (all required unless mutually exclusive):
  `schema_version=agent-interchange-adapter/v1`, `direction`, exactly one of
  `source_json`, `source_base64`, or governed `source_locator` (locator at most
  2,048 characters), `source_media_type`, `target_media_type`, and the
  core-enumerated `source_inventory` when the source is JSON. Base64 decodes to
  at most 1 MiB. Requests contain no credentials or ambient authority.
- Adapter response (all required unless conditional):
  `schema_version=agent-interchange-adapter/v1`,
  `status=converted|requires_runtime|unsupported|invalid`, `adapter_ref`,
  `adapter_version`, `adapter_digest_algorithm=sha256`, `adapter_digest`,
  `source_inventory`, and `report`. `status=converted` requires exactly one of
  `candidate_json` (canonical bytes at most 256 KiB and 64 components) or
  RFC 4648 padded `output_base64` (at most 1,398,104 ASCII characters and 1 MiB
  decoded) and forbids `error_code`. Every non-converted status forbids both
  output fields and requires `[a-z][a-z0-9_]{0,63}` `error_code`. The complete
  response is at most 2 MiB canonical JSON. The declarative mapping artifact
  is at most 128 KiB with at most 512 rules. Unknown versions, malformed or
  incomplete inventories, over-limit payloads, duplicate JSON keys,
  non-canonical base64, and ungoverned source locators fail closed before
  stage or receipt persistence.

## Open Questions

- Production usage may justify a retention shorter than the conservative
  24-hour initial deadline; lengthening it requires a new privacy review.
- Named external project adapters remain separate source-specific changes with
  current research and opposite-provider review; the conformance fixture makes
  no compatibility claim.
