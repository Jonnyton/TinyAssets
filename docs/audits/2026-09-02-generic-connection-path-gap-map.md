# The generic connection path against the first-wave platforms

**Date:** 2026-09-02. **Tree:** `origin/main` at `1a92bd57` (+ one docs commit), canonical
`tinyassets/` only. **Method:** a read-only code audit (Claude subagent), every claim cited to a
file and line; no runs, no live calls.

**Why this exists.** The founder's bar (2026-09-01, in the app and to me): a universe must be
able to connect to ANY outside platform, even ones nobody planned for, ask for exactly the
user-facing credentials it needs, and build any graph on it, with **zero platform-specific
patches**. GitHub, then x.com, then a surprise service are the acceptance test. Tiny named the
first wave it wants: Slack, Google Workspace/Gmail, Notion, Stripe, HubSpot, Shopify, GitHub,
Twilio. This map says, per credential and transport shape those platforms actually use, whether
the generic path carries it today and exactly where it stops.

Audits are diagnostic, never a source of truth (AGENTS.md). Each gap below becomes real work
only as an OpenSpec change or a concern; the ranked list at the end is the proposed order.

## What the generic path carries today

The outbound half is genuinely channel-agnostic. Four auth schemes are depositable
(`tinyassets/api/http_connection.py:101`), the broker signs all of them inside a
credential-blind child (`tinyassets/storage/outbound_connections.py:1230`), and the effector's
packet is fully user-specified with no per-service branch
(`tinyassets/effectors/authenticated_external_call.py:20`). Five methods are allowed
(`outbound_connections.py:1069`), bodies are 5 MB in and 8 MB out, redirects are structurally
off (`outbound_connections.py:2111`), and the per-endpoint allowlist supports path placeholders
plus declared query keys (`outbound_connections.py:36`).

Two flags gate all of it. **Outbound is on** in production
(`TINYASSETS_OUTBOUND_HTTP_CONNECTIONS_ENABLED=1`, `docs/host-actions.md:259`). **Inbound is
dark** by default (`tinyassets/webhook_inbound.py:92`), unset in production
(`docs/reviews/2026-08-29-codex-background-loop-shape.md:21`), its enabling task still
unchecked (`openspec/changes/channel-agnostic-inbound/tasks.md:24`). So the whole outbound
half of this audit is live and the whole inbound half is code that cannot execute.

## Gap map

| Platform | Shape it actually needs | Today | Evidence | What is missing |
|---|---|---|---|---|
| GitHub | Bearer PAT, JSON bodies | yes | `http_connection.py:101`; `outbound_connections.py:1243` | nothing; a live connection already exists |
| x.com | OAuth 1.0a, four secrets | partial | `http_connection.py:104`; `outbound_connections.py:1176` | the signature base string covers query params only, never form-encoded body params, so v1.1 form endpoints get a 401 (`outbound_connections.py:1198`); v2 JSON endpoints are unaffected |
| Slack (outbound) | Bearer bot token, JSON | yes | `outbound_connections.py:1243`; `_encode_request_body` at `:2238` | nothing |
| Notion | Bearer plus a required `Notion-Version` header | yes | caller headers allowed, only auth/framing names refused (`outbound_connections.py:1020`, `:1033`) | works, but the version header must be retyped in every node's packet; no per-connection constant headers |
| Shopify | `X-Shopify-Access-Token` header, GraphQL POST | partial | scheme exists (`http_connection.py:101`); applied at `outbound_connections.py:1247` | the header **name** is per-call only (`authenticated_external_call.py:977`), not stored on the connection row (`outbound_connections.py:96`), absent from the connections readback, never mentioned on the served tool surface |
| Stripe | Bearer plus form-urlencoded bracket-nested bodies | partial | only dict and list auto-encode, as JSON (`outbound_connections.py:2238`) | no form encoder and no `$ta` transform for one; the node must emit a hand-built urlencoded string and set the content type itself |
| Twilio | HTTP Basic, form-urlencoded required | partial | basic scheme at `http_connection.py:101`, split at `outbound_connections.py:2467` | same missing form encoder as Stripe |
| HubSpot (private app) | Bearer, JSON | yes | as Slack | nothing |
| HubSpot (public app), Google Workspace, Gmail | OAuth2 access token that expires, refreshed against a token endpoint | **no** | zero hits for refresh, expiry, or token endpoint across `tinyassets/storage/` and `tinyassets/effectors/` | there is no refresh mechanism at all; a Google token dies in an hour and only a fresh owner paste revives it. Same class as the Codex subscription P0 (`docs/concerns/2026-09-01-a-subscription-credential-dies-permanently-at-its-first-token-expiry.md`) |
| Slack, Stripe, Shopify, GitHub inbound | Webhook POST plus HMAC signature check | partial | receiver at `tinyassets/webhook_inbound.py`; signature headers forwarded at `:67` with the raw body at `:225` | no HMAC or compare primitive exists among the six body transforms (`authenticated_external_call.py:203`), so verification is not expressible in any graph |
| Slack Events API setup | Echo the `url_verification` challenge in the HTTP response | no | every success returns a fixed body (`webhook_inbound.py:193`, `:236`, `:242`) | a branch cannot shape the response, so Slack will never accept the Request URL |

## Two frictions tiny reported, confirmed

