# Cloud drain provider carrier evidence

Date: 2026-08-01 America/Los_Angeles
Environment: Windows 11, Python 3.14
Branch: `codex/cloud-drain-provider-carrier-20260802`

## Scope

The already-armed provider receipt, active execution claim, and
`launch_started` reservation now form one immutable in-process
`ProviderInvocationCarrier`. It has no public dictionary schema, refuses
pickling, is minted only after the authority store wins the one-shot arm, and
is sealed with a process-local keyed digest. Direct construction, launch
replay, subclasses, record mutation, and second use fail closed. It verifies
the content digests and exact cross-record generations and rejects inactive,
unarmed, mismatched, over-budget, wrong-role, or wrong-operation tuples.

The existing explicit `UniverseContext` carrier accepts this object. The three
existing router sinks—role fallback, policy routing, and judge ensemble—validate
it before auth-health, quota, or provider access. A valid carrier narrows the
route to exactly its provider, applies its finite token ceiling, never widens
fallback, bypasses policy alternatives, and converts ensemble fan-out into one
authorized invocation. The caller must supply the server-classified operation;
the sink matches it against the reservation before consuming the carrier.
Calls without a carrier retain shipped behavior.

Mint and consumption state live in a process-owned locked registry rather than
inside the otherwise immutable Python object. The durable reservation digest
can enter that registry once, and an opaque sealed carrier identity can leave
the active set once. Resetting or replacing an object field therefore cannot
restore spent authority; concurrent validation has one winner.

## Verification

- RED: carrier-focused authority and router tests failed collection because
  `ProviderInvocationCarrier` did not exist.
- GREEN after independent-review repair: store-mint, replay, keyed-seal,
  one-use, role/operation, exact-type, token-ceiling, no-fallback, and no-fanout
  coverage passed.
- Exact related command on 2026-08-01:
  `$providerTests = @(Get-ChildItem -LiteralPath tests -File | Where-Object { $_.Name -eq 'test_provider_work_authority.py' -or $_.Name -eq 'test_providers.py' -or $_.Name -like 'test_provider_router*.py' } | ForEach-Object { $_.FullName }); python -m pytest @providerTests -q`
  — 153 passed. One pre-existing mocked Claude-process unawaited-coroutine
  warning (plus pytest's collection-time echo of it) remains unrelated.
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
