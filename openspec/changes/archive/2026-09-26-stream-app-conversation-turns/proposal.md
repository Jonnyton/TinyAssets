# Concurrent app-conversation turns (many-user reliability)

## Why

An inbound Slack event runs the whole converse turn **synchronously on the
Starlette event loop**: `app_ingress_http.py::_app_events` (async) calls the
blocking `handle_request` directly (`:391`), which runs the turn and blocks on the
router thread's `future.result()` for the entire turn (now up to Slice 1's 600s
cap). So **concurrent conversations serialize** — one long turn head-of-line-blocks
every other user's message on the single ingress worker. This is the "we can't
manage many users" failure at the transport layer: it is invisible with one user
but breaks the moment two conversations overlap.

Slice 1 made a single turn reliable; Slice 2 makes many concurrent turns reliable.

## What changes (no public surface change)

- **Get the turn off the event loop.** `_app_events` offloads `handle_request` to a
  worker so the Starlette loop is never blocked for the duration of a turn; many
  ingress events can be accepted and dispatched concurrently.
- **Bounded interactive worker pool.** A fixed-size pool caps how many turns (and
  thus `claude -p` subprocesses) run at once, so concurrency never spawns an
  unbounded number of subprocesses. Excess work queues; a full queue returns a
  truthful "busy, try again" rather than blocking or dropping.
- **Per-conversation FIFO ordering.** Turns for the same
  `(workspace, channel, thread)` conversation execute in arrival order (a user's
  follow-up never overtakes their previous message), while different conversations
  run in parallel. This removes cross-user head-of-line blocking without reordering
  a single conversation.
- **Truthful overload + fail-closed admission.** When the pool/queue is saturated,
  the ingress returns an honest overload notice; an event is only acknowledged as
  accepted once it is admitted to a worker (no silent drop).

Native Slack progressive streaming (chat.startStream/appendStream) is a later slice
— it needs a provider chunk callback Slice 1 deferred. This slice keeps the single
final post and focuses on concurrency.

## Impact

- Specs: `external-app-principal-mapping` (concurrent admission + per-conversation
  ordering + truthful overload).
- Code: `tinyassets/app_ingress_http.py` (offload + bounded pool + FIFO dispatch),
  a small `tinyassets/app_ingress_workers.py` (the bounded per-conversation
  executor), `tinyassets/app_ingress.py` (thread-safety of the delivery path);
  plugin mirror + tests.
- Removes Socket Mode cross-user head-of-line blocking without an unbounded
  subprocess fan-out. Scoped for the single-founder deployment now; the bound is a
  config knob that grows with capacity.
