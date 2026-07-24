## 1. Adapt The Authority Contract

- [x] 1.1 Confirm the obsolete five-handle collapse change remains archived with `--skip-specs`.
- [x] 1.2 Record the 2026-07-24 host directive: `TinyAssets` is the only user-facing name, `/mcp` is the sole remote product endpoint, `/mcp-directory` retires promptly after safe migration, and the directive is standing cutover authorization without a second discretionary approval.
- [x] 1.3 Adapt proposal, design, delta specs, and tasks from three products to two: remote `/mcp` and local MCPB.
- [x] 1.4 Obtain independent architecture, security, and coverage review of the adapted contract before runtime work.
- [ ] 1.5 Coordinate PR #1522 so its useful naming/provenance corrections fold into this lane without restoring the retired directory-product premise.
- [ ] 1.6 Before either dependent change applies or syncs, adapt and strict-validate `retire-legacy-live-mcp-tools` so it depends on this change, removes every directory-preservation requirement/scenario, and leaves directory deletion here; block `operator-request-trigger-contract` tasks 4.1/4.6 and its delta sync until that change binds request-admission invariants once to canonical `universe_server` at `/mcp` and removes directory parity implementation/tests.

## 2. Preserve Completed MCPB Parity

- [x] 2.1 Add a failing staged regression for the former manifest/runtime catalog mismatch.
- [x] 2.2 Enumerate the middleware-applied staged runtime from the normal MCPB build path.
- [x] 2.3 Isolate the subprocess probe and fail packaging on import/enumeration errors.
- [x] 2.4 Declare exactly the seven canonical handles in the MCPB manifest.
- [x] 2.5 Keep the semantic parity regression and official schema validator green.
- [ ] 2.6 Prove launcher/config behavior for required data directory, optional default universe, stdio transport, and observed local auth posture.
- [ ] 2.7 Keep package/parity/acceptance tests provider-free and record actor-dependent limitations honestly.

## 3. Make Canonical `/mcp` Review-Safe

- [ ] 3.1 Add failing tests for exact `public-status-v1` covering both `read_graph(target=status)` and `get_status`: full, first-contact, access-denied, source-failure, malformed/non-object, unknown top-level/nested sentinel, and projection-exception cases must emit only the versioned schema and fixed failure envelopes with no raw fallback.
- [ ] 3.2 Remove operator logs, identities, sessions, paths, hashes, exceptions, and debug fields from public MCP status; reuse an existing internal operator surface, or require a separate OpenSpec/security review—do not add an eighth public MCP tool here.
- [ ] 3.3 Add failing tests that reject forced tool calls, prompt imports, impersonation, and unsolicited `converse` in server instructions.
- [ ] 3.4 Replace canonical instructions with neutral capability and selection guidance; require explicit user intent for universe conversation.
- [ ] 3.5 Add the delta's exact per-tool `securitySchemes` and identical `_meta["securitySchemes"]` back-compat mirrors; advertise only AuthKit-issuable `openid profile email offline_access`, publish Protected Resource Metadata with `resource=https://tinyassets.io/mcp`, return pre-dispatch HTTP `401` + `WWW-Authenticate` on pure identity-gated handles, and include tool-result `_meta["mcp/www_authenticate"]` for mixed-router lazy linking; test wire responses, not source objects alone.
- [ ] 3.6 Verify RS256 signature, issuer, audience/resource, expiry, and non-anonymous subject at the bearer boundary; separately enforce founder grants/capabilities plus visibility, ownership, and action/object ACLs before effects. Do not advertise internal `tinyassets.*` capabilities as OAuth scopes or treat `org_id` metadata as tenant authority.
- [ ] 3.7 Pin and test the exact seven-handle `readOnlyHint`/`destructiveHint`/`idempotentHint`/`openWorldHint` table from the delta spec plus descriptions for publication, overwrite, persistence, provider/data sharing, cost, confirmation, reversibility, and uncertain outcomes.
- [ ] 3.8 Bound and sanitize public errors/results, including provider failures; prove no secrets or raw internal exceptions escape.
- [ ] 3.9 Finalize privacy disclosures for WorkOS identity, activity evidence, retention/deletion, public commons, and BYOC/third-party provider routing.
- [ ] 3.10 Run focused security tests plus the required concurrent-session/load proof before any external metadata cutover.

## 4. Migrate Registries, Submissions, And Clients

