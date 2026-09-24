## 1. Shape

- [x] 1.1 Short design: pre-start durable ticket, reuse of the pool database, event-driven hand-off

## 2. Implementation

- [x] 2.1 `workspace_waiters` table and ticket helpers (enqueue, position, turn, remove) in `workspace_pool`
- [x] 2.2 FIFO in `_acquire_lock`; ticket consumed on acquisition
- [x] 2.3 Terminal transactions remove the run's ticket and nominate the next waiter
- [x] 2.4 Admission gate in `_execute_branch_core`; dispatch on turn from the admission envelope with fresh owner provider binding
- [x] 2.5 Startup and read-time recovery skip never-started waiters and nominate them
- [x] 2.6 Cancelling a waiting run settles it immediately
- [x] 2.7 `workspace_wait` in `get_run` and the run snapshot

## 3. Verification and delivery

- [x] 3.1 Tests red on the unfixed tree, then green: overlap, FIFO, restart while waiting, cancellation, no replay; neighbouring workspace/lease/admission suites
- [x] 3.2 Plugin mirror, ruff, cloud pre-push Linux oracle
- [ ] 3.3 Cross-family (Codex) review, owed while ChatGPT is rate-limited
- [ ] 3.4 Deploy, live app acceptance, spec sync and archive
