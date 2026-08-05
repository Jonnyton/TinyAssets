# Admit Slack app events over HTTP

## Why

The Slack custom-agent chain is fully built and unit-tested — `app_event_ingress`
(signature verification + replay ledger), `app_principal_mapping`,
`app_conversation_authority`, `app_reply_authority`, `app_outbound_adapter`,
`effectors/slack_transport`. **None of it has a production entry point.**

Verified on `origin/main` at `d65801eb`, and independently confirmed by an
opposite-family (Codex) review dispatched to *refute* the finding — it ran 11
distinct refutation attempts and found nothing:

| Probe | Result |
|---|---|
| `custom_route` / `add_route` / `@app.post` across `tinyassets/`, `deploy/`, `scripts/` | only `GET /` plus MCP + four `GET` OAuth-discovery routes |
| callers of `SlackRequestVerifier` / `SlackAppEventBoundary` outside `tests/` | none |
| `/slack`, `slack/events`, `url_verification` anywhere in the tree | only the *outbound* `chat.postMessage` URL |
| `deploy/cloudflared.yml`, `deploy/compose.yml` | no Slack path, no ingress service |
| Cloudflare Worker | route `tinyassets.io/mcp*`; `shouldProxy` accepts only `/mcp` and `/mcp/…` |

The as-built spec already records this gap rather than contradicting it —
`universe-custom-agents` states that a stored Slack channel reference leaves the
binding `configured` and that the platform "does not send, receive, or claim a
connected channel". This change closes exactly that gap.

Consequence today: a user can create a custom agent and bind a Slack channel,
but no message they send can ever reach it. Slack would sign and POST to an
address that does not answer.

## What Changes

- **ADD** an authenticated Slack Events API endpoint at **`POST /mcp/app/slack/events`**
  on the universe server, composing the existing `SlackAppEventBoundary`.
- **ADD** handling for Slack's `url_verification` challenge, which the existing
  boundary deliberately rejects (`_normalize_authenticated_envelope` admits only
  `event_callback`). Without this the Request URL can never be saved in Slack at
  all, so no other behavior in this change is reachable.
- **ADD** fail-closed configuration resolution for the Slack signing secret and
  expected app id. Absent or malformed configuration disables the route; it MUST
  NOT degrade into accepting unverified requests.
- **ADD** ack-fast response semantics — Slack retries when an endpoint does not
  respond within 3 seconds, and a retry storm on a signature-verifying endpoint
  is self-inflicted load.

### Why `/mcp/app/slack/events` and not a new top-level path

The public edge only forwards `/mcp` and `/mcp/…`: the Cloudflare route binding
is `tinyassets.io/mcp*` and the Worker's `shouldProxy` re-checks the same prefix.
A new top-level path such as `/app/slack/events` would be unreachable from the
internet until someone changes the Cloudflare route binding in the dashboard —
a host-only action that would block this work.

Mounting under `/mcp/` needs **zero** Cloudflare changes, and the pattern is
already proven in production: `/mcp/.well-known/oauth-protected-resource` is an
existing `custom_route` living under the same prefix alongside the MCP mount.
The Worker preserves method, header set, and the body *stream* unmodified, which
HMAC verification requires — a body rewrite would break every signature.

This does not weaken the "`tinyassets.io/mcp` is the only public user-facing URL"
invariant: a Slack webhook is a machine callback, not a user-facing URL.

## A reversed invariant this change must retire explicitly

`tests/test_app_event_ingress.py` carried
`test_boundary_is_dark_and_has_no_production_consumer`, asserting the boundary
had **no** production consumer. That was correct when #2246 landed it — the
boundary existed before anything downstream did. This change reverses it, so it
cannot be left to pass quietly.

It also has to be *replaced* rather than deleted, because it was already
unsound: it grepped `universe_server.py` and `tinyassets/api/*.py` for the
literal string `app_event_ingress`. Routing through one intermediate module
(`app_slack_ingress.py`) satisfies the substring check while the boundary is
fully wired to a public endpoint — **verified: it passes green against this
branch.** It failed in exactly the situation it was written to catch.

The replacement walks the import graph instead of matching a name, pins the
exact expected consumer set, and additionally asserts the ingress module is
fail-closed when unconfigured. Proof it guards: planting a second module that
imports the boundary turns it red, while the original guard was demonstrably
blind to this branch's real wiring.

Activation is therefore gated by *configuration* (both env vars present), not
by the absence of a caller — which is the honest gate, since a caller's absence
was never actually being checked.

## Impact

- Affected specs: `live-mcp-connector-surface` (new non-MCP route under the same
  prefix), `universe-custom-agents` (the "not a connected channel" scenario stops
  being unconditional once an installation is configured).
- Affected code: `tinyassets/universe_server.py`, new
  `tinyassets/app_slack_ingress.py`, `deploy/compose.yml` (env plumbing),
  `deploy/cloudflare-worker/worker.test.js` (assert the prefix keeps forwarding).
- **Out of scope, deliberately:** dispatching an admitted event to the agent turn
  and delivering the reply. This change admits and acknowledges events only. The
  execution half must run on the requester's own provider — the path `run_graph`
  already proves works — not on a maintainer-run worker pool, and that routing
  decision deserves its own change rather than being smuggled in here.
- **Security posture:** this is a publicly reachable, unauthenticated-by-TinyAssets
  endpoint whose only trust anchor is Slack's HMAC. It gets a cross-family
  security review before it is deployed, not after.
