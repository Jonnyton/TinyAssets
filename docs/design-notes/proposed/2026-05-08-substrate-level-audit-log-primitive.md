---
title: Substrate-Level Audit Log Primitive
date: 2026-05-08
author: codex-wiki-design
status: proposed
request_id: WIKI-DESIGN
github_issue: 443
wiki_source: pages/patch-requests/pr-041-substrate-level-audit-log-primitive-tamper-evident-retention.md
scope: design-only; no runtime code in this branch
classification: project-design
builds_on:
  - PLAN.md#state-and-artifacts
  - PLAN.md#api-and-mcp-interface
  - docs/specs/2026-04-19-connectors-two-way-tool-integration.md#audit-log
  - docs/specs/2026-04-18-full-platform-schema-sketch.md#node_activity
  - docs/specs/2026-04-18-daemon-host-tray-changes.md#audit-log-tab-in-tray
---

# Substrate-Level Audit Log Primitive

## 1. Recommendation Summary

Add a substrate audit log primitive as the shared event spine for compliance
evidence, trust debugging, and daemon accountability. V1 should not add a new
chatbot-visible MCP action. It should define the durable storage, retention,
tamper-evidence, and export contract that existing and future surfaces can
write through.

Workflow already has several local audit shapes: connector audit logs,
append-only `node_activity`, routing events, run transcripts, and settlement
records. The gap is that these are surface-specific records, not a single
substrate contract with common integrity, retention, redaction, and export
rules. The smallest useful project change is to standardize the shared event
shape and the rules that each surface must satisfy before implementation.

## 2. Design Goals

1. **Tamper-evident, not tamper-proof theater.** The log should make deletion,
   mutation, and history rewrite detectable through a hash chain and external
   anchors. It should not claim legal immutability unless deployed on a WORM or
   equivalent storage layer.
2. **Retention-aware by construction.** Every event carries a retention class,
   expiry timestamp, and redaction policy. Retention is a first-class field, not
   a cleanup script side effect.
3. **Payload-minimizing.** Audit rows store metadata, references, hashes, and
   result states. Private payloads, provider tokens, prompts, and customer data
   are not stored in plaintext by default.
4. **Exportable as evidence.** A user, host, checker, or compliance workflow can
   produce a bounded export bundle with the relevant events, hash-chain proof,
   anchor receipts, and caveats.
5. **Composable across existing surfaces.** Connector pushes, routing decisions,
   node edits, bids, moderation decisions, deploy actions, and daemon loop
   handoffs should use one substrate contract even when they keep specialized
   read models.

## 3. Event Shape

The substrate table should be append-only and write-only outside controlled
platform functions:

```sql
CREATE TABLE public.substrate_audit_events (
  event_id bigserial PRIMARY KEY,
  stream_id text NOT NULL,
  actor_ref text NOT NULL,
  subject_ref text NULL,
  event_kind text NOT NULL,
  event_version int NOT NULL DEFAULT 1,
  occurred_at timestamptz NOT NULL DEFAULT now(),
  source_surface text NOT NULL,
  result_status text NOT NULL,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  payload_digest text NULL,
  previous_event_digest text NULL,
  event_digest text NOT NULL,
  retention_class text NOT NULL,
  expires_at timestamptz NULL,
  redaction_state text NOT NULL DEFAULT 'active',
  anchor_batch_id text NULL
);
```

Field intent:

- `stream_id` is the chain boundary. Examples: `user:<id>`, `universe:<id>`,
  `daemon:<id>`, `issue:<number>`, or `deploy:prod`.
- `actor_ref` and `subject_ref` are stable references, not necessarily raw
  database UUIDs. They can point to users, daemons, service accounts, issues,
  branches, nodes, or connectors.
- `event_kind` is typed and versioned. Free-text audit messages belong in
  `metadata.reason`, not in the event type.
- `payload_digest` records a hash of any external evidence object without
  storing the object itself.
- `previous_event_digest` and `event_digest` form the per-stream hash chain.
- `retention_class`, `expires_at`, and `redaction_state` let reapers enforce
  retention without losing proof that an event once existed.

The event digest should cover the canonical JSON form of every immutable field
plus `previous_event_digest`. Fields that may change for retention, such as
`redaction_state`, must be outside the immutable digest or represented through
new redaction events instead of updates. Recommendation: prefer redaction
events and keep original rows immutable except for storage-layer archival
markers.

## 4. Integrity Model

V1 tamper evidence should use three layers:

1. **Per-stream hash chains.** Every event links to the previous digest in the
   same `stream_id`. A missing or edited row breaks the chain.
2. **Batch anchors.** A scheduled job groups recent event digests into a Merkle
   root and publishes the root to at least one append-only external surface:
   GitHub release artifact, signed git commit, object storage with versioning,
   or another host-independent anchor.
3. **Export verification.** Every export includes the event rows, the local
   chain path, the batch root proof, and the external anchor reference. The
   verifier can prove that exported rows match an anchored root without trusting
   the live database.

This is intentionally weaker than a blockchain claim and stronger than an
ordinary database audit table. It matches Workflow's current operating model:
GitHub, Postgres, daemon logs, and deployment artifacts are already the
coordination spine.

## 5. Retention And Redaction

Default retention classes should be explicit and conservative:

