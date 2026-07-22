## Context

TinyAssets intentionally distributes three MCP products from one codebase:

| Product | Runtime / entry point | Transport / location | Advertised catalog | Authentication and configuration |
|---|---|---|---|---|
| Remote live connector | `tinyassets.universe_server` | Streamable HTTP at `https://tinyassets.io/mcp` | Seven: `read_graph`, `write_graph`, `run_graph`, `read_page`, `write_page`, `converse`, `get_status` | Production `UNIVERSE_SERVER_AUTH=workos`; anonymous reads remain open and write/costly/admin calls require identity. The registered pre-dispatch write challenges are `write_graph`, `run_graph`, `write_page`, and `converse`. |
| Local MCPB package | staged `tinyassets.universe_server` via `packaging/mcpb/server.py` | Local stdio, launched as `uv run --project ${__dirname} ${__dirname}/server.py` | The same seven names as the remote live connector | Required `tinyassets_data_dir` maps to `TINYASSETS_DATA_DIR`; optional `default_universe` maps to `UNIVERSE_SERVER_DEFAULT_UNIVERSE`. The manifest neither exposes nor sets `UNIVERSE_SERVER_AUTH`, so unset configuration currently selects `DevAuthProvider` (local no-auth), not WorkOS/OAuth. |
| Remote directory-review surface | `tinyassets.directory_server`, mounted by the remote app | Streamable HTTP at `/mcp-directory` and the Registry's current versioned `/mcp-directory/catalog/<version>` URL | Five: `read_graph`, `write_graph`, `run_graph`, `read_page`, `write_page`; no `converse`, `get_status`, hidden fat tools, or catch-all `action` | Inherits remote bearer resolution/write gates, but is excluded from `/mcp`'s missing-token pre-dispatch OAuth challenge. Listing/public reads remain available; anonymous writes receive tool/action-level rejection. Status is `read_graph(target=status)` with directory-safe redaction. |

The split is deliberate. Shared handle names are catalog reuse, not evidence of
transport, auth, configuration, storage, or trust-boundary equivalence.
`packaging/mcpb/manifest.json`, however, still lists only the hidden legacy
`universe` and `extensions` tools. The MCPB schema validator checks JSON shape,
not agreement with the imported FastMCP runtime, so current packaging tests
cannot detect this contradiction.

Catalog parity is not functional parity. With the manifest-provided local
configuration, MCPB selects `DevAuthProvider` and has no resolved actor;
`converse` is advertised but returns `auth_required`. This limitation must be
visible in acceptance and must be resolved or deliberately redesigned before a
shared-runtime legacy retirement can claim the local product is ready.

The recovered `WORKFLOW_DESIGN_HANDOFF_FOR_POLSIA.md` compounds the ambiguity:
it says the live handle cutover has not shipped, documents legacy calls, and
predates WorkOS auth. PR #1522 renames that file and fixes product identifiers
but explicitly leaves the technical content stale. It also touches the obsolete
five-handle change being archived, so it cannot independently satisfy this
change.

## Goals / Non-Goals

**Goals:**

- Specify the remote live connector, local MCPB package, and remote directory
  surface as separate products with non-substitutable acceptance evidence.
- Make MCPB-declared tools exactly match the middleware-applied advertised
  catalog of the runtime copied into the bundle.
- Make catalog parity executable so future runtime additions/removals cannot
  leave install metadata behind.
- Preserve the five-handle directory product and its separately verified
  Registry and ChatGPT artifacts.
- Correct the canonical live-surface spec's stale implication that the
  directory advertises `get_status`; its redacted view is a `read_graph` target.
- Replace the recovered Polsia snapshot with current, source-linked integration
  guidance that states which product an integrator is using.
- Correct the MCPB README's stale source/dependency claims.
- Establish manifest reconciliation as a prerequisite for later legacy-tool
  retirement.

**Non-Goals:**

- No MCP handler, registration, auth, storage, routing, or provider behavior
  changes.
- No attempt to add WorkOS/OAuth to the current local MCPB package or to treat
  its local process boundary as a remote identity boundary.
- No removal of hidden legacy live tools or their middleware.
- No expansion of `directory_server` to `converse` or `get_status`.
- No remote runtime change; the live-surface delta is an as-built wording
  correction only.
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

### Keep all three product contracts explicit

MCPB launches `universe_server`, so its manifest declares the same seven names
as `/mcp`; that catalog parity is the only equivalence asserted. The bundle is
a local stdio process with local directory configuration and a current
dev/no-auth default. The remote live connector remains a Streamable-HTTP
WorkOS resource server. A remote canary cannot prove MCPB launch/configuration,
and an MCPB host run cannot prove the remote WorkOS boundary.

