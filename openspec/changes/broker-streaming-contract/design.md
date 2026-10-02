# Design: the credential broker's streaming and duplex contract (I14)

## Context

As built (`tinyassets/storage/outbound_connections.py`):

- `ConnectionLedger.resolve_exact_scoped_proxy` checks the principal, grant,
  connection and revocation. It then **spawns a worker process** per proxy
  (`_start_scoped_proxy`, `multiprocessing` spawn) and talks to it over a pipe.
- The worker's `CredentialBlindBroker.dispatch`:
  - re-reads the grant;
  - resolves the credential in the worker;
  - merges constant headers;
  - for `oauth2`, takes the access token and on a 401 refreshes and sends
    once more;
  - performs one pinned HTTPS request through `_TrustedNetworkDriver`. That
    request has no ambient proxies, and follows redirects only within the
    declared endpoints, re-validating authority on each hop. It is bounded by
    header count, header bytes, body bytes (5 MiB) and a total deadline (30 s,
    up to `INFERENCE_MAX_SECONDS` = 600 s for a model source);
  - reads the WHOLE body;
  - refuses the response if `_contains_secret` finds any held secret in it;
  - writes an audit record.
- Errors cross the pipe as a fixed set of typed, secret-free classes:
  `PermissionError`, `GrantResolutionError`, `AmbiguousProxyOutcome`,
  `OutboundDeadlineExceeded`, `ConnectionAuthorizationError` and
  `ProxyRequestError`.

Everything below keeps those guarantees. What changes is the process shape,
the unit of authorization (proxy -> request) and the unit of transfer
(response -> stream of frames).

### Consumers

