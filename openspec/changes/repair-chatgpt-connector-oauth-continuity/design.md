## Context

On 2026-07-30 a rendered ChatGPT Temporary Chat reproduced the same failure
both before and after a successful TinyAssets reconnect. Production received
the OAuth discovery and Streamable-HTTP handshake requests successfully, then
returned `401` for the first authenticated tool call. The resource server
currently converts every PyJWT validation failure into an anonymous result and
logs details only at DEBUG, so production evidence cannot yet distinguish
audience, issuer, expiry, required-claim, or signing-key failure.

This is not only a connector acceptance defect. TinyAssets defines a chatbot
with the installed connector as the complete control surface for user-owned
cloud workflows. The first conformance proof is Jonathan's private
GitHub-to-OpenSpec drain, but the product behavior must be user-neutral: any
user can bind an authorized repository and their own spec to an ordinary
Branch composition, then build, inspect, repair, and evolve it without a
personal computer online.

Authentication remains fail-closed. Production uses WorkOS/AuthKit, the exact
`https://tinyassets.io/mcp` resource indicator, RS256, issuer binding, and
required claims. The repair cannot use the development audience bypass,
anonymous-write fallback, raw token logging, or maintainer identity.

## Goals / Non-Goals

**Goals:**

- Identify the exact post-reconnect token rejection using bounded,
  non-sensitive production evidence.
- Make OAuth authorization, token validation, refresh/reconnect, and MCP calls
  interoperable for the advertised resource.
- Make rendered connector identity continuity an implementation prerequisite
  for user-owned cloud automation.
- Preserve fail-closed resource-server and owner-authorization boundaries.

**Non-Goals:**

- Adding a new identity provider, MCP handle, local companion process, or
  privileged drain service.
- Accepting tokens without signature, issuer, audience, expiry, subject, or
  algorithm validation.
- Logging bearer tokens, JWT payloads, claim values, or user-identifying data.
- Implementing the cloud drain itself in this repair lane.

## Decisions

### 1. Diagnose the exact validator boundary before changing acceptance

`WorkOSAuthProvider.resolve_token` will classify validation failures into a
small allowlisted taxonomy such as `expired`, `audience`, `issuer`,
`required_claim`, `signature`, `signing_key`, and `malformed`. Production logs
will include only the category and stable event name. The exception string,
token, headers, payload, and claim values will never be logged.

Tests will first prove that representative PyJWT failures produce the expected
category and that secrets/claims are absent. This is preferred over changing
WorkOS dashboard settings or validator parameters speculatively, because the
observed `401` has several standards-valid causes.

### 2. Treat public metadata, AuthKit configuration, and validation as one contract

The advertised Protected Resource Metadata resource, the resource sent during
authorization, the WorkOS Resource Indicator, and `WORKOS_MCP_RESOURCE` must
all be the same canonical URL after normalization. The repair will capture
current values without tokens, reproduce once with safe diagnostics, and
correct only the mismatched boundary the evidence identifies.

If the failure is client registration or refresh behavior, the authorization
server configuration will be corrected using WorkOS-supported MCP settings
(including Resource Indicator and the supported client registration mechanism)
rather than relaxing resource-server validation. If it is server validation,
the validator will be corrected narrowly and retain the same security
invariants.

### 3. Continuity is proven as a sequence, not by isolated green endpoints

Acceptance requires one rendered chatbot sequence:

1. connect or reconnect TinyAssets;
2. complete MCP initialization;
3. perform an authenticated read/control call;
4. perform a later authenticated call using the continued or refreshed
   session; and
5. confirm the same TinyAssets account/universe is addressed.

Direct metadata requests, unit tests, canaries, and server logs support this
proof but cannot replace it. The sequence must also remain valid after the
cloud service restarts without a personal computer or local credential broker.

### 4. Cloud-automation implementation is gated at the identity seam

This change's connector-continuity requirement applies to generic user-owned
GitHub-to-spec production loops, with Jonathan's drain as the first conformance
instance. Only planning, specification, review, and dependency verification
may advance until the live connector completes the authenticated continuity
sequence. No drain runtime code—including inactive adapters, persistence,
execution, or activation scaffolding—may start before that proof. The
separately evolving `activate-main-universe-spec-drain` artifacts are not
rewritten by this restack.

This avoids building a nominally cloud-resident workflow that its owner cannot
operate, repair, or evolve through the product's canonical interface.

## Risks / Trade-offs

- **[A safe category is still too vague]** → Keep the taxonomy aligned with
  validation boundaries and correlate by timestamp/request outcome, never by
  token or claim content.
- **[A dashboard-only correction drifts later]** → Add parity checks for public
  metadata and deploy configuration where automatable; record any unavoidable
  WorkOS control-plane setting and verify it in the live sequence.
- **[Refresh works once but later expires]** → Exercise a later call after
  continuity/refresh and retain a monitoring watch until post-fix real-user
  evidence exists.
- **[A repair broadens token acceptance]** → Keep negative tests for wrong
  algorithm, issuer, audience, expiry, subject, and missing claims; production
  audience bypass remains disabled.
- **[Connector recovery delays the cloud drain]** → Keep this lane narrow and
  treat it as the shortest prerequisite; do not mix cloud scheduler or GitHub
  execution code into this change.

## Migration Plan

1. Land test-first sanitized validation classification and deploy it without
   changing token acceptance.
2. Reproduce one authenticated call and capture the exact safe category plus
   public metadata/config parity.
3. Implement the smallest evidence-backed code or WorkOS configuration repair;
   retain all fail-closed negative tests.
4. Run focused auth tests, lint, public MCP canary, and rendered ChatGPT
   continuity proof.
5. Check production for post-fix clean use. If none exists yet, leave a dated
   monitoring row rather than claiming proven organic use.
6. Sync/archive this change, then unblock the generic cloud-drain
   implementation gate.

Rollback restores the prior validator/configuration while keeping sanitized
diagnostics available. If rollback reintroduces the authenticated-call `401`,
the cloud automation remains blocked rather than falling back to anonymous or
desktop control.

## Open Questions

- Which safe validation category will the post-instrumentation reproduction
  produce?
- If configuration differs, is the mismatch in WorkOS Resource Indicator,
  client registration/refresh behavior, advertised metadata, or deployed
  resource-server environment?

These are diagnostic questions, not permission to weaken validation.
