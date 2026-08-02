# ChatGPT OAuth continuity diagnosis

Date: 2026-07-30
Environment: production `https://tinyassets.io/mcp` and Windows test worktree
Change: `repair-chatgpt-connector-oauth-continuity`

## Current conclusion

A successful ChatGPT reconnect does not continue into an accepted
authenticated TinyAssets tool call. OAuth discovery and MCP initialization
complete, then the first bearer-authenticated call receives `401
invalid_token`. This blocks runtime implementation of the generic user-owned
GitHub-to-spec cloud production loop.

The exact JWT validation boundary is not yet known. No audience, issuer,
expiry, key, or claim repair is authorized until token-safe production
telemetry identifies it.

A second rendered attempt on 2026-08-01 reached ChatGPT's
`link_success=true` return but did not retain TinyAssets in the returned
conversation's plugin picker. A complete, non-truncated production journal
window for that attempt contained no sanitized token-rejection category. This
attempt therefore failed before the instrumented bearer validator; it is not
evidence for relaxing or changing JWT validation.

A third rendered attempt on 2026-08-02 reattached TinyAssets successfully
through the same-tab OAuth return. The original call did not resume, and an
explicit retry with TinyAssets visibly attached produced no rendered assistant
or tool result before the 120-second driver timeout. This again fails before an
accepted authenticated call and does not authorize a JWT change.

## Rendered reproduction

In a one-tab ChatGPT Temporary Chat, the user completed `Reconnect TinyAssets`
successfully. A fresh conversation then sent:

> use my TinyAssets connector — can you tell me what work is currently running
> or waiting in my main universe?

ChatGPT again rendered `Reconnect TinyAssets` and reported that the connection
had expired. Correlated production requests were:

| UTC timestamp | Request | Result |
|---|---|---|
| 19:28:52.245 | `POST /mcp` | 401 |
| 19:28:52.601 | `POST /mcp` | 200 |
| 19:28:52.977 | `GET /mcp` | 200 |
| 19:28:53.055 | `POST /mcp` | 202 |
| 19:28:53.417 | `POST /mcp` | 401 |

No token, JWT material, claim value, or user-identifying value was captured.
Rendered evidence is also preserved locally in
`output/user_sim_session.md`.

The 2026-08-01 follow-up used ChatGPT Pro, Temporary Chat, the Instant model,
and the visibly attached TinyAssets plugin. An anonymous live read succeeded
and reported no bearer credential. The next custom-agent read rendered
`Reconnect TinyAssets`; reconnect and Connect returned through
`link_success=true`, but the original call did not retry. Returning to the
observed conversation target left TinyAssets absent from the attachment
picker, and an explicit post-return identity prompt produced neither a tool
call nor an assistant response. The custom-agent read therefore did not run.
Exact prompts, rendered results, and main-pane screenshots are in
`output/user_sim_session.md`.

The 2026-08-02 follow-up used ChatGPT Pro, Temporary Chat, Instant, and one
host-visible tab. The first connector call rendered `Reconnect TinyAssets`.
Reconnect and Connect completed in the same tab and returned
`link_success=true`; returning to the exact conversation preserved the user
turn. The original call ended without a tool result. TinyAssets was then
explicitly attached again and the user asked for the connector check to retry.
That second turn also produced no rendered assistant or tool result before the
120-second driver timeout. No principal fingerprint was rendered, so neither
turn is authenticated-call acceptance evidence.

## Public and deployed configuration parity

Public metadata fetched 2026-07-30:

- protected resource: `https://tinyassets.io/mcp`
- authorization server and issuer:
  `https://inventive-van-62-staging.authkit.app`
- scopes: `openid`, `profile`, `email`, `offline_access`
- grants: authorization code, refresh token, device code
- PKCE: `S256`
- JWKS: one RSA key advertising `RS256`

Safe production environment inspection:

- `UNIVERSE_SERVER_AUTH=workos`
- `WORKOS_AUTHKIT_DOMAIN=inventive-van-62-staging.authkit.app`
- `WORKOS_MCP_RESOURCE=https://tinyassets.io/mcp`
- `WORKOS_REQUIRE_AUTH=0`
- `WORKOS_ALLOW_NO_AUDIENCE=0`