- [ ] 4.1 Regenerate and version-bump MCP Registry metadata so the current remote resolves to `https://tinyassets.io/mcp`; verify through the Registry API.
- [ ] 4.2 Rebuild `chatgpt-app-submission.json` from canonical exact-seven runtime metadata, including `converse` and `get_status`, OAuth schemes, truthful annotations/descriptions, exactly the required positive/negative cases, and exact user-facing name `TinyAssets` with no lifecycle qualifier.
- [ ] 4.3 Replace current OpenAI and Claude submission/runbook answers with exact name `TinyAssets`, canonical `/mcp`, OAuth, exact seven, current privacy/support links, and fresh challenge-token instructions.
- [ ] 4.4 Refresh current integration/client packs for Codex, Cursor, Open WebUI, LibreChat, and every maintained supported host; preserve dated proof artifacts unchanged.
- [ ] 4.5 Reclassify hosts that cannot support canonical OAuth as anonymous-read-only or unsupported; do not retain anonymous mutation through the old route.
- [ ] 4.6 Refresh the Polsia handoff to a source-linked two-row remote `/mcp` / local MCPB matrix, folding useful PR #1522 naming/provenance corrections.
- [ ] 4.7 Correct MCPB README/source guidance without conflating the local product with remote OAuth.

## 5. Prove Migration Through Real User Paths

- [ ] 5.1 Prove canonical `/mcp` exact-seven enumeration, safe status projection, neutral instructions, metadata/runtime OAuth agreement, anonymous reads, and authenticated mutation without provider calls.
- [ ] 5.2 Record rendered ChatGPT web/mobile and Claude connector conversations against `/mcp`, including OAuth and at least one safe read plus authorized write/converse path; any provider turn uses requester BYOC or an accepted-market grant, never maintainer credentials or personal limits.
- [ ] 5.3 Submit canonical seven-tool metadata to OpenAI and Claude and record each accepted, published, pending, unavailable, rejected, or withdrawn state. Treat acceptance/publication as launch evidence; for a pending or unavailable review, set a predeclared decision date and then record the registration as pending, unavailable, withdrawn, or unsupported rather than retaining `/mcp-directory` indefinitely.
- [ ] 5.4 Publish and verify the MCP Registry current version resolving to `/mcp`.
- [ ] 5.5 Record supported Codex, Cursor, Open WebUI, LibreChat, Registry, and other maintained-client dispositions and proofs.
- [ ] 5.6 Record first normal external-user discovery/install/use and matching server evidence, or leave an explicit watch item.
- [ ] 5.7 Run a predeclared `/mcp-directory*` telemetry window with exact start/end/evidence source and zero unexplained maintained callers.
- [ ] 5.8 Run §14 concurrent-user/load, duplicate/retry, auth-revocation, and cross-account/universe isolation proof on canonical `/mcp`; do not infer an organization-tenant boundary from an informational `org_id` claim.
- [ ] 5.9 Assemble a dated cutover record covering migration, acceptance/publication, telemetry, concurrency/isolation, and risks. The 2026-07-24 host directive is standing authorization to proceed when these objective gates pass; stop only for a concrete newly discovered supported caller or safety failure recorded in `STATUS.md`.

## 6. Remove `/mcp-directory`

- [ ] 6.1 As soon as Sections 3–5 pass under the standing 2026-07-24 cutover authorization, remove `directory_server`, directory catalog constants, mounts, versioned catalog paths, and discovery metadata.
- [ ] 6.2 Remove `/mcp-directory*` Cloudflare routing and current operational guidance in the same reviewed slice.
- [ ] 6.3 Regenerate the Claude plugin mirror and every derived artifact from canonical source.
- [ ] 6.4 Add old-path rejection tests proving `/mcp-directory*` is absent and never redirects, proxies, or silently translates to `/mcp`.
- [ ] 6.5 Re-run canonical canaries, Registry resolution, rendered clients, and post-cutover logs after removal.

## 7. Verification, Review, And Foldback

- [ ] 7.1 Run focused runtime, auth, status, annotation, Registry, submission, Worker, MCPB, and client-contract tests plus lint and `git diff --check`.
- [ ] 7.2 Run strict OpenSpec validation and independent architecture/security/diff review.
- [ ] 7.3 Update PLAN's distribution substrate only after the approved host direction and required opposite-provider review are recorded.
- [ ] 7.4 Sync delta specs into canonical `live-mcp-connector-surface` and `mcp-connector-distribution`, archive the change, and retire its STATUS row only after completed tasks and external evidence are truthful.
- [ ] 7.5 Re-evaluate `retire-legacy-live-mcp-tools` only after this change and local MCPB migration/identity gates are complete.
