---
status: active
---

# Paid-Market + Crypto Settlement (Base L2 Testnet) — Track E

**Date:** 2026-04-18
**Author:** dev (task #29 pre-draft; unblocks track E when dispatched)
**Status:** Pre-draft spec. No code yet. Executable on dispatch without design re-research.
**Source of truth:**
- Memory: `project_monetization_crypto_1pct.md` (host 2026-04-18 directive — Base testnet, 1% fee, crypto-native day-one).
- Memory: `project_paid_requests_model.md` (bid market shape: requester sets node+LLM+price; daemons filter by LLM, no floor).
- Memory: `project_paid_market_trust_model.md` (cooperative trust, not stranger-marketplace; don't scope escrow/rep infra until abuse appears).
- Design note: `docs/design-notes/2026-04-18-full-platform-architecture.md` §6 (paid market), §14.7 (moderation backstop).
- Schema spec: `docs/specs/2026-04-18-full-platform-schema-sketch.md` §1.6 (`request_inbox`) + §1.7 (`ledger`).

This spec turns the host's 2026-04-18 Q4 answer (Base L2 testnet, 1% fee to treasury, crypto-native) into an executable track-E plan. Every choice optimizes for the "change tokens later without a rewrite" constraint.

---

## 1. Bid lifecycle — end-to-end state machine

```
                   ┌──────────────────────────────────────────────────┐
                   │   off-chain (Postgres)             on-chain (Base) │
                   └──────────────────────────────────────────────────┘

T1 requester:            ┌─ place_paid_request ─┐
  wallet NOT required    │  POST /v1/requests   │
  until HERE ───────────►│  with bid_amount +   │
                         │  wallet signature    │
                         └──────────┬───────────┘
                                    │
                                    ▼
                   ┌────────────────────────────────────────┐
                   │ request_inbox row                      │
                   │  state='pending'                       │
                   │  escrow_status='none' (v1 off-chain) ──┼─► [NO on-chain write yet]
                   │  OR escrow_status='held' (v2 escrow) ──┼─► [contract.lock(amount)]
                   └──────────────┬─────────────────────────┘
                                  │  Realtime push on bids:<capability_id>
                                  ▼
            ┌──────────────────────────────────────────┐
            │ qualifying daemons subscribed to channel │
            │ see row; one calls claim_request RPC     │
            └──────────────┬───────────────────────────┘
                           │
                           ▼
                   ┌────────────────────────────────┐
                   │ request_inbox row              │
                   │  state='claimed',              │
                   │  claimed_by_host=<host_id>     │
                   └──────────────┬─────────────────┘
                                  │ daemon runs the node
                                  ▼
                   ┌────────────────────────────────┐
                   │ complete_request RPC           │
                   │ state='completed',             │
                   │ deliverable stored off-chain   │
                   └──────────────┬─────────────────┘
                                  │ dispute-window timer starts
                                  ▼
                     ┌────────┴────────┐
                     │                 │
         requester accepts        window expires (auto-accept)
                     │                 │
                     └────────┬────────┘
                              ▼
            ┌──────────────────────────────────┐
            │ settle_request RPC               │
            │ compute 99/1 split ──────────────┼─► contract.transfer(daemon_wallet, 0.99*amount)
            │                                  │─► contract.transfer(treasury_addr, 0.01*amount)
            │ ledger rows inserted,            │
            │ tx_hash recorded                 │
            └──────────────────────────────────┘

(Failure path: complete_request w/ state='failed' → refund_request RPC → contract.refund(requester_wallet))
```

**Key states on `request_inbox`:**
`pending → claimed → running → completed → (accepted | disputed | auto-accepted) → settled`
**or** `pending → ... → failed → refunded`.

Each state-transition is an RPC with RLS-enforced role (requester, claimed_host, service_role for auto-accepts). No direct SQL updates.

---

## 2. On-chain vs off-chain split

**On-chain (Base L2):**
- Wallet verification at registration (one-time tx-sig proof).
- Fund lock / escrow (optional per §3 pick).
- Settlement transfer (99% → daemon wallet, 1% → treasury).
- Refund on failed completion.
- tx_hash recorded in `ledger`.

**Off-chain (Postgres):**
- Bid metadata (capability_id, deadline, signal columns).
- Request-deliverable payload (can be MBs; never on-chain).
- Dispute correspondence (messages between requester + daemon host).
- Claim races, state transitions, audit log.
- Read-model: balance views, earnings dashboards, leaderboards.

**Tradeoff note: per-bid on-chain writes are gas-expensive.** At Base L2 gas prices (~$0.05-0.15/tx in May 2026 depending on calldata size), a $0.50 bid loses 10-30% to gas — shape-breaking for micro-bids.

**Recommendation for testnet MVP: Option A (off-chain ledger + batched on-chain settlement) with a weekly cadence initially, shrinking as price signals warrant.** Justified in §3.

---

## 3. Settlement flow — three options, pick one

| Option | Flow | Gas per bid | Trust | MVP fit |
|---|---|---|---|---|
| **A. Off-chain ledger + batched on-chain payout** | Requester pre-funds balance (or credit issued); bids debit off-chain; weekly job aggregates + executes one batch transfer per daemon-host + one treasury batch | ~$0.05 amortized (~1 tx per host per week) | Low — requester trusts platform to settle; daemon trusts platform | **Ship this for testnet MVP** |
| **B. Per-bid on-chain escrow** | Bid time: contract.lock(amount). Accept time: contract.release(host, 99%) + contract.release(treasury, 1%). Failure: contract.refund(requester) | ~$0.15 × 2-3 txs per bid | Highest — funds provably escrowed | Migrate v2; defer until real-money volume justifies |
| **C. Per-bid direct transfer** | Bid time: no lock. Accept time: contract.transfer(host, 99%) + contract.transfer(treasury, 1%), requires requester's signature at settle-time | ~$0.10 per bid | Medium — requester could refuse to sign; cooperative-trust memo tolerates | Fallback if A's batched model proves too opaque |

**Recommendation: Option A.** Rationale:
- Per-bid on-chain writes (B or C) make gas > 20% of bid value for anything under ~$1. Kills micro-bid market the paid-requests model explicitly preserves ("no floor on cheap work").
- Cooperative-trust memory authorizes off-chain ledger at MVP; "don't scope escrow/rep infra until abuse appears."
- Base testnet substrate means funds aren't real anyway — batched settlement exercises the plumbing without risking user money.
- Migration path to B (mainnet) = add a smart contract, swap the settle-batch job for per-bid escrow. Ledger rows already carry all the fields needed; no data migration.

**Option A flow detail:**

```
Requester wallet (on-chain balance)
         │
         │  one-time top-up: user sends WF tokens → platform-controlled treasury-in address
         ▼
  Postgres `ledger` credits user balance
         │
         │  place_paid_request: debits ledger balance (reserve), no on-chain activity
         ▼
  request_inbox + ledger reserve row
         │
         │  accept: releases reserve → daemon-host off-chain balance + treasury off-chain balance
         ▼
  ledger shows daemon owed X, treasury owed Y
         │
         │  weekly batch-settle job:
         │  groups by (daemon wallet, chain_id), sums, calls contract.bulkTransfer()
         ▼
  on-chain txs; ledger rows updated with tx_hash + settled_at
```

**"Daemon pulls earnings" alternative:** daemons call a `request_payout` RPC whenever they want. Gas charged to the daemon (deducted from payout). Lets daemons avoid the weekly wait at their own cost. Recommend adding this as a daemon-opt alongside the default weekly batch.

---

## 4. Wallet-connect flow for tier-1 chatbot users

**Invariant:** wallet connection is ONLY required at the moment of placing a paid bid. Browse, create, collaborate, upvote, fork, remix, run free nodes — all work without a wallet. This preserves the tier-1 zero-install property.

### 4.1 Wallet connection via chatbot

New MCP tool: `connect_wallet` — returns a WalletConnect v2 URI + deep link.

```
connect_wallet() → {
  "wc_uri": "wc:abc123@2?relay-protocol=irn&symKey=...",
  "qr_code_url": "https://tinyassets.io/qr/abc123.png",
  "mobile_deep_link": "https://metamask.app.link/wc?uri=...",
  "expires_at": <unix_ts>
}
```

Chatbot presents the URI/QR to the user. User opens wallet app (Coinbase Wallet, MetaMask, Rainbow, etc.), scans, approves. The wallet signs a one-time "prove ownership" message.

Gateway receives the signed message via `verify_wallet(wc_session_id, signature)`; stores the verified address in a new `wallets` table keyed to `user_id`. Subsequent bids reference this wallet by default.

### 4.2 Bid placement (after wallet connected)

```
place_paid_request(capability_id, inputs, bid_amount_wei) →
```

Gateway:
1. Loads user's primary wallet.
2. Checks Postgres ledger balance ≥ bid_amount_wei. If yes, bid goes ahead — no signature needed per-bid (Option A model).
3. If no / insufficient balance, returns `{"kind": "insufficient_balance", "required_top_up_wei": <int>, "top_up_url": "..."}`. User tops up via a one-time on-chain transfer to the platform's treasury-in address.

### 4.3 Gas abstraction

**Recommend: platform sponsors gas for all on-chain operations on testnet.** Rationale:
- Testnet gas is free (testnet ETH is faucet-claimable) but the UX if users manage their own faucet-claim → wallet-fund → bid flow is brutal.
- At mainnet migration, evaluate Base Paymaster (user-paid gas via ERC-4337) vs platform-sponsored. Recommend user-paid on mainnet for cost reasons; platform-sponsored only for micro-txs below a gas-vs-value threshold.

Flag in §11 OPEN Q1.

---

## 5. Daemon-side earnings flow

### 5.1 Wallet registration at install

Tray install flow adds a "Register payout wallet" step (skippable for `visibility=self` or `network` hosts). Same WalletConnect flow as §4.1; same `wallets` table row keyed to the daemon host's `user_id`.

Multiple wallets per user allowed (`is_primary` flag). Switch primary from the tray UI without downtime.

### 5.2 Earnings accrual

Completed-accepted bids credit the daemon's off-chain balance. Postgres view:

```sql
CREATE VIEW public.daemon_earnings AS
SELECT
  w.user_id,
  w.address AS wallet_address,
  COALESCE(SUM(l.amount) FILTER (WHERE l.entry_kind = 'credit'), 0) AS earned_wei,
  COALESCE(SUM(l.amount) FILTER (WHERE l.entry_kind = 'payout'), 0) AS paid_out_wei,
  COALESCE(SUM(l.amount) FILTER (WHERE l.entry_kind = 'credit'), 0)
   - COALESCE(SUM(l.amount) FILTER (WHERE l.entry_kind = 'payout'), 0) AS balance_wei
FROM public.wallets w
JOIN public.ledger l ON l.user_id = w.user_id
WHERE w.is_primary = true
GROUP BY w.user_id, w.address;
```

Tray dashboard reads this view for the earnings panel.

### 5.3 Payout timing

- **Default: weekly batch.** Every Sunday 00:00 UTC, job runs `bulkSettle(wallets_with_balance_over_threshold)`. Threshold default 0.01 test-token (~$0 testnet; tunable for mainnet).
- **On-demand:** daemon calls `request_payout` RPC. Gas deducted from payout. Immediate settlement.
- **Treasury:** same weekly job splits accrued 1%-fee credits to treasury address.

---

## 6. Data model additions

Cross-refs #25 schema spec. Net-new tables + columns:

### 6.1 `wallets` (new)

```sql
CREATE TABLE public.wallets (
  wallet_id      uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id        uuid NOT NULL REFERENCES public.users(user_id),
  address        text NOT NULL,           -- 0x-prefixed, lowercased
  chain_id       int NOT NULL,            -- 84532 = Base Sepolia testnet; 8453 = Base mainnet
  is_primary     bool NOT NULL DEFAULT true,
  verified_at    timestamptz NOT NULL,    -- when sig-verify succeeded
  verify_sig     text,                    -- the one-time proof-of-ownership signature
  label          text,                    -- user-editable ("Main wallet", "Hot wallet")
  created_at     timestamptz NOT NULL DEFAULT now(),
  UNIQUE (address, chain_id),
  UNIQUE (user_id, is_primary) DEFERRABLE INITIALLY DEFERRED
);

CREATE INDEX wallets_user ON public.wallets (user_id);
```

Primary-wallet uniqueness is a partial unique index variant — only one `is_primary=true` per user:

```sql
CREATE UNIQUE INDEX wallets_one_primary_per_user
  ON public.wallets (user_id) WHERE is_primary = true;
```

### 6.2 `request_inbox` — additive columns

```sql
ALTER TABLE public.request_inbox
  ADD COLUMN requester_wallet_id uuid REFERENCES public.wallets(wallet_id),
  ADD COLUMN bid_token_addr      text,       -- ERC-20 contract address; null = native gas token
  ADD COLUMN bid_amount_wei      numeric(40,0),
  ADD COLUMN escrow_status       text NOT NULL DEFAULT 'none'
    CHECK (escrow_status IN ('none','reserved_offchain','held_onchain','released','refunded')),
  ADD COLUMN dispute_window_expires_at timestamptz,
  ADD COLUMN auto_accept_at     timestamptz; -- set at complete_request; default = complete + dispute_window
```

No existing-row backfill needed; Option A starts with `escrow_status='reserved_offchain'` on every new paid bid.

### 6.3 `ledger` — additive columns

```sql
ALTER TABLE public.ledger
  ADD COLUMN fee_amount     numeric(40,0),    -- 1% portion, on credit entries
  ADD COLUMN daemon_amount  numeric(40,0),    -- 99% portion, on credit entries
  ADD COLUMN chain_id       int,
  ADD COLUMN tx_hash        text,             -- null until on-chain settle
  ADD COLUMN settled_at     timestamptz,
  ADD COLUMN batch_id       uuid;             -- groups ledger entries in the same settle batch
```

Entry kinds extended (§1.7 has `reserve|release|debit|credit|refund|bonus|adjustment`); add `payout` and `fee`.

### 6.4 `settlement_batches` (new)

```sql
CREATE TABLE public.settlement_batches (
  batch_id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  chain_id            int NOT NULL,
  scheduled_for       timestamptz NOT NULL,
  started_at          timestamptz,
  completed_at        timestamptz,
  status              text NOT NULL DEFAULT 'scheduled'
    CHECK (status IN ('scheduled','running','completed','failed')),
  total_payout_wei    numeric(40,0) NOT NULL DEFAULT 0,
  total_fee_wei       numeric(40,0) NOT NULL DEFAULT 0,
  tx_hash             text,                   -- null until submitted
  error               text
);
```

One row per cadence run. `ledger.batch_id` FKs here.

### 6.5 `treasury_config` (new, host-admin-owned)

```sql
CREATE TABLE public.treasury_config (
  chain_id            int PRIMARY KEY,
  treasury_address    text NOT NULL,
  token_contract_addr text NOT NULL,    -- TinyAssets test-token ERC-20 address on this chain
  fee_bps             int NOT NULL DEFAULT 100,  -- 1% = 100 basis points
  min_payout_wei      numeric(40,0) NOT NULL,
  batch_cadence_hours int NOT NULL DEFAULT 168,  -- weekly default
  is_active           bool NOT NULL DEFAULT true,
  updated_at          timestamptz NOT NULL DEFAULT now()
);
```

**Load-bearing:** treasury_address, token_contract_addr, fee_bps, cadence, min_payout all runtime-editable. Switching testnet → mainnet is an `UPDATE` here plus a new row at `chain_id=8453`, NOT a code deploy. Per host directive: "moving from testnet token → mainnet token is a config change only."

---

## 7. Rate limits + abuse vectors

### 7.1 Micro-bid spam

1% fee as flat percentage is a no-op for dust bids (1% of $0.001 = $0.00001 gas-indistinguishable). Attackers can't easily skim value, but they can flood `request_inbox`, triggering Realtime fan-out on capability channels.

**Defenses:**
- **Min-bid threshold per capability** (`capabilities.min_bid_wei`). Default 0.01 test-token. Rejects lower at RPC.
- **Per-user rate limit** — max N bids/min/user (via Upstash bucket, same as §14.7 moderation backstop + gateway rate-limit from #27).
- **Account-age gate** (§14.7 memory): new accounts can't place paid bids until N days + N interactions. Cuts sock-puppet bid-spam throughput.

### 7.2 Sybil daemon-hosts winning fake bids

Attacker spins up N daemon-hosts on their own ID → own requester auto-accepts own daemon's completions → fake flow of credits masking wash trading.

**Defenses:**
- **Same-user bidding refused.** `claim_request` RPC rejects if `claimer_host.owner_user_id = request.requester_user_id`. Trivial but load-bearing.
- **One-primary-wallet-per-user** (§6.1 constraint) prevents one user from registering N daemon-host wallets to dodge.
- **Alt accounts:** mitigated by account-age + GitHub-OAuth-only auth at launch (GitHub accounts are harder to sybil than email).

### 7.3 Fake-completion cash-outs

Daemon host posts garbage deliverable, completes, requester auto-accepts via window expiry, host pockets payout.

**Defenses:**
- **Dispute window** (§8) — requester has X hours to flag after complete_request. During window, payout is reserved, not released.
- **Deliverable hashing** — `complete_request` stores sha256 of deliverable; forgery later is provable.
- **Reputation via negative signals** (existing §15.1 `negative_signals.known_failure_modes`). A daemon-host with repeated dispute-upheld entries gets filtered from the default bid-acceptance ranking.

### 7.4 Slashing — explicitly not in MVP

Per cooperative-trust memory. Dispute-upheld = refund + reputation ding, not staking-slash. Slashing becomes an OPEN flag if dispute volume > X per week.

---

## 8. Dispute resolution — lightest-touch MVP

Defer real dispute infra per cooperative-trust model. MVP shape:

1. **Dispute window** — 48h default (`capabilities.dispute_window_hours`; configurable). `complete_request` sets `request_inbox.dispute_window_expires_at = now() + capability.dispute_window`.
2. **Requester action** during window:
   - **Accept** — `accept_request` RPC. Credits daemon, queues for settle.
   - **Dispute** — `dispute_request` RPC with text reason. Flips state to `disputed`; credits stay reserved.
3. **Daemon response** to dispute — 24h to respond via `respond_to_dispute` with text + optional corrected deliverable. If daemon provides corrected work, requester has a fresh 24h acceptance window.
4. **Unresolved escalates** — expired dispute window without resolution → `host_admin_review` queue (thin admin UI; host triages manually at MVP per §14.7).
5. **Auto-accept** — window expires, no dispute filed → credits released, settlement queued. This is the default path at MVP (cooperative trust).

**Post-MVP OPEN:** formal arbitrator role (community-elected? slashing-bonded?) — flag in §11 Q5.

---

## 9. Testnet → mainnet migration path

**Config-only changes (no code deploy):**
- `treasury_config` row updated: `chain_id=8453` (Base mainnet), new `token_contract_addr`, new `treasury_address`.
- Existing testnet `treasury_config` row set `is_active=false`; preserved for historical ledger reads.
- `wallets.chain_id` filter on active primary wallets — users re-register a mainnet wallet. Their testnet wallet stays in the table marked non-primary.

**Code changes (deploy):**
- RPC `verify_wallet` checks signature against the user's wallet on the active chain. When `chain_id` switches in config, the verify check shifts.
- `settlement_batches` runner loads `treasury_config` at batch-start; same code executes against either chain.
- Contract ABI for `bulkTransfer` should be identical testnet vs mainnet (both ERC-20 transfers); verified before migration.

**Data migration:**
- Unsettled testnet balances: two options.
  - (a) Zero-out at migration — "testnet is a test, not real value." Document in terms-of-service from day one. Cleanest.
  - (b) Mirror balances to mainnet token 1:1 at migration. Generous but reinforces "testnet value" confusion.
- **Recommend (a).** Announce the migration date, let users consume balances or write off. Day-one TOS must say "testnet balances have no mainnet claim."

**Risk:** a user who top-ups testnet tokens and doesn't spend before mainnet migration loses them. Mitigation: treasury-in pre-mint is explicitly free (testnet faucet-fed), so no real-money loss.

---

## 10. Honest dev-day estimate

Navigator's §10 estimate: **1 dev-day** for track E (bids + claim + settlement wiring).

My build-out:

| Work item | Estimate |
|---|---|
| Schema additions (wallets, settlement_batches, treasury_config, ALTER request_inbox/ledger) | 0.15 d |
| WalletConnect v2 integration (gateway-side; libs handle most) | 0.4 d |
| `connect_wallet`, `verify_wallet` MCP tools + wallet proof-of-ownership sig-verify | 0.3 d |
| `place_paid_request` RPC — wallet check + ledger reserve + Realtime fan-out | 0.25 d |
| `accept_request` + `dispute_request` + `respond_to_dispute` + auto-accept cron | 0.35 d |
| `settlement_batches` runner — reads `daemon_earnings` view, builds batch, submits tx, updates ledger with tx_hash | 0.5 d |
| Solidity: deploy TinyAssets test-token (ERC-20) on Base Sepolia + treasury address + bulkTransfer contract | 0.3 d |
| Daemon tray wallet-registration flow (new tray UX) | 0.3 d |
| `earnings` dashboard view + MCP surface + tray panel | 0.2 d |
| Min-bid threshold + account-age gate + same-user-bidding-refused (§7) | 0.15 d |
| On-demand `request_payout` RPC + gas-deduct logic | 0.2 d |
| CI — deploy solidity contracts to testnet on merge, update treasury_config row | 0.2 d |
| Integration smoke: full flow end-to-end on testnet (place bid → claim → complete → accept → settle → verify tx on BaseScan) | 0.4 d |
| Docs (runbook, testnet faucet instructions for devs) | 0.15 d |
| **Total** | **~3.85 d** |

**Revision: 1 d → ~3.75-4 d.** Navigator's 1d was aggressive — it assumed "mostly Postgres + Realtime glue" without the wallet-connect integration, Solidity contract, settlement batch runner, or tray-side wallet UX. Those are real chunks.

**Defer paths** (if host wants closer to 1d):
- **Ship fully off-chain ledger only, no on-chain component** = ~0.8 d. Acceptable rationale: "testnet isn't real; ledger-only on testnet is honest." Defer wallet-connect + Solidity to mainnet-migration moment. Breaks the "crypto-native day one" memory — flag to host as a materially different direction.
- **Skip tray wallet UX (daemons can't collect earnings yet)** = drop 0.3 d. Tolerable for tier-1-heavy launch; tier-2 daemon hosts get the UX in a fast-follow.
- **Skip dispute window (accept-immediate)** = drop 0.35 d. Rolls "dispute" into post-MVP list. Cooperative-trust memo authorizes this at MVP.

**Recommend full-scope ~4 d**; the 3× overshoot is real honest work, not padding. Pushes §10 total by ~3d across all my pre-drafts (#25 +0d match, #26 +2d, #27 +1d, #29 +3d). Running total of revisions: +6d over navigator's estimates. Track's still weeks-not-months.

---

## 11. OPEN flags

| # | Question |
|---|---|
| Q1 | Gas abstraction at mainnet — platform-sponsored via Paymaster (Base supports ERC-4337) vs user-paid? Sponsored is better UX but platform cost grows linearly with bid volume. Recommend user-paid mainnet + sponsored for micro-txs under threshold. Testnet = always sponsored. |
| Q2 | Off-chain vs on-chain at testnet — my recommendation (Option A off-chain ledger + batched on-chain payouts) differs from pure "crypto-native day one" if read strictly. Host confirm: is the testnet intent "prove the on-chain contract works" (→ Option B) or "build the flow so mainnet is config-change" (→ Option A, my recommendation)? |
| Q3 | Multi-chain support — launch Base Sepolia only, or also Base mainnet + Ethereum mainnet + Arbitrum etc? Launch Base-only recommended; multi-chain is a config multiplier later. |
| Q4 | Wallet library — wagmi/viem on web + WalletConnect v2 on mobile? Many libs at 2026; pick one and stick. Recommend viem + WalletConnect. |
| Q5 | Dispute arbitration post-MVP — community-elected arbitrators? Slashing-bonded arbitrators? Host-as-sole-arbitrator forever? Deferred until dispute volume makes it real. |
| Q6 | Treasury governance — host-controlled key at MVP per memory. When to migrate to multisig / DAO? Flag when treasury balance > threshold. |
| Q7 | Fee-on-token design — is the fee always 1%, or progressive (e.g. lower for large bids, higher for micro)? Flat 1% is the memory directive; flagged in case host wants tunability. |
| Q8 | Refund semantics on `failed` completion — full refund (recommended) or partial (capability-dependent)? Memory's "default full refund; partial for degraded" is pointed at per-capability configurability; flag as `capabilities.refund_policy` column. |
| Q9 | Payout currency — always the TinyAssets token, or settle in USDC/ETH if user requests? Multi-token settle is gas-expensive and adds conversion tracking. Recommend TinyAssets-token-only at MVP. |
| Q10 | KYC/sanctions screening — needed at mainnet? On-chain tx data is public; regulatory clarity is not. Flag as "revisit before mainnet"; off-scope MVP. |

---

## 12. Acceptance criteria

Track E is done when, on Base Sepolia testnet:

1. TinyAssets test-token (ERC-20) contract deployed + address in `treasury_config`; treasury address funded with test-tokens from faucet.
2. A tier-1 user can: connect wallet via `connect_wallet` → verify via `verify_wallet` → top-up ledger balance → place a paid bid → daemon claims → daemon completes → user accepts → daemon host sees pending-payout balance → weekly batch settles → tx visible on BaseScan with 99/1 split.
3. Failure path: daemon fails → refund_request → user's ledger balance restored.
4. Dispute path: user disputes → daemon responds with correction → user accepts → settlement routes to daemon.
5. Auto-accept: user idle → window expires → settlement auto-fires.
6. `daemon_earnings` view reflects all credits + payouts correctly across a test day.
7. Sybil defense: same-user `claim_request` refused; min-bid threshold honored; account-age gate enforced on fresh accounts.
8. Integration test (one scripted flow) passes in CI against the deployed testnet contracts.
9. Migration documentation in `docs/specs/mainnet-migration-runbook.md` — confirms config-only changes for the path.
10. All 10 OPEN flags in §11 resolved or explicitly deferred.

If any of the above fails, track E is not shippable; the paid-market promise is not real without it.
