## Context

The live server currently registers thirteen MCP tools: the seven canonical handles plus six legacy fat tools (`universe`, `community_change_context`, `extensions`, `goals`, `gates`, and `wiki`). `_DeprecatedToolVisibility` hides the legacy registrations from `tools/list`, logs calls, and rejects anonymous calls in gating modes. That was an explicitly bounded migration state, not the intended permanent architecture.

Three evidence gaps prevent immediate removal:

1. External manifests and host-facing packets must first be reconciled by `reconcile-external-connector-manifests`.
2. Production telemetry and rendered host proof must show that supported consumers no longer call hidden names; the host must accept the migration evidence before a breaking removal.
3. The current canary requires six handles and merely allows `get_status`, while the canonical contract says exactly seven. The live-surface test proves registration/listing but never calls `run_graph` through MCP and reads the resulting durable run back.

The directory server is an intentional separate reviewed surface. PR #1561 concerns the unrelated legacy stdio process in `tinyassets/mcp_server.py`; PR #1553 concerns authorization inside the directory server. Neither is this live-registration retirement.

Collision inventory observed 2026-07-22, to be rechecked before implementation:

- `tinyassets/universe_server.py` and its packaged mirror overlap open PRs #1560, #1550, #1549, #1493, #1467, #1466, #1465, and #1464.
- `scripts/mcp_public_canary.py` and `tests/test_mcp_public_canary.py` overlap stacked draft PR #1478.
- `tests/test_universe_server_five_handles.py` overlaps stranded PR #1550.
- `tinyassets/directory_server.py` overlaps PRs #1553, #1550, and #1467, but is outside this change's write set regardless.

## Goals / Non-Goals

**Goals:**

- End the migration window only after manifest, telemetry, host, and rendered-client evidence gates pass.
- Leave exactly seven tools in both the live MCP registry and advertised `tools/list` surface.
- Remove `_DeprecatedToolVisibility` because no hidden live registrations remain.
- Preserve internal Python wrapper behavior initially, or migrate every import caller explicitly before deleting a wrapper.
- Make `get_status` required by the public exact-seven canary.
- Prove `run_graph` through a real MCP call and a durable read-back without spending external model compute.

**Non-Goals:**

- Removing, replacing, or folding `tinyassets/directory_server.py`.
- Changing the seven canonical handle schemas, auth policy, primitive behavior, or run semantics.
- Implementing or merging PR #1561's stdio-server fence or PR #1553's directory authorization change.
- Deleting internal implementation functions merely because their former MCP registrations are removed.
- Making runtime or test edits in this specification-only lane.

## Decisions

### 1. Removal is evidence-gated, not date-gated

Implementation SHALL remain blocked until all of the following are durable and reviewed:

1. `reconcile-external-connector-manifests` is landed and external packets no longer instruct clients to call a hidden name.
2. The host records the supported-client matrix and observation window before telemetry is evaluated.
3. Telemetry for that window shows zero hidden-name calls, or identifies every caller and proves each migrated.
4. A rendered chatbot conversation from each host in the accepted matrix succeeds through canonical handles.
5. The host explicitly accepts the breaking removal.

A calendar-only "one release elapsed" test was rejected because it says nothing about actual consumers. Requiring zero lifetime calls was also rejected because historic calls do not block a completed migration; the predeclared observation window prevents cherry-picking.

### 2. Unregister at the MCP boundary before deleting Python behavior

Remove the six `_mcp_* = _register_structured_tool(...)` registrations and remove `_DeprecatedToolVisibility` plus its legacy-name set once nothing else uses them. Keep the underlying Python functions on the first removal pass unless an import/call inventory proves that each function can be deleted or explicitly migrates every caller to the owning API/canonical route. Add no compatibility aliases.

Deleting whole functions immediately was rejected because repository modules may import them directly even though external MCP callers must migrate. Keeping hidden registrations behind a renamed middleware was rejected because it preserves the architectural defect.

### 3. Prove both the advertised set and the underlying registry

The public canary SHALL compare `tools/list` to one exact seven-name set; `get_status` is no longer optional. A local contract test SHALL inspect the server registry with middleware bypassed and prove the same exact seven names. This catches reintroduction of a hidden tool, which an advertised-surface canary alone cannot see.

Inaccurate internal `assert_five_handles*` names SHALL be renamed without aliases when the canary files are implemented. The CLI flag remains `--assert-handles`, so external automation does not need a compatibility shim.

### 4. `run_graph` proof crosses MCP and durable storage boundaries

The proof SHALL start an authenticated in-process MCP client against the real `universe_server.mcp`, call `run_graph` for a deterministic no-provider branch in isolated temporary storage, extract the returned run identifier, then call `read_graph(target="run", run_id=...)` through MCP and observe that same persisted run. Provider/model execution may be replaced with a deterministic test executor, but the MCP registration, `_extensions_impl(action="run_branch")`, run creation, result envelope, and run read path SHALL NOT be stubbed or replaced by AST/schema assertions.

A direct Python call or a `tools/list` assertion was rejected because neither proves the user-visible dispatch round trip.

### 5. Directory and stdio surfaces retain separate ownership

The reviewed `/mcp-directory` server remains narrower and intentionally distinct; its tool set need not become seven. The live retirement SHALL not modify it. PR #1561 may fence `tinyassets/mcp_server.py`, and PR #1553 may repair directory `run_graph` authorization, but neither counts as evidence that the six live registrations were removed.

## Risks / Trade-offs

- **An unobserved external client still calls a hidden name** → predeclare the supported-client matrix/window, inspect telemetry, migrate identified callers, require host acceptance, and retain rollback to the prior image.
- **A Python import caller breaks when a wrapper is removed** → inventory imports and preserve wrappers on the first pass unless every caller is explicitly migrated and tested.
- **`tools/list` stays green while hidden registrations return** → assert exact equality against the middleware-bypassed registry in local tests.
- **A nominal `run_graph` test is vacuous** → require a real MCP call, durable run identifier, and MCP read-back; mutation-check that bypassing run creation makes it fail.
- **Concurrent PRs overwrite or invalidate the implementation** → rerun claim/file collision checks immediately before claiming or broadening runtime files; depend on or wait for live owners rather than editing through them.
- **Rollback reintroduces hidden registrations** → rollback is allowed only as an incident response, must be recorded as contract regression, and reopens the removal lane before green status is claimed.

## Migration Plan

1. Land and externally accept `reconcile-external-connector-manifests`.
2. Record the host-approved client matrix and telemetry observation window; gather hidden-call telemetry and rendered canonical-handle conversations.
3. Obtain explicit host removal approval and independent security/interface review.
4. Refresh `origin/main`, active PRs, worktrees, provider context, and file collision checks. Claim only collision-free runtime/test paths.
5. Add failing tests for middleware-bypassed exact-seven registration, exact-seven public canary behavior, and the MCP-to-durable-run round trip.
6. Remove exactly six live registrations and `_DeprecatedToolVisibility`, preserving or explicitly migrating Python callers; update the packaged mirror.
7. Run focused tests, mutation proof, mirror parity, strict OpenSpec validation, full relevant MCP/auth suites, and independent diff review.
8. Deploy, run the public exact-seven canary, complete rendered chatbot `ui-test` acceptance, and record whether post-fix organic user evidence exists.
9. Roll back to the prior image on regression; record the reintroduced hidden registry state and keep this change open until removal is restored and reverified.

## Open Questions

- Which supported-host matrix and telemetry observation window will the host accept as sufficient migration proof? These must be recorded before measurement begins.
