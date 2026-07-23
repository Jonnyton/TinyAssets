## Why

PR #1440 landed a pure, conservation-checked paid-market core, but no live adapter persists its matches or settlement postings. The prototype migration directory also has ambiguous numbering and no applied-migration ledger, so enabling migrations 006–008 as-is could apply the right rules in the wrong order or more than once.

## What Changes

- Add a Wave 2 transport contract that keeps `tinyassets.paid_market` I/O-free while adapters persist claims and settlements.
- Require offer selection through `match.best_execution`; transport code may not reimplement or replace the matcher with a greedy policy.
- Require every logical accounting transition to be derived by the pure ledger adapters and committed through one database RPC/transaction that combines business-state compare-and-set, body-bound idempotency, `market.apply_tx()`, and `market.assert_drained()` for every logical reservation/collateral account. Reusing a key with different canonical postings SHALL conflict; a balanced database transaction never proves real-fund authority.
- Require authenticated, authorized actors at money boundaries; the environment-fallback actor is not money-path authority.
- Harden the `SECURITY DEFINER` boundary with a fixed search path, non-login owner, explicit execute revocation from public/user roles, a dedicated internal caller, bounded payloads, and actor-to-account binding.
- Make the v0 fixture history unambiguous and replay-safe, then require a read-only inventory and host-approved production-native Supabase baseline before the token-normalization, forwards, or double-entry ledger migrations can be enabled. Prototype SQL SHALL NOT be promoted as production authority.
- Keep `public.ledger` frozen as v1 history, keep the paid market default-off, and prohibit applying the new migration chain to live data as part of this change.
- Keep adapters and migration scaffolding dark until distributed-execution S14/B36 provides fence-bound accepted-result authority, the required §18.6 hybrid chain-settlement successor supplies separately verified wallet/chain receipts, and a host-approved cutover completes. The platform SHALL remain non-custodial: user-owned wallets remain the source of real-fund authority, PostgreSQL records only bounded logical reservation/accounting intent, and Wave 2 adds no signer, payout dispatcher, or smart-contract escrow.
- Add concurrency, idempotency, conservation, contention, migration-replay, and load-test acceptance gates required for 24/7 zero-host operation.

## Capabilities

### New Capabilities

- None.

### Modified Capabilities

- `paid-market-economy`: Replace the as-built “pure core only” limitation with the required claim/settle transport boundary, hardened actor authority, idempotent persistence, production-native migration prerequisites, and fail-closed enablement behavior.

## Impact

- Future implementation: paid-market transport/adapters, an injected RPC boundary, PostgreSQL RPC/grants, a v0 fixture runner, a production schema audit and host-approved production-native migration lane, focused unit/integration/concurrency/load tests, and the packaged runtime mirror where production code is mirrored. This change is the sole successor owner of the umbrella transaction delta; live price discovery remains owned by the dependent `paid-market-live-price-discovery` successor.
- Operational: no live migration, claim/settle activation, on-chain payout, or feature-flag enablement occurs in this proposal; a later apply lane depends on distributed-execution S14/B36, a separately reviewed successor implementing the locked §18.6 hybrid settlement posture without importing escrow into Wave 2, and host-approved dual-verify/cutover, with reviewed migration, rollback, canary, and load evidence before rollout.
- Compatibility: `public.ledger` remains byte-for-byte historical; callers gain no alternate money writer or compatibility shim.