**Consent state is not readable up front.** `read_graph target=connections` projects
`connection_id`, `grant_id`, `provider`, `destination`, `connection_class`, `scopes`,
`allowed_endpoints`, `action_cap`, `git_scopes` and a hard-coded `status: "connected"`
(`tinyassets/api/cloud_connections.py:58`). It carries no `auth_scheme` and no consent row for
the `authenticated_external_call` sink. The only consent that rides along is
`workspace_consents` (`cloud_connections.py:255`), filtered to the git sink
(`cloud_connections.py:92`); outbound HTTP consent is a different sink
(`authenticated_external_call.py:125`). At call time the effector fails closed on a missing
row (`authenticated_external_call.py:663`), so the first signal is a refused live call. Nothing
in the deposit path grants it: `connect_http` returns it as a manual next step in prose
(`http_connection.py:233`), and answering a `connect_http` ask does not grant it either; the
ask path's only `grant_consent` is for the workspace sink (`pending_requests.py:879`). The one
writer the universe's agent can reach is `source_channel approve`
(`api/source_channel.py:395`); there is no matching read on the served surface (read targets
pinned at `engine_mcp_server.py:231`; `list_effector_consents` exists only on the deprecated
extensions tool, `extensions_consent_actions.py:154`).

**Branch read versus create shape, half fixed.** Create accepts a nested `graph` blob only for
edges, conditional edges and entry point, via the `_spec_get` fallback from PR-037
(`api/branches.py:2327-2345`, used at `:2413`, `:2418`). Nodes are read from the top level only
(`spec.get("node_defs") or spec.get("nodes")`, `:2408`); the blob is never consulted for them.
So posting a read response back nests the nodes, they are silently dropped, the edges survive,
and validate reports nodes unreachable from the entry point: the exact contradiction tiny hit.
The read side returns the flat dict with `node_defs` at the top (`:555`); the genuinely nested
blob comes from a different entity, the `branches` table row (`daemon_server.py:2452`).

## Ranked primitives, smallest first by gaps closed

Generic, never platform-specific. Each is one OpenSpec change (public surface or storage
shape) or one build-then-spec slice.

1. **A refreshable OAuth2 credential.** An `oauth2` scheme whose vault string holds client id,
   client secret and refresh token, plus a token endpoint stored on the connection; the broker
   child exchanges for an access token when the cached one is missing or stale. The only item
   that turns a hard no into a yes. A user cannot build the refresh themselves: the three effect
   sinks are the external call, wiki write-back and workspace (`effectors/__init__.py:264`), so
   no graph can write a new token back to the vault. Touches `outbound_connections.py` (scheme
   set `:363`, bundle builder `:2433`, a pre-request exchange inside the child),
   `api/http_connection.py` (`:101`, `:104`), `api/pending_requests.py` (`:87`), the vault
   writer. Design it together with the subscription-credential P0: one rotating-credential
   story, not two.
2. **Body encoding as a declared packet field.** `encoding: json | form`, bracket-nesting for
   dicts, and form parameters folded into the OAuth 1.0a signature base string when the
   encoding is form. Unblocks Stripe writes, Twilio, and x.com v1.1 in one change. Touches
   `authenticated_external_call.py`, `outbound_connections.py:1198`, `:2238`.
3. **Per-connection constant headers and a persisted auth header name.** A small header map on
   the connection row, applied in the broker. Removes Shopify's silent-failure mode and the
   retyped version headers on Notion and Stripe. Touches `outbound_connections.py`,
   `api/http_connection.py`, `api/pending_requests.py`, `api/cloud_connections.py`.
4. **Signature verification declared on the Source, not in the graph.** A signing secret per
   webhook, HMAC verified before enqueueing, so the secret never reaches a model. Unblocks
   trustworthy inbound for Stripe, Shopify, GitHub and Slack together. Touches
   `webhook_inbound.py`, `storage/webhook_hooks.py`, `api/webhook_ops.py`. (Inbound must also be
   turned on: it is dark in production.)
5. **A declarative challenge echo on the Source.** Echo one named request field in the
   response so Slack's URL verification can be answered. A few lines in `webhook_inbound.py`,
   `api/webhook_ops.py`.
6. **Outbound consent readable, or granted at the ask.** Add `auth_scheme` and the sink's
   consent row to the connections projection (`api/cloud_connections.py:58`), or grant the
   consent when the owner answers the credential ask, since answering it is the authorization
   (`api/pending_requests.py`).
7. **Read nodes from the graph blob on create.** A one-line symmetry fix at
   `api/branches.py:2408`.

## What this means for the acceptance test

- **GitHub**: carried today. The remaining blockers were control-plane (locks, serving), fixed
  2026-09-01/02.
- **x.com**: carried for v2 JSON endpoints (post a tweet); v1.1 form endpoints (media upload)
  need item 2.
- **A surprise service**: any static-token API is carried today with the caveats of items 3 and
  6; anything OAuth2-refreshed (Google, HubSpot public app) is not, until item 1.
- **24/7 on the user's behalf**: not in this map. It is a user-built graph with a trigger, and
  its blocker is that triggers still fire through the fleet-era consumer instead of the
  ordinary run path (`docs/concerns/2026-08-29-background-loop-activation-is-fleet-era.md`).
