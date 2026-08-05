# Design — Slack app event ingress endpoint

## Context

Six modules exist and are unit-tested; none is reachable. This change adds the
one missing door and nothing else. The trust anchor is Slack's HMAC over the
exact request bytes, so every design decision below is downstream of "the body
must arrive byte-identical, and nothing unverified may proceed".

## Decisions

### D1 — Mount at `/mcp/app/slack/events`, not a new top-level path

The public edge forwards only `/mcp` and `/mcp/…`: the Cloudflare route binding
is `tinyassets.io/mcp*`, and `shouldProxy()` in `deploy/cloudflare-worker/worker.js`
re-checks `pathname === '/mcp' || pathname.startsWith('/mcp/')`.

- A new top-level path is unreachable until someone edits the Cloudflare route
  binding — a host-only dashboard action that would block this work outright.
- `/mcp/.well-known/oauth-protected-resource` already proves a non-MCP
  `custom_route` coexists with the MCP mount under this prefix.
- The Worker preserves method, headers, and the body *ReadableStream* unmodified.
  This is load-bearing: any body rewrite (re-encoding, JSON round-trip,
  whitespace normalisation) invalidates every signature.

Rejected: `POST /app/slack/events` (blocked on host action);
`mcp.tinyassets.io` directly (Access-gated — Slack cannot present the CF Access
service-token headers, so every delivery would 403).

### D2 — Read the raw body once, verify, and never re-serialise

`SlackRequestVerifier.authenticate` takes `raw_body: bytes` and computes
`v0:{timestamp}:{body}`. The handler therefore does `await request.body()` and
passes those bytes through untouched. JSON parsing happens *inside* the verifier,
after the HMAC check — never before it, and never on a re-encoded copy.

### D3 — `url_verification` is handled before the boundary, but after signature check

The boundary rejects anything that is not `event_callback`
(`_normalize_authenticated_envelope`). Slack's Request URL handshake is a
`url_verification` body, so routing it through the boundary makes the endpoint
unsaveable in Slack — the change would be dead on arrival.

Order matters and is easy to get backwards:

1. verify the HMAC over raw bytes (same secret, same staleness window),
2. *then* parse; if `type == "url_verification"`, echo only `challenge`,
3. otherwise hand the same raw bytes to `boundary.admit()`.

Verifying first means an attacker cannot use the handshake branch as an
unauthenticated echo/oracle. The handshake writes no admission receipt — it is
not an event — and a body claiming to be a handshake never admits an event even
if it also carries `event_callback` fields.

### D4 — Fail closed on configuration, and make refusals indistinguishable

The verifier requires `signing_secret` and `expected_api_app_id`. Both come from
server-owned configuration (`TINYASSETS_SLACK_SIGNING_SECRET`,
`TINYASSETS_SLACK_API_APP_ID`), resolved once at construction.

If either is missing or malformed, the route refuses everything. The failure mode
being designed against is the ambient-credential shape this project has already
been bitten by: a missing secret must never fall back to a default, an empty
string, or anything request-supplied — an HMAC with an empty key still *verifies*,
which is exactly how "fails open" would look in passing tests.

Refusals return a single fixed response. "Not configured", "bad signature", and
"wrong app id" are indistinguishable from outside, so the endpoint is not an
oracle for whether a given app id is installed.

### D5 — Acknowledge fast; do not couple the ack to execution

Slack retries after 3 seconds. Signature verification plus a ledger write is
cheap; an agent turn is not. The handler acknowledges once admitted, and the
execution half is out of scope here (see D6). This keeps the endpoint from
generating its own retry storm — each retry costs another HMAC verification.

### D6 — Admission only; execution is a separate change

This change deliberately stops at "the event is authenticated, deduplicated, and
acknowledged". Wiring an admitted event to an agent turn and delivering the reply
raises a question this change should not silently answer: **whose provider runs
the turn.**

The host directive is that a user with a subscription runs on their own LLM and
never needs maintainer infrastructure. `run_graph` already executes that way and
is proven live; scheduled automations route through a maintainer-run worker pool
and sit at `awaiting_cloud_worker` forever. Choosing between those is a real
architectural decision and gets its own change rather than being smuggled in
under an ingress endpoint.

Being explicit about the boundary: **after this change lands and deploys, a user
still cannot hold a conversation with their agent in Slack.** What changes is
that Slack can verify the Request URL and events stop being dropped on the floor.

## Risks

| Risk | Mitigation |
|---|---|
| Body mutation anywhere in the path breaks all signatures | Assert byte-identity in tests; Worker already streams the body through |
| Endpoint becomes an unauthenticated oracle | Fixed refusal body; verify before any branch, including the handshake |
| Secret absent in production ⇒ silently accepts | Fail-closed construction; a test that mutates the secret to empty must go red |
| A green test suite that cannot detect the above | Mutation-probe the fail-closed paths before claiming coverage |
| Publicly reachable attack surface | Cross-family security review **before** deploy, not after |

## Security-review findings and their resolution

An opposite-family (Codex) review of `4ee22abf`, framed as "refute that this is
safe to expose publicly", returned **REJECT** with 9 findings. It demonstrated
two live exploits rather than describing them. Resolution:

| # | Sev | Finding | Resolution |
|---|---|---|---|
| 1 | HIGH | Only `api_app_id` checked — any `team_id` admitted. Demonstrated: `{'unlisted_team_status': 200, 'admitted': True}` | `TINYASSETS_SLACK_TEAM_IDS` allow-list, enforced after authentication. Empty/absent admits nobody |
| 2 | HIGH | A 1-character signing secret (`'0'`) constructed a verifier and admitted an event | `MIN_SIGNING_SECRET_LENGTH = 16`; Slack issues 32 hex chars |
| 3 | HIGH | `request.body()` buffers before the 1 MiB check | Already fixed in `6b56d292`, which the review predates — `read_bounded_body` appears 0 times in its output |
| 4 | HIGH | Sync SQLite admission inside the async route can block the event loop for the store's 30s busy timeout | Offloaded via `run_in_threadpool` |
| 5 | MED | Unbounded ledger growth per accepted workspace | **Residual, mitigated not closed** — see below |
| 6 | MED | `AppEventReplayConflict` escaping as a distinct status is a ledger-membership oracle | Caught and normalised to the fixed refusal |
| 7 | LOW | Unconfigured requests skip HMAC work, so timing distinguishes configuration state | `_burn_equivalent_work` hashes and discards on the unconfigured path |
| 8 | MED | The "indistinguishable" test compared only bodies, so a status-code oracle stayed green | Compares `(status, body)`; now also covers the unlisted-workspace refusal |
| 9 | MED | The size test fed bytes straight to the verifier, so it could not prove an *ingress* limit | Added a route-level oversize test that goes through the real HTTP path |

Every fix is mutation-verified: removing the allow-list, defaulting it to
allow-all, removing the secret-length floor, or letting the replay conflict
escape each turns a specific test red.

### Residual risk accepted here, deliberately

**#5, ledger growth.** Retention/quota belongs to the admission store, which
this change does not own. The allow-list narrows the exposure from "anyone who
installs the app" to "an allow-listed workspace", so the remaining actor is one
the operator explicitly trusted. That is a materially different threat model,
but it is not zero — a compromised or malicious allow-listed workspace can still
grow the ledger without bound. It needs a retention policy in the store's own
lane before this endpoint carries untrusted multi-tenant traffic.

Stating it rather than silently closing it: a MEDIUM finding downgraded by a
mitigation is still open.
