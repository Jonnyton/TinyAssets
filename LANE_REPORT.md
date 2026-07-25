# Paid-market Wave 2 workflow lane report

Date: 2026-07-25 PT
Branch: `codex/osx-market-workflow`
Base: `origin/main` at `92d730bc9f667f4ccedda75413ac72f176fee38b`
Implementation commits: `bfb31b1d` (`feat: add dark paid-market workflow spine`), `be0e7509` (`fix: enforce paid-market match authority`)
Push: `origin/codex/osx-market-workflow`

## Delivered

- Added `tinyassets/payments/market_workflow.py`: immutable commands/results, injected store/realtime/delivery/ledger boundaries, a thread-safe reference store, body-bound replay, append-only lifecycle history, requester-authorized early close, cap/window/deadline enforcement, runtime transition-table enforcement, selected-host claim authority, capacity/version fences, and bounded three-attempt oracle recomputation.
- Added `tinyassets/payments/market_realtime.py`: privacy-minimal announcements, subscribe/buffer/snapshot/watermark/outbox reconciliation, bounded multi-page catch-up, compaction/retry-exhaustion fallback, dedupe/coalescing, and fair bounded output.
- Added fixture-only `prototype/full-platform-v0/migrations/010_paid_market_workflow.sql`: dark workflow tables, command log, exact-result replay metadata, durable outbox, RLS, non-login command ownership, logical settlement wrapper, and zero-host status.
- Extended the fixture migration runner's exact baseline verification and catalog fingerprint.
- Rebuilt the Claude plugin runtime mirror.
- Did not create `market_delivery.py`; did not add delivery receipt, acceptance, or dispute tables; did not add `lease_fence` or `accepted_result_sha256`.

## Per-task result

- 3.5 — complete. The fixture wrapper locks the accepted request, exact winning match, and exact winning bid/version; requires `gross == immutable match total <= spend cap`; independently verifies requester/host/grant/account authority; invokes the landed fee-bearing settlement; asserts logical escrow drain; and commits the settlement transition atomically. The settlement caller role is denied the raw ledger function; only the wrapper's non-login definer retains it. Failure rolls back ledger and workflow effects. It confers no wallet-funding or chain authority.
- 3.6 — complete. Randomized persistent transactions are checked account-for-account against pure `Ledger`, including replay/conflict, residual escrow rollback, same-owner settlement, and native/external supply. Every positive settlement has a positive treasury fee.
- 3.7 — partial, left unchecked. Tenant/actor derivation, mixed-tenant rejection, signed/account/amount/time/generation-bound and revoked grants, server hashes, composite keys, coalescing, and fee invariance are covered. A production-shaped global cross-family lock/deadlock proof was not available.
- 4.1 — partial, left unchecked. The complete delta-spec graph, body-bound request replay, forbidden edges, authority, cancellation/claim races, fan-out bounds, original-result replay, and append-only history are covered. Canonical API-router delegation and fence-dependent later transition implementations remain absent.
- 4.2 — partial, left unchecked. Immutable non-delivery commands/results and all four requested injection protocols exist without psycopg/Supabase imports. A delivery command was not stubbed because its fence/hash authority is externally owned.
- 4.3 — partial, left unchecked. Migration 010 contains request, bid, match, match-bid, fan-out-slot, claim, event, outbox, grant, and command-log rows with denial/RLS/ownership/search-path proofs. Delivery receipt, dispute, and acceptance rows are intentionally absent.
- 4.4 — complete. Realtime tests cover atomic outbox append, post-commit announcement, cancellation tombstones, privacy-minimal envelopes, eligibility errors, snapshot/watermark/catch-up/buffer merge, multi-page replay, exhaustion refusal, compacted-watermark fallback, duplicate/out-of-order frames, coalescing, bounds, fairness, and degraded freshness without global polling.
- 4.5 — complete. Bid tests cover exact host/grant authority, immutable monotonic versions, quote id/version/digest binding, one bid to one landed `BookOffer`, replacement/cancellation/expiry/revocation, capacity fences, deterministic oracle selection, requester-only early close, host matching only after the window and within spend cap, hard request deadline, bounded rejection receipts, persisted match decisions, and cross-request capacity exclusion.
- 4.6 — complete for the buildable dark spine. Claims use landed `best_execution`, canonical request/slot/bid lock identity, exact version/capacity/cap/window/deadline rechecks, requester early-close receipts, selected-host authority, the canonical runtime transition guard, stale atomic rejection, three bounded attempts with jitter, and honest insufficient/contention results. Cross-owner aggregate claims fail closed pending independently fenced host slots.
- 5.1 — partial, left unchecked. Zero-or-one recovery is covered around request/outbox/notification/bid/match/claim and fixture ledger/drain/database/replay boundaries. Completion, acceptance/dispute, and delivery-response faults were not stubbed.
- 5.2 — complete as local code evidence. One hundred simultaneous selected-host claim attempts produce one applied claim and one capacity consumption matching the pure oracle. A separate two-request race proves one capacity grant cannot sell twice. This is not a production §14 load proof.
- 5.5 — untouched. Its task text does not separate a code half from a legal artifact, so the user's conditional authorization did not apply.
- 5.6 — complete as fixture evidence. With no daemon/tray host, database-owned reads preserve honest pending state, fabricate no settlement, and report settlement unavailable.

## Red/green evidence

