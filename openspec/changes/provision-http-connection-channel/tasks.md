# Tasks — provision-http-connection-channel (Slice 1: connector connect_http)

## 1. Handler
- [ ] 1.1 New `tinyassets/api/http_connection.py::connect_http` — owner admin-ACL
      gate (mirror connect_llm); parse+validate payload (destination, auth_scheme
      ∈ none/bearer/basic/header, secret, allowed_endpoints >=1).
- [ ] 1.2 Vault deposit via `write_credential_vault` (list-wrapped, http record,
      service==destination==vault key); `credential_ref=vault://http/<dest>`;
      connect_llm-style error mapping; fail-closed.
- [ ] 1.3 Idempotent `create_connection(connection_type="http", …, allowed_endpoints)`
      + `grant_connection` with deterministic ids + conflict-checks; redacted
      projection return with a `next` consent hint. Never echo the secret.
- [ ] 1.4 Wire `operation=="connect_http"` into `universe_server.py` write_graph
      target=connection dispatch; mirror into the packaging runtime.

## 2. Tests
- [ ] 2.1 Happy path: owner provisions → vault record written under the key, http
      connection created with the endpoint allow-list, grant bound to the universe,
      projection redacted (no secret/credential_ref).
- [ ] 2.2 Auth: anonymous + non-admin (write-collaborator) both get uniform
      not_found; nothing created.
- [ ] 2.3 Fail-closed: empty allow-list, `oauth1a`, and cross-owner transfer each
      rejected with nothing mutated.
- [ ] 2.4 Idempotency: second call returns the same ids; ownership/type conflict
      returns connection_conflict. Full focused suite green + ruff + mirror parity.

## 3. Review + rollout
- [ ] 3.1 Codex SHAPE review of the design BEFORE build; then exact-head review of
      the diff returns approve/adapt (authority/credential-sensitive).
- [ ] 3.2 Merge + deploy; confirm prod `release_state.git_sha` contains it +
      `--assert-handles` canary still green (no connector handle regression).
- [ ] 3.3 Host-action: enable `TINYASSETS_OUTBOUND_HTTP_CONNECTIONS_ENABLED` via
      apply-daemon-env so outbound effects fire live.
- [ ] 3.4 Live proof: provision an http (Slack) connection, build a node with the
      `authenticated_external_call` effect, grant effector consent, run, and
      confirm a real outbound post.

## Follow-ups (prose)
Slice 2: expose connect_http + write_graph target=branch + consent/mint on the
SERVED surface (engine_mcp_server.py) so the universe builds channels itself.
oauth1a/multi-secret bundle; typed http credential validation (deferred task 1.8).
