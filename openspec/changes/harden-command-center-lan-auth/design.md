## Context

`command_center` is a standalone stdlib local dashboard that reads provider session logs, worktree/STATUS state, universes, and optional live MCP data. It also writes agent/universe inboxes, updates local universe provider presets, and can spawn peer provider CLIs. The merged baseline binds `0.0.0.0`, treats a token as optional, accepts it from a query parameter, stores it in `localStorage`, and performs POST actions without origin validation. This makes any machine on the LAN a reader and lets a hostile browser page drive mutations or provider spending.

The surface is a local host dashboard, not an MCP or platform-auth surface. The repair must remain stdlib-only and must not invent an account system or route local state through the platform. Plain HTTP on a LAN cannot protect the bearer or private responses from network observers, so this change deliberately makes phone/LAN access unavailable. A future remote-access change must supply authenticated confidentiality, such as an HTTPS reverse proxy or authenticated tunnel, before relaxing the listener boundary.

## Goals / Non-Goals

**Goals:**

- Make a bare launch safe on a developer laptop.
- Authenticate every data-bearing or mutating API request.
- Keep the shared token out of HTTP URLs, persistent browser storage, referrers, and normal access logs.
- Complete configuration validation and socket binding before any cache, collector, network, or worker activity begins.
- Block cross-origin and simple-form mutation requests before any collector call.
- Reject non-loopback listeners and DNS-rebinding `Host` values before route or token processing.
- Ensure no provider CLI can be spawned unless the operator enabled dispatch at launch.
- Preserve the zero-build static UI for direct loopback use.

**Non-Goals:**

- Multi-user accounts, remote internet exposure, TLS termination, OAuth, or platform identity.
- Phone/LAN access before an authenticated HTTPS or tunnel transport is designed and verified.
- Authorizing which local sessions/universes an authenticated operator may inspect.
- Changing MCP auth, provider credentials, paid-market behavior, or peer-agent implementation.
- Treating a shared token as suitable for an untrusted network.

## Decisions

### 1. Every launch has an environment-supplied or generated bearer token

`Config` receives either a URL-safe 20-128 character token from `TINYASSETS_VILLAGE_TOKEN` or a fresh `secrets.token_urlsafe(32)` value. Empty, short, long, or non-URL-safe environment values fail before socket construction. Supplying adequate entropy in an environment token is the operator's responsibility; the syntax/length check prevents malformed input, not weak choices.

The secret-valued `--token` and `--mcp-token` flags are removed because command arguments leak through process listings and shell history. Existing `WORKFLOW_MCP_TOKEN` environment resolution remains the only command-center MCP bearer input.

The CLI defaults to `127.0.0.1` and accepts only literal `127.0.0.1` or `::1`. It rejects `0.0.0.0`, hostnames such as `localhost`, LAN addresses, and every other value before constructing the HTTP server. A token never overrides this listener boundary. The launch log prints a fragment URL such as `http://127.0.0.1:8787/#token=...`; fragments are not transmitted in the HTTP request.

Alternatives rejected:

- Optional auth: leaves private sessions and writes exposed.
- Secret-valued CLI flags: expose credentials to shell history and same-host process inspection.
- A token only for LAN binds: loopback is reachable by hostile browser pages and DNS rebinding.
- Token-authenticated plaintext LAN: exposes bearer credentials and private responses to network observers.
- Resolving hostnames and accepting any result that includes loopback: creates resolver ambiguity and rebinding opportunities; literal loopback is the smallest auditable contract.
- Cookies: require a bootstrap/exchange route and CSRF token lifecycle without adding useful security to this local one-operator surface.

### 2. Static shell is inert; every API is header-authenticated

The index and checked-in static assets are readable without credentials and contain no local state. Every `/api/*` route, including health, requires `X-Village-Token`, compared with `hmac.compare_digest`. Query-string tokens are ignored and rejected as credentials.

