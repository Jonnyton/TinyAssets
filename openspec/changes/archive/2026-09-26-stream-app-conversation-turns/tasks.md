# Tasks — Concurrent app-conversation turns (Slice 2)

## 1. The keyed bounded FIFO executor
- [x] 1.1 `tinyassets/app_ingress_workers.py`: `ConversationExecutor(max_concurrency, max_queue)` with `submit(key, fn) -> bool`, per-key FIFO, global concurrency bound, bounded backlog (submit returns False on overload), no pool-thread starvation (a key waiting does not hold a worker), `shutdown()`. All structure mutation under one lock; `fn` runs off-lock on a ThreadPoolExecutor.
- [x] 1.2 Config: `TINYASSETS_INGRESS_MAX_CONCURRENCY` (default 4) + `TINYASSETS_INGRESS_MAX_QUEUE` (default 64) via the resolver; a module-level singleton executor.

## 2. Wire the ingress
- [x] 2.1 `app_ingress_http.py::_app_events`: parse+HMAC-verify on the loop, derive the conversation key, `submit` the turn, return the ack WITHOUT awaiting; on overload (submit False) post a truthful busy notice.
- [x] 2.2 Set the `_authenticated_app_transport` ContextVar INSIDE the worker fn (contextvars don't cross threads), not on the loop.
- [x] 2.3 Worker exception isolation: a raising turn is caught + surfaced via the existing honest-notice path; the key is released; the executor keeps running.

## 3. Tests (drive the real executor, deterministic via barriers/events — no sleeps-as-sync)
- [x] 3.1 FIFO per key: t1,t2,t3 on key K run strictly in order, never overlapping.
- [x] 3.2 Cross-key concurrency: slow A + fast B → B finishes while A runs.
- [x] 3.3 Global bound: max_concurrency=2, 4 barrier-blocked keys → at most 2 concurrent.
- [x] 3.4 Overload: tiny max_queue → submit past it returns False; nothing dropped.
- [x] 3.5 No pool starvation: a same-key backlog never blocks a different key.
- [x] 3.6 Worker exception isolation: a raising turn doesn't wedge the executor; next runs; key released.
- [x] 3.7 Ingress wiring: `_app_events` returns the ack without awaiting the turn; the turn runs on a worker; ContextVar set in the worker.

## 4. Codex ADAPT resolution (round 1 verdict: adapt)
Verdict: "make shutdown drain accepted work without post-shutdown pool submission
or state corruption; add fair ready-key rotation; surface overload and escaped
worker failures to the user; replace the racy/self-confirming tests with
deterministic reproductions."
- [x] 4.a Shutdown guard: `_dispatch_locked()` returns immediately if `_shutdown`; in-flight drain delegated to `pool.shutdown(wait=True)`; no submission to a closed pool from the `_run` finally re-entry.
- [x] 4.b Fair ready-key rotation: `_pending` is an `OrderedDict`; a dispatched key with remaining work is `move_to_end()`'d. New test `test_ready_keys_rotate_fairly_across_a_single_slot` forces interleaving (a1,b1,a2,b2).
- [x] 4.c Surface to the user: `deliver_app_notice()` (routes like a real reply, no model turn, never recorded as a universe utterance). Overload posts `OVERLOADED_NOTICE` off-loop (`run_in_threadpool`) then 503; an ESCAPED turn posts `_failure_notice(exc)`. Both best-effort. New tests assert both.
- [x] 4.d Deterministic tests: removed `time.sleep`-as-sync; same-key-no-overlap holds turn 0 on a gate + asserts turn 1 not started; concurrency-bound asserts a later turn's event stays unset while both slots held. Only remaining sleep is the `_wait` poll interval.

## 5. Review + land + verify
- [x] 5.1 Plugin mirror rebuild + parity; ruff; targeted pytest green (70 passed local; Linux CI authoritative).
- [ ] 5.2 Codex cross-family RE-review of the adapt fixes (concurrency correctness + adapt items); resolve approve/adapt. (dispatched)
- [ ] 5.3 Land to main (own PR, rebased onto squashed Slice 1); sync delta + archive.
- [ ] 5.4 Deploy note: no env change beyond the two new optional knobs (safe defaults).
