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

Foreign formats are not added to the canonical validator. Keeping one native
shape avoids a growing format enum and makes every adapter replaceable.

### 2. Foreign imports are sanitized private stages, not publications

A foreign import creates an actor-owned `AgentImportStage`. The request's raw
source is bounded and processed without being written to the database or
application logs. Durable stage content contains only:

- the sanitized canonical candidate;
- source format/media metadata and a SHA-256 digest of the raw bounded input;
- adapter identity, semantic version, and immutable artifact digest;
- a structured `ConversionReport`;
- a content-bound `ConversionReceipt`;
- status, actor ownership, timestamps, and optional resulting definition ID.

The stage never contains recovered credential values or an executable runtime
snapshot. Items requiring private configuration become typed placeholders in
the candidate and `requires_private_binding` report entries. Publishing and
binding remain two explicit, independently authorized operations. Successful
conversion therefore cannot surprise a user by exposing or activating an
agent.

Persisting the raw foreign document was rejected because the current control
plane is not a general secret vault and inspection does not require retaining
the secret-bearing bytes.

### 3. Reports are exhaustive and machine-readable

Each relevant source item receives one terminal classification:
`preserved`, `normalized`, `unsupported`, `omitted_secret`,
`requires_private_binding`, or `requires_runtime`. Entries carry a stable
source path, optional canonical target path, safe reason code, and bounded
non-secret detail. The report also declares whether the conversion is
lossless; that flag is true only when every item is `preserved` and the
canonical round-trip fingerprint proves equality.

Safe unknown objects are retained under bounded namespaced extension keys.
Silently discarding an unknown field or collapsing it into prose was rejected
because it prevents honest round-trip and power-user editing.

### 4. Receipts bind source, adapter, output, and report

The receipt is canonical JSON containing a schema version, source digest,
adapter identity/version/digest, direction, canonical candidate fingerprint or
foreign-output digest, report digest, and creation time. Its receipt digest is
SHA-256 over all preceding receipt fields. Any adapter revision therefore
produces distinct provenance even when output happens to match.

Receipts contain hashes and safe identifiers only. They are evidence of what
ran, not an authority token, signature, execution attestation, or proof that a
foreign project endorses the conversion.

### 5. Adapters conform to a protocol and compose from governed primitives

`agent-interchange-adapter/v1` defines bounded JSON input/output envelopes for
`import` and `export`. Adapter references resolve immutable public artifact
versions. Where conversion requires executable code, the adapter runs only as
an admitted Engine OS workload with no ambient credentials, universe
authority, network entitlement, or provider access. Its output is untrusted
until the canonical validator and report validator pass.

The platform may ship the protocol runner and canonical native adapter, but
foreign adapters are ordinary public, remixable, evaluable commons artifacts,
preferably immutable Branch workflows. A registry table or built-in list of
named external formats was rejected.

### 6. Universal remix extends the existing verified lineage transaction

The existing `publish_definition` transaction remains the sole publisher. It
resolves parent definition/component pairs without comparing parent author to
child author, validates shares and depth, and writes the child plus lineage
atomically. Interchange adds tests proving parents from independent actors can
be selected together, that newly authored residual content is credited to the
child author, and that unresolved imported origins remain informational.

Import stages do not create verified lineage. Only explicit publication can
resolve declared origins against the current local commons and write verified
edges.

### 7. Existing graph handles carry explicit operations

The public surface continues to use `read_graph` and `write_graph` targets for
agents. The agent write target gains explicit staged-import, publish-stage,
remix, and export-conversion operations only where the current payload is
insufficient; private stage reads require the authenticated stage owner.
Responses are bounded structured documents suitable for chatbot inspection.

A new `agents` tool was rejected because interchange is a graph-artifact
operation and the canonical live surface must remain exactly seven handles.

### 8. Storage is additive and retry-safe

Add SQLite tables for import stages and immutable conversion receipts beside
the existing custom-agent tables. A non-empty idempotency key is unique per
actor, operation, source digest, direction, and adapter digest. Repeating an
identical request returns the original stage/receipt; reuse with different
content fails. Publish-stage delegates to the existing author-scoped publish
idempotency transaction.

No data migration or compatibility shim is needed. Existing canonical import
continues as the native fast path, while foreign sources use the staged path.

## Risks / Trade-offs

- **[Secret detection is necessarily incomplete]** → reject known
  secret-bearing keys recursively, classify credential-shaped values and
  authority-bearing fields conservatively, never persist raw foreign input,
  and prove absence in database rows, reports, receipts, errors, and logs.
- **[A malicious adapter can lie about preservation]** → treat its report as
  untrusted, independently validate paths/categories/digests, recompute native
  fingerprints, and reserve `lossless=true` for verifier-proven equality.
- **[Namespaced extensions can become an opaque dumping ground]** → bound
  total canonical size, component count, nesting, keys, and per-entry report
  count under the existing definition limits.
- **[Adapter execution may not yet be available]** → preserve adapter
  references and return `requires_runtime`; do not fall back to in-process
  execution or claim conversion succeeded.
- **[Stages can accumulate private metadata]** → support bounded pagination
  and a retention policy that deletes sanitized candidates and receipts only
  after their documented evidence lifetime; never infer deletion of a
  published immutable definition.
- **[Concurrent publish can duplicate work]** → use SQLite transactions,
  uniqueness constraints, and the existing definition idempotency boundary.

## Migration Plan

1. Land `universe-custom-agents` and sync its canonical capability before this
   change archives.
2. Add red domain tests for native round-trip, cross-user blend, sanitization,
   report/receipt integrity, idempotency, and concurrency.
3. Add the additive staging/receipt schema and pure validators with foreign
   adapter execution disabled by default.
4. Add API and graph-target operations, preserving the seven-handle manifest.
5. Admit executable adapters only through the Engine OS gate; ship no
   in-process fallback.
6. Deploy, run focused/load/security gates and the public canary, then complete
   a rendered chatbot import → inspect → blend → publish → bind → export flow.

Rollback removes the new routing operations and adapter admission while
leaving additive stage/receipt rows inert for forward repair. It never deletes
published definitions or private bindings.

## Open Questions

- What bounded retention duration should apply to sanitized abandoned import
  stages after production usage data exists?
- Which first foreign adapter should be used solely as end-to-end proof? The
  choice does not create a maintained starter or format catalog and requires
  source-specific review if it targets a named external project.
