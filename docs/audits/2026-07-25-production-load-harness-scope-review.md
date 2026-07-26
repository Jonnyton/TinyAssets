# Production Load Harness Scope Review

Date: 2026-07-25
Provider: Codex GPT-5.6 with three independent read-only reviewers
Main evidence base: `origin/main@8ec01ab34802f349d4ca97527c0aaed0633da11c`
Lane: `codex/implement-production-load-harness-20260725`
Disposition: target-only OpenSpec; no runtime, public load, or capacity authority

## Decision

The smallest shared dependency is a production-load **evidence protocol**, not
a generic load generator and not a live baseline. It implements the active
`production-load-evidence` contract and is consumed by capability-owned
workloads later.

Shared ownership:

- closed versioned registry and manifest shapes;
- RFC 8785 canonical bytes and SHA-256 digest tree;
- rooted atomic write-once artifact publication;
- allowlisted environment fingerprint shape;
- universal population/percentile recomputation, typed owner-result validation,
  and failure-first rollup;
- generic oracle/fault/reconciliation result interfaces;
- shared blocking-code registry and owner namespaces;
- offline conformance tests and protocol-only README.

Capability-local ownership:

- scenario identity/version and required/applicable classification;
- equivalence profile, workload, population, arrival model, seed, and payload;
- thresholds, adapter behavior, invariant predicates, injected faults,
  reconciliation semantics, baseline selection, and activation.

## Current Runtime Evidence

`origin/main` contains exactly two files under `tests/load/`:

- `operator_admission_v2.py`
- `operator_admission_v2_fixture.py`

They are owner-local operator-admission evidence. The harness defaults to 400
v2 workers, 100 v1 workers, 100 status readers, plus one maintenance process:
601 processes, despite help text saying 600. It emits useful per-process sorted
compact JSONL with monotonic and wall clocks, but it does not emit a common
manifest, environment fingerprint, digest tree, independent denominator or
percentile recomputation, resource/saturation evidence, reconciliation,
authorization, cleanup receipt, or protocol verdict.

The fixture's absolute database path, unbounded status snapshot, and
capability-local identifiers are unsafe as shared durable evidence. The owner
may later wrap its raw stream through a separately claimed adoption change; the
shared lane must not edit these files or inherit their record shape.

Historical Track J is superseded and is not implementation authority. Draft PR
#1695 is future scenario/topology planning that should consume this protocol,
not define a competing manifest or verdict system.

## Exact Future Runtime Boundary

After broad `tests/` claims release or narrow:

- `tests/load/_protocol/__init__.py`
- `tests/load/_protocol/schema.py`
- `tests/load/_protocol/artifacts.py`
- `tests/load/_protocol/environment.py`
- `tests/load/_protocol/rollup.py`
- `tests/load/README.md`
- `tests/test_production_load_protocol.py`

The surface is registry load, manifest validate/canonicalize/write, artifact
verify, safe fingerprint collect, scenario/aggregate evaluate, and an offline
Python API that cannot invoke an adapter.

The implementation uses standard library plus the existing direct `rfc8785`
dependency. Artifact storage stays injected and local for conformance. It does
not select a production backend or default to `output/`; a real scenario
without accepted custody/retention remains `not_run`.

## Collision And Dependency Evidence

- The OpenSpec-only change directory and this audit path are collision-free.
- Runtime is blocked by broad active `tests/` claims owned by the
  universe-personification relay and outbound-boundary lanes. That mechanical
  claim remains binding even though neither specifically owns `tests/load/`.
- `test-identity-and-reset`, two ordinary authorization-server-issued test
  subjects, the private alias roster, identity fingerprint key, and accepted
  closed-world cleanup block a live connector baseline, not offline protocol
  conformance.
- The host must approve the isolated canonical `/mcp` environment, provider-free
  traffic envelope, abort thresholds, and canary window before public load.
- PostgreSQL, Realtime, fleet, settlement, and fault-control owners must supply
  their real substrates and adapters. Until then their scenarios are
  machine-readable `not_run`.
- Provider-invoking paths also require requester BYOC or accepted-market
  authority and provider-attempt receipts. Jonathan's and platform-maintainer
  quotas are never load sources.
- No current `origin/main` workflow runs the general pytest suite. Draft PR
  #1502 is stale and failing; CI rehabilitation is a separate lane.

## Security And Evidence-Integrity Gates

- Canonical bytes and the complete referenced artifact tree are recomputed;
  summaries are never trusted.
