# Distributed execution platform

> Canonical, always-current scope for the distributed-execution program so any AI
> reading the repo sees the whole picture in one place. The full engineering plan
> (S0–S16, authority model, vertical-slice order, anti-loss backlog) lives at
> `docs/exec-plans/active/2026-07-18-distributed-execution-platform.md`; this
> change is its OpenSpec surface and the live delivery ledger.

## Why

A universe run must be executable by an **external owner-daemon** — a
subscription-backed worker the platform never co-hosts — so the platform holds
no user compute and no ambient credentials, while still guaranteeing exactly-once,
tamper-evident results. Getting there surfaced one systemic defect class that
recurs on every authority surface (S2 lease completion, S3 identity, GitHub
review/merge, paid-market claims, blob authority):

> **Authority was being derived from mutable, INSERT-able database state** —
> append-only-but-insert-permitted event rows, unsigned row fields, thumbprints
> stored beside the key they should hash from. Eight review rounds each found a
> new axis of the same hole.

The program replaces that with one principle across all surfaces.

## What Changes

- **Unified authority derivation.** Every authority decision derives from a
  cryptographically-signed artifact or a platform re-execution. Mutable DB state
  may only **narrow, reject, or serve as audit log** — never authorize. Three
  mechanisms share one `Verified[T]` return type but not its constructor:
  **M1** platform-signature (`RecordVerifier`), **M2** content-addressing (blobs,
  git `head_sha`, digests), **M3** external re-confirmation (WorkOS JWT, GitHub
  approval, ledger settlement). Total unification was considered and rejected as
  false unification.
- **B2 authenticated execution protocol.** A daemon enrolls (device key), claims
  a job over an authenticated transport, receives a capsule-bound signed lease
  grant, executes through a narrow seam, submits a device-signed candidate plus
  content-addressed blobs, and the platform fenced-completes with a signed
  terminal attestation. Forged or stale rows/events cannot create success;
  restart replay re-derives the same terminal fact.
- **Per-domain immutable signed-field contracts.** The verifier no longer accepts
  a caller-supplied `unbound_fields` opt-out; a domain separator selects a fixed
  partition of every signed field into row-bound / specialized-validated / inert.
  Unknown domains fail closed.
- **Confined per-job execution (S0/S6–S9).** Source/node execution moves out of
  the platform process so platform secrets are never co-resident; Linux and
  Windows isolation backends; exact-source staging, revalidation, destruction.
- **Exactly-once GitHub PR effect (S10.5).** One accepted result yields exactly
  one result-bound branch and one reviewable PR across retries/crashes — no
  ambient token, no caller-selected repo, no stale-head write, no approve/merge
  authority.
- **Market execution over the same protocol (S13/S14/B3).** Deterministic market
  selection in front of the unchanged B2 path; fenced escrow, verification,
  settlement, reputation.

## Delivery model (host-approved 2026-07-20)

Un-bundled into **runnable vertical slices** (V1–V8); the dual-family review gate
is **batched pre-deploy**, not per-slice; confirmed findings become
**mutation-proven regression tests**, not review documents. This OpenSpec change
and the exec plan hold the full vision so nothing deferred out of a slice is lost.

## Impact

- New specs: `distributed-execution` capability (see `specs/`).
- Affected code: `tinyassets/runtime/{signed_records,lease_store,blob_refs,execution_capsule,execution_result,execution_plane,daemon_auth,sandbox_runner}.py`,
  `tinyassets/api/{execution_jobs,execution_transport,daemon_enrollment,runs,github_effect_actions}.py`, `tinyassets/host_pool/execution_client.py`.
- Live surfaces (WorkOS enforcement, market settlement, GitHub merge) stay
  **host-gated**: staged rollout with a bounded dual-verify window and explicit
  go/no-go per surface. Never dark-cut a live authority path autonomously.