| Consumer | Needs |
|---|---|
| Thin loop (S7), in the execution owner | async; many concurrent waiting streams at ~KiB each; first byte early; cancel; owner generation |
| In-box endpoint for API-key CLIs (D5, via `boxhostd`) | plain HTTP from the box mapped onto streams; principal derived from box identity, never from the caller |
| Effectors, discovery, voice signaling (today's `proxy.request` callers) | unchanged semantics |
| Fence barrier (D5, D11) | cancel every stream below generation G; refuse below G; acknowledge |

## Decisions

### 1. One broker process, many streams per connection

- **Process.** The broker is one long-lived process. It is the only holder of
  the vault key (S6 task 1) and the only process that resolves a credential.
  No per-request process exists.
- **Transport.** Callers connect over a Unix socket now and mTLS when remote,
  with the same framing as `boxhostd` (D2): a fixed header, a length-prefixed
  JSON control frame, and raw byte frames.
- **Multiplexing.** Frames carry a `stream` id chosen by the caller and unique
  per connection. One connection carries any number of concurrent streams.
  That is the "duplex": request bytes, response bytes, credit and cancel all
  flow on the same connection at the same time.
- **Client side.** The client is asyncio streams. A waiting stream in the
  loop is a coroutine plus a credit window, with no thread.

### 2. Who the caller is, and who the principal is

The broker identifies the connecting process by its socket peer credential
(`SO_PEERCRED` uid, or the mTLS identity later), never by anything the caller
sends. A connection is one of two classes:

- **Owner channel.** This is the execution owner, the only process that
  authenticated a user. It states the principal and command center in each
  OPEN, because it is the authority for them, exactly as today's
  `verify_authenticated_principal` callable is.
- **Box channel.** This is `boxhostd` relaying a box's request. The OPEN
  carries the box handle that `boxhostd` authenticated (D2). The broker
  derives the principal from it (box -> command center -> owning account) and
  ignores any principal field. The CLI's connection id is a selector only.

Either way, every OPEN is resolved with the **same** checks as
`resolve_exact_scoped_proxy` today: the authenticated principal, an active
grant, the grant's owner and command center, the connection's identity and
owner, and revocation. A refusal here is a typed `not_sent` end, and nothing
reaches the network.

### 3. The stream lifecycle

| Frame | From | Content |
|---|---|---|
| `OPEN` | caller | `stream`, `op_id`, `owner_generation`, principal/cc (owner channel) or box handle (box channel), `grant_id`, `connection_id`, `verb`, `url`, `headers`, `body`: `inline` bytes or `streamed`, `reply_budget_s`, `idle_s`, initial `credit` |
| `BODY` / `BODY_END` | caller | request body bytes, for `streamed` |
| `HEAD` | broker | `status`, sanitized `headers`. Sent only after the redirect chain and the single OAuth refresh-and-retry are settled |
| `DATA` | broker | response bytes, never more than the outstanding credit |
| `CREDIT` | caller | grant n more response bytes |
| `CANCEL` | caller | abort this stream |
| `END` | broker | `outcome` (`completed`, `cancelled`, `refused`, `failed`), `side_effect_state` (`none`, `unknown`), `error_class` (today's typed set plus `fenced`), bytes, duration |
| `STATUS` / `STATUS_IS` | caller / broker | the recorded outcome of an `op_id` |
| `FENCE` / `FENCE_ACK` | owner / broker | the barrier (decision 6) |

Rules that carry today's guarantees:

- **Retries happen only before `HEAD`.** The OAuth 401 refresh-once and
  redirects follow today's rules and happen before any response byte is
  forwarded. After `HEAD`, the broker never sends the request again.
- **Bounds:** header count and bytes as today. The body cap applies
  cumulatively over a stream. A model-source connection may declare a larger
  stream cap than 5 MiB, and its ceiling is read from the connection, never
  from the request.
- **Deadlines:**
  - `reply_budget_s` is the absolute cap. It is granted only for a model
    source, and only up to `INFERENCE_MAX_SECONDS`, exactly as
    `_inference_budget_s` does today.
  - `idle_s` bounds silence: no upstream byte for that long ends the stream
    `failed`/`OutboundDeadlineExceeded`. SSE comment pings are bytes, so a
    model that is thinking but pinging stays alive.
- **`side_effect_state`:**
  - `none` only when the broker proves no request byte left it: a refusal
    before connect, a pre-send authorization or fence refusal, or a 4xx
    admission refusal as `_pre_generation` defines it today.
  - Everything else is `unknown`. That includes any cancel after the request
    was written, and any 5xx. The loop holds on `unknown` (S7).

### 4. Backpressure

The broker reads from the upstream socket only while the stream has credit.
Per stream it buffers at most the credit window plus the scan hold-back
(decision 5). The default window is 64 KiB. A slow consumer slows the
upstream read; TCP backpressure then applies to the provider. It never grows
broker memory. The memory a stream costs in the broker is therefore bounded
by window + hold-back + one TLS record, about 100 KiB.

### 5. The secret scan, incrementally

Today the broker refuses a response if any held secret appears anywhere in
it: the credential, both OAuth tokens, and every segment of a capability URL
(`url_secret_sensitive_values`). On a stream:

- **Headers** are scanned whole before `HEAD`.
- **Body.** Let L be the longest held secret, as encoded bytes. The broker
  forwards only bytes that can no longer be the start of a match: it keeps the
  last L-1 bytes back until more arrive or the stream ends. On a match the
  stream ends `failed`/`ProxyRequestError("unsafe destination response")`
  with an audit record. The caller has received only bytes that contained no
  complete secret and no prefix of a later match.
- **The matcher is today's `_contains_secret`**, as a byte-substring test over
  the concatenated stream. It is not weakened or re-implemented per encoding;
  any widening (escaped forms) is a separate change for both paths.

What changes, stated plainly: today a response with a secret anywhere is
refused WHOLE. On a stream, the bytes before the match have already been
delivered. That is safe because none of them is part of a secret. The
remainder is withheld, and the caller learns the stream failed.

### 6. Owner-generation fence

Every `OPEN` carries the owner's lease generation
(`control_plane.lease.current_owner_lease().generation`). The broker persists
the highest acknowledged fence:

- `OPEN` below the fence ends `refused`/`fenced`, `side_effect_state: none`.
- `FENCE{G}` persists G durably, ends every open stream whose generation is
  below G (`cancelled`/`fenced`, `unknown` if its request was sent), then
  sends `FENCE_ACK{G}`.
- A broker restart reloads the fence before it serves. "Highest seen" alone
  is never the fence; the acknowledgment is (D5).

### 7. Lost replies: `op_id`

- The broker records each stream's outcome by `op_id` (`not_sent`,
  `sent:{status}`, `completed`, `cancelled`, `failed`) for a retention window
  (default 24 h, bounded by count).
- A caller that loses its connection mid-stream reconnects and sends
  `STATUS{op_id}`.
- The broker never re-sends a request whose `op_id` reached `sent`. An `OPEN`
  reusing such an `op_id` returns its recorded outcome.
- A stream's response bytes are not replayable; a lost stream is the caller's
  `unknown`. This is the journal's rule (S7, D2) applied to model calls.

### 8. Compatibility: request/close becomes a wrapper

`ScopedConnectionProxy.request(verb, request)` keeps its signature, errors and
return shape (`{"status", "reason", "headers", "body"}`). It opens one stream
with an inline body and unlimited credit up to the existing body cap, and
collects it to `END`. Every current caller (effectors, discovery, voice
signaling, `ApiKeyHttpProvider`) is unchanged. The spawned worker and its
startup handshake are deleted with S6; `close()` becomes a no-op.

### 9. The in-box endpoint maps onto streams

`boxhostd` serves plain HTTP on the box's private channel, in base-URL mode.
It turns each request into one stream on its box channel: method, path,
headers and a `streamed` body, with the box handle as the identity. It
relays `HEAD`/`DATA`/`END` back as the HTTP response. Its client disconnect
is a `CANCEL`. A CLI therefore gets exactly the loop's guarantees, and the
endpoint is never weaker than the loop path (refute round 2 of #4263).

### 10. Vendor neutrality

The broker forwards bytes. It never parses SSE events or any vendor's
envelope; its only content inspection is the secret scan. Parsing belongs to
the caller: the loop's incremental SSE reader folds chunks with the same
codec it uses today (`agent_chat_codec`). WebSocket upgrade is refused in v1:
no consumer needs it, and model streaming is SSE over HTTP/1.1.

## Rejected

- **Keep a worker process per stream.** This is today's memory cost, now
  times every waiting turn.
- **Give the loop the credential and let it stream itself.** That breaks the
  invariant this whole architecture rests on: no real credential in the loop
  or the box (S6 acceptance).
- **Scan only at the end and then release the stream.** This is today's
  shape, and it is exactly the latency we are removing.
- **gRPC/HTTP2 to the broker.** It would add a dependency and a code path for
  framing the D2 RPC already defines. Keep one framing for both local RPCs.

## Risks

- **The shape of the guarantee changes.** A response is no longer withheld
  whole on a scan hit. Decision 5 states why the delivered prefix is safe. A
  reviewer should attack the hold-back argument.
- **One broker process is one failure domain.** Today a crashed worker kills
  one request; a crashed broker kills every stream. Mitigations:
  - a supervised restart;
  - the fence reloads before serving;
  - every lost stream is `unknown`, so nothing replays.

  The blast radius is measured in S6's tests.
- **`SO_PEERCRED` is Linux-only.** On a Windows development host there is no
  broker socket. S6 must fail closed there, never fall back to an unchecked
  caller.

## Measurement owed by S6

- Broker memory per open stream at window 64 KiB (target about 100 KiB).
- Time to first byte versus today's request/close, through a mock SSE
  upstream.
- 500 concurrent streams through one broker process, with no thread per
  stream.
