## Context

PR #2137 separated provider-carrier minting into a record-only grant issuer and
a grant-consuming carrier constructor. The issuer verifies record shape and a
public content digest but has no durable-store provenance, so a caller can
derive a fresh reservation identity, recompute the digest, issue its own grant,
and validate an unaccounted provider call. The carrier is dark, but activation
would turn this into a provider-spend authority bypass.

The correction must preserve the existing durable one-winner arm and router
carrier seam. It must not introduce a second provider sink, public bearer, new
database schema, provider call, or activation.

## Goals / Non-Goals

**Goals:**

- Make a committed store-arm transition the only source of mint proof.
- Bind proof and carrier use to one reservation digest, one use, and one PID.
- Fail before copied post-fork locks can be acquired.
- Publish registry entries only after weakref cleanup exists.
- Preserve canonical/package parity and existing router behavior.

**Non-Goals:**

- Enable the dark background-provider runtime or cloud cutover.
- Complete settlement, cancellation, credential dereference, or assignment
  admission.
- Treat arbitrary code already executing inside trusted TinyAssets modules as
  a sandbox boundary; Engine OS remains the owner for untrusted code.

## Decisions

### 1. The store issues an opaque proof after commit

`ProviderInvocationReservationWriteResult` carries an internal, non-repr
`mint_proof` only for an `APPLIED` arm. `SQLiteProviderWorkAuthorityStore`
creates that proof after its transaction context exits successfully. The proof
type and active registry live in the storage module, so the provider-authority
model no longer exposes any record-to-grant issuer.

The proof registry maps a random identity to the exact armed reservation
digest and issuer PID. Carrier minting requires the exact proof type and
atomically consumes that registry entry before publishing the carrier.

Alternatives rejected:

- A keyed digest over the public reservation still requires a callable
  record-to-grant issuer and recreates the exploit.
- A process-lifetime set keyed only by reservation digest cannot distinguish a
  store-committed arm from a recomputed forged record.
- Reverting the entire PR would also remove legitimate dark ledger and router
  work; the bounded correction can restore the actual missing provenance.

### 2. PID is part of both proof and carrier authority

Mint proof consumption checks the current PID before its registry lock.
Carriers freeze their issuer PID into the keyed seal and check it before their
registry lock. A forked child therefore fails closed without touching locks
copied from a possibly concurrent parent.

### 3. Cleanup precedes registry publication

Proofs and carriers are fully populated and receive their weakref finalizer
before their random identity is added to an active registry. If construction
or finalizer installation fails, no live authority entry exists. Tests use
explicit garbage collection rather than assuming CPython refcount timing.

## Risks / Trade-offs

- **[Risk] The proof is process-local and cannot support a later process
  handoff.** → The parent OpenSpec already assigns cross-process envelopes to a
  separate one-use claim contract; this carrier remains in-process only.
- **[Risk] A committed arm whose proof is abandoned consumes its launch slot.**
  → This is the existing fail-closed ambiguous-launch rule; recovery and
  settlement remain with the parent authority change.
- **[Risk] Python module privacy is not an untrusted-code sandbox.** → No
  record-only issuer remains, exact types and active identities are required,
  and untrusted execution stays outside this process under Engine OS.

## Migration Plan

1. Keep activation and cutover paused.
2. Land the forged-record regression red on the merged head.
3. Replace record-issued grants with post-commit store proofs and PID-bound
   carrier validation in canonical and packaged runtimes.
4. Run focused, concurrency, parity, and strict OpenSpec checks.
5. Sync/archive the delta and obtain fresh independent approval of the exact
   final head before merge.
6. Verify the merged main head before the cloud lane may resume.

Rollback is a targeted revert of this correction while activation remains
paused; if exact-head review rejects the design, revert the carrier portion of
PR #2137 instead of enabling the vulnerable path.

## Open Questions

None for this bounded correction. Cross-process carrier handoff and durable
result settlement remain explicitly owned by the parent authority change.
