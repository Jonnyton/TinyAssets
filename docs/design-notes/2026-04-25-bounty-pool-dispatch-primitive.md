---
status: active
---

# Bounty-Pool Dispatch Primitive

**Date:** 2026-04-25
**Author:** dev-2
**Status:** Design proposal. Bookkeeper layer that consumes Task #82 substrate to distribute funds. Closes the contribution-economy loop: emit (#48 / #71 / #72 / #75 implementation) → outcome attribution (#77) → aggregation (#82) → distribution (this proposal).
**Builds on:** Task #82 §2 substrate template; Task #69 storage-auth pattern; Task #74 §4 read-only orthogonality precedent; `project_monetization_crypto_1pct` (1% fee → treasury); `project_designer_royalties_and_bounties` (50% of fee → bounty pool recursive funding); `project_paid_market_trust_model` (provenance discipline).
**Scope:** schema/contract design only. No code changes.

---

## 1. Recommendation summary

Two-table state-machine model: `bounty_pools` + `bounty_distributions`. Idempotent `dispatch_bounty_pool` MCP action drives transitions `open → locked → dispatched → closed`. Re-call on dispatched pool returns existing distributions (safe-replay).

Platform-fee deduction in dispatch flow per `project_monetization_crypto_1pct`: 1% of pool to treasury. Recursive bounty-pool funding per `project_designer_royalties_and_bounties`: 50% of treasury fee routes to system bug-bounty pool.

**Top tradeoff axis:** **state-machine clarity vs schema complexity.** 2-table model gives clear invariants (pool can only dispatch once via lock; failed-payout retry is row-level on `bounty_distributions`); 1-table-with-distributions-as-JSON would muddle audit + retry semantics. Going 2-table.

---

## 2. Schema

### `bounty_pools` table

```sql
CREATE TABLE bounty_pools (
    pool_id              TEXT PRIMARY KEY,
    pool_kind            TEXT NOT NULL,             -- enum: see §3
    funder_actor_id      TEXT NOT NULL,             -- who funded
    funder_evidence_ref  TEXT NOT NULL DEFAULT '',  -- audit pointer (chatbot session_id, txid, etc.)
    target_artifact_id   TEXT,                      -- optional; the artifact this pool rewards
    total_currency_amount REAL NOT NULL,
    currency_unit        TEXT NOT NULL,             -- "USD-test" | "WORK-token" | etc.
    window_start_ts      REAL NOT NULL,
    window_end_ts        REAL NOT NULL,
    status               TEXT NOT NULL,             -- "open" | "locked" | "dispatched" | "closed"
    platform_fee_pct     REAL NOT NULL DEFAULT 0.01,
    bounty_pool_recursion_pct REAL NOT NULL DEFAULT 0.5,
    created_at           REAL NOT NULL,
    locked_at            REAL,
    dispatched_at        REAL,
    closed_at            REAL,
    metadata_json        TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX idx_bounty_pools_status ON bounty_pools(status);
CREATE INDEX idx_bounty_pools_funder ON bounty_pools(funder_actor_id, created_at);
CREATE INDEX idx_bounty_pools_artifact ON bounty_pools(target_artifact_id);
```

### `bounty_distributions` table

```sql
CREATE TABLE bounty_distributions (
    distribution_id      TEXT PRIMARY KEY,
    pool_id              TEXT NOT NULL,
    actor_id             TEXT NOT NULL,
    actor_handle         TEXT NOT NULL DEFAULT '',
    share                REAL NOT NULL,             -- from #82 substrate, post-floor
    currency_amount      REAL NOT NULL,             -- share × distributable / total_share
    status               TEXT NOT NULL,             -- "pending" | "queued" | "paid" | "failed"
    payout_evidence_ref  TEXT,                      -- txid for crypto / batch_id for fiat
    failure_reason       TEXT,                      -- populated when status=failed
    created_at           REAL NOT NULL,
    updated_at           REAL NOT NULL,
    metadata_json        TEXT NOT NULL DEFAULT '{}',
    FOREIGN KEY (pool_id) REFERENCES bounty_pools(pool_id)
);

CREATE INDEX idx_bounty_distributions_pool ON bounty_distributions(pool_id);
CREATE INDEX idx_bounty_distributions_actor ON bounty_distributions(actor_id, created_at);
CREATE INDEX idx_bounty_distributions_status ON bounty_distributions(status);
```

