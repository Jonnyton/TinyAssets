# Dark provider-work ledger core

Date: 2026-07-31 America/Los_Angeles / 2026-08-01 UTC
Environment: Windows worktree `wf-cloud-drain-provider-issuance`

## Verdict

This slice adds an inert durable ledger core for one requester-owned
`universe_work` provider attempt. A trusted server resolver can narrow one
exact current `ProviderWorkBinding` into a typed receipt; one worker/runtime can
claim it; and the claim can reserve bounded invocation ordinals. None of these
records is bearer authority, and this slice has no provider carrier, credential
resolver, launch transition, external effect, or rollout-gate mutation.

The main-universe cloud drain is not live. The tray remains its only executor,
provider-authority V2 remains dark, and the epoch-2 cloud consumer remains
disabled.

## Closed authority flow

1. A runtime-checked server-owned resolver returns exact principal, universe,
   Branch version, physical work item, operation, role, executor, binding, and
   budget facts. The public production store exposes no direct receipt-issue
   method.
2. Receipt insertion revalidates the complete current active binding inside
   the same `BEGIN IMMEDIATE` transaction, including generation, digest,
   revocation, assignment, provider, credential-reference digest, allowed
   operation/role, expiry, and ceilings.
3. The physical receipt key is `(universe_id, work_item_kind, work_item_id)`.
   Concurrent equivalent issuance creates one record and replays it; changed
   authority conflicts instead of replacing it.
4. Claim insertion validates the exact active receipt and binding. Concurrent
   distinct workers produce one winner; the same request replays. An expired
   claim becomes stale and is not renewed implicitly.
5. Reservation insertion revalidates receipt, binding, claim generation,
   nonce-derived claim digest, worker lease, operation, and role under one
   transaction. Concurrent callers receive unique ordinals while aggregate
   invocation, token, and cost reservations never exceed the receipt ceilings.

Persisted receipt, claim, and reservation JSON is strict-schema,
content-digested, and checked against indexed columns on every read. Tampering
fails closed. IDs, digests, nonces, serialized rows, queue identity, and worker
identity cannot call a provider or resolve a credential in this slice.

## Deliberate remaining gates

- Only the `universe_work` variant and initial active/reserved states are
  implemented. `maintainer_maintenance`, heartbeat/invalidation, launch-start,
  settlement, cancellation, reconciliation, and ambiguous-attempt fencing
  remain with the provider-authority change.
- The trusted resolver seam has no production background implementation yet.
  A production requester-owned provider binding still requires the canonical
  provider-assignment and credential-custody owners; this slice does not invent
  them or expose fixture installation.
- Branch/target authority is resolved before the provider-ledger transaction
  because it is independently owned. Before any future `launch_started`
  transition, the composition must revalidate that authority just in time and
  block on unreadable or changed lineage.
- No receipt or reservation reaches the existing provider router. Carrier
  integration, receipt enforcement, rollout canaries, task 1.2 composition,
  and tray-to-cloud cutover remain later reviewed slices.

## Fresh verification

Verified 2026-07-31 America/Los_Angeles:

- `python -m pytest tests/test_provider_work_authority.py -q` — 34 passed.
- Related cloud continuation, user-owned automation, background authority,
  activation, and epoch-2 admission regression suite — 483 passed.
- Ruff and format checks on the domain, storage, and focused test — clean.
- `git diff --check` — clean.
- Strict validation of `harden-background-provider-execution-authority` and
  `activate-main-universe-spec-drain` — valid.

The host-approved same-provider fallback independently reviewed exact head
`064c5f81fd7701dc756cddf4edacdabff37096f3` after two ADAPT rounds closed the
public transaction issuance/claim/reservation bypasses. Final verdict:
`APPROVE`, with no blocking or nonblocking findings.
