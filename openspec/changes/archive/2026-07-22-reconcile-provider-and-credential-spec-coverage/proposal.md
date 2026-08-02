## Why

The full-coverage audit found shipped provider and credential behavior that is
not represented in the canonical capability specs. The omissions hide the
provider call contract, Codex refresh-viability quarantine, status/cooldown
evidence, and the ordinary-path guard for a universe without its own
credential. It also hides two shipped leakage limitations: partial overlays and
unexpected non-validation overlay errors can retain host subscription values.

## What Changes

- Extend `provider-routing` with the common provider request/response contract
  and explicit per-universe call context used across synchronous and
  asynchronous routing.
- Specify provider registration, quota/cooldown tracking, effective-chain
  diagnostics, and the best-effort cooldown evidence exposed by `get_status`.
- Specify conservative subscription-auth health, including Codex's layered
  presence/freshness/cached-live-probe verdict and its worker/status split.
- Extend `credential-vault` with the shipped subprocess environment behavior:
  the no-credential ordinary path strips host subscription auth, while partial
  overlays and swallowed unexpected errors can retain it.
- Record current limitations rather than target behavior: provider health and
  cooldowns are process-local except for Codex's shared verdict file,
  `get_status` never launches a live Codex probe, the viability ladder can be
  disabled, inconclusive probes do not quarantine a writer, and the credential
  overlay is not fail-closed on partial or unexpected-error paths.

## Capabilities

### New Capabilities

<!-- none -->

### Modified Capabilities

- `provider-routing`: add the shipped provider envelopes, explicit universe
  context, availability/cooldown diagnostics, and subscription-auth health and
  status contracts.
- `credential-vault`: add host-subscription stripping and its current partial-
  overlay and unexpected-error limitations for universe-scoped subprocesses.

## Impact

- Delta specs under
  `openspec/changes/reconcile-provider-and-credential-spec-coverage/specs/`,
  later synced into the two existing canonical capability specs.
- No runtime, API, storage, deployment, website, or test behavior changes.
- Current source and focused tests are evidence only; pending `R2-1a`
  allowlist work is not claimed as shipped and must be rechecked before sync.
