## 1. Recover prior implementation

- [x] 1.1 Locate the #617 / PR-047 merge SHA via the PR-047 wiki audit pages and `git log` — merge `cfd724bd` ("Collapse directory MCP surface to five handles")
- [x] 1.2 `git show <sha>:workflow/directory_server.py` and recover its 5-handle router + `shape=` dispatch — recovered; current `workflow/directory_server.py` is the live-current descendant (per-universe substrate update) and was used as the forward-port source
- [x] 1.3 Recover the #617 tests; catalog which `api/*` handler each handle/shape mapped to — `tests/test_directory_server.py`; fold-map: read.graph→universe/market/status/extensions, write.graph→market/universe, run.graph→extensions(run_branch), read.page/write.page→wiki

## 2. Implement handles on the live server

- [x] 2.1 Add `read.graph`, `write.graph`, `run.graph`, `read.page`, `write.page` as `@mcp.tool` registrations in `workflow/universe_server.py`
- [x] 2.2 Implement the `shape=`/`target=` dispatcher routing each handle to the CURRENT `workflow/api/*` handlers (rebound to present-day signatures; read.graph target=status uses the full unredacted live status)
- [x] 2.3 Ensure `run.graph` is the only run-producing verb; map `read.page`/`write.page` to the `wiki` read/write handlers
- [x] 2.4 Keep legacy tools registered but hidden from `tools/list` + callable for one release; `_DeprecatedToolVisibility` middleware logs every deprecated-tool call
- [x] 2.5 Mirror all handler/registration changes into `packaging/claude-plugin` (byte-parity; `build_plugin.py` + `invariants_run.py --check mirror-parity` OK)

## 3. Tests

- [x] 3.1 Contract test: `tools/list` (run_middleware=True) returns exactly the 5 handles + get_status (`tests/test_universe_server_five_handles.py`)
- [x] 3.2 Round-trip test per handle/shape (goal write→read; status full vs directory-redacted; unknown-target)
- [x] 3.3 Deprecation test: hidden legacy tool still dispatchable by plain name and emits a deprecation log
- [x] 3.4 `ruff check` clean on touched files; targeted `pytest` green offline (mocked providers). NOTE: one pre-existing baseline failure `test_directory_read_page_schema_advertises_changed_since` (KeyError 'description', FastMCP-3.2/Python-3.14 schema env issue) is red on origin/main, unrelated to this change.

## 4. Canary + drift guard

- [x] 4.1 Extend `scripts/mcp_public_canary.py` with `--assert-handles` (full handshake → tools/list → exactly-5-handles assertion, exit code 4 on drift; unit-tested offline)
- [x] 4.2 Wire the assertion into Hard Rule #11 (AGENTS.md) + a dedicated post-deploy step in `.github/workflows/deploy-prod.yml`

## 5. Gate + deploy

- [~] 5.1 Open PR; record canonical position records for the triple-key gate — PR opened; position records being recorded
- [ ] 5.2 Obtain Codex execution key + Cowork checker key + explicit host key — GATED (external; host + Codex + Cowork)
- [ ] 5.3 Deploy new image; run the public canary against `https://tinyassets.io/mcp --assert-handles`; confirm 5 handles live — GATED on merge/deploy access

## 6. Consumer migration + cleanup

- [ ] 6.1 Update the Polsia handoff doc + any connector manifests to the 5-handle surface — GATED on deploy (the "live" flip is only true post-deploy); `WORKFLOW_DESIGN_HANDOFF_FOR_POLSIA.md` not present in this checkout — locate/confirm with host
- [ ] 6.2 After the migration window, open a follow-up change to remove the deprecated legacy tools and retire `workflow/directory_server.py` — FOLLOW-UP change
