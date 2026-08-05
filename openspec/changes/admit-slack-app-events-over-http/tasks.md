# Tasks — Slack app event ingress endpoint

## 1. Configuration resolution (fail closed)

- [ ] 1.1 Add `tinyassets/app_slack_ingress.py` with a resolver that reads
      `TINYASSETS_SLACK_SIGNING_SECRET` and `TINYASSETS_SLACK_API_APP_ID` from
      server-owned configuration and returns a built `SlackAppEventBoundary`, or
      `None` when either is absent, empty, or malformed.
- [ ] 1.2 Test: absent secret ⇒ no boundary; absent app id ⇒ no boundary;
      whitespace-only values ⇒ no boundary.
- [ ] 1.3 Test: the resolver never consults a request-supplied value and never
      substitutes a default or empty key. Mutation-probe it — replacing the
      "missing ⇒ None" branch with "missing ⇒ empty secret" MUST turn a test red.
- [ ] 1.4 Add both variables to `docs/reference/environment-variables.md`.

## 2. The endpoint

- [ ] 2.1 Register `@mcp.custom_route("/mcp/app/slack/events", methods=["POST"])`
      in `tinyassets/universe_server.py`, delegating to `app_slack_ingress`.
- [ ] 2.2 Read the raw body exactly once with `await request.body()` and pass those
      bytes to the verifier untouched — no parse, re-encode, or normalisation
      before the HMAC check.
- [ ] 2.3 Verify the signature first; then branch on `url_verification` (echo only
      `challenge`) versus `event_callback` (hand the same raw bytes to
      `boundary.admit()`).
- [ ] 2.4 Return a single fixed `401` refusal for every rejection reason, and `405`
      for non-POST.
- [ ] 2.5 Acknowledge `200` as soon as the event is admitted; do not await agent
      execution, provider calls, or outbound delivery.

## 3. Tests

- [ ] 3.1 Correctly signed `event_callback` ⇒ `200`, exactly one admission receipt.
- [ ] 3.2 Redelivered `event_id` ⇒ `200`, reported as replay, no second receipt.
- [ ] 3.3 Forged signature, tampered body, stale timestamp, and wrong `api_app_id`
      each ⇒ `401`, zero receipts. Assert the four refusal bodies are byte-identical.
- [ ] 3.4 Signed `url_verification` ⇒ `200` echoing exactly the challenge, and
      **no** admission receipt. Unsigned handshake ⇒ `401`, nothing echoed.
- [ ] 3.5 A body declaring `url_verification` that also carries `event`/`event_id`
      ⇒ handled strictly as a handshake, no event admitted.
- [ ] 3.6 Non-POST methods ⇒ `405`, boundary never invoked (assert via a boundary
      double that records calls).
- [ ] 3.7 Unconfigured server ⇒ every request on the path refused, including a
      *correctly signed* one. This is the test that catches fail-open.
- [ ] 3.8 Byte-identity: a body containing non-ASCII text and insignificant JSON
      whitespace still verifies — proves nothing re-serialises it in the path.
- [ ] 3.9 Mutation-probe the suite: for each of 3.3, 3.4-unsigned, and 3.7,
      confirm the guard's removal turns a specific test red. Record which paths
      did **not** go red — those are the finding, not the passing ones.

## 4. Edge reachability

- [ ] 4.1 Add a `worker.test.js` case asserting `shouldProxy('/mcp/app/slack/events')`
      is `true`, so a future narrowing of the prefix cannot silently unreach this
      endpoint.
- [ ] 4.2 Confirm no Cloudflare dashboard change is required, and state that
      explicitly in the PR body so nobody waits on a host action that isn't needed.

## 5. Deploy plumbing

- [ ] 5.1 Pass both variables through `deploy/compose.yml` to the daemon service.
- [ ] 5.2 Record that the signing secret is a real secret: it belongs in the vault
      / GitHub secret path, never a committed file.
- [ ] 5.3 Rebuild the plugin mirror (`python packaging/claude-plugin/build_plugin.py`)
      since `tinyassets/*` runtime files changed.

## 6. Gates

- [ ] 6.1 `ruff check` and the full `pytest` suite.
- [ ] 6.2 Cross-family (Codex) **security** review of the endpoint before deploy —
      framed as "refute that this is safe to expose publicly". Log the verdict.
- [ ] 6.3 Do **not** claim a user can talk to their agent in Slack. State plainly
      that admission works and execution is the next change.
