---
status: proposed
supersedes-storage-model-of: docs/specs/2026-04-18-paid-market-crypto-settlement.md
---

# Base Testnet Money — Scoping + Slice 0 (off-chain money loop)

**Date:** 2026-06-08
**Author:** Claude Code lead (host directive: "make money testable, using Base testnet";
"build toward the final implementation so we can reiterate from there").

## 1. Current reality — money substrate is fragmented, none of it records

Three+ disbursement surfaces existed, **none of which actually wrote the money ledger**:

- `workflow/gates/actions.py` — gate-bonus stake/unstake/release on `gate_claims`
  columns. `compute_bonus_payout` computed the 1% take but **discarded it** (returned
  in the response, wrote nothing). `#1219`-hardened (retracted claims rejected).
- `workflow/payments/escrow.py` (`escrow_locks`) — market-action lock/release/refund;
  **no fee at all**.
- `workflow/payments/schema.py` (`escrow_balance`/`pending_settlement`/`settlement_batch`/
  `transaction_log`) + `workflow/treasury/` (`treasury_balance`/`bounty_pool`/`royalty`) —
  the full settlement+treasury ledger, **written by nobody**.
- `workflow/treasury/status.py` `treasury_status` (`#906`) — **reads** exactly those
  unwritten tables.

Net: the write side filled tables the read surface ignores, the read surface read tables
nothing wrote. That gap is why "money isn't a thing yet."

`docs/specs/2026-04-18-paid-market-crypto-settlement.md` is the older spec but assumes
Postgres + RLS + Realtime; the live platform is SQLite. Its flow + on/off-chain reasoning
holds (Option A: off-chain ledger is source of truth, batched on-chain settlement later);
its data-model section is stale. Build on `workflow/payments/` + `workflow/treasury/`.

## 2. Slice 0 — the final-shaped foundation (this PR)

Per "build toward the final implementation": the final money loop needs **one
disbursement-ledger write primitive** every path calls. Built:

`workflow/payments/settlement_ledger.py`:
- `record_settlement(...)` — splits gross into net-to-recipient + 1% take (via
  `treasury.distribution.split_take`, the single split-math source: 50% treasury /
  50% bounty pool), writes `pending_settlement` + `treasury_balance` +
  `bounty_pool_balance` + `transaction_log`. Idempotent on `settlement_key`.
- `record_refund(...)` — no-fee refund, `transaction_log` audit entry only.

First consumer wired: `gates/actions.py release_bonus` — a `pass` records a settlement
(net to recipient, 1% to treasury); a `fail`/`skip` records a refund. The `#906`
`treasury_status` read surface now reflects real flow.

E2E proof (`tests/test_payments_settlement_ledger.py`): stake 1,000,000 → release pass
→ recipient nets 990,000, treasury fee 10,000 (5,000 retained + 5,000 bounty pool),
settlement recorded, `treasury_status` reflects all of it. No chain. Testable today.

## 3. Iterate from here (not in this PR)

- Migrate the other disbursement paths onto `record_settlement`: market-escrow
  (`payments/escrow.py`) and paid-bid (`bid/settlements.py`).
- Converge the lock-side models (`escrow_locks` vs `escrow_balance` vs `gate_claims`
  bonus columns) — slice 0 unified the **settlement** side only.
- **Slice 1 (on-chain):** a `settle_batch(recipient, amount) -> tx_ref` backend
  interface with `internal` (today) + `base_sepolia` (testnet USDC, platform-custodial
  wallet, batched net balances) backends. Chain choice = env/config routing, not
  architecture. Host decisions still open: asset (rec testnet USDC), custody (rec
  platform-custodial testbed), and the host-only action of creating + faucet-funding
  the Base Sepolia treasury wallet into the secrets vault.

## 4. Anti-over-engineering check

Slice 0 adds one primitive + wires one consumer, all from existing split math + tables +
read surface. No new schema, no chain code, no speculative abstraction.
