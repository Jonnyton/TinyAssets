# Tasks — channel-agnostic-outbound

Design-gate change. No task here is started until the opposite-provider (Codex) review returns
`approve`/`adapt` and the founder confirms the ownership split + coordinated sync with
`outbound-boundary-layer`. The execution seam is the EXISTING spawned credential-blind broker
(`storage/outbound_connections.py`); there is no in-process secret-resolution path. Each channel
migration is proven by a semantic equivalence matrix (design.md D6), backfills its ledger
connection, and flips atomically — never two credential paths live, never a fall-through to
another credential source.

## 0. Prerequisites and premise verification

- [ ] 0.1 Re-verify against `origin/main` that the assumed as-built shapes still hold: `twitter_post._resolve_credentials:190` still reads `TWITTER_*` from host env; `slack_transport.resolve_slack_bot_token:58` is vault-first; the two dispatch ladders (`github_pr.run_effects_for_branch:2294`, `effectors/__init__.run_effects_for_branch:83`) still hard-code each sink; the broker seams `resolve_exact_scoped_proxy:1136` / `CredentialBlindBroker.dispatch:325` / `_contains_secret:726` are unchanged. Reclassify any task whose premise moved.
- [ ] 0.2 Confirm the corrected ownership split: `outbound-boundary-layer` OWNS grants-as-resource, the spawned proxy/broker (landed code), action-cap enforcement, system-derived idempotency, and the derived-identity `github_pull_request` receipts; `credential-vault` OWNS custody/resolution; this change OWNS the general HTTP driver + strict SSRF transport + channel descriptor/request-mapping + migrations, and CONSUMES the other two. Record the coordinated `external-effect-adapters` sync plan.
- [ ] 0.3 Confirm no new advertised MCP handle; connection CRUD rides the existing `write_graph target=source_channel`-style owner surface, and every projection returns a redacted `ConnectionView`.

## 1. Extend the credential-blind broker (all dark — no channel migrated)