- V1 pins exact scenario/command/argv/blocker registries, selection and gate-set
  records, bundle membership, aggregate/validation/safety records, trust sets,
  receipt envelopes, nested manifest records, and raw event/fault/
  reconciliation shapes. Protocol errors, capacity verdicts, and safety
  disposition are separate axes.
- Production passes require accepted independent capture sources, including a
  service-side receipt/log for cross-checkable counts; a self-authored
  internally consistent bundle remains shaped or `not_run`. Independence means
  distinct authenticated trust domains.
- Finalized evidence is immutable. Corrections use `supersedes`.
- Absolute/parent/alternate-stream paths, symlinks, junctions/reparse points,
  unexpected hard links, root escape, mutation, missing/extra artifacts, and
  digest collisions fail closed.
- Raw populations retain unsuccessful and lost operations. Offered and
  achieved load, planned/actual send time, client queueing, generator
  saturation, and clock skew prevent survivorship and coordinated-omission
  claims.
- V1 result-defining evidence is inspectable closed-schema JSON/JSONL. Opaque
  diagnostics cannot satisfy privacy or recomputation gates without an
  accepted versioned scanner.
- Evidence excludes raw identities, content, tokens, credentials, ambient
  provider homes, arbitrary environment values, and local paths. Counts and
  hashes are access-classified and bind enforced backend policy, retention,
  export/delete behavior, and access-control proof.
- Deployment pseudonyms bind an accepted PRF scheme/version/domain and key
  fingerprint; plain hashes are not accepted identities. Dirty-tree identity
  covers relevant generated and untracked executed code without retaining diff
  contents.
- Owner adoption changes provide typed receipts for allowlisted child
  environments and server-side provider/model pre-dispatch tripwires. The
  shared kernel validates them but launches no process or traffic.
- Authorization selects `provider_free`, `requester_byoc`, or
  `accepted_market`; full-interval receipts distinguish authorized,
  unauthorized, and maintainer-authority attempts. Jonathan's and platform
  maintainer quotas are never accepted user/load authority.
- Each scenario-registry entry pins one custody mode and accepted backend
  policy digest; artifact leaves cannot self-select a different custody or
  retention policy.
- Live authorization binds exact environment, window, envelope, identities,
  endpoints, scenarios, aborts, canary, and cleanup. CI cannot select live
  production by default.
- Host authorization and a distinct operator-domain local opt-in are separate.
  Provider-attempt and canary evidence must cover authenticated traffic start
  through stop; exhaustive dispatch receipts reconcile to retry-aware sent
  attempt events. A pre-run zero receipt is insufficient.
- Owner adoption cleanup uses the accepted scoped reset plan/lease/allowlist,
  preserves foreign/shared/credential-bearing/obligated state, emits immutable
  cleanup evidence, and durably locks out later runs on residue. The shared
  kernel validates those receipts but performs no cleanup or lockout.
- Protocol conformance stays distinct from capacity verdicts. Empty,
  unavailable, mock, or shaped evidence cannot produce false green.
- Invalid post-traffic evidence has null capacity and a separate
  `unknown_locked` safety disposition; trusted violation/residue evidence is
  `failed_locked`. Unidentifiable malformed input is `unresolved`, never safe.

## Review And Publication Gate

The target change requires strict validation and independent
correctness/security/concurrency/evidence-integrity review. Literal Claude
Opus 5 approved clean current-main commit `6eb585e1` at delta-spec SHA-256
`F4FA76A5FB49B73C7D79284A0BD1D52AA7B948B2AC44A041E17101FED65765DC`,
but that verdict is superseded rather than reused: a subsequent independent
review found authorization-expiry, stop-before-drain, overlapping-overshoot,
provider-authority, scenario-custody, cleanup-truth, and superseded-run binding
defects.

The adapted packet now:

- bounds every send interval and actual send by authorization expiry;
- keeps stop and provider/canary coverage open through resource release;
- aggregates overlapping overshoot against one run-wide allowance;
- represents provider-free, requester-BYOC, and accepted-market authority
  while rejecting any maintainer-funded or unbound attempt;
- pins scenario custody/backend policy and the superseded run identifier; and
- distinguishes authenticated cleanup failure from missing/invalid proof.

The adapted delta-spec SHA-256 is
`9BC1A85E62643A4877F61F7C32E03E5B4FA87027C9659FD4961A2751143DB412`.
Strict validation passes 48/48. Fresh independent and literal Opus 5 approval
of this exact adapted packet remains required before push or apply. No runtime
or live traffic is authorized.
