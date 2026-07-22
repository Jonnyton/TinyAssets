## Context

TinyAssets intentionally serves two MCP catalogs from one codebase:

| Product | Runtime | Advertised catalog |
|---|---|---|
| Live remote connector and local MCPB | `tinyassets.universe_server` | Seven: five graph/page handles, `converse`, `get_status` |
| Registry/ChatGPT directory product | `tinyassets.directory_server` | Five graph/page handles, no catch-all actions |

The split is deliberate. The directory product is narrower and redacts status
for external review; the live/local product includes authenticated conversation
and status. `packaging/mcpb/manifest.json`, however, still lists only the hidden
legacy `universe` and `extensions` tools. The MCPB schema validator checks JSON
shape, not agreement with the imported FastMCP runtime, so current packaging
tests cannot detect this contradiction.

The recovered `WORKFLOW_DESIGN_HANDOFF_FOR_POLSIA.md` compounds the ambiguity:
it says the live handle cutover has not shipped, documents legacy calls, and
predates WorkOS auth. PR #1522 renames that file and fixes product identifiers
but explicitly leaves the technical content stale. It also touches the obsolete
five-handle change being archived, so it cannot independently satisfy this
change.

## Goals / Non-Goals

**Goals:**

- Make MCPB-declared tools exactly match the middleware-applied advertised
  catalog of the runtime copied into the bundle.
- Make catalog parity executable so future runtime additions/removals cannot
  leave install metadata behind.
- Preserve the five-handle directory product and its separately verified
  Registry and ChatGPT artifacts.
- Replace the recovered Polsia snapshot with current, source-linked integration
  guidance that states which product an integrator is using.
- Establish manifest reconciliation as a prerequisite for later legacy-tool
  retirement.

**Non-Goals:**

- No MCP handler, registration, auth, storage, routing, or provider behavior
  changes.
- No removal of hidden legacy live tools or their middleware.
- No expansion of `directory_server` to `converse` or `get_status`.
- No Registry publication, ChatGPT/Claude directory submission, or assertion
  that an external host has accepted the connector.
- No synchronization of the obsolete `mcp-five-handle-surface` delta.

## Decisions

### Compare the staged artifact, not two source files

The parity gate SHALL run the normal MCPB staging path, read the manifest from
the staged directory, and enumerate `mcp.list_tools(run_middleware=True)` from
the staged `tinyassets.universe_server` in a subprocess. This verifies what a
user installs, includes visibility middleware, avoids module-cache pollution,
and catches staging mistakes as well as source drift.

Comparing a hand-maintained constant with the manifest was rejected because it
would create a third catalog. Comparing registered tools with middleware
disabled was rejected because it would incorrectly require hidden legacy tools
in public install metadata.

### Keep product-specific catalogs explicit

MCPB launches `universe_server`, so its manifest declares the seven live/local
handles. The Registry manifest continues to point to the versioned
`/mcp-directory/catalog/<version>` remote and does not acquire a seven-handle
tool list. The ChatGPT packet continues to equal the five tools enumerated by
`directory_mcp`; its existing runtime-parity test remains the authority.

This avoids forcing unlike products into a lowest-common-denominator catalog
and prevents an external directory packet from accidentally advertising
authenticated live-only operations.

### Hidden compatibility tools are not package catalog entries

The six deprecated fat tools are registered internally but filtered from
`tools/list`. They SHALL remain absent from the MCPB `tools` declaration. The
later `retire-legacy-live-mcp-tools` change may unregister them only after this
manifest ships and migration evidence is reviewed.

### Fold PR #1522; do not stack stale content on its rename

Implementation SHALL preserve the rename/provenance corrections from PR #1522
while replacing the stale technical sections in the same resulting file. The
implementation lane must first coordinate PR #1522's disposition; merging its
naming-only task edit into the archived change would recreate a dead active
path and falsely imply the integration guide is current.

The refreshed handoff SHALL use a small current-surface matrix and link to the
canonical OpenSpec/runtime tests instead of copying a large action inventory
that will decay again. It must describe current WorkOS/OAuth boundaries and
must distinguish live-seven from directory-five wherever it gives connection
or tool-selection guidance.

## Risks / Trade-offs

- **Runtime enumeration can import environment-sensitive modules** → Run the
  staged probe in a subprocess with an isolated temporary data directory and
  compare only `tools/list`; fail loudly on import or enumeration errors.
- **The MCPB manifest schema may accept declarations without enforcing runtime
  equality** → Keep schema validation and add the separate semantic parity
  gate; neither substitutes for the other.
- **A seven-handle update could accidentally leak into directory artifacts** →
  Retain the exact-set ChatGPT/directory test and the deterministic Registry
  generator check in the same verification suite.
- **PR #1522 can conflict with the archive and refreshed handoff** → Fold its
  rename/provenance content or close/supersede it before implementation; never
  resolve the conflict by restoring the obsolete active change.
- **Static integration prose will drift again** → Prefer source links and a
  concise product matrix; add assertions for the named handle sets and reject
  pre-cutover claims.

## Migration Plan

1. Confirm the obsolete collapse change is archived with `--skip-specs` and
   coordinate PR #1522 as folded/superseded.
2. Add a failing staged MCPB manifest/runtime parity test demonstrating the
   current `{universe, extensions}` versus seven-handle mismatch.
3. Update the MCPB manifest to the exact seven advertised handles and make the
   staged parity test pass; keep normal MCPB schema validation green.
4. Re-run the Registry generator/equality checks and the ChatGPT/directory exact
   catalog test to prove those products remain five-handle surfaces.
5. Rename and substantively refresh the Polsia handoff, preserving useful
   design intent while removing pre-cutover and pre-WorkOS claims.
6. Run focused tests, strict OpenSpec validation, packaging validation, public
   read-only canaries for both remote products, and the required rendered-host
   acceptance proof for the changed packaged/user-facing metadata. Record
   explicitly if no post-change real-user evidence exists yet.

Rollback is a normal revert of the manifest/handoff implementation commit. It
does not alter runtime registrations or stored data. Reverting the parity gate
alone is not an acceptable steady state because it would restore silent drift.

## Open Questions

- Which MCPB-compatible rendered host is available for final installed-bundle
  acceptance? If none is available, implementation may land only with the
  missing external acceptance called out as a host-owned follow-up; it must not
  claim rendered-host proof.
