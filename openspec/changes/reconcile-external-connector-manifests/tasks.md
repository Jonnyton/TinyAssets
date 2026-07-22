## 1. Resolve lane prerequisites

- [ ] 1.1 Confirm `collapse-live-mcp-surface-to-5-handles` has been archived with `--skip-specs`; do not restore or sync its obsolete `mcp-five-handle-surface` delta.
- [ ] 1.2 Coordinate PR #1522 before touching the handoff: preserve its rename/provenance corrections by folding them into this lane or close/supersede it; do not merge its edit to the archived change.
- [ ] 1.3 Re-run the current live and directory `tools/list` probes and record the expected live/local-seven and directory-five catalogs as implementation evidence.

## 2. Lock MCPB catalog parity test-first

- [ ] 2.1 Add a failing regression test that stages the MCPB artifact and reports the current manifest/runtime mismatch (`{universe, extensions}` versus the seven middleware-advertised handles).
- [ ] 2.2 Add a staged subprocess catalog probe to `packaging/mcpb/build_bundle.py` that imports the staged `tinyassets.universe_server`, enumerates `tools/list` with middleware applied, and fails loudly with missing/extra sets when the staged manifest differs.
- [ ] 2.3 Isolate the subprocess probe with a temporary TinyAssets data directory and prove import/enumeration failures fail the build rather than being skipped or converted to warnings.
- [ ] 2.4 Update `packaging/mcpb/manifest.json` to declare exactly `read_graph`, `write_graph`, `run_graph`, `read_page`, `write_page`, `converse`, and `get_status`; do not declare hidden legacy fat tools.
- [ ] 2.5 Make the red parity regression green and retain the official MCPB schema validator as a separate passing check.

## 3. Prove directory products did not widen

- [ ] 3.1 Run the deterministic Registry generator equality check and assert its remote remains the current versioned `/mcp-directory/catalog/<version>` URL, not `/mcp`.
- [ ] 3.2 Run the source/runtime parity test proving `chatgpt-app-submission.json` still equals the five-handle `directory_mcp` catalog and annotations.
- [ ] 3.3 Add only the minimum missing regression coverage needed to make an MCPB-seven edit fail if it leaks `converse`, `get_status`, or a hidden legacy tool into either directory artifact.

## 4. Replace the stale Polsia handoff

- [ ] 4.1 Rename `WORKFLOW_DESIGN_HANDOFF_FOR_POLSIA.md` to `TINYASSETS_DESIGN_HANDOFF_FOR_POLSIA.md`, preserving the correct provenance/naming work from PR #1522.
- [ ] 4.2 Replace the pre-cutover tool/action guidance with a source-linked product matrix that separately lists the live/local seven handles and directory five handles and identifies the correct endpoint for each.
- [ ] 4.3 Replace the pre-WorkOS auth guidance with the current WorkOS/OAuth read/write boundary; remove instructions to call hidden legacy fat tools.
- [ ] 4.4 Refresh or remove the dated built-versus-not-built snapshot so the handoff does not present June 2026 state as current truth.
- [ ] 4.5 Add a focused handoff contract check that fails on the old “cutover not live” claim, legacy action-call instructions, or a missing live-seven/directory-five distinction.

## 5. Verification, review, and foldback

- [ ] 5.1 Run focused MCPB build/parity/schema tests, Registry generator checks, ChatGPT/directory exact-set tests, handoff contract checks, `ruff check` on touched Python, and `git diff --check`.
- [ ] 5.2 Run strict OpenSpec validation and an independent diff review covering catalog correctness, external-surface separation, stale-doc removal, and overengineering.
- [ ] 5.3 Build the MCPB and obtain rendered MCPB-host acceptance for the installed seven-handle catalog when an eligible host is available; otherwise record the missing host-owned acceptance explicitly and do not claim that proof.
- [ ] 5.4 Run read-only production canaries against both `/mcp` and the versioned directory endpoint to prove the metadata/doc change did not alter either runtime; record whether post-change real-user evidence exists.
- [ ] 5.5 After implementation and required review land, sync this delta into `live-mcp-connector-surface`, archive the change, and unblock `retire-legacy-live-mcp-tools` without changing that successor's telemetry/host-evidence gate.