- [ ] 1.1 Add a general HTTP `_network_request` driver inside the broker child, selected by `connection_type` in `_TrustedNetworkDriver:677`, replacing/augmenting the GitHub-only `_ProductionGitHubNetworkDriver:587`. It applies the D3 strict transport and the D5 auth scheme entirely inside the child.
- [ ] 1.2 Implement the D3 strict SSRF transport as a first-class module used by the driver: canonical single-`https` URL parse (reject userinfo/fragment/control chars/backslash/encoded-host/unexpected-port/dot-segments/double-encoding/caller Host+Authorization+Cookie+proxy headers); `ipaddress`-global-only with ALL A/AAAA validated (incl. IPv4-mapped IPv6, unspecified/reserved/shared, unusual literals); address pinning with preserved TLS SNI/hostname verification and connected-peer validation (no preflight-then-plain-urlopen); redirects disabled (per-hop full re-check if ever enabled, no cross-origin cred forwarding); ambient proxies disabled via `ProxyHandler({})`; response-size/header/timeout/redirect-hop/decompression bounds.
- [ ] 1.3 Add the general typed-bundle credential resolver alongside `_ProductionVaultCredentialResolver:429` in `_TrustedCredentialResolver:482`, returning a `ConnectionSecretBundle` whose shape is fixed by connection type (Slack bot vs app token distinct; Twitter's 4 OAuth values; github token; http token/basic). Extend `_contains_secret:726` response declassification to scan EVERY bundle member, not one string.
- [ ] 1.4 Extend the connection resource + `ConnectionLedger` with `connection_type`, `auth_scheme`, and `allowed_endpoints` (plus the next numbered storage migration); keep revocation + per-universe grant semantics.
- [ ] 1.5 Add authority-checked resolution + a redacted `ConnectionView` projection: the adapter resolves ONLY via `resolve_exact_scoped_proxy:1136` / `resolve_scoped_proxy:1084` (authenticated principal + active grant + server-known universe); `get_connection:922` is never the effect seam; no CRUD/list/evidence path returns `credential_ref` or the raw storage dataclass.
- [ ] 1.6 Add the `ChannelTypeDescriptor` registry (`connection_type -> {auth_scheme, endpoint templates, request/response mapping}`) seeded with `github`/`slack`/`twitter`/`http`, plus owner create/list/revoke through the existing owner surface.
- [ ] 1.7 Add the general `authenticated_external_call` adapter with the D1 gate order (soul authority → connection-descriptor resolution [no secret] → consent → egress admission → fire in broker). Never raises to the completion path.
- [ ] 1.8 Add the general typed-bundle resolver to `credential_vault.py` + the general `connection` credential record; vault-first, never env fallback; reuse the existing secret-free summary/exception hygiene.
- [ ] 1.9 Adversarial credential-blindness test: prove a graph/adapter cannot recover ANY bundle member from run state, packet fields, `ConnectionView`, egress-refusal evidence, `credential_ref`, or proxy/exception text (including `__context__`, the Slack `Authorization`-leak class at `slack_transport.py:89`).

## 2. Slack first (Slice 3 depends on it)

- [ ] 2.1 Backfill a `slack` ledger connection from the existing exact vault record (social/slack keyed by connection_id, `credential_vault.py:1201`), keeping the app-level token distinct.
- [ ] 2.2 Build the per-channel semantic equivalence matrix (design.md D6) vs the verbatim `slack_transport` oracle: normalized wire request; gate ORDER; receipt/evidence compatibility; exception behavior; intentional deltas; flag (named default/scope/readiness/rollback); concurrency.
- [ ] 2.3 Re-express `build_slack_transport` as an instance: resolve the named `slack` connection under authority → dispatch `authenticated_external_call` (POST `chat.postMessage`) through the broker. Preserve the `xoxb-`-only bot-token check and the no-body-round-trip rule; keep `app_outbound_receipts` idempotency untouched (different concern).
- [ ] 2.4 Flip Slack atomically per universe after the matrix passes and a live `ui-test` shows the background follow-up delivered through the general primitive. Prove a disabled/failing new path fails closed. Post-fix clean-use watch item in `STATUS.md`.

## 3. GitHub pull-request

- [ ] 3.1 Backfill a `github` ledger connection from the existing vcs/github vault record; build the D6 matrix vs the verbatim `github_pr` credential-resolution + dispatch oracle.
- [ ] 3.2 Re-express `github_pull_request` as a `github`-typed connection instance: credential resolution + dispatch + egress unify through the general adapter and broker; the multi-step PR materialization (blobs→tree→commit→ref→PR) stays a github-typed request handler under one connection. Do NOT touch the `outbound-boundary-layer`-owned derived-identity/reconciliation behavior; route the live completion path through the proxy (it resolves in-process today).
- [ ] 3.3 Flip GitHub atomically on a private test destination; confirm vault-outranks-env precedence is preserved and no credential enters Branch-visible evidence.

## 4. Twitter (closes the cross-universe env hole)

- [ ] 4.1 Build the D6 matrix vs the verbatim `twitter_post` effector (env credentials + hand-rolled OAuth), explicitly recording the intentional deltas: credential source env→vault, and gate-order reconciliation (Twitter is consent-before-credential today at `twitter_post.py:587`; the general order is no-secret-before-consent, which is compatible).
- [ ] 4.2 Provision + VERIFY a per-universe vault `twitter` connection (4 OAuth values as a typed bundle) FIRST. Do NOT dual-read vault-then-env.
- [ ] 4.3 Re-express `twitter_post` as a `twitter`-typed instance using the `oauth1a` handler inside the broker; preserve destination-derived account binding (`twitter_post.py:507`) and `handle_authority_mismatch`.
- [ ] 4.4 Flip the universe ATOMICALLY to the connection-backed path; prove OAuth signature equivalence (modulo nonce/timestamp) and live rollback. Remove the `TWITTER_*` env resolution (`_resolve_credentials:190`) for a flipped universe entirely; prove the new path never reads process env and fails closed when the connection is missing.

## 5. Collapse the ladders and the resolvers

- [ ] 5.1 Replace both hard-coded dispatch ladders with the registry-driven dispatch; route every migrated channel through the one adapter.
- [ ] 5.2 Delete each bespoke effector module only after its D6 matrix passes; keep the per-service vault resolvers as thin wrappers over the general typed resolver until all callers migrate, then collapse.
- [ ] 5.3 Keep `wiki_write_back` (internal, no external HTTP) and `github_merge` on their own paths unless they cleanly fit the general primitive; do not force-fit — record the decision.

## 6. Proof, review, and sync

- [ ] 6.1 §14 concurrency/load proof for the general adapter + broker: concurrent calls across connections do not cross-leak any bundle member or receipt; the strict SSRF transport and endpoint allowlist hold under concurrency; a new/disabled path never falls through to another credential source.
- [ ] 6.2 Opposite-provider (Codex) review re-checks the ownership split, the SSRF transport contract, the credential-blindness of the broker extension, and the equivalence-matrix method; log `approve`/`adapt`/`reject` and gate build/push/rollout on it.
- [ ] 6.3 Rendered chatbot `ui-test` for the migrated Slack/GitHub user surface + post-fix clean-use evidence, freshness-stamped.
- [ ] 6.4 Sync the `external-effect-adapters`, `credential-vault`, and `app-outbound-adapter` deltas in ONE coordinated sync with `outbound-boundary-layer`, combining the general adapter with its derived-identity receipt requirements so no as-built limitation and no half-general adapter is left stranded beside the other.