The Registry manifest continues to point to the versioned
`/mcp-directory/catalog/<version>` remote and does not acquire a seven-handle
tool list. The ChatGPT packet continues to equal the five tools enumerated by
`directory_mcp`; its existing runtime-parity test remains the authority. The
directory surface inherits remote bearer resolution and write gates while
retaining its own reviewed schemas and redaction. It is excluded from `/mcp`'s
missing-token pre-dispatch challenge, so anonymous writes reach tool/action-
level rejection rather than an equivalent OAuth-launch response; those
properties are tested rather than inferred from either other product.

This avoids forcing unlike products into a lowest-common-denominator catalog
and prevents an external directory packet from accidentally advertising
authenticated live-only operations.

### Hidden compatibility tools are not package catalog entries

The six deprecated fat tools are registered internally but filtered from
`tools/list`. They SHALL remain absent from the MCPB `tools` declaration. The
later `retire-legacy-live-mcp-tools` change may unregister them only after this
manifest ships and migration evidence is reviewed. Because MCPB stages the
same `tinyassets.universe_server` source, remote telemetry cannot prove local
callers migrated. Retirement also requires installed-host/version evidence and
a resolution or explicit redesign of the local identity/authority limitation;
the later lane must rebuild the stage, not update a nonexistent runtime mirror.

### Fold PR #1522; do not stack stale content on its rename

Implementation SHALL preserve the rename/provenance corrections from PR #1522
while replacing the stale technical sections in the same resulting file. The
implementation lane must first coordinate PR #1522's disposition; merging its
naming-only task edit into the archived change would recreate a dead active
path and falsely imply the integration guide is current.

The refreshed handoff SHALL use a three-row current-surface matrix and link to the
canonical OpenSpec/runtime tests instead of copying a large action inventory
that will decay again. It must describe current WorkOS/OAuth boundaries and
local MCPB configuration/no-auth posture separately, and must distinguish the
remote live seven, local MCPB seven, and remote directory five wherever it
gives connection, auth, or tool-selection guidance.

### Accept each product through its real user path

Acceptance evidence is product-scoped and SHALL NOT be substituted across
rows in the matrix:

- Remote live acceptance proves Streamable-HTTP, the exact seven handles,
  anonymous reads, an OAuth challenge and signed-in write or `converse`, a
  rendered Claude.ai/ChatGPT connector conversation where applicable, and
  post-change clean-use evidence (or an explicit unproven watch item).
- Local MCPB acceptance proves official schema validation, installation and
  stdio launch in an MCPB-compatible host, exact-seven enumeration, required
  data-directory and optional default-universe wiring, and the observed local
  auth mode using an isolated temporary data directory. It records that
  actorless `converse` is currently unavailable instead of calling all seven
  handles operational. It makes no remote canary or WorkOS/OAuth claim.
- Remote directory acceptance proves deterministic Registry generation,
  ChatGPT packet/runtime name-and-annotation parity, status redaction,
  versioned-endpoint behavior, and rendered directory-host behavior under its
  observed auth boundary. It makes no MCPB claim.

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

- **Matching seven-name catalogs could be mistaken for product equivalence** —
  Assert only catalog parity, state transport/auth/config separately, and fail
  the handoff contract check if remote and local rows are collapsed.
- **An acceptance run could consume maintainer provider quota** — Keep catalog,
  launch, configuration, read, and auth-failure proofs provider-free. Any
  future model execution requires requester BYOC or an accepted-market grant;
  without one, hold before provider invocation.

## Migration Plan

1. Confirm the obsolete collapse change is archived with `--skip-specs` and
   coordinate PR #1522 as folded/superseded.
2. Capture three baselines separately: remote `/mcp` seven, staged local MCPB
   seven over stdio, and the versioned remote directory five.
3. Add a failing staged MCPB manifest/runtime parity test demonstrating the
   current `{universe, extensions}` versus seven-handle mismatch.
4. Update the MCPB manifest to the exact seven advertised handles and make the
   staged parity test pass; keep normal MCPB schema validation green.
5. Re-run the Registry generator/equality checks and the ChatGPT/directory exact
   catalog test to prove those products remain five-handle surfaces.
6. Rename and substantively refresh the Polsia handoff, preserving useful
   design intent while removing pre-cutover and pre-WorkOS claims.
7. Correct the MCPB README so it names the staged `tinyassets/` package and its
   actual dependency shape rather than the removed `fantasy_author` mirror.
8. Run focused tests, strict OpenSpec validation, and the separate acceptance
   paths above. Record explicitly which product lacks a rendered host or
   post-change real-user evidence; do not generalize proof from another row.

Rollback is a normal revert of the manifest/handoff implementation commit. It
does not alter runtime registrations or stored data. Reverting the parity gate
alone is not an acceptable steady state because it would restore silent drift.

## Open Questions

- Which MCPB-compatible rendered host is available for final installed-bundle
  acceptance? If none is available, implementation may land only with the
  missing external acceptance called out as a host-owned follow-up; it must not
  claim rendered-host proof.