The app reads `token` only from the URL fragment or current tab's `sessionStorage`, synchronously removes the fragment from the displayed URL, and sends the token as a header. The share button deliberately reconstructs a fragment URL. On an old `?token=...` URL, the app synchronously removes that query entry while preserving non-secret deep-link parameters and never promotes the legacy value into session storage or an authentication header.

Every success and error response, including `OPTIONS` and default-method failures, carries `Referrer-Policy: no-referrer`, `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, and exactly:

`Content-Security-Policy: default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'none'`

Every API success or error also carries `Cache-Control: no-store`. The server emits no CORS allow headers and its disabled request log never records tokens, targets, or headers.

Alternative rejected: continuing query authentication and merely redacting logs. URLs also leak through history, copied links, referrers, screenshots, and intermediary tooling.

### 3. Every request has a validated loopback authority

Before routing, serving a static asset, or evaluating a credential for any supported or rejected HTTP method, the server requires exactly one `Host` to name the actual bound loopback authority and port. For an IPv4 listener the accepted authority is `127.0.0.1:<bound-port>`; for an IPv6 listener it is `[::1]:<bound-port>`. Port `0` is replaced by the actual post-bind port. For the HTTP default port 80, the browser-canonical forms omit `:80`: `127.0.0.1` and `[::1]`. Missing, duplicate, comma-joined, whitespace-variant, wrong-family, or wrong-port values are rejected.

The production server selects an IPv4 or IPv6 address family from the already validated literal listener and uses a request backlog of at least 64. It ignores `Forwarded` and `X-Forwarded-Host`; neither can affect the accepted authority. It does not accept arbitrary hostnames that resolve to loopback.

This closes the DNS-rebinding path in which a hostile domain resolves to `127.0.0.1`, loads the otherwise inert app shell, and then issues same-origin requests to the local service. Rejection happens before routing so neither static assets nor route-existence differences are exposed through a hostile authority.

Alternative rejected: accepting `localhost` and checking only that it resolves to loopback. Resolution can vary by family, hosts-file state, and rebinding behavior; direct literal authorities keep the browser origin and listener identity exact.

### 4. Mutations require deterministic auth, routing, framing, and schema validation

Before parsing a POST body or invoking `collector`, the server validates in this order:

1. the singleton loopback `Host`;
2. exactly one valid, shape-checked `X-Village-Token`, compared with `hmac.compare_digest`;
3. the supported route and method;
4. exactly one `Origin` equal to `http://` plus that validated authority;
5. exactly one `Content-Type` equal to `application/json` or `application/json; charset=utf-8`;
6. no `Transfer-Encoding` and exactly one decimal `Content-Length` from 1 through 65,536;
7. exactly that many bytes of valid UTF-8 JSON whose top level is an object;
8. a route-specific strict schema.

Talk accepts only string `target` and a non-empty string `message` of at most 4,000 characters. Hire accepts only string `universe_id` and `provider`, optional string `task` of at most 2,000 characters, optional integer-not-boolean `count` from 1 through 8, and optional boolean `preset`. Unknown fields are rejected. Every accepted string rejects NUL and unpaired UTF-16 surrogate code points before it reaches a filesystem, subprocess, or collector boundary. This prevents type coercions such as `"preset": "false"` becoming a write and prevents late encoding/path failures from turning hostile input into dropped connections or 500s.

Unknown routes remain 404 only after authentication, preventing unauthenticated route probing. Missing/wrong origin returns 403, unsupported media returns 415, oversized bodies return 413, and framing/schema failures return a bounded 400. Body reads use a five-second socket deadline. Bad, oversized, partial, or timed-out framing closes the connection without parsing a partial body. `OPTIONS`, `HEAD`, and unsupported methods pass Host validation, return a bounded non-2xx response with security headers, expose no route detail to an unauthenticated request, and emit no CORS allow headers.

Alternative rejected: checking `Sec-Fetch-Site` alone. It is a useful browser hint but not an authorization boundary and is absent from non-browser clients.

### 5. Provider spending has a second explicit operator gate

