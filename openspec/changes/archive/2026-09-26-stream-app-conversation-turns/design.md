# Design — Concurrent app-conversation turns (Slice 2)

Slice 1 made one served turn reliable (stream + idle watchdog). Slice 2 makes MANY
concurrent turns reliable by getting the turn off the ingress event loop and
bounding + ordering concurrent execution. No public-surface change; the single
final Slack post stays (native progressive streaming is a later slice).

## The bug (confirmed)

`app_ingress_http.py::_app_events` (async Starlette route) calls the blocking
`handle_request(...)` synchronously (`:391`), which runs the whole turn and blocks
on the router thread's `future.result()` for the turn's duration (Slice 1: up to a
600s cap). The event loop is therefore blocked for the whole turn, so a second
conversation's event cannot be processed until the first finishes — cross-user
head-of-line blocking.

Note the transport does NOT read the reply from the HTTP response: `deliver_app_event`
posts the reply to Slack itself (`_post`), and `_app_events` returns only an ack.
So the turn can run AFTER the ack — the offload is safe.

## The ConversationExecutor (`app_ingress_workers.py`)

A keyed, bounded, FIFO executor:

- **Global bound.** At most `max_concurrency` turns (and thus `claude -p`
  subprocesses) run at once. Config: `TINYASSETS_INGRESS_MAX_CONCURRENCY`
  (default small, e.g. 4, for the single-founder box; grows with capacity).
- **Per-key FIFO.** Work is keyed by `(workspace, channel, thread)`. Turns for the
  SAME key run strictly in submission order (a follow-up never overtakes its
  predecessor); DIFFERENT keys run concurrently up to the global bound. A key never
  holds more than one running turn.
- **Bounded queue + truthful overload.** The total pending backlog is bounded
  (`TINYASSETS_INGRESS_MAX_QUEUE`); a `submit` that would exceed it is REJECTED
  (returns False) so the caller can post a truthful "busy, try again" instead of
  growing unboundedly or dropping silently.
- **No pool-thread starvation.** A key waiting for its turn does NOT occupy a
  worker thread; the executor tracks per-key deques + an `active` set and only
  dispatches a key's next item when the previous completes AND a concurrency slot
  is free. (i.e. a slow conversation on key A never blocks key B by holding a
  worker.)

Shape:
```
class ConversationExecutor:
    def __init__(self, max_concurrency, max_queue): ...
    def submit(self, key, fn) -> bool:   # False if queue full (overload)
        # append to _pending[key]; try to _dispatch under the lock
    # internal: _dispatch() starts eligible keys (not active, slot free) on a
    # ThreadPoolExecutor(max_workers=max_concurrency); on completion, mark the
    # key inactive, pop its next item if any (re-dispatch same key first to
    # preserve FIFO), release the slot, dispatch other waiting keys.
    def shutdown(self): ...
```
All structure mutations under a single `threading.Lock`; the actual `fn` runs
OUTSIDE the lock on a pool thread.

## Wiring

- `_app_events`:
  1. Parse + HMAC-verify (as today, cheap, on the loop).
  2. Derive the conversation key from the event (workspace/channel/thread).
  3. `submit(key, lambda: handle_request(body, headers))` to the module-level
     executor. If it returns False (overload) → post a truthful busy notice and
     return an accepted-but-deferred ack.
  4. Return the ack immediately (do NOT await the turn) — the worker runs
     `handle_request`, which posts the reply to Slack itself.
- Thread-safety: `handle_request`/`deliver_app_event` now run on worker threads
  (were on the loop). They already use SqliteSaver (per-connection) + a fresh
  provider call per turn. The `_authenticated_app_transport` ContextVar must be
  set INSIDE the worker (contextvars do not cross threads) — set it in the
  submitted `fn` wrapper, not in `_app_events`.

## Failure / fail-closed posture

- An event is "accepted" only once `submit` admits it (or the overload notice is
  posted). A worker exception is caught, logged, and surfaced as the honest
  failure notice via the existing `deliver_app_event` path (Slice 1) — never a
  silent drop.
- Durable cross-crash admission (survive a daemon restart mid-turn) is Slice 3
  (Epoch-2 admission). Slice 2's executor is in-process; a crash loses in-flight
  turns, which the user retries. Documented, not silently assumed.

## Tests

1. **FIFO per key.** Submit t1,t2,t3 for key K (each records start/end order via a
   shared list under a lock); assert they ran strictly in order and never
   overlapped.
2. **Cross-key concurrency.** Submit a slow turn on key A and a fast turn on key B;
   assert B completes while A is still running (no head-of-line blocking).
3. **Global bound.** With `max_concurrency=2`, submit 4 turns on 4 distinct keys
   that block on a barrier; assert at most 2 run concurrently.
4. **Overload.** With a tiny `max_queue`, submit past it; assert `submit` returns
   False (so the caller posts a truthful overload) and nothing is dropped.
5. **No pool starvation.** Many same-key turns do not prevent a different key from
   running (a same-key backlog never consumes all worker slots).
6. **Worker exception isolation.** A turn that raises does not wedge the executor;
   the next submission still runs; the key is released.
7. **Ingress wiring.** `_app_events` returns the ack WITHOUT awaiting the turn
   (the loop is not blocked); the turn runs on a worker; the ContextVar is set in
   the worker.
