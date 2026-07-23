## MODIFIED Requirements

### Requirement: Agent Village Observes Durable Coordination State

The `command_center` runtime SHALL serve a zero-build browser interface and a JSON state endpoint that aggregate detected provider sessions, `STATUS.md` claims, worktree status, recent file/git/activity signals, local universes, and reachable public MCP state. Missing transcripts, provider homes, worktree probes, or remote platform data MUST degrade to absent or explicitly unavailable state rather than fabricated agents, universes, or health.

The listener SHALL default to literal `127.0.0.1`, SHALL accept only literal `127.0.0.1` or `::1`, and SHALL reject every hostname, wildcard, LAN, or other non-loopback listener value before opening a socket. A token MUST NOT override this boundary. Configuration validation and a successful IPv4/IPv6 socket bind MUST complete before any cache, poller, collector, external-network, provider, or other worker activity begins. Validation or bind failure MUST close any partial listener and leave zero worker threads, collector calls, external calls, or durable effects.

Every launch SHALL use either a URL-safe 20-128 character token supplied through `TINYASSETS_VILLAGE_TOKEN` or a newly generated cryptographically random token. Secret-valued Village and MCP CLI arguments MUST NOT be accepted. Every `/api/*` request, including health, MUST authenticate through exactly one shape-valid `X-Village-Token` header using constant-time comparison; a query parameter MUST NOT authenticate. The inert index and checked-in static assets MAY load without authentication but MUST contain no local coordination, session, universe, provider, path, or health state.

The browser SHALL receive a share token only through the URL fragment, retain it only in current-tab session storage, synchronously remove it from the displayed URL, and send it only in the authentication header. It MUST NOT persist the token in local storage or append it to API URLs. A legacy query token SHALL be synchronously removed while preserving other deep-link parameters and MUST NOT be promoted into session storage or authentication.

Before routing, asset serving, or authentication for any supported or rejected method, the server SHALL require exactly one `Host` equal to the actual post-bind literal loopback authority and port, using bracketed IPv6 and browser-canonical port-80 omission. Missing, duplicate, comma-joined, whitespace-variant, wrong-port, hostname, or wrong-family authorities MUST be rejected; forwarded-host metadata MUST be ignored.

