## Why

PR #1440 landed a pure, conservation-checked paid-market core, but no live adapter persists its matches or settlement postings. The prototype migration directory also has ambiguous numbering and no applied-migration ledger, so enabling migrations 006–008 as-is could apply the right rules in the wrong order or more than once.

## What Changes

- Add a Wave 2 transport contract that keeps `tinyassets.paid_market` I/O-free while adapters persist claims and settlements.
- Require offer selection through `match.best_execution`; transport code may not reimplement or replace the matcher with a greedy policy.
- Require every value movement to be derived by the pure ledger adapters and committed through one database RPC/transaction that combines business-state compare-and-set, body-bound idempotency, `market.apply_tx()`, and `market.assert_drained()` for every escrow/collateral account. Reusing a key with different canonical postings SHALL conflict.
- Require authenticated, authorized actors at money boundaries; the environment-fallback actor is not money-path authority.
- Harden the `SECURITY DEFINER` boundary with a fixed search path, non-login owner, explicit execute revocation from public/user roles, a dedicated internal caller, bounded payloads, and actor-to-account binding.
- Make the v0 fixture history unambiguous and replay-safe, then require a read-only inventory and host-approved production-native Supabase baseline before the token-normalization, forwards, or double-entry ledger migrations can be enabled. Prototype SQL SHALL NOT be promoted as production authority.
- Keep `public.ledger` frozen as v1 history, keep the paid market default-off, and prohibit applying the new migration chain to live data as part of this change.
- Keep adapters and migration scaffolding dark until distributed-execution S14/B36 provides fence-bound accepted-result authority and a host-approved cutover. The platform SHALL remain non-custodial; Base escrow owns funds, while PostgreSQL records bounded settlement intent/accounting and cannot independently trigger a live payout.
- Add concurrency, idempotency, conservation, contention, migration-replay, and load-test acceptance gates required for 24/7 zero-host operation.

## Capabilities

### New Capabilities

- None.

### Modified Capabilities

- `paid-market-economy`: Replace the as-built “pure core only” limitation with the required claim/settle transport boundary, hardened actor authority, idempotent persistence, production-native migration prerequisites, and fail-closed enablement behavior.

## Impact

- Future implementation: paid-market transport/adapters, an injected RPC boundary, PostgreSQL RPC/grants, a v0 fixture runner, a production schema audit and host-approved production-native migration lane, focused unit/integration/concurrency/load tests, and the packaged runtime mirror where production code is mirrored. Live price discovery remains owned by the dependent `paid-market-live-price-discovery` successor.
- Operational: no live migration, claim/settle activation, on-chain payout, or feature-flag enablement occurs in this proposal; a later apply lane depends on distributed-execution S14/B36 and host-approved dual-verify/cutover, with reviewed migration, rollback, canary, and load evidence before rollout.
- Compatibility: `public.ledger` remains byte-for-byte historical; callers gain no alternate money writer or compatibility shim.
