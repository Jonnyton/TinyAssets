# A `converse` SSE response is silent for minutes and nothing keeps it alive

**Filed:** 2026-08-28
**Verified:** partially — the client-side symptom is reproduced and fixed; the
server-side cause below is *suspected*, not proven on the wire.
**Severity:** P2 — the client now survives it (PR #2640), so this is "stop it
happening", not "stop it breaking".

## The claim

`converse` runs the user's own LLM as a subprocess, which takes minutes — the
watcher on 2026-08-28 recorded turns at `NEW TURN after 3m` and `after 2m`. The
canonical `/mcp` app is created with
`mcp.http_app(path="/mcp", transport="streamable-http")`
(`tinyassets/universe_server.py:3099`), which defaults to `json_response=False`,
so every tool call is answered over an SSE stream.

That stream sends **nothing at all** until the result frame. The MCP SDK's
priming event is not in play: `_maybe_send_priming_event`
(`mcp/server/streamable_http.py:270`) only fires when an `event_store` is
configured *and* the client negotiated protocol >= `2025-11-25`, and the
onboarding app sends `protocolVersion:"2024-11-05"` with no event store
configured. There is no other keepalive.

A minutes-long response with zero bytes is exactly the shape an intermediary
terminates. When it does, the client sees a 200 whose body ends mid-frame.

## Why this is the suspected root cause of the "json issue"

The user-visible symptom was `Couldn't reach your universe: no JSON or SSE
frame`, thrown from the client's `_parse` on an HTTP **200**. A 200 whose body
is non-empty but carries no complete `data:` line is a truncated SSE stream —
the body holds the `event: message` line and stops. Every other failure mode
reaching that string was ruled out: 4xx/5xx take other branches, and a wholly
empty body throws `empty MCP response` instead.

**This is not yet proven on the wire.** It is the best-supported explanation,
not a confirmed one. Proving it needs the raw response captured at the moment
of failure (browser network log, or `curl -N` against `/mcp` for a turn known to
exceed the timeout) plus the tunnel's own log for the same request id.

## What is already done

PR #2640 makes the client survive it: a truncated stream now invalidates the
session, reports a sentence instead of the parser string, and offers a
**Send again** button. It deliberately does **not** auto-replay — the universe
may have taken the turn and be answering it, so replaying could double-send.

## What is not done

The stream is still silent, so long turns can still be cut, and the user still
has to press Send again. Options, roughly in order of appetite:

1. **Emit SSE comment keepalives** (`: ping\n\n`) on the response stream while a
   tool call is running. Standard, invisible to compliant clients, and it resets
   every idle timer in the path. Needs a hook into the SDK's SSE writer that
   does not fork the SDK.
2. **Return the turn asynchronously** — answer the tool call immediately with a
   run id and let the client poll or reconnect. A much larger change to the
   connector contract, and it affects chatbot clients too, not just the app.
3. **Raise the intermediary's timeout** if the cut is Cloudflare's and not the
   origin's. Cheapest if it is sufficient, but it only moves the ceiling.

Option 1 is the one to try first, and it should be measured against a turn known
to run past the current cut-off rather than assumed.

## How to resolve this file

Delete it when a long `converse` (>3 min) completes over the live connector
without the client reporting `stream_truncated`, with the evidence stamped:
date, the turn's duration, and the surface it ran on.