### `funder_evidence_ref` rationale

Pointer to where funds came from at funding time. Chatbot session_id for chatbot-funded pools; txid for crypto-bridged transactions; system fee transaction id for platform-fee-funded recursion pools. Useful for audit/provenance + downstream reconciliation.

Cite `project_paid_market_trust_model`: at platform scale, paid-market is cooperative-trust today but provenance pointers create the substrate for abuse-detection if abuse appears later. Cheap to add now (one TEXT column); expensive to retrofit.

---

## 3. Pool-kind enum (3 values; v1 force-discipline)

Three named `pool_kind` values for v1. Force pool-type discipline early; prevent "junk pool" sprawl.

| pool_kind | Funder | Target |
|---|---|---|
| `patch_bounty` | Chatbot user funds "I'll pay $X for fix" | A specific BUG-id or patch_request artifact |
| `node_royalty` | Node-author escrow at run-time (per `project_designer_royalties_and_bounties`) | A specific node_def_id or branch_def_id |
| `outcome_reward` | Host-funded for outcome milestones (e.g. "branch attains stable for 30 days → +$X") | A specific branch_version_id |

If a chatbot wants to fund a pool that doesn't fit one of these three, they file a feature request and v2 extends the enum. v1 rejects unknown `pool_kind` values with structured error.

Not landing `operator_funded` catch-all — too vague to imply funding mechanism. Surfaced in §11 Q1 as truly-open: should v2 extend?

---

## 4. State machine + dispatch flow

### Transitions

```
   open  --(dispatch_bounty_pool, host-only)-->  locked  --(success)-->  dispatched  --(all paid)-->  closed
                                                   |                            |
                                              (5min stale)                 (failed payouts)
                                                   v                            v
                                                  open                      stays dispatched
                                              (cleanup job)              (host retries via separate action)
```

### Dispatch flow (the heart of the primitive)

1. **Lock** (atomic via SQLite WHERE):
   ```sql
   UPDATE bounty_pools
   SET status='locked', locked_at=now()
   WHERE pool_id=:pool_id AND status='open';
   ```
   Rows-affected check: 0 → pool already locked/dispatched/closed → return early with current state. Same-result safe-replay.

2. **Read substrate:** call `bounty_calc_query_template(...)` from #82 §2:
   ```python
   from workflow.attribution.bounty_calc import bounty_calc_query_template
   sql, params = bounty_calc_query_template(
       target_artifact_id=pool.target_artifact_id,
       window_start_ts=pool.window_start_ts,
       window_end_ts=pool.window_end_ts,
   )
   shares = execute(sql, params)  # returns [(actor_id, actor_handle, share), ...]
   ```

3. **Compute fee splits** using rate-snapshot fields from the pool row (NOT system defaults — see §6):
   ```python
   pool_total = pool.total_currency_amount
   treasury_take = pool_total * pool.platform_fee_pct
   bounty_pool_recursion = treasury_take * pool.bounty_pool_recursion_pct
   treasury_net = treasury_take - bounty_pool_recursion
   distributable = pool_total - treasury_take
   total_share = sum(s.share for s in shares)
   ```

4. **INSERT bounty_distributions rows** for each (actor_id, share) tuple:
   ```sql
   INSERT INTO bounty_distributions (...)
   VALUES (..., share=:share, currency_amount=:share * :distributable / :total_share, status='pending', ...)
   ```

5. **INSERT 2 system distributions:**
   - `actor_id="treasury"` with `currency_amount=treasury_net` (status='pending')
   - `actor_id="system_bounty_pool"` with `currency_amount=bounty_pool_recursion` (status='pending')
   The system_bounty_pool distribution is the recursion seed — when claimed, it funds a new `pool_kind="patch_bounty"` pool for the next bug-bounty cycle.

6. **UPDATE pool:** `status='dispatched', dispatched_at=now()`. All steps in single transaction; abort-all on failure.

7. **Return:**
   ```json
   {
     "pool_id": "...",
     "status": "dispatched",
     "distributions": [...],
     "treasury_take": ...,
     "bounty_pool_recursion": ...,
     "distributable": ...
   }
   ```

### Cleanup of stale locks

