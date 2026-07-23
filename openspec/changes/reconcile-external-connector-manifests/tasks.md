## 1. Resolve lane prerequisites

- [x] 1.1 Confirm `collapse-live-mcp-surface-to-5-handles` has been archived with `--skip-specs`; do not restore or sync its obsolete `mcp-five-handle-surface` delta.
- [ ] 1.2 Coordinate PR #1522 before touching the handoff: preserve its rename/provenance corrections by folding them into this lane or close/supersede it; do not merge its edit to the archived change.
- [ ] 1.3 Record three separate observations: exact-seven `tools/list` from remote `/mcp`, exact-seven middleware-applied enumeration from the staged local MCPB runtime, and exact-five `tools/list` from the current versioned remote directory endpoint. A remote probe SHALL NOT stand in for a local package probe.

## 2. Lock MCPB catalog parity test-first

- [x] 2.1 Add a failing regression test that stages the MCPB artifact and reports the current manifest/runtime mismatch (`{universe, extensions}` versus the seven middleware-advertised handles).
- [x] 2.2 Add a staged subprocess catalog probe to `packaging/mcpb/build_bundle.py` that imports the staged `tinyassets.universe_server`, enumerates `tools/list` with middleware applied, and fails loudly with missing/extra sets when the staged manifest differs.
- [x] 2.3 Isolate the subprocess probe with a temporary TinyAssets data directory and prove import/enumeration failures fail the build rather than being skipped or converted to warnings.
- [x] 2.4 Update `packaging/mcpb/manifest.json` to declare exactly `read_graph`, `write_graph`, `run_graph`, `read_page`, `write_page`, `converse`, and `get_status`; do not declare hidden legacy fat tools.
- [x] 2.5 Make the red parity regression green and retain the official MCPB schema validator as a separate passing check.
- [ ] 2.6 Add launcher/config tests proving the package selects stdio, requires and validates `TINYASSETS_DATA_DIR`, preserves optional `UNIVERSE_SERVER_DEFAULT_UNIVERSE`, and does not expose or set `UNIVERSE_SERVER_AUTH`.
- [ ] 2.7 Prove unset package auth selects `DevAuthProvider` and that default actorless `converse` returns `auth_required` before provider selection/invocation; exact-seven enumeration SHALL NOT be reported as seven operational handles.
- [ ] 2.8 Keep all package/parity/acceptance tests provider-free: no maintainer/platform model, credential, quota, or compute may be supplied or consumed.

## 3. Prove directory products did not widen

- [ ] 3.1 Run the deterministic Registry generator equality check and assert its remote remains the current versioned `/mcp-directory/catalog/<version>` URL, not `/mcp`.
- [ ] 3.2 Run the source/runtime parity test proving `chatgpt-app-submission.json` still equals the five-handle `directory_mcp` catalog and annotations.
- [ ] 3.3 Add only the minimum missing regression coverage needed to make an MCPB-seven edit fail if it leaks `converse`, `get_status`, or a hidden legacy tool into either directory artifact.
- [ ] 3.4 Verify the directory surface inherits remote bearer resolution/write gates but is excluded from `/mcp`'s missing-token pre-dispatch OAuth challenge: listing/public reads remain available and anonymous writes receive the observed tool/action-level rejection. Do not promise `/mcp`-equivalent OAuth UX without rendered proof.

## 4. Replace the stale Polsia handoff

- [ ] 4.1 Rename `WORKFLOW_DESIGN_HANDOFF_FOR_POLSIA.md` to `TINYASSETS_DESIGN_HANDOFF_FOR_POLSIA.md`, preserving the correct provenance/naming work from PR #1522.
- [ ] 4.2 Replace the pre-cutover tool/action guidance with a source-linked three-row product matrix for remote `/mcp` seven, local MCPB stdio seven-name catalog, and remote versioned directory five; identify each endpoint/launch transport separately.
- [ ] 4.3 State product-specific auth/config behavior: remote `/mcp` uses the deployed WorkOS read-open/write-challenged boundary; MCPB requires a local data directory, optionally selects a default universe, defaults to dev/no-auth, and has no WorkOS claim; directory inherits remote bearer resolution/write gates but lacks `/mcp`'s missing-token challenge and redacts status.
- [ ] 4.4 Refresh or remove the dated built-versus-not-built snapshot so the handoff does not present June 2026 state as current truth.
- [ ] 4.5 Add a focused handoff contract check that fails on the old “cutover not live” claim, legacy action-call instructions, any two-product collapse, a WorkOS/OAuth claim for current MCPB, or substitution of one product's acceptance evidence for another.
- [ ] 4.6 Correct `packaging/mcpb/README.md`: remove the stale `fantasy_author/universe_server.py` source claim and the false implication that the staged runtime contains only FastMCP.

## 5. Verification, review, and foldback

- [ ] 5.1 Run focused MCPB build/parity/stdio/config/auth/schema tests, Registry generator checks, ChatGPT/directory exact-set/auth/redaction tests, handoff contract checks, `ruff check` on touched Python, and `git diff --check`.
- [ ] 5.2 Run strict OpenSpec validation and an independent diff review covering catalog correctness, external-surface separation, stale-doc removal, and overengineering.
- [ ] 5.3 Build the MCPB and, using an isolated temporary data directory, obtain MCPB-compatible-host installation, stdio launch, exact-seven enumeration, config wiring, observed auth posture, and safe usable-local-operation evidence. Keep provider execution at zero; if no eligible host is available, record acceptance as host-owned and unproven.
- [ ] 5.4 Run exact-set production probes against remote `/mcp` and the versioned directory endpoint separately; the six-required/optional-status public canary alone is not exact-seven proof. Obtain applicable rendered remote-product evidence under each observed auth contract and record post-change real-user evidence or an explicit watch item.
- [ ] 5.5 Before legacy retirement, record supported MCPB host/version migration evidence and either resolve the local identity/authority gap or approve an explicit local-product redesign. Remote telemetry SHALL NOT substitute for local package migration evidence.
- [ ] 5.6 After implementation and required review land, sync the distribution delta into `mcp-connector-distribution` and the narrow directory-status wording correction into `live-mcp-connector-surface`, archive the change, and only then reconsider `retire-legacy-live-mcp-tools` with all of its telemetry, local-package, host-evidence, and explicit-approval gates intact.
