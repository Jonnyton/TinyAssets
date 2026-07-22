## 1. Specify the Repair

- [x] 1.1 Record the live 404, current connector-catalog source of truth, deterministic drift gate, and publication boundary.
- [x] 1.2 Add the `live-mcp-connector-surface` delta for generated registry metadata.

## 2. Prove the Drift

- [x] 2.1 Add a focused test comparing committed `server.json` with the generator's complete deterministic document and prove it fails on the stale URL.
- [x] 2.2 Prove direct `generate_server_json.py --check` fails in the current clean-checkout invocation path before the repair.

## 3. Implement the Repair

- [x] 3.1 Make the generator import the repository's real `tinyassets.connector_catalog` when executed directly.
- [x] 3.2 Regenerate `packaging/registry/server.json` from the current catalog version.
- [x] 3.3 Add the generator `--check` command to the packaging workflow.

## 4. Verify and Land

- [x] 4.1 Run focused connector-catalog tests and the direct generator `--check` command (4 focused tests passed; generator matched).
- [x] 4.2 Run strict OpenSpec validation and `git diff --check` (strict change valid; diff clean).
- [x] 4.3 Verify the generated versioned URL lists the current directory catalog through a read-only live MCP handshake (`mcp_public_canary.py`: OK, 2026-07-22 PT).
- [ ] 4.4 Obtain independent review of the generated artifact, import bootstrap, and CI gate.
- [ ] 4.5 Sync the requirement into the canonical `live-mcp-connector-surface` spec, archive this completed change, and re-run strict validation.
