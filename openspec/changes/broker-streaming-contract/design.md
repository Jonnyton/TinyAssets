# Design: the credential broker's streaming and duplex contract (I14)

## Context

As built (`tinyassets/storage/outbound_connections.py`):

- `ConnectionLedger.resolve_exact_scoped_proxy` checks the principal, grant,
  connection and revocation, then **spawns a worker process** per proxy
  (`_start_scoped_proxy`, `multiprocessing` spawn) and talks to it over a pipe.
- The worker's `CredentialBlindBroker.dispatch`:
  - re-reads the grant;
  - resolves the credential;
  - merges constant headers;
  - for `oauth2`, takes the access token, and on a 401 refreshes and sends
    once more, only if the refreshed token differs (`_send`, ~L1177-1188);
  - performs one pinned HTTPS exchange through `_TrustedNetworkDriver`:
    - no ambient proxies;
    - redirects only within the declared endpoints, with authority
      re-validated per hop;
    - bounded header count and bytes, body bytes (5 MiB) and a total deadline
      (30 s, up to `INFERENCE_MAX_SECONDS` = 600 s for a model source);
  - reads the WHOLE body;
  - refuses the response if any sensitive value appears in it;
  - writes an audit record.
- Errors cross the pipe as a fixed set of typed, secret-free classes.

Everything below keeps those guarantees. Three things change:

- the process shape (one broker, not a worker per proxy);
- the unit of authorization (request, not proxy);
- the unit of transfer (response stream, not whole response).

### Consumers

