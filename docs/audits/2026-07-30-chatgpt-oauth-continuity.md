# ChatGPT OAuth continuity diagnosis

Date: 2026-07-30
Environment: production `https://tinyassets.io/mcp` and Windows test worktree
Change: `repair-chatgpt-connector-oauth-continuity`

## Current conclusion

A successful ChatGPT reconnect does not continue into an authenticated
TinyAssets tool call. The strongest current reproduction stops before the
resource server: ChatGPT returns through `link_success=true`, an explicitly
reattached call never reaches TinyAssets, and a brand-new Temporary Chat
immediately marks the connection expired. Two complete bounded production
windows recorded no instrumented bearer rejection. A fixed malformed-bearer
positive control later proved that the deployed logger did emit `malformed`
and that the exact Compose-prefixed bare warning is safely detectable. The
rendered attempts therefore produced no rejected bearer, but this alone does
not prove whether ChatGPT sent no bearer or sent an accepted one. No audience,
issuer, expiry, key, or claim repair is authorized.

A second rendered attempt on 2026-08-01 reached ChatGPT's
`link_success=true` return but did not retain TinyAssets in the returned
conversation's plugin picker. A complete, non-truncated production journal
window for that attempt contained no sanitized token-rejection category. This
attempt therefore failed before the instrumented bearer validator; it is not
evidence for relaxing or changing JWT validation.

The client-registration boundary is now concrete. ChatGPT's live Advanced
OAuth discovery selects Dynamic Client Registration and renders: `CIMD is
unavailable because the server did not advertise CIMD support.` The installed
TinyAssets settings surface simultaneously shows `Reconnect` immediately
after the successful OAuth return. AuthKit's live authorization-server
metadata indeed omits `client_id_metadata_document_supported`.

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

A second control explicitly reattached TinyAssets after the OAuth return and
sent `ok, i reconnected it — use TinyAssets now and tell me which account it
sees and what universe i'm in`. The rendered call remained in progress without
a tool result until stopped. A new Temporary Chat then attached the still-
visible plugin and immediately rendered `Reconnect TinyAssets`. The settings
page also listed `TinyAssets — Reconnect`. Plugin visibility therefore did not
mean ChatGPT held a usable OAuth credential.

## Public and deployed configuration parity

Public metadata fetched 2026-07-30:

- protected resource: `https://tinyassets.io/mcp`
- authorization server and issuer:
  `https://inventive-van-62-staging.authkit.app`
- scopes: `openid`, `profile`, `email`, `offline_access`
- grants: authorization code, refresh token, device code
- PKCE: `S256`
- token endpoint accepts public clients with `none`
- DCR registration endpoint is present
- `client_id_metadata_document_supported` is absent
- JWKS: one RSA key advertising `RS256`

Safe production environment inspection:

- `UNIVERSE_SERVER_AUTH=workos`
- `WORKOS_AUTHKIT_DOMAIN=inventive-van-62-staging.authkit.app`
- `WORKOS_MCP_RESOURCE=https://tinyassets.io/mcp`
- `WORKOS_REQUIRE_AUTH=0`
- `WORKOS_ALLOW_NO_AUDIENCE=0`

This proves visible URL/issuer/algorithm parity, but not the rejected token's
actual `aud`, expiry, issuer, subject, or signing-key match.

ChatGPT's discovery UI confirms the same resource, AuthKit endpoints, OIDC
scopes, and `offline_access`, but can only select DCR. The
[OpenAI authentication guide](https://developers.openai.com/plugins/build/auth)
states that ChatGPT prioritizes CIMD when advertised, and the
[WorkOS AuthKit MCP guide](https://workos.com/docs/authkit/mcp) says CIMD is
off by default and should be enabled under Connect → Configuration while DCR
can remain enabled for legacy clients. Enabling CIMD is therefore the smallest
supported control-plane experiment; it is not yet proof that missing CIMD
caused the old DCR credential to expire.

Test-first `scripts/check_oauth_discovery_contract.py` makes the public
contract repeatable without secrets. On Windows/Python 3.13, 9 focused tests
pass. Against production on 2026-07-31 it returns one issue only:
`cimd_not_advertised` (exit 1). Scoped rendered evidence is
`output/chatgpt_oauth_discovery_dcr_only_2026-07-31.png`.

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

Two follow-up main-revision diagnostic runs corroborate the client-side
boundary:

- run 30680168689, 2026-08-01T02:25:00Z–02:31:00Z: complete, 198 lines,
  `input_truncated=false`, `oauth_rejection_categories=[]`;
- run 30680303470, 2026-08-01T02:31:00Z–02:35:00Z: complete, 54 lines,
  `input_truncated=false`, `oauth_rejection_categories=[]`.

Both ran exact main `7932b333a5b14be7d25983d85e66f82affd4164a`
and published no raw journal text.

Claude's opposite-provider review returned `ADAPT` and is preserved in
`output/claude-oauth-cimd-review.md`. It approved the bounded CIMD experiment
but required a live positive control for the sanitizer. Fixed non-secret
malformed bearers sent at 02:56:15Z and 02:57:37Z each returned `401
invalid_token`; complete runs 30681000676 and 30681046575 nevertheless returned
`oauth_rejection_categories=[]`. Branch run 30681215115 safely classified the
same 02:57:00Z–02:58:00Z window as signal category `malformed` with a
noncanonical `prefixed` envelope. Source inspection identified the exact
deployed shape: `tinyassets.universe_server` does not install the timestamped
root formatter assumed by the first sanitizer, while Compose adds its
allowlisted daemon service prefix. The strict exact-envelope adaptation then
replayed the same immutable window in run 30681363132 at head
`f4a6251f78b79a0c320345f0a3ec86a7619e84e5` and returned
`oauth_rejection_categories=["malformed"]`, `input_truncated=false`, 44 lines,
and no raw journal text. The detector is now live-sensitive; the earlier empty
rendered-attempt windows prove only that they produced no rejected bearer, not
that no request or accepted bearer reached the resource server.

Claude's opposite-provider exact-head review returned `APPROVE` for
`cee3baf1d3bc0a51d999b118be71af8b118d0aad` and is preserved in
`output/claude-oauth-cimd-exact-head-review.md`. The reviewer independently
verified the immutable workflow result, reproduced the single live
`cimd_not_advertised` issue, ran 95 core focused tests plus Ruff and strict
OpenSpec validation, and adversarially confirmed arbitrary prefixes cannot
enter the canonical category field. Two low, non-gating checker hardening nits
remain: trailing-slash normalization and clean classification of non-string
first-party metadata fields.

## Next evidence gate

After opposite-provider review, enable AuthKit CIMD while retaining DCR,
recreate or update the ChatGPT connector registration so ChatGPT selects CIMD,
and rerun the public discovery check. Then start a fresh rendered conversation
and perform the immediate plus later authenticated calls. A success changes
both registration freshness and mechanism, so it does not attribute the old
failure specifically to missing CIMD. If CIMD does not restore continuity,
revert that control-plane experiment and diagnose DCR registration/token
exchange directly; do not modify JWT acceptance.

Final acceptance requires both an immediate authenticated call and a later
continued/refreshed call to the same owner/universe from a rendered chatbot,
with no personal computer dependency.