A pool stuck in `status='locked'` for >5 min indicates a crashed dispatch attempt. A separate cleanup job (out of scope here; named in §12) auto-resets to `open` so dispatch can retry. v1 has no auto-cleanup; host manually resets via direct DB update or future `extensions action=unlock_pool` (v2).

### Idempotency

Re-calling `dispatch_bounty_pool` on a `dispatched` pool: read bounty_distributions for that pool_id, return existing rows (no new INSERT). Pure safe-replay. The state-machine + atomic-lock at step 1 makes this trivially correct.

---

## 5. MCP surface

### `extensions action=dispatch_bounty_pool` (host-only WRITE)

```
extensions action=dispatch_bounty_pool
  pool_id <required, str>
  → returns {pool_id, status, distributions, treasury_take, bounty_pool_recursion, distributable}
```

Authority: gates on new `check_dispatch_authority(actor_id)` in `tinyassets/storage/authority.py` (per #69 pattern). Host-only per `project_monetization_crypto_1pct` "Treasury = host-controlled for now."

```python
# tinyassets/storage/authority.py — new check function
def check_dispatch_authority(base_path, actor_id) -> None:
    if actor_id != _host_actor():
        raise AuthorizationError(
            actor_id, "dispatch bounty pool",
            f"bounty pool dispatch is host-only (per project_monetization_crypto_1pct); host actor is {_host_actor()!r}",
        )
```

### `extensions action=create_bounty_pool` (write — funded by various actors)

```
extensions action=create_bounty_pool
  pool_kind <required, str>          # one of "patch_bounty" | "node_royalty" | "outcome_reward"
  total_currency_amount <required, float>
  currency_unit <required, str>
  window_seconds <int> = 86400
  target_artifact_id <optional, str>
  funder_evidence_ref <optional, str>   # auto-set to chatbot session_id for chatbot funders
  → returns {pool_id, status: "open", ...}
```

Authority: any authenticated actor can create a pool (they're funding it, after all). Storage-auth check is permissive — `check_create_pool_authority` only rejects anonymous callers (per #66 / #74 no-anonymous-default discipline).

### Read-side actions (read-only, no auth check)

- `extensions action=get_pool pool_id=<id>` — pool state + distributions (if dispatched).
- `extensions action=list_pools status=<filter>?` — list with optional status filter.

Read-only orthogonality with #69 storage-auth per #74 §4 precedent.

---

## 6. Rate-snapshot at funding time (intentional immutability)

`platform_fee_pct` and `bounty_pool_recursion_pct` are stored as **per-pool columns**, NOT read from system defaults at dispatch time. This is intentional immutability:

The pool was funded at the rates active when funded. The pool is dispatched at the rates baked in at funding time. A chatbot that funded a pool at 1% fee in 2026 does NOT see their fee retroactively raised to 2% if governance changes the system default in 2027.

### Why this matters

- **Trust:** funders bet their money on a known fee structure. Retroactive rate changes break the trust contract.
- **Audit:** when a pool dispatches in 2027 with `platform_fee_pct=0.01`, the historical record shows the rate that was in effect at funding.
- **Governance flexibility:** the system default CAN change without breaking historical pools. Future governance votes adjust system defaults; old pools retain their original rates.

### How it's implemented

`extensions action=create_bounty_pool` reads system defaults at creation time (`os.environ.get("TINYASSETS_PLATFORM_FEE_PCT", "0.01")` etc.) and copies them into the pool row. The pool row is the source of truth from then on. Dispatch reads from the pool row, not from env.

This is the kind of "obvious-to-implementer-non-obvious-to-future-reader" decision that should be documented up front so a future maintainer doesn't "fix" the redundancy by removing the per-pool columns.

---

## 7. MCP intent disambiguation — host vs chatbot

`dispatch_bounty_pool` is a **HOST-action**. Chatbot-callable variants would be misuse.

When a chatbot user asks "pay out the bounty," the chatbot should:

1. Call `extensions action=get_pool` (read-side) to fetch the pool state.
2. Render the pool state with visualization (per chatbot visuals-first rule):
   - Pool status (open / locked / dispatched / closed)
   - Total currency
   - Funder
   - Window
   - Top-N expected distributions if dispatched (or "preview shares" if not)
3. **Tell the user:** "this pool dispatch is a host action; ask the host to run `extensions action=dispatch_bounty_pool pool_id=...`."
4. **NEVER auto-call dispatch.** The MCP action layer rejects non-host callers with structured `AuthorizationError` per §5; chatbot should not even try.

This composes with the project memory `project_chatbot_assumes_workflow_ux` — chatbots aggressively assume workflow context for ambiguous user intent, but **money-moving operations are the explicit exception**. Dispatch is irreversible (currency leaves the pool); the friction of "ask the host" is correct.

---

## 8. Composition with sibling proposals

### Task #82 substrate

Dispatcher CALLS `bounty_calc_query_template(...)` from `tinyassets/attribution/bounty_calc.py` directly. No string-construct SQL. Substrate stays currency-agnostic per #82 §11 Q5; dispatcher applies `pool_total_currency × share / total_share` for each distribution. Hard dependency.

### Task #77 outcome events

Outcome events DO NOT trigger pool dispatch. They modulate per-actor shares INSIDE the #82 substrate query. So when `dispatch_bounty_pool` runs the substrate query, outcome events flow through automatically:
- `outcome_stable` (+3) increases an actor's share via the SUM
- `outcome_rolled_back` (-10) decreases, then floor-at-zero per #82 §4

Pool dispatch fires on its OWN cadence (manual host-trigger v1, scheduled v2). Reading the substrate at dispatch time picks up whatever outcome events have accumulated by then.

### Task #69 storage-auth

`dispatch_bounty_pool` is write-side (creates pools + distributions rows). Gates on `check_dispatch_authority(actor_id)` — host-only. Read-side `get_pool` / `list_pools` are read-only; no auth check needed (per #74 §4 orthogonality precedent).

### Task #66 / #74 — orthogonal

PatchNotes / author_patch_notes don't interact with bounty-pool layer. Bounty pools reference `target_artifact_id` (branch_version_id, etc.); PatchNotes data lives elsewhere.

### `project_monetization_crypto_1pct` (1% fee → treasury)

Platform fee at line 11. Default `platform_fee_pct=0.01` matches verbatim.

### `project_designer_royalties_and_bounties` (50% of fee → bounty pool)

Recursive bounty-pool funding: 50% of treasury fee routes to system bug-bounty pool. Default `bounty_pool_recursion_pct=0.5` matches.

### `project_paid_market_trust_model` (provenance)

Cited for `funder_evidence_ref` rationale: at platform scale, paid-market is cooperative-trust today but provenance pointers create the substrate for abuse-detection if abuse appears later.

---

## 9. State invariants (must hold at all times)

1. **Pool can only be dispatched once.** Atomic lock at step 1 of dispatch flow guarantees this.
2. **Dispatched pool has at least 2 system distributions** (treasury + system_bounty_pool) PLUS one row per actor with positive share.
3. **Sum of distributions' currency_amounts ≤ pool.total_currency_amount.** Floor-at-zero from #82 + fee deduction guarantees no over-distribution.
4. **A locked pool is either being dispatched (in-flight) or stale (>5min).** Stale → cleanup job resets to open.
5. **A closed pool has all distributions in terminal state** (`paid` or `failed` with explicit no-retry decision).

These invariants drive integration tests; design must enforce all 5 at SQL + handler level.

---

## 10. Tests footprint preview

`tests/test_bounty_pool_dispatch.py`, ~10-12 tests:

- **Lock atomicity:** concurrent dispatch_bounty_pool calls — one wins, others see status=locked.
- **State transitions:** open → locked → dispatched succeeds; locked → dispatched fails (re-call returns existing).
- **Dispatched-pool re-call:** safe-replay returns identical distributions.
- **Fee math:** treasury_take = total × platform_fee_pct; bounty_pool_recursion = treasury_take × recursion_pct.
- **Rate-snapshot immutability:** create pool at fee_pct=0.01; change env to 0.02; dispatch still uses 0.01.
- **3 pool_kind values accepted; "operator_funded" rejected** (forces v1 discipline).
- **Funder evidence ref preserved** through dispatch.
- **Authority:** host-only dispatch rejects non-host callers.
- **Anonymous create rejected** per discussion in §5.
- **System distributions present** after dispatch (treasury + system_bounty_pool rows exist).
- **Floor-at-zero shares** (per #82 §4) NOT included in distributions (zero-currency rows skipped).
- **Failed payout** stays in `status='failed'` with `failure_reason`; pool stays `dispatched`.

---

## 11. Open questions

1. **v2 extending pool_kind enum.** RECOMMENDED v1: 3 kinds only (`patch_bounty`/`node_royalty`/`outcome_reward`). Truly open whether v2 should add `operator_funded` (catch-all) or stay disciplined and require chatbot to file a feature request for new pool kinds. Recommend stay disciplined — junk-pool sprawl is harder to clean up later than to prevent now.

2. **Dispatch scheduling.** RECOMMENDED v1: manual host-trigger only via MCP action. Truly open: auto-fire on window-expires (cron-bounded) is v2. Reasoning: dispatch is high-stakes (real currency moves); v1 wants explicit host-in-the-loop.

3. **Failed payouts.** RECOMMENDED: stays at `status='failed'` with `failure_reason`. Truly open: time-bounded auto-route to treasury after N days unclaimed. Recommend NO auto-route — host explicitly resolves via separate `extensions action=retry_distribution` v2 action. Funds remain logically allocated.

4. **Negative shares (debt-tracking).** RECOMMENDED: aligned with #82 §11 Q2 — v1 floor at zero. If v2 opens negative-shares, separate `bounty_debt` table tracks actor-level debt across pools. Cite #82 §11 Q2 as governing decision; this proposal inherits.

5. **Cross-pool composition.** TRULY OPEN. Single dispatch event spanning multiple pools (e.g., "branch_version landed cleanly, distribute from BOTH royalty pool AND outcome-reward pool")? RECOMMENDED v1: NO — each `dispatch_bounty_pool` call is one-pool. Multi-pool dispatch is v2 via "dispatch group" primitive.

---

## 12. What this proposal does NOT cover

- **No code changes.** Design only; lead routes implementation as separate dispatch.
- **No payout execution layer.** Distributions go to `status='pending'`; an external payout-queue (crypto-bridge, fiat-batcher, etc.) drains pending rows and updates status. Out of scope here.
- **No `retry_distribution` action.** v2 follow-up.
- **No `unlock_pool` action.** Stale-lock cleanup is v2 cron; v1 host-manual via direct DB.
- **No multi-pool dispatch.** §11 Q5 v2 deferral.
- **No debt-tracking.** §11 Q4 v2 conditional on #82 Q2.
- **No currency-conversion logic.** Each pool has one `currency_unit`; cross-currency pools are v2.
- **No DAO governance hooks.** v2 when DAO substrate ships per `project_dao_evolution_weighted_votes`.

---

## 13. References

- Substrate (hard dep): `docs/design-notes/2026-04-25-bounty-calc-query-substrate.md` (Task #82) — `bounty_calc_query_template(...)` + 3-actor canonical fixture.
- Outcome composability: `docs/design-notes/2026-04-25-outcome-attribution-primitive.md` (Task #77) — outcome events modulate shares via #82.
- Storage-auth pattern: `docs/design-notes/2026-04-25-storage-auth-refactor-proposal.md` (Task #69) — `check_dispatch_authority` lives in policy module.
- Read-only orthogonality precedent: `docs/design-notes/2026-04-25-author-patch-notes-mcp-wrapper.md` (Task #74) §4.
- Convention adherence: `docs/design-notes/2026-04-25-design-proposal-pattern-convention.md` — 5-move pattern.
- Companion principles:
  - `project_monetization_crypto_1pct` — 1% fee → treasury (drives `platform_fee_pct` default).
  - `project_designer_royalties_and_bounties` — 50% of fee → bounty pool (drives `bounty_pool_recursion_pct` default).
  - `project_paid_market_trust_model` — provenance discipline (drives `funder_evidence_ref` field).
  - `project_chatbot_assumes_workflow_ux` — explicit exception for money-moving operations (§7 dispatch is host-action).
- Existing dispatch + auth patterns (engine integration points):
  - `_action_extensions_*` registry for `dispatch_bounty_pool` / `create_bounty_pool` / `get_pool` / `list_pools`.
  - `_current_actor()` for `funder_actor_id` server-set per #74 precedent.
  - `_host_actor()` from `tinyassets/storage/authority.py` per #69 pattern (after #69 ships).
- Adopts grep-anchored references per #77 line-drift fix lesson — this proposal cites docs by section, not exact line numbers.
