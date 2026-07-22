# Token Naming And Test-Currency Boundary

Date: 2026-04-29
Status: Accepted by host directive

## Decision

The real currency reference for public Workflow messaging is `Destiny (tiny)`.
The symbol is `tiny`.

Workflow's current roadmap must touch only `test tiny` on Base Sepolia until a later real-currency integration phase is explicitly opened. Real-token contract addresses may appear as reference-only anchors so the site and docs do not need a naming rewrite when integration becomes real.

## Source

The Base contract address `0x0BB570E30f0b3C5D909C08e3316Dade9C1Dc7fE0` resolves publicly as Destiny with ticker TINY. The contract constructor also encodes the ERC-20 name/symbol as Destiny/tiny. Sources used during the naming pass:

- BaseScan: https://basescan.org/token/0x0BB570E30f0b3C5D909C08e3316Dade9C1Dc7fE0
- Coinbase asset page: https://www.coinbase.com/price/base-destiny

## Canonical Terms

| Term | Meaning | Use |
|---|---|---|
| `Destiny (tiny)` | Real currency reference | Public/legal copy when naming the real asset |
| `tiny` | Real symbol/ticker | Symbol, governance copy, later real-token settlement |
| `test tiny` | Workflow test currency | Current paid-market and settlement testing on Base Sepolia |
| `Base Sepolia` | Current Workflow test chain | Any current Workflow token interaction |
| `Tiny Assets` | Site/org/brand context | Brand references only, not the token name |
| `ta` | Legacy alias | Do not use in active public copy except historical notes |

## Product Boundary

- Current Workflow surfaces may model bids, settlement, staking, fee splits, payouts, and governance using `test tiny` only.
- Public copy must not imply Workflow currently pays, stakes, custodies, or governs with mainnet `Destiny (tiny)`.
- Real contract addresses are reference-only until the real-currency integration phase is opened and separately approved.
- The naming should already match the live currency so launch messaging does not split into "test name" and "real name."
