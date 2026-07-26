## Why

The reviewed `harden-production-load-evidence` change defines TinyAssets'
shared concurrency/load evidence contract, but no shared implementation exists.
The only current harness is capability-local operator-admission evidence. It
does not provide the versioned registry, immutable digest tree, recomputation,
privacy enforcement, environment fingerprint, or failure-first rollup that
every uptime capability needs before it can honestly claim scale.

This dependent change turns the reviewed contract into one reusable protocol
implementation without taking ownership of any capability's workload,
threshold, adapter, invariant, or activation decision.

## What Changes

- Specify a bounded, closed, versioned protocol implementation under the
  future `tests/load/_protocol/` package and document its operator contract in
  `tests/load/README.md`.
- Require canonical serialization, content-addressed raw artifacts and
  manifests, write-once finalization, exact digest-tree verification, and
  superseding runs instead of evidence mutation.
- Require a versioned scenario registry, stable fail-closed validation codes,
  failure-first rollup, independent recomputation of universal counts and
  percentiles, and typed/digest-bound validation of owner-executed oracle,
  fault, reconciliation, threshold, and baseline results.
- Prevent false capacity proof from mock/shaped substrates, empty required
  selections, denominator truncation, coordinated omission, generator
  saturation, dirty or mismatched deployments, and mixed-substrate aggregate
  laundering.
- Require synthetic and pseudonymized durable evidence, bounded artifact
  paths, no symlink/reparse traversal, and typed owner-supplied receipts for
  environment isolation, provider/model-dispatch tripwires, authorization,
  abort, canary coordination, and cleanup.
- Keep all generator launch, egress control, tripwire execution, cleanup,
  lockout, connector traffic, and baseline execution in separately accepted
  capability-owner adoption changes.
- Keep unavailable PostgreSQL, Realtime, fleet, settlement, provider, and
  fault-control scenarios explicitly `not_run`; protocol conformance never
  converts them into capacity proof.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `production-load-evidence`: Define the executable protocol boundary,
  canonical artifact publication and verification behavior, stable validation
  failures, isolation controls, and the dependency gates for the first
  provider-free connector baseline.

## Impact

This lane changes only target OpenSpec and its scope review. Future apply work
may claim `tests/load/_protocol/**`, `tests/load/README.md`, and focused
protocol tests only after all overlapping `tests/` claims release or narrow.
Capability-owned adapters—including the landed operator-admission harness and
any connector baseline—stay outside the shared package.

No public route, MCP handle, provider call, deployment, production database,
identity, credential, or load environment changes here. A live canonical
`/mcp` baseline remains a separate host-authorized execution gate and must not
consume Jonathan's OpenAI/Anthropic limits or platform-maintainer quota.