| Consumer | Needs |
|---|---|
| Thin loop (S7), in the execution owner | async; many concurrent waiting streams at ~KiB each; first byte early; cancel; owner generation |
| In-box endpoint for API-key CLIs (D5, in `boxhostd`) | plain HTTP from the box mapped onto streams; principal derived from box identity |
| Effectors, discovery, voice signaling (today's `proxy.request` callers) | unchanged semantics |
| Fence barrier (D5, D11) | stop every older-generation send; refuse below G; acknowledge |

## v1 scope, deliberately small

- **Request bodies are capped and collected** before the request is sent
  (inline, within today's bound). Only **responses** stream. That is all
  model streaming needs. It also keeps OAuth refresh-once correct: the broker
  still holds the exact body it must resend. Streamed uploads, and the
  bounded spooling they would need, are out of v1.
- **No WebSocket upgrade.** No consumer needs it, and model streaming is SSE
  over HTTP/1.1.

## Decisions

### 1. One broker process, many streams per connection

- **Process.** The broker is one long-lived process. It is the only holder of
  the vault key (S6 task 1) and the only process that resolves a credential.
- **Transport.** Callers connect over a Unix socket now and mTLS when remote,
  with the same framing as `boxhostd` (D2): length-prefixed JSON control
  frames and raw byte frames, each carrying a caller-chosen `stream` id that
  is unique per connection.
- **Duplex.** Response bytes, credit, cancel and status flow concurrently for
  any number of streams on one connection.
- **Client.** The client is asyncio streams; a waiting stream is a coroutine
  plus a credit window, with no thread.

### 2. Roles, principals and generations

**Roles.** The owner process and `boxhostd` run as DISTINCT uids. The broker
maps uid to role from its own static configuration (`SO_PEERCRED` now, the
mTLS identity later). A connection from an unmapped uid is refused. Frames a
role may not send are refused before anything else is read:

- principal assertion, `FENCE` and `STATUS` for another namespace on a box
  channel;
- a box handle on an owner channel.

**Principals.**
- *Owner channel:* states the principal and command center in each `OPEN`.
  It is the only process that authenticated a user, which is what today's
  `verify_authenticated_principal` callable stands for.
- *Box channel:* carries the box handle `boxhostd` authenticated (D2). The
  broker derives the principal (box -> command center -> owning account). The
  CLI's connection id is a selector only (decision 9).

**Authorization.** Every `OPEN` runs the **same** checks as
`resolve_exact_scoped_proxy`: the authenticated principal, an active grant,
the grant's owner and command center, the connection's identity and owner,
and revocation. A refusal is `refused`, nothing is sent, and the stream
reports `side_effect_state: none`.

**Generation.** Comparing a number cannot fence a stale owner, which could
claim a future generation. So the barrier mints the credential:

- `FENCE{G}` (decision 6) returns a fresh random **generation token** in
  `FENCE_ACK`.
- Every owner-channel `OPEN` carries `(G, token)`. The broker admits it only
  if both equal its persisted current fence. An old owner never sees the new
  token.
- `boxhostd` receives the same `(G, token)` through its own D5 barrier and
  stamps it on every relayed stream. A box never supplies a generation.

### 3. The stream lifecycle

| Frame | From | Content |
|---|---|---|
| `OPEN` | caller | `stream`, `op_id`, `(G, token)`, principal/cc (owner) or box handle (box), `grant_id`, `connection_id`, `verb`, and `request`: today's request document unchanged (`url`, `headers`, `header_name`, `body` as str, dict or list with today's serialization and content-type rules, `reply_budget_s`); plus `idle_s` and initial `credit` |
| `HEAD` | broker | `status`, `reason`, sanitized `headers`, `redirect_count`. Sent only after the redirect chain and the OAuth refresh-once are settled |
| `DATA` | broker | response bytes, at most `MAX_FRAME` (64 KiB) per frame and never beyond granted credit |
| `CREDIT` | caller | grant n more bytes; outstanding credit is capped at `MAX_WINDOW` (256 KiB) |
| `CANCEL` | caller | abort this stream |
| `END` | broker | `outcome` (`completed`, `cancelled`, `refused`, `failed`), `side_effect_state`, `error_class` (today's typed set plus `fenced`, `duplicate`, `expired`), the structured authorization failure where today's `ConnectionAuthorizationError` carries one, byte count, duration |
| `STATUS` / `STATUS_IS` | caller / broker | an `op_id`'s recorded state (decision 7) |
| `FENCE` / `FENCE_ACK` | owner / broker | decision 6 |

**Retries happen only before `HEAD`, and only today's.**
- **OAuth.** The refresh-once resends the retained body only when the
  refreshed token differs.
- **Redirects.** They follow today's endpoint rules. Each intermediate
  response and each redirect target is scanned before it is followed
  (decision 5).
- After `HEAD` nothing is resent.

**Bounds.**
- Header count and bytes are as today.
- The body cap applies cumulatively over the stream. A model-source
  connection may declare a larger stream cap; the ceiling is read from the
  connection, never from the request.

**Deadlines.**
- The **absolute deadline** starts at admission and covers everything: DNS,
  OAuth refresh, redirects, the retry (which shares what is left), waiting for
  credit, and cancellation. Its default is today's 30 s. A longer
  `reply_budget_s` is granted exactly as `_inference_budget_s` grants it
  today: POST, an `http` connection carrying a model capability, a finite
  number, clamped to `INFERENCE_MAX_SECONDS`.
- The **idle bound** (`idle_s`) counts bytes actually read from upstream, not
  bytes forwarded. It pauses while the broker has stopped reading for lack of
  credit, so a slow consumer cannot make an active provider look silent; the
  absolute deadline still runs. SSE comment pings are bytes.

**`side_effect_state` is strictly about transmission.**
- `none` only when the broker proves no request byte left it: a refusal
  before the socket write (authorization, fence, duplicate, expiry, a pinning
  or DNS refusal).
- Everything after the first write is `unknown`, and it stays `unknown`
  across the OAuth retry, redirects, cancellation and any later refusal.
- A 4xx is NOT `none` here. Whether a model source's 4xx proves nothing was
  generated is model-admission knowledge, and it stays in the consumer
  (`ApiKeyHttpProvider._pre_generation`), where it is today.

### 4. Backpressure and memory, as bounds

- **Response side.** The broker reads upstream only while the stream has
  credit, and never sends past it. A caller's per-stream receive buffer
  therefore never exceeds the credit it granted. The client demultiplexer
  hands each frame to its stream without blocking, so one stalled stream
  cannot stop `HEAD`/`END` for the others.
- **Hard caps on everything else:** `MAX_FRAME`, `MAX_WINDOW`, a per-stream
  scan hold-back (decision 5), headers within today's 64 KiB bound, admitted
  streams per connection (`MAX_STREAMS`, refused as `refused` beyond it), and
  a per-connection output queue.
- **Memory target, not yet a fact.** Window plus hold-back plus headers plus
  one TLS record, about 100-350 KiB per stream depending on credit. S6 must
  measure it, including parser and transport buffers.

### 5. The scan, incrementally, over today's full set

**The set is today's union, not just the dispatch tuple.** It covers:

- the credential;
- the old and new OAuth access and refresh tokens;
- every capability-URL segment (`url_secret_sensitive_values`);
- Basic username and password separately, and the generated Basic payload;
- OAuth1 bundle members and signatures;
- every generated authorization header value;
- redirect authenticators and capability material accumulated across hops,
  including the decoded forms the driver already derives (~L3273-3307,
  L3684-3692, L3781-3811, L3917-3936).

Nothing the driver scans today is dropped. Widening the encodings is a
separate change for both paths.

**Order:**
- Intermediate redirect responses and targets are scanned before following,
  as today.
- The final headers are scanned whole before `HEAD`.
- The set is **final at `HEAD`**, because all redirect material accrues
  before it.

**The body.** Let L be the longest value in the set, as bytes.
- Before forwarding anything, the broker scans the retained suffix plus the
  new bytes. It forwards everything except the last L-1 bytes, which are kept
  back.
- Any occurrence a future byte could complete must start within those L-1
  bytes, so no forwarded byte belongs to it. This holds for unequal lengths,
  overlapping values and arbitrary chunk boundaries.
- At a clean EOF the held tail is scanned and flushed. On a match the stream
  ends `failed` (unsafe destination response), the tail is discarded, and an
  audit record is written.
- An empty set means no hold-back.

**What is guaranteed, stated precisely:** no byte belonging to a complete
occurrence of a held value is ever forwarded. A clean response that merely
ends in a prefix of a value is delivered whole. The request/close wrapper
additionally keeps today's check on the UTF-8-decoded body (decision 8).

### 6. Owner-generation fence

The fence is per cell: one broker serves one execution owner lineage.

- **One lock.** Admission, and every transition that can put a byte on the
  wire (first write, OAuth resend, each redirect hop), runs under a fence read
  lock and re-checks `(G, token)` immediately before writing. `FENCE` takes
  the write lock.
- **`FENCE{G}`:**
  1. Persist `max(current, G)` with a new token, durably.
  2. Mark every older-generation stream cancelled.
  3. Wait until no older producer holds the read lock. After that none can
     start another write.
  4. Close those upstream sockets.
  5. Send `FENCE_ACK{G, token}`.
- Bytes already sent stay `unknown`. The ACK promises that no further write
  happens, not a remote rollback.
- **Restart.** The broker enforces the persisted fence whether or not the
  ACK reached the caller, and refuses every `OPEN` until it has loaded it.

### 7. `op_id`: a durable, authorized operation record

**Namespace and binding.**
- A record is keyed by the authority namespace (owner principal and command
  center, derived the same way as in decision 2) plus `op_id`.
- It is bound to the request's identity: a digest of grant, connection,
  verb, destination and body.
- An `OPEN` or `STATUS` naming an `op_id` outside its own namespace finds
  nothing.
- An `OPEN` reusing an `op_id` with a different request identity is
  `refused`/`duplicate`.

**The state machine.** Persisted and fsynced before it is relied on:

- `reserved`: an atomic insert at admission. A concurrent `OPEN` of the same
  in-flight `op_id` is `refused`/`duplicate`.
- `may_have_sent`: written durably **before the first byte reaches the
  socket**. A crash after this point reads as `unknown`, never as
  `not_sent`.
- Terminal: `completed`, `failed`, `cancelled` or `refused`. Each keeps
  whether a byte may have left.

**Reuse, crashes and expiry.**
- An `OPEN` reusing a recorded `op_id` returns the recorded state and never
  sends.
- The OAuth resend is part of the same operation, not a second one.
- `op_id`s are ULIDs. The broker refuses an `OPEN` whose `op_id` timestamp is
  older than the retention window (`expired`), so a record cannot be evicted
  and its id then accepted as new.
- `STATUS` distinguishes `not_sent`, `unknown`, the terminal states and
  `expired`. `expired` is never read as `not_sent`.
- A lost stream's bytes are not replayable; the caller holds on `unknown`.
  This is the journal's rule (S7, D2).

### 8. Compatibility: request/close is a wrapper

`ScopedConnectionProxy.request(verb, request)` keeps its signature, return
document (`status`, `reason`, `headers`, `body` decoded UTF-8 with
replacement), redirect fields and typed errors, including
`ConnectionAuthorizationError`'s provider detail.

- It opens one stream with the request document unchanged, grants credit up
  to the connection's body cap, collects the stream to `END`, and runs
  today's `_contains_secret` over the decoded document before returning.
- `close()` sets a local closed flag, so a later `request` still raises
  "outbound proxy is closed".
- The spawned worker and its startup handshake are deleted with S6. Every
  existing caller's tests stay unchanged.

### 9. The in-box endpoint (in `boxhostd`)

**Selection.** The CLI is configured with base URL `http://broker.box/c/<connection_id>`.
- `boxhostd` resolves the grant for (the box's command center,
  `connection_id`).
- The destination host is always the connection's declared host. The path
  after the prefix must match the connection's allowed endpoints, as today.
- The caller cannot choose a host, a grant or a principal.

**Requests.** The request body is collected within the cap, then one `OPEN`
is sent on the box channel. A client disconnect is a `CANCEL`.

**Before `HEAD`, errors map to a status.** `refused` -> 403, `fenced` -> 503,
deadline -> 504, any other failure -> 502. The body is a small JSON document
naming `error_class` and nothing of the destination's.

**After `HEAD`, a failure is an incomplete response.**
- `boxhostd` relays the status and sanitized headers, drops hop-by-hop
  headers, and re-frames the body as chunked.
- On a failed `END` it **aborts the connection without the terminating
  chunk**. An HTTP client then sees a truncated response, never a successful
  short one.
- A completed `END` writes the terminating chunk.

### 10. Vendor neutrality

The broker forwards bytes. It never parses SSE events or any vendor's
envelope; its only content inspection is the scan. Parsing belongs to the
caller: the loop's incremental SSE reader folds chunks with today's codec
(`agent_chat_codec`).

## Rejected

- **A worker process per stream.** This is today's memory cost, now times
  every waiting turn.
- **The credential in the loop.** That breaks the invariant the architecture
  rests on: no real credential in the loop or the box.
- **Scan at the end, then release.** This is today's shape, and exactly the
  latency being removed.
- **Streamed uploads in v1.** They need bounded spooling for the OAuth resend
  and upload flow control, and no consumer needs them yet.
- **gRPC/HTTP2.** A second framing for a local RPC D2 already frames.

## Risks

- **One broker is one failure domain.** A crash ends every stream. Mitigations:
  - a supervised restart;
  - the fence and the `op_id` records reload before serving;
  - every lost stream is `unknown`, so nothing replays.

  S6 measures the blast radius.
- **Distinct uids are now a deployment requirement.** The owner and
  `boxhostd` must not share one. Where peer credentials are unavailable (a
  Windows development host) the broker fails closed.
- **The guarantee's shape changes.** A response is no longer withheld whole on
  a scan hit; decision 5 states exactly what is guaranteed instead.

## Measurement owed by S6

- Broker memory per open stream at the default window, including headers,
  TLS, parser and transport buffers.
- Time to first byte versus today's request/close, through a mock SSE
  upstream.
- 500 concurrent streams through one broker process, with no thread per
  stream.

## Appendix R. Cross-family review (gpt-6-astra)

- **Round 1 (a1c9ad07): ADAPT, 9 x P1/P2 acted on.**
  - The scan set narrower than today's driver set: now the full union
    (decision 5).
  - 4xx counted as `none`: now strictly pre-send, with model admission left
    in the consumer.
  - `op_id` not crash- or concurrency-safe: now a durable state machine,
    namespaced, request-bound, with ULID expiry.
  - Fence not linearized against sends: now a read/write lock, re-check
    before each write, monotonic persistence.
  - Roles and generation spoofable: now distinct uids and a barrier-minted
    token.
  - Streamed uploads incompatible with OAuth resend: uploads are out of v1.
  - Memory and liveness claims unproved: now bounds plus a measurement
    target.
  - Idle deadline under backpressure: now upstream-read based and paused
    without credit.
  - Compatibility fields missing: decision 8.
  - In-box failure after `HEAD`: an aborted chunked response.
  - Agreed: the hold-back argument, with the guarantee restated precisely.