This proves visible URL/issuer/algorithm parity, but not the rejected token's
actual `aud`, expiry, issuer, subject, or signing-key match.

## Diagnostic implementation

`WorkOSAuthProvider` now maps validation failures to an allowlisted category:

- `signing_key`
- `expired`
- `audience`
- `issuer`
- `required_claim`
- `signature`
- `algorithm`
- `malformed`
- `invalid_token`
- `invalid_subject`

The log message contains only the stable category and a numeric suppressed
count. It excludes exception strings and uses neither token nor decoded
header/payload/claims. Each allowlisted category emits at most once per
60-second process window; the next emitted event reports how many same-category
events were suppressed. Malformed compact JWTs are classified before JWKS
lookup, so they cannot be mislabeled as signing-key failures.

Test-first evidence on Windows/Python 3.13:

- Red: 10/10 initial focused tests failed before implementation; independent
  review added 2/2 red tests for log bounding and real malformed-token ordering.
- Green: all 12 new focused tests passed after implementation.
- Regression: `py -m pytest -q tests/test_workos_provider.py` → 53 passed.
- Lint: `py -m ruff check tinyassets/auth/workos_provider.py
  tests/test_workos_provider.py` → clean.

Independent same-provider review first returned `ADAPT` for unbounded public
warning amplification and malformed-token misclassification. Both findings
were fixed test-first. The reviewer then returned `APPROVE` for staged diff
`f885f69a42f01bb1d9940a58a25bdb3418325c4f` at base `b9ce7d59`, with fresh
53-test, Ruff, and diff-check evidence.

The production journal sanitizer was then extended test-first to return only
the already-allowlisted rejection categories from the exact
`universe_server.auth.workos` warning envelope. It accepts only the known
optional daemon Compose prefixes, and rejects bare, arbitrary-prefix,
wrong-logger, wrong-service, malformed-count, trailing, and unknown-category
lines. The first exact-head review correctly found that a bare-message matcher
would miss every formatted production warning. The adapted exact head
`7a8e1f2fbfc39e38055723e1da23ea34ad9ed612` passed 84 focused sanitizer,
workflow, and auth tests, changed-file Ruff, strict OpenSpec validation, and
diff hygiene; independent review returned `APPROVE`.

Manual read-only workflow run
`https://github.com/Jonnyton/TinyAssets/actions/runs/30679614519` inspected
2026-08-01T01:52:00Z through 02:02:00Z at that exact head. The sanitizer
reported `input_truncated=false`, 812 source lines, and
`oauth_rejection_categories=[]`; raw journal text was neither printed nor
published. The empty category is evidence that this rendered attempt did not
reach a logged bearer rejection, not evidence that the validator accepted a
token.

## Production rollout and rollback

The diagnostic does not change token acceptance or the caller's standard `401
invalid_token` response.

Rollback trigger:

- health/canary regression;
- new authentication response behavior;
- sensitive value in logs;
- unexpected error-volume or latency increase.

Rollback action:

1. revert the diagnostic implementation commit;
2. deploy the revert through the normal production workflow;
3. verify `/health` and the public MCP canary;
4. confirm production remains fail-closed with
   `WORKOS_ALLOW_NO_AUDIENCE=0`.

There is no data migration and no persistent-state rollback.

## Next evidence gate

After the diagnostic lands, start a fresh rendered conversation, explicitly
attach TinyAssets after the OAuth return, perform one authenticated call, and
read the bounded category at the correlated timestamp if the server rejects
it. If ChatGPT still cannot attach TinyAssets and the bounded category remains
empty, treat the connector-return/attachment seam—not JWT validation—as the
next repair boundary. Only implement the smallest evidence-backed correction.

Final acceptance requires both an immediate authenticated call and a later
continued/refreshed call to the same owner/universe from a rendered chatbot,
with no personal computer dependency.

Freshness check 2026-08-02 16:32 PDT against `origin/main`
`9f8975ea51b063d868b89f25b080fe03606feb8b`: the available repository issue,
PR, session, and audit evidence contains no independent post-fix clean ChatGPT
OAuth use. Keep an explicit monitoring watch; do not count this synthetic,
failed acceptance traffic as organic use.
