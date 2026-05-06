# Proposed: Substrate-Level Audit Log Primitive

Status: Proposed
Date: 2026-05-06
Request: Issue #443 / WIKI-DESIGN
Source wiki path: `pages/patch-requests/pr-041-substrate-level-audit-log-primitive-tamper-evident-retention.md`
Classification: project design

## Summary

Workflow needs a tamper-evident, retention-aware audit-log capability for
trust-critical state transitions and compliance evidence exports. The smallest
useful project change is to define the contract before implementation: what
must be recorded, how tamper evidence is represented, how retention works, and
what export can safely prove.

This proposal does not add a ninth engine substrate. It treats audit logging as
a cross-cutting evidence capability composed from existing substrates:

- E3 persistent checkpoint for durable run state and recovery evidence.
- E7 catalog for branch, goal, bid, gate, and public commons records.
- E8 dispatcher for request, claim, retry, and completion transitions.
- The self-auditing-tools pattern for chatbot-visible evidence plus caveats.

The irreducible gap is not "another log file." It is a standard append-only
event contract with hash chaining, retention classes, redaction boundaries, and
export manifests that every trust-critical module can share.

## Goals

1. Record trust-critical transitions in a single typed event shape.
2. Make event mutation or deletion detectable within each retained segment.
3. Preserve privacy and commons-first boundaries: private payloads stay on the
   host; platform records contain identifiers, actor references, digests,
   decisions, and caveats, not private content.
4. Support compliance-style export bundles with manifest hashes, retention
   metadata, and explicit caveats about what the export does and does not prove.
5. Keep MCP/user-facing tooling composable: chatbots can request evidence and
   narrate it, but cannot turn caveated evidence into stronger claims.

## Non-Goals

- No runtime implementation in this design pass.
- No global immutable storage guarantee. The primitive is tamper-evident, not
  tamper-proof.
- No platform-side storage of private branch content, transcripts, uploaded
  files, or raw prompts.
- No pre-baked SOC2, HIPAA, PCI, or legal-compliance mode. Those are policies
  composed by users and communities on top of the primitive.
- No convenience MCP action per audit question until the minimal-primitive test
  is rerun against the accepted tool surface.

## Proposed Event Contract

Every audit event should be a canonical JSON object before hashing:

```json
{
  "event_id": "audit_evt_...",
  "segment_id": "audit_seg_...",
  "sequence": 42,
  "occurred_at": "2026-05-06T00:00:00Z",
  "recorded_at": "2026-05-06T00:00:01Z",
  "actor": {
    "actor_type": "user|daemon|host|system|provider",
    "actor_id": "stable-id-or-pseudonym"
  },
  "surface": "mcp|api|daemon|dispatcher|catalog|payments|moderation",
  "action": "claim_request",
  "target": {
    "target_type": "request|branch|run|gate|bid|settlement|wiki_page",
    "target_id": "stable-id"
  },
  "decision": {
    "status": "accepted|rejected|updated|completed|failed",
    "reason_code": "machine-readable-reason",
    "policy_refs": ["wiki-or-plan-ref"]
  },
  "evidence_refs": [
    {
      "kind": "run|commit|artifact|log_tail|external_url",
      "ref": "stable-handle",
      "digest": "sha256:..."
    }
  ],
  "privacy": {
    "retention_class": "ephemeral|operational|compliance|legal_hold",
    "sensitivity": "public_metadata|host_private_digest|restricted",
    "redaction": "none|digest_only|field_redacted"
  },
  "prev_event_hash": "sha256:...",
  "event_hash": "sha256:..."
}
```

Hash input must exclude `event_hash` and include a canonicalized representation
of every other field. `prev_event_hash` links events within a segment. Segment
manifests link segments over rotation boundaries.

## Retention Model

Retention is a field on each event, not a directory naming convention.

| Class | Default intent | Example events | Deletion behavior |
|---|---|---|---|
| `ephemeral` | Short-lived debugging evidence | verbose provider diagnostics | prune quickly; segment manifest records pruning |
| `operational` | Normal support and abuse response | request claimed, run failed, gate changed | retain on host or platform according to surface |
| `compliance` | User/exportable accountability | settlement, moderation decision, paid claim, permission change | retain until configured compliance horizon |
| `legal_hold` | Explicit freeze | dispute, abuse investigation, host directive | no automated deletion while hold is active |

Exports must include the retention class and the configured retention horizon.
If an event was legitimately pruned, the export must say so in the caveats
rather than silently implying a complete timeline.

## Export Contract

An audit export should be a bundle, not a raw log dump:

```json
{
  "export_id": "audit_export_...",
  "created_at": "2026-05-06T00:00:00Z",
  "scope": {
    "target_type": "branch|request|run|host|date_range",
    "target_id": "..."
  },
  "included_segments": [
    {
      "segment_id": "audit_seg_...",
      "first_sequence": 1,
      "last_sequence": 100,
      "first_hash": "sha256:...",
      "last_hash": "sha256:...",
      "manifest_hash": "sha256:..."
    }
  ],
  "redactions": [
    {
      "field": "evidence_refs[2].ref",
      "reason": "host_private_digest"
    }
  ],
  "caveats": [
    "Tamper evidence is scoped to retained segments and known manifests.",
    "Digest references prove byte equality only when the referenced artifact is available.",
    "Private host payloads are represented by digests or stable handles, not content."
  ]
}
```

This shape follows the self-auditing-tools pattern: evidence and caveats stay
separate so a chatbot can compose a truthful narrative without inventing trust.

## Minimal Implementation Slices

1. Contract only: land this note and decide whether audit logging is a
   storage-level service, an event schema under `workflow/protocols.py`, or both.
2. Local append-only writer: add a canonicalization and hash-chain library with
   unit tests for stable hashing, previous-hash linkage, and corruption
   detection.
3. Retention + rotation: add segment manifests and retention pruning that
   records pruned ranges without leaking private payloads.
4. First producer: wire one high-value transition, preferably dispatcher claim
   or paid settlement, before broadening to all trust-critical surfaces.
5. Export reader: expose a self-auditing export payload through the existing API
   composition layer only if the minimal-primitive test still says the action is
   irreducible.

## Verification Gates For Implementation

- Unit tests prove canonical JSON hashing is stable across key order and fails
  on changed event fields.
- Unit tests prove chain validation detects missing, reordered, or modified
  events inside a retained segment.
- Retention tests prove pruned events leave manifest evidence and do not leak
  redacted private fields.
- Export tests prove caveats are always present and distinguish complete,
  partial, and redacted evidence.
- Public MCP acceptance, if an MCP surface is added, must use rendered chatbot
  verification with the live connector and post-fix clean-use evidence per
  `AGENTS.md`.

## Open Questions

1. Should the canonical event schema live in `workflow/protocols.py`, a new
   `workflow/audit/` package, or `workflow/storage/audit_log.py`?
2. Which transition should be the first producer: dispatcher claim, paid-market
   settlement, moderation action, or permission/config change?
3. What default retention horizons should apply to hosted platform commons vs.
   local-app host-private logs?
4. Should export bundles be signed with a host/platform key in addition to hash
   chaining, or is hash-chain plus artifact digest enough for the first slice?
5. How should cross-provider review verify claims about compliance evidence
   without importing a full compliance framework into platform policy?

## Recommendation

Accept the primitive gap as real but keep it below the substrate count: a shared
audit-log evidence contract, not a new engine substrate. The first implementable
slice should be a tiny hash-chain library plus one producer and one export path.
Anything broader risks becoming a compliance product instead of the minimal
evidence primitive Workflow needs.
