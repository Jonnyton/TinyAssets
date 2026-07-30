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

After the diagnostic reaches production, perform exactly one fresh rendered
reconnect/authenticated call and read the bounded category at the correlated
timestamp. Only then implement the smallest evidence-backed correction.

Final acceptance requires both an immediate authenticated call and a later
continued/refreshed call to the same owner/universe from a rendered chatbot,
with no personal computer dependency.
