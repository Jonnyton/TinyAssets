## 1. Review gate

- [ ] 1.1 Get a cross-family (Codex) refute of this proposal and design, attacking Q1 (request-scoped authority on replay) and D6 (at-most-once). Fold in its findings before any code.

## 2. Hold and inbox

- [ ] 2.1 `scripts/turns_in_flight.py` takes `--hold`, and `deploy/wait_for_turns.sh` sets it after `TURN_HOLD_AFTER_S`. The marker is cleared after the swap rather than before it, so the clear moves to a post-canary step.
- [ ] 2.2 Add a `deferred_turns` store (D3): an idempotent enqueue, a claim that names its boot, settle, and a drain that runs in `created_at` order. Tests cover every state transition and the account-deletion sweep.
- [ ] 2.3 Split `converse` into its caller-facing part and `_served_turn` (D5) with no behaviour change. The existing converse tests stay green.
- [ ] 2.4 Admission (D2/D4/D8): under a live hold, enqueue, record the founder row and the queued notice, and return the queued reply. Tests use a real marker, a refused-auth case, and an expired-marker case.

## 3. Replay

- [ ] 3.1 The boot drainer runs after `reconcile_orphaned_turns` and also on a 30s timer when no hold is set (Q2). It re-checks authority (D5), runs `_served_turn`, records the reply, and settles each row. A row claimed under another boot settles `interrupted` (D6).
- [ ] 3.2 Tests: a queued message is answered once; replay is idempotent across two drains; a crash between claim and settle ends `interrupted`, never re-run; a changed home ends `failed` with a notice.

## 4. Proof

- [ ] 4.1 Extend the Linux repro: a held turn arrives during the wait, the swap happens, and the new daemon answers it in the thread.
- [ ] 4.2 Live: during a real production deploy hold, send a message through the app and see it answered after the swap (`ui-test`).
- [ ] 4.3 Sync `uptime-and-alarms`, then archive.
