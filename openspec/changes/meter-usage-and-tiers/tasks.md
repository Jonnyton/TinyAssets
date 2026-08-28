# Tasks

## 1. Metering foundation

- [ ] 1.1 Per-universe usage ledger holding effects, compute-minutes and storage. Reuse the
      atomic `BEGIN IMMEDIATE` count-and-insert shape from `_engine_run_admit`
      (`tinyassets/engine_mcp_server.py:86-148`) — it closes a real TOCTOU race — and the
      symlink/path-escape refusal guarding that ledger.
- [ ] 1.2 Enforce effect quota through the EXISTING reservation lifecycle in
      `tinyassets/storage/external_write_receipts.py`: reserve budget in
      `try_reserve_receipt` (refusing pre-flight when exhausted), return it in
      `release_reservation`, commit it in `finalize_receipt(SUCCEEDED)`. Counting only on
      success would make the cap post-hoc on an irreversible action — an accounting record,
      not a control. Replay settles against the existing reservation, never a second one.
- [ ] 1.3 Meter compute-minutes as run subprocess wall-time per universe, recorded through
      the run executor (`tinyassets/runs.py`; 4-worker top-level pool at `:3002`).
- [ ] 1.4 Attribute run-transcript storage per universe so the storage dimension is honest
      — `api/status.py:1252-1277` currently attributes only checkpoint/log/outputs, while
      the large pools stay shared. Storage stays a **cap, not a charge** until this lands.

## 2. Tiers and enforcement

- [ ] 2.1 Tier resolved per universe supplying effect/compute/storage limits; configurable
      with documented defaults added to `docs/reference/environment-variables.md`. Free tier
      = absence of a subscription. Unresolvable tier falls back to free, never to unlimited.
- [ ] 2.2 Split the shared counter: billable effect quota (from 1.2) vs a far more generous
      compute guard on run admission. Update all four call sites — `:377`, `:884`, `:1163`,
      `:1405` — so authoring no longer starves running. Preserve the fail-open (run) /
      fail-closed (autonomous write) asymmetry from Codex ADAPT 2026-08-22 #6.
- [ ] 2.3 Refusals name the exhausted dimension and the refill time, replacing
      "try again shortly".

## 3. Billing

- [ ] 3.1 Stripe adapter reporting Billing Meter events from the ledger, keyed by the WorkOS
      `sub`. Enforce the boundary: no Stripe import outside the adapter, asserted by a test.
      Key is vault-first via `scripts/load_secrets.sh`, never committed, never in compose.
- [ ] 3.2 One $20/month subscription product plus the upgrade flow from a free universe.

## 4. Verification

- [ ] 4.1 Tests: effect meter moves only on terminal success; reads/writes/edits/failures
      leave it untouched; replay counts once; two concurrent effects at the cap admit exactly
      one. **Mutation-check every assertion can actually go red** — this repo has a history
      of green tests that cannot fail.
- [ ] 4.2 `ruff`, the 249-test outbound suite green, and plugin mirror parity
      (`python packaging/claude-plugin/build_plugin.py`).
- [ ] 4.3 Live proof through the app as a real user (`ui-test`), not via MCP: burn the run
      guard with failing attempts and confirm a **successful** post still goes through — the
      exact scenario that broke on 2026-08-28 — then confirm the effect cap stops the effect
      past the limit. Plus cross-family review via `peer-agents` before landing, required
      for an authority/public-surface change.