| Retention class | Example events | Default retention | Notes |
|---|---|---:|---|
| `operational` | routing decisions, dispatch handoffs, tool metadata | 30 days | Enough for debugging normal failures |
| `trust` | connector writes, node edits, moderation actions | 1 year | User-visible accountability |
| `regulated` | regulated-universe routing, compliance-relevant consent | 7 years or host policy | Disabled until regulated tier ships |
| `security` | auth changes, key revocation, admin actions | 1 year minimum | May be longer by deployment policy |
| `ephemeral_debug` | opt-in debug metadata | 7 days | Requires explicit user/session opt-in |

Retention should delete or archive payload-adjacent evidence before metadata.
When a row must be removed, the reaper should emit a `retention_pruned` event
that preserves the original `event_digest`, retention class, and prune reason.
That keeps the chain explainable without retaining sensitive content forever.

No event class may store provider tokens, raw prompts, private node payloads, or
connector payloads in plaintext by default. This preserves the existing
connector audit principle: metadata is logged, payload content is not.

## 6. Export Contract

An evidence export is a bounded bundle, not a database dump:

```json
{
  "schema_version": "1",
  "exported_at": "2026-05-08T00:00:00Z",
  "scope": {"stream_id": "universe:...", "since": "...", "until": "..."},
  "events": [],
  "redactions": [],
  "chain_proofs": [],
  "anchor_receipts": [],
  "caveats": []
}
```

Required caveats:

- Whether the export is complete for the requested scope.
- Which retention policies may have pruned older evidence.
- Which payloads are represented only by digest or external reference.
- Which external anchors were checked, and at what time.
- Whether the export was produced from production, staging, local, or a restored
  backup.

The export path should start as an internal script or admin endpoint. A
chatbot-visible read/export tool can be added later only if a user-facing
workflow requires it. For v1, the public MCP surface should not grow merely to
expose an operator/compliance maintenance path.

## 7. Composition With Existing Work

- **Connector audit log:** keep `connector_audit_log` as a specialized read
  model or compatibility view, but make connector writes emit substrate audit
  events with `source_surface='connector'`.
- **`node_activity`:** remains the activity/counter source. High-value
  mutations such as create, edit, fork, moderation, converge, and deprecate
  should also map to substrate events when trust or compliance evidence matters.
- **Routing audit tab:** `daemon_routing_events` can remain optimized for the
  tray/dashboard, with substrate events providing integrity and export proof.
- **Run transcripts:** transcripts are artifacts with separate retention. The
  audit event should store transcript handle, digest, size, and retention class,
  not duplicate transcript content.
- **Settlements and bids:** settlement records should emit substrate events for
  claim, completion, dispute, payout, and evidence export boundaries.
- **Moderation:** moderation actions should be first-class audit events because
  they are user-trust and abuse-response evidence.

## 8. Implementation Sketch

Step 0: add a schema/spec update that names `substrate_audit_events`, event
types, retention classes, and export bundle schema. This proposed note is the
design scoping step, not the runtime implementation.

Step 1: implement an append-only writer helper that canonicalizes metadata,
computes event digests, enforces payload bans, assigns retention fields, and
serializes events through one platform-side path.

Step 2: add the first adapters for low-risk, already-audited surfaces:
connector writes and routing decisions. Keep existing tables or views so no UI
or tool has to migrate in the same change.

Step 3: add anchor batching and export verification. Do not claim compliance
evidence until an export bundle can be independently verified against an
external anchor.

Step 4: broaden to node edits, bid/settlement events, moderation, and deploy
events after the first two adapters prove the shape.

## 9. Gate Requirements

Any implementation branch should include:

1. Unit tests for canonical event digest stability and hash-chain linkage.
2. Tests that payload-like fields are rejected or reduced to digests.
3. Retention tests for expiry assignment and prune-event behavior.
4. Export verifier tests that detect missing, edited, and reordered events.
5. RLS/security tests proving users can only read permitted audit scopes.
6. A migration/backfill plan for existing audit tables, even if backfill is
   deferred.
7. Opposite-family checker review before runtime code lands, because this is a
   trust and compliance substrate.

## 10. Open Questions

1. Which external anchor should ship first? Recommendation: signed git commit
   or GitHub release artifact, because both fit the current GitHub-centered
   coordination model.
2. Are retention defaults host-configurable from day one? Recommendation: yes
   for longer retention, no for shorter than the class minimum.
3. Should regulated-tier retention be enabled before the regulated user tier
   exists? Recommendation: define the class now, but do not route users into it
   until export verification and access controls are proven.
4. Should every read action be audited? Recommendation: no for v1. Audit
   mutations, external writes, routing decisions, auth/security changes,
   moderation, and compliance exports. Sample or summarize reads unless a
   regulated tier explicitly requires full read logs.
5. Should the primitive replace existing surface-specific tables? Recommendation:
   no. Use it as the integrity/export spine and let product surfaces keep
   optimized read models.

## References

- `PLAN.md` State And Artifacts
- `PLAN.md` API And MCP Interface
- `docs/specs/2026-04-19-connectors-two-way-tool-integration.md`
- `docs/specs/2026-04-18-full-platform-schema-sketch.md`
- `docs/specs/2026-04-18-daemon-host-tray-changes.md`
- `docs/design-notes/2026-04-19-self-auditing-tools.md`
