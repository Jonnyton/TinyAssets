## Why

Target architecture (#4263) left one interface open: the credential broker's
streaming and duplex contract (I14, design escalation c). S7, the thin agent
loop, depends on it, and so do the in-box endpoint for API-key CLIs and the
owner-generation fence (D5, D11).

Today the broker is request/close. `resolve_exact_scoped_proxy` spawns a
Python worker process for each proxy. That worker reads the whole upstream
response into memory, scans it for credential material, and returns it in one
message. This costs three things:

- **Memory.** An in-flight model round costs a whole process: 29 MiB RSS for
  the worker's imports alone (measured 2026-10-01, `control-plane-agent-loop`
  design). The loop itself holds a waiting turn in 61-228 KiB.
- **No streaming.** The first token reaches nobody until the last one is
  generated. That makes time-to-first-token as bad as it can be, and model
  streaming to the app (S7 task 2.3) is impossible.
- **No cancellation.** A turn that is stopped cannot stop its upstream request.
  The only lever is killing the worker.

## What Changes

This is a design-only change: it fixes the contract so S6 can be built.

- **One long-lived broker process.** Callers reach it over a local socket with
  length-prefixed frames. Many concurrent **streams** share one connection,
  each with its own request body, response, flow-control credit and cancel.
  The broker remains the only process that resolves a credential.
- **Per-request authorization.** Every stream is authorized as it opens,
  through the same checks as `resolve_exact_scoped_proxy` today. Authorization
  is no longer granted once, when a proxy starts.
- **Streaming responses with backpressure.** The broker sends a head (status
  and sanitized headers) once redirects and the single OAuth refresh-and-retry
  are settled, then the body as byte frames. It reads upstream only as far as
  the caller has granted credit.
- **Cancellation both ways.** A caller cancel aborts the upstream request. A
  broker-side end (deadline, scan hit, fence) reaches the caller as a typed
  end frame.
- **The secret scan stays complete.** The scan runs incrementally and holds
  back the bytes a match could still end in, so no prefix of a held secret is
  ever forwarded.
- **Lost replies resolved by `op_id`.** A stream's outcome is recorded by
  `op_id`. A caller that lost its connection asks for the status. It never
  re-sends a request the broker recorded as sent.
- **Owner-generation fence.** Every stream carries the owner's lease
  generation. An acknowledged fence barrier cancels the streams of older
  generations and refuses any new stream below the fence.
- **Compatibility.** `proxy.request(verb, request)` becomes a client-side
  wrapper that opens one stream and collects it, so every existing caller
  keeps its semantics. The per-proxy spawned worker is retired.

## Impact

- Authority: unchanged in substance. The same grant, owner, command center,
  connection and revocation checks run, now per request. The broker remains
  the only process that holds the vault key.
- Storage: one bounded outcome record per `op_id` for a retention window.
  There is no schema change to connections or the vault.
- Public MCP surface: none.
- Depends on: S1 (key escrow) and S4 (box identity, for the in-box endpoint)
  only for the parts that name them. The loop-side contract here can be built
  first.
