---
status: proposed
depends-on: docs/design-notes/proposed/2026-06-08-base-testnet-money-scoping.md (Slice 0)
---

# Base Testnet Money — Slice 1 (on-chain Base Sepolia settlement)

**Date:** 2026-06-08
**Author:** Claude Code lead (host directive: money on Base testnet).

## 1. Premise (inherited from Slice 0)

Slice 0 made the **off-chain ledger the source of truth**: `record_settlement`
credits a recipient's off-chain spendable budget (`staker_escrow_budget`) and
accrues the 1% to `treasury_balance`. Slice 1 does **not** settle every release
on-chain (per-tx gas would exceed any sub-$1 amount). Slice 1 is a **withdrawal
bridge**: accumulated off-chain balance → real testnet USDC via batched on-chain
transfers from a platform-custodial wallet. (This is the 2026-04-18 spec's
Option A — the implementation that makes testnet→mainnet a config change.)

## 2. Grounded testnet facts (verified 2026-06-08)

- **Chain:** Base Sepolia, chainId **84532** (OP-Stack L2, gas paid in ETH).
- **Asset:** Circle official testnet **USDC = `0x036CbD53842c5426634e7929541eC2318f3dCF7e`**,
  **6 decimals**.
- **Clean mapping:** USDC's 6 decimals == our `MicroToken` (1_000_000 / Token).
  So **1 MicroToken ↔ 1 USDC base unit, 1:1, no conversion math.**
- **RPC:** public `https://sepolia.base.org`, or Alchemy / Coinbase Developer
  Platform for reliability.
- **Faucets:** Coinbase Developer Platform (0.1 ETH / 24h + USDC), Circle USDC faucet.

Sources: developers.circle.com/stablecoins/usdc-contract-addresses;
docs.base.org/base-chain/network-information/network-faucets.

## 3. Components

1. **Settlement-backend interface** — `settle_batch(recipient_wallet, amount_base_units) -> tx_ref`.
   Backends selected by env `WORKFLOW_SETTLEMENT_BACKEND`:
   - `internal` (default): marks settled, `tx_ref` = local id. No behavior change.
   - `base_sepolia`: ERC-20 USDC transfer; `tx_ref` = on-chain tx hash.
2. **Payout-wallet registry** — `actor_id → (address, chain_id)`. New `payout_wallet`
   table + self-serve `escrow_set_wallet` action (recipient registers their address).
3. **On-chain client** — thin `web3.py` module: build/sign/send ERC-20 transfer from
   the custodial key, poll receipt, return tx hash. The ONLY external/on-chain code,
   isolated behind the backend interface (internal mode imports no web3).
4. **Withdraw action** — `escrow_withdraw`: a recipient settles their off-chain
   spendable balance on-chain. On success: `settle_batch` → debit off-chain balance
   + write `settlement_batch` row + tx_hash. On-demand (testnet MVP), not a cron.
5. **Config / secrets** — custodial key in vault (`WORKFLOW_BASE_SEPOLIA_KEY`), USDC
   contract addr, RPC URL, `min_payout`, chain_id. All env/config → testnet→mainnet
   is a config change, not a code deploy.

## 4. Slices (build order)

- **Slice 1a (PR-able now, zero network):** backend interface + wallet registry +
  `escrow_withdraw` action + a **mock** `base_sepolia` client + unit tests proving
  withdraw debits the off-chain balance, calls the backend, records `tx_ref`.
  `internal` stays default → no behavior change for existing flows.
- **Slice 1b (real testnet):** real `web3.py` `base_sepolia` client + a live
  acceptance test against Base Sepolia (host-funded wallet) showing a USDC transfer
  on BaseScan. Gated on the host-action (wallet) + opposite-provider review +
  the `web3.py` dependency.

## 5. Host decisions (product / strategy / external — your call)

1. **Asset** = testnet USDC (rec; 1:1 MicroToken mapping). Confirm.
2. **Custody** = platform-custodial treasury wallet (rec for testnet). Confirm.
3. **Wallet binding** = self-serve `escrow_set_wallet` action. Confirm shape.
4. **Settlement trigger** = on-demand `escrow_withdraw` (rec) vs periodic batch cron.
5. **Library** = add `web3.py` dependency. Confirm OK.
6. **host-action (only you):** create the Base Sepolia wallet, faucet-fund ETH (gas)
   + USDC, store the key in the secrets vault; pick the RPC (public `sepolia.base.org`
   vs an Alchemy/Coinbase key). I cannot hold keys or fund a wallet.

## 6. Anti-over-engineering + review gate

Slice 1a adds no network calls and no real dependency (mock client); `internal`
default = zero behavior change. Defer (all carried in the 2026-04-18 spec, none
needed for testnet withdrawal): per-bid on-chain escrow, multi-chain, user-paid gas
(custodial sender pays trivially on testnet), dispute arbitration.

**Review gate:** Slice 1b is on-chain code touching money + an external network —
exactly the class that needs **opposite-provider (Codex) review before build/push/
rollout** per AGENTS.md research/external-action norms. 1a is internal substrate +
mock and can proceed without that gate.