- Initial RED: workflow, bid, claim, realtime, fault, and PostgreSQL tests failed on missing modules/migration and missing command behavior.
- PostgreSQL RED included missing migration 010, hostile-path/runtime errors, absent grant/account bounds, and absent settlement rollback/binding behavior.
- Independent-review RED regressions reproduced one-page catch-up, mutable replay meaning, missing cancellation invalidation, requester-owned claims, cross-request capacity double-sell, tenant-wide RLS reads, and settlement amount under-binding.
- Final regression RED reproduced retry-budget partial convergence, cross-owner aggregate claiming, and spend-cap-versus-match-total confusion.
- GREEN: `406 passed in 15.73s` across all 15 `tests/test_paid_market_*.py` files using local PostgreSQL 15 (`pgvector/pgvector:pg15`) on 2026-07-25 PT.
- GREEN: focused `ruff check` passed for every touched Python source/test.
- GREEN: `py_compile` passed for the two new modules and migration runner.
- GREEN: `openspec validate paid-market-track-e-wave-2-transport --strict`.
- GREEN: plugin build import probe passed; mirror parity reported all 268 canonical files matched.
- REVIEW: the prior independent approval was superseded by the Opus 5 REJECT. The four blocking manipulation/enforcement findings are folded below with fresh behavioral and mutation evidence.

## Opus 5 money-review fold

### F1 - eligible-host self-match was unbounded

- RED: the reviewer-shaped test placed a 100-micros cheap but insufficient bid beside the attacker's 99,900,000-micros/Mtok bid. At the window boundary the eligible attacker recorded a 999,000,000-micros match against a 1,000,000-micros requester cap; the test failed because the command returned `Applied`.
- FIX: a requester or bounded requester grant may close early. After the window, an eligible host may invoke only the deterministic full-snapshot matcher, and both `record_match` and `claim_match` reject a recorded total above `spend_cap_micros`. The early-close authority bit is persisted and included in the decision digest.
- GREEN: both the 999,000x price repro and the corrupted over-cap decision claim return `Conflict("match_spend_cap_exceeded")`; neither mutates request, bid, capacity, match, or claim state.
- MUTATION: temporarily removing the record and claim cap guards made both focused tests fail (`2 failed`); restoring them returned the nine-finding focused set to `9 passed`.

### F2 - bid window and request deadline were decorative

- RED: a host recorded before `bid_window_ends_at`, a requester recorded at `deadline`, and a host claimed at `deadline` from a bid expiring later; all three boundary tests failed because the unsafe commands proceeded.
- FIX: hosts cannot record before the window; a requester-authorized match may close early and lets only its selected host claim. Record and claim both reject `now >= deadline`, even when bid expiry is later.
- GREEN: early host match returns `bid_window_open`; record and claim at the deadline return `request_deadline_elapsed`; requester early-close plus selected-host claim remains green.
- MUTATION: temporarily removing the window/deadline guards made all three boundary tests fail (`3 failed`), proving the tests exercise the comparisons rather than stored fields.

### F3 - `_ALLOWED_TRANSITIONS` was declarative only

- RED: deleting `("bidding", "claimed")` still let claim apply, while opening the table to all 169 pairs still could not drive a formerly forbidden command because a separate `allowed_sources` list overrode the table.
- FIX: `_enforce_transition` raises on every unlisted request-state edge. Generic request transitions and claim call it before mutation, and the divergent caller-supplied source-state list was removed.
- GREEN: deleting the claim edge now returns `state_transition_forbidden` with the request still bidding; opening all 169 pairs changes the repeated-cancel command from conflict to applied.
- MUTATION: the two behavioral table-mutation tests pass together (`2 passed`); they inspect command/state outcomes, not set equality.

### Task 3.5 - settlement role retained the raw ledger grant

- RED: migration 010 contained no revoke, and live PostgreSQL reported `(True, True)` for raw `market.apply_settlement` privilege on the settlement role and workflow owner.
- FIX: migration 010 revokes raw execution from `tinyassets_fixture_settlement` and leaves it only with `tinyassets_fixture_workflow_owner`, the bounded wrapper's non-login definer. Raw-ledger tests execute under that owner; settlement-role tests require an actual PostgreSQL privilege error.
- GREEN: source and live-role tests pass; the live privilege tuple is `(False, True)`, direct raw invocation as the settlement role is denied, and fee-bearing wrapper settlement remains green.
- MUTATION: temporarily removing the revoke made both the source assertion and live privilege repro fail (`2 failed`), restoring the bypass exactly.

## State-machine coverage map

| Source | Allowed targets covered by the graph test | Implemented command in this lane |
|---|---|---|
| pending | bidding, cancelled, expired | open bidding; cancel |
| bidding | claimed, cancelled, expired | selected-host claim; cancel |
| claimed | running, failed | graph only; external execution authority pending |
| running | completed, failed | graph only; delivery fence/hash pending |
| completed | accepted, auto_accepted, disputed | graph only; acceptance/domain authority pending |
| disputed | accepted, refunded, running | graph only; dispute/correction authority pending |
| accepted | settled | fixture accounting wrapper |
| auto_accepted | settled | fixture accounting wrapper |
| failed | refunded | graph only |

Every other ordered pair among the declared states is rejected by `allowed_transition`. Graph enumeration is not represented as an implementation of the externally gated delivery/acceptance/dispute commands.

## Honest remainder

- No production-shaped Supabase Realtime/load run, one-million-transfer run, or cross-family deadlock proof was performed; §14 production uptime/load completion is not claimed.
- The fixture migration is not a production Supabase migration or live rollout.
- Canonical API-router delegation remains for 4.1.
- Delivery commands/storage, completion receipts, acceptance, dispute, correction, and refund execution remain gated on the distributed-execution owner of `job_id:lease_fence:accepted_result_sha256`.
- Multi-owner matches are reproducible, but aggregate claiming fails closed until independently fenced per-host slots are implemented.
- 2.5, 2.6, 5.3, 5.4, 6.4, 4.7, and 5.7 were not touched.
- No PR was opened.

LANE_RESULT: done - all Opus 5 manipulation/enforcement findings folded with red, green, and mutation evidence; branch remains dark and unadvertised