Every success and error response, including `OPTIONS` and default-method failures, SHALL set `Referrer-Policy: no-referrer`, `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, and `Content-Security-Policy: default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'none'`. Every API response SHALL also set `Cache-Control: no-store`. No response SHALL emit CORS allow headers, and the disabled request log MUST NOT record tokens, targets, or headers.

#### Scenario: Remote world data is unreachable

- **WHEN** the configured public MCP endpoint cannot be read
- **THEN** the snapshot keeps local coordination and universe evidence available
- **AND** it identifies the remote world as unavailable without synthesizing remote entities

#### Scenario: Bare launch is loopback and authenticated

- **WHEN** the command center starts without an explicit host or token
- **THEN** it binds `127.0.0.1` and generates a fresh bounded URL-safe token
- **AND** its printed browser URL transports that token in the fragment rather than the query

#### Scenario: Non-loopback listener is refused

- **WHEN** an operator configures a wildcard, hostname, LAN, or other non-loopback listener even with a valid token
- **THEN** startup fails before opening a socket
- **AND** the service does not claim that plaintext phone or LAN access is secure

#### Scenario: Validation or bind failure starts no observation

- **WHEN** launch receives an invalid host, port, or environment token, or the validated port cannot be bound
- **THEN** startup fails without starting the state cache, collector, external platform access, or any worker
- **AND** it leaves no listener or durable effect

#### Scenario: Ambiguous or DNS-rebinding authority is refused

- **WHEN** a request has a missing, duplicate, comma-joined, hostname, forwarded, wrong-family, wrong-port, or other non-canonical `Host`
- **THEN** the server rejects it before routing, authentication, static-asset serving, or collector access
- **AND** forwarded-host metadata cannot change the accepted authority

#### Scenario: Static shell contains no private state

- **WHEN** an unauthenticated client requests the index or a checked-in static asset
- **THEN** the server may return that inert asset
- **AND** an unauthenticated request to any `/api/*` route is rejected without local state

#### Scenario: Header token protects the village

- **WHEN** a client requests an API with no token, a wrong header token, or a matching query token only
- **THEN** the server returns unauthorized
- **AND** the same request with the matching `X-Village-Token` may reach that API

#### Scenario: Browser secret does not persist or enter requests

- **WHEN** the app opens a fragment-token share URL
- **THEN** it stores the token only for the current tab and removes the fragment from the displayed URL
- **AND** subsequent API URLs, history, and referrer data contain no token

#### Scenario: Legacy query token is retired without promotion

- **WHEN** the app opens an old URL containing `?token=...` plus non-secret deep-link parameters
- **THEN** it synchronously removes only the token query entry from the displayed URL
- **AND** it never copies the legacy value into session storage or an authentication header

### Requirement: Agent Village Writes Only Through Explicit Talk And Hire Actions

The command center SHALL remain read-only except for explicit authenticated talk and hire requests. Every POST SHALL validate in this order before any collector call: singleton canonical loopback `Host`; exactly one shape-valid header token; supported route/method; exactly one `Origin` equal to `http://<validated-authority>`; exactly one JSON or UTF-8 JSON `Content-Type`; no `Transfer-Encoding`; exactly one decimal `Content-Length` from 1 through 65,536; exactly that many bytes of valid UTF-8 JSON with an object top level; and a strict route schema.

Talk SHALL accept only a string `target` plus a non-empty string `message` of at most 4,000 characters. Hire SHALL accept only string `universe_id` and `provider`, optional string `task` of at most 2,000 characters, optional integer-not-boolean `count` from 1 through 8, and optional boolean `preset`; unknown fields SHALL be rejected. Every accepted string SHALL reject NUL and unpaired surrogate code points before any collector, filesystem, or subprocess boundary.

Missing or cross-origin requests, browser-simple forms, transfer encoding, duplicate/invalid/empty/oversized framing, partial bodies, non-object or malformed JSON, schema/type confusion, unknown routes, and rebinding authorities MUST produce bounded failures without mutation. Body reads SHALL have a five-second socket deadline; framing failures or timeouts SHALL close the connection. `OPTIONS`, `HEAD`, and unsupported methods SHALL pass Host validation, return bounded non-2xx responses with the required security headers, and produce no effect. The server MUST NOT enable cross-origin request handling or successful CORS preflight.

Talking to an agent SHALL append a durable inbox/chat record and SHALL dispatch a provider CLI only when dispatch mode is enabled. Talking to a running local universe SHALL write an engine-compatible note; talking to a dormant universe SHALL pin an inbox note. Hiring SHALL validate the universe and advertised provider capability, MAY update the universe's preferred-writer preset, and SHALL spawn peer CLI work only when the provider is available and dispatchable AND the operator enabled dispatch mode at process launch.

After strict `preset` parsing, a non-preset hire with dispatch disabled MUST fail before universe/provider discovery, peer-script lookup, inbox/config writes, or thread creation, and the collector-level dispatch function MUST recheck the gate. When dispatch is enabled, one shared atomic per-process limiter SHALL cap talk and hire provider process trees at eight in flight. A hire that cannot reserve its entire count MUST produce no partial dispatch, write, or thread; a talk that cannot reserve its one worker SHALL preserve its explicit inbox write but start no provider thread and report capacity exhaustion.

Every dispatched peer environment MUST omit `TINYASSETS_VILLAGE_TOKEN` and `WORKFLOW_MCP_TOKEN` while preserving the separately allowed provider subscription authentication. The provider timeout MUST be strictly shorter than its wrapper timeout. Both launcher layers MUST own a platform-appropriate process group and terminate plus reap the complete descendant process tree on timeout or cancellation. A talk or hire reservation MUST count the real provider process tree and MUST be released in `finally` only after normal exit or verified process-tree cleanup, never merely when an outer wrapper times out. Hosted or market capacity MUST remain disabled and honestly labeled while that execution stack is absent.

#### Scenario: Agent talk without dispatch mode

- **WHEN** an authenticated same-origin user sends a valid message to an agent while dispatch mode is disabled
- **THEN** the command center appends the message to that agent's durable village inbox and chat history
- **AND** it starts no provider CLI process

#### Scenario: Cross-origin mutation is rejected before collection

- **WHEN** a POST has a missing or non-matching origin, a missing/wrong header token, a non-JSON media type, or an oversized body
- **THEN** the server rejects it before calling talk, hire, provider discovery, or any filesystem mutation

#### Scenario: Ambiguous framing or schema is rejected

- **WHEN** a POST has duplicate Origin or media headers, transfer encoding, duplicate or invalid content length, a partial body, non-object JSON, unknown fields, a wrong field type, NUL, or an unpaired surrogate
- **THEN** the server returns a bounded failure before collection and closes the connection for a framing failure
- **AND** string or boolean coercion cannot turn the request into a preset, worker count, target, or message

#### Scenario: Browser preflight and unsupported methods stay disabled

- **WHEN** an `OPTIONS`, `HEAD`, or unsupported-method request reaches the listener
- **THEN** Host validation still applies and the response is non-successful with the required security headers
- **AND** it emits no CORS allow header and causes no cache, collector, provider, or durable effect

#### Scenario: Mixed concurrent hostile requests have no effects

- **WHEN** a barrier simultaneously releases at least 32 requests whose declared mix includes every anonymous-read, query-token-read, cross-origin-write, simple-form-write, oversized/framing-write, rebinding-authority, and valid-auth dispatch-disabled-hire class across GET and POST routes
- **THEN** every request completes within a fixed deadline with a bounded non-5xx response
- **AND** no cache read, collector/provider call, provider thread, inbox/config write, preset update, or other durable mutation occurs

#### Scenario: Hire dispatch requires process-level enablement

- **WHEN** an authenticated same-origin hire selects an available dispatchable provider while dispatch mode is disabled
- **THEN** both the entry point and collector dispatch boundary reject before discovery, lookup, writes, or thread creation
- **AND** an explicit preset-only update remains separately available without spending provider quota

#### Scenario: Talk and hire share atomic bounded dispatch capacity

- **WHEN** dispatch-enabled talk and hire requests together would exceed eight provider process trees in flight
- **THEN** an over-cap hire is rejected without partial dispatch, write, or thread while an over-cap talk remains inbox-only and reports capacity exhaustion
- **AND** completed or failed talk and hire workers release their reserved slots

#### Scenario: Provider peers cannot inherit command-center bearers

- **WHEN** talk or hire dispatches a peer using valid provider subscription authentication
- **THEN** the peer process and its descendants cannot read `TINYASSETS_VILLAGE_TOKEN` or `WORKFLOW_MCP_TOKEN`
- **AND** the separately allowed provider authentication remains available

#### Scenario: Timeout reaps the paid process tree before releasing capacity

- **WHEN** a provider peer exceeds its shorter provider timeout or the outer wrapper reaches its timeout
- **THEN** the platform-appropriate launcher terminates and reaps the complete peer process tree
- **AND** the shared capacity slot is released only after no descendant provider process remains

#### Scenario: Unsupported market hire is refused

- **WHEN** a hire request selects hosted or market capacity advertised as unavailable
- **THEN** the command center returns a validation failure and spawns no worker
- **AND** the response preserves the current coming-later limitation
