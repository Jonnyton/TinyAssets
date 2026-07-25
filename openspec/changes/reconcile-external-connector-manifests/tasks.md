## 1. Adapt The Authority Contract

- [x] 1.1 Confirm the obsolete five-handle collapse change remains archived with `--skip-specs`.
- [x] 1.2 Record the 2026-07-24 host directive: `TinyAssets` is the only user-facing name, `/mcp` is the sole remote product endpoint, and `/mcp-directory*` retires promptly to ordinary absent-route/404 behavior without a second discretionary approval.
- [x] 1.3 Adapt proposal, design, delta specs, and tasks from three products to two: remote `/mcp` and local MCPB.
- [x] 1.4 Obtain independent architecture, security, and coverage review of the adapted contract before runtime work.
- [x] 1.5 Close superseded PR #1522 after recording its useful naming/provenance corrections here without restoring the retired directory-product premise.
- [x] 1.6 Adapt and strict-validate `retire-legacy-live-mcp-tools` so it depends on this change, removes every directory-preservation requirement/scenario, and leaves directory deletion here; adapt `operator-request-trigger-contract` to bind request-admission invariants once to canonical `universe_server` at `/mcp` and require directory parity implementation/tests to leave during retirement.

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

## 5. Prove The Surviving Product Through Real User Paths

- [ ] 5.1 Prove canonical `/mcp` exact-seven enumeration, safe status projection, neutral instructions, metadata/runtime OAuth agreement, anonymous reads, and authenticated mutation without provider calls.
- [ ] 5.2 Record at least one rendered supported-chatbot conversation against `/mcp` through ChatGPT web Developer Mode or a supported Claude connector surface, including OAuth and at least one safe read plus authorized write/converse path; ChatGPT mobile is not a required gate while OpenAI documents custom MCP apps as web-only. Any provider turn uses requester BYOC or an accepted-market grant, never maintainer credentials or personal limits.
- [ ] 5.3 Submit canonical seven-tool metadata to supported OpenAI and Claude surfaces and record each accepted, published, pending, unavailable, rejected, or withdrawn state. Acceptance/publication is launch evidence after route retirement. A pending or unavailable surface becomes a dated watch item and never preserves `/mcp-directory*`.
- [ ] 5.4 Publish and verify the MCP Registry current version resolving to `/mcp`.
- [ ] 5.5 Record supported Codex, Cursor, Open WebUI, LibreChat, Registry, and other maintained-client dispositions and proofs.
- [ ] 5.6 Record first normal external-user discovery/install/use and matching server evidence, or leave an explicit watch item.
- [ ] 5.7 After removal, monitor ordinary `/mcp-directory*` 404s with exact start/end/evidence source; use observations to repair stale guidance or contact known maintained callers, never to restore a compatibility route.
- [ ] 5.8 Run §14 concurrent-user/load, duplicate/retry, auth-revocation, and cross-account/universe isolation proof on canonical `/mcp`; do not infer an organization-tenant boundary from an informational `org_id` claim.
- [ ] 5.9 Assemble a dated post-retirement record covering registration dispositions, acceptance/publication, 404 monitoring, concurrency/isolation, and risks without recasting evidence as cutover authorization.

## 6. Remove `/mcp-directory` First

- [x] 6.1 Before Sections 3–5, prove provider-free `/mcp` initialize and exact-seven tool enumeration, then remove `directory_server`, directory catalog constants, mounts, versioned catalog paths, and discovery metadata in the same focused slice. Vendor review, Registry publication, rendered-client breadth, telemetry, and canonical hardening do not gate this removal.
- [x] 6.2 Remove `/mcp-directory*` Cloudflare routing and current operational guidance in the same reviewed slice.
- [x] 6.3 Regenerate the Claude plugin mirror and every derived artifact from canonical source.
- [x] 6.4 Add edge and application rejection tests proving every `/mcp-directory*` path returns the ordinary 404 with no mount, handler, `Location`, redirect, proxy, alias, silent translation, 410, or compatibility body.
- [ ] 6.5 Repoint each maintained old registration to `/mcp` or withdraw it, then re-run canonical canaries and start post-removal 404 monitoring. Registry publication and rendered clients remain later evidence.

## 7. Verification, Review, And Foldback

- [ ] 7.1 Run focused runtime, auth, status, annotation, Registry, submission, Worker, MCPB, and client-contract tests plus lint and `git diff --check`.
- [ ] 7.2 Run strict OpenSpec validation and independent architecture/security/diff review.
- [x] 7.3 Update PLAN's distribution substrate only after the approved host direction and required opposite-provider review are recorded.
- [ ] 7.4 Sync delta specs into canonical `live-mcp-connector-surface` and `mcp-connector-distribution` and archive the change only after completed tasks and external evidence are truthful. The planning-only PR row is retired when that PR lands; a separate collision-checked runtime row owns apply work.
- [ ] 7.5 Re-evaluate `retire-legacy-live-mcp-tools` only after this change and local MCPB migration/identity gates are complete.
