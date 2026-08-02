# Cloud drain provider carrier evidence

Date: 2026-08-01 America/Los_Angeles
Environment: Windows 11, Python 3.14
Branch: `codex/cloud-drain-provider-carrier-20260802`

## Scope

The already-armed provider receipt, active execution claim, and
`launch_started` reservation now form one immutable in-process
`ProviderInvocationCarrier`. It has no public dictionary schema, refuses
pickling, verifies the content digests and exact cross-record generations, and
rejects inactive, unarmed, mismatched, over-budget, or wrong-role tuples.

The existing explicit `UniverseContext` carrier accepts this object. The three
existing router sinks—role fallback, policy routing, and judge ensemble—validate
it before auth-health, quota, or provider access. A valid carrier narrows the
route to exactly its provider, applies its finite token ceiling, never widens
fallback, bypasses policy alternatives, and converts ensemble fan-out into one
authorized invocation. Calls without a carrier retain shipped behavior.

## Verification

- RED: carrier-focused authority and router tests failed collection because
  `ProviderInvocationCarrier` did not exist.
- GREEN: 5 authority carrier tests and 6 router carrier tests passed.
- Related provider suite: 163 passed. One pre-existing mocked Claude-process
  unawaited-coroutine warning remains unrelated to this change.
- Ruff, both strict OpenSpec validations, cross-provider drift, and
  `git diff --check` passed.

## Remaining boundary

This increment remains dark: no production caller constructs the carrier, the
epoch-2 queue consumer remains disabled, and no assignment admission,
credential dereference, provider settlement, GitHub effect, or tray cutover is
enabled. The next slice must mint the carrier inside the claimed cloud attempt,
validate its frozen assignment tuple under the existing assignment owner, and
settle one conclusive provider result without rereading the authority store
under another lock.