Authentication authorizes access to the local dashboard but does not imply permission to spend provider quota. After strict `preset` parsing, `collector.hire` refuses every non-preset hire when `cfg.dispatch` is false before universe discovery, provider discovery, peer-script lookup, inbox/config writes, or thread creation. `_hire_dispatch` rechecks the gate as defense in depth. The existing `--dispatch` switch remains the explicit spending gate. Authenticated preset updates remain available because they change local configuration but do not invoke a provider.

Dispatch mode grants any bearer holder authority to spend the configured local provider subscriptions. One shared per-process atomic limiter covers both talk and hire and permits at most eight real provider process trees in flight. A hire that cannot reserve its full requested count is rejected with no partial dispatch, inbox write, or thread creation. A talk that cannot reserve its one worker still preserves its explicit inbox write but reports that dispatch capacity is full and starts no provider thread.

Every command-center peer wrapper receives a copied environment with `TINYASSETS_VILLAGE_TOKEN` and `WORKFLOW_MCP_TOKEN` removed. All unrelated provider subscription authentication remains available to `peer_agent.py`, whose own provider policy continues to select the allowed subscription environment. A fake peer probe must prove the two command-center bearers are absent without stripping the expected fake provider-auth marker.

The wrapper invokes `peer_agent.py` with a 540-second provider timeout and owns a 600-second outer timeout. Both the wrapper and peer launcher start a platform-appropriate process group and, on timeout or cancellation, terminate and reap the complete descendant process tree before returning. A limiter slot counts that real process tree and is released only after normal exit or verified process-tree cleanup, never merely because the Python wrapper timed out. Every success, error, and timeout path releases its reservation in `finally` after that condition is true. This preserves defense in depth and bounds the consequence of a compromised authenticated tab.

Talking to an agent remains inbox-only when dispatch mode is disabled. It may perform the explicit durable inbox write but starts no dispatch thread or subprocess.

### 6. Binding succeeds before observation starts

Configuration resolves and validates host, port, environment credentials, and all other launch invariants first. The production listener then constructs and successfully binds its socket. Only after successful binding may `StateCache.start()` launch polling or any collector, remote-platform, or worker activity.

Invalid configuration, address-family failure, or an occupied/unbindable port therefore leaves no listener, cache/poller thread, collector call, external network call, provider dispatch, or durable write. Listener-construction exceptions close any partially created socket before propagating.

## Risks / Trade-offs

- **[Static shell reveals the product name and asset bytes]** → It exposes no session, universe, path, provider, or health data; all APIs remain authenticated.
- **[Fragment token is readable by same-origin JavaScript]** → Keep scripts checked in and same-origin under CSP, use per-launch tokens and tab-scoped storage, and never claim this is safe for internet exposure.
- **[Existing phone/LAN workflow stops working]** → Failing closed is intentional because the old workflow exposes both bearer and private state over plaintext. Remote access returns only through a separately specified authenticated-confidential transport.
- **[Origin or Host validation rejects proxies]** → Remote/proxied service is a non-goal; the documented runtime is direct stdlib HTTP on literal loopback.
- **[An operator chooses a weak environment token]** → Document that entropy remains the operator's responsibility; generated tokens are cryptographically random, while syntax checks only reject malformed values.

## Migration Plan

1. Land red real-HTTP and CLI tests against the insecure baseline.
2. Add secure token/default resolution, API/header enforcement, mutation checks, and dispatch gating.
3. Update the browser token transport and README launch instructions.
4. Run the command-center suite, Ruff, strict OpenSpec, a real browser loopback flow, non-loopback and rebinding-negative probes, and a 32-request hostile-concurrency proof with zero collector calls or durable mutations.
5. Sync the modified canonical requirement and archive this change in the landing PR.

Rollback is permitted only to a loopback-only listener while repairing an incident; reverting to optional unauthenticated LAN behavior reopens the P0 and is not a safe steady state.

## Open Questions

None. Phone, LAN, internet, or multi-user access requires a separate authenticated-confidential reverse-proxy/tunnel or product-auth design.
