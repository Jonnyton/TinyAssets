## Context

TinyAssets intentionally distributes two MCP products:

| Product | Runtime / transport | Catalog | Authority |
|---|---|---|---|
| Remote TinyAssets | `tinyassets.universe_server`, Streamable HTTP at `https://tinyassets.io/mcp` | Exactly seven: `read_graph`, `write_graph`, `run_graph`, `read_page`, `write_page`, `converse`, `get_status` | WorkOS/OAuth; anonymous public reads and identity-gated mutations/costly work |
| Local MCPB | staged `tinyassets.universe_server` via `packaging/mcpb/server.py`, local stdio | Same seven names, without claiming functional parity | User-selected local data directory; current package does not configure WorkOS and relies on its local process boundary |

The prior design treated `/mcp-directory` as a third remote product with five
handles, separate redaction, different auth-challenge behavior, and versioned
catalog URLs. The host rejected that product split on 2026-07-24. One name and
one remote endpoint avoid two TinyAssets experiences and eliminate catalog,
auth, documentation, and behavior drift.

Current `/mcp` cannot simply replace the old directory URL today:

- its status paths intentionally expose operator diagnostics;
- its server instructions force `converse` and import embodiment behavior;
- per-tool OpenAI OAuth `securitySchemes` and runtime challenge metadata are
  incomplete;
- broad router annotations understate public, overwrite, persistence, cost,
  and provider effects;
- current privacy disclosure is draft/incomplete;
- several clients and Registry metadata still point to `/mcp-directory`.

The migration therefore hardens `/mcp`, moves consumers, proves the real paths,
and removes the old route. The old route does not become a redirect or
indefinite compatibility shim.

Completed MCPB manifest parity remains valid and is preserved.

## Goals / Non-Goals

**Goals:**

- Make `/mcp` the sole remote TinyAssets endpoint and exact-seven contract.
- Make `TinyAssets` the exact durable public name without `DEV` or another
  lifecycle qualifier.
- Make its public status, instructions, auth metadata, annotations,
  descriptions, errors, and privacy disclosures suitable for reviewed hosts.
- Bind Registry, ChatGPT, Claude, and maintained client guidance to `/mcp`.
- Preserve dated `/mcp-directory` evidence as historical truth while
  superseding active guidance.
- Prove supported consumers migrated before removing every directory mount,
  constant, server, and Worker route.
- Preserve local MCPB as a distinct stdio/configuration/identity product.
- Keep all acceptance and migration work free of maintainer compute.

**Non-Goals:**

- No anonymous mutation compatibility path.
- No redirect, proxy alias, auto-scope, or other permanent
  `/mcp-directory` shim.
- No claim that remote OAuth evidence proves local MCPB identity or launch.
- No provider/model execution without requester BYOC or accepted-market
  authority.
- No bulk rewriting of dated audits, archived changes, or historical proof.
- No removal of hidden legacy live tools except through their separately
  gated change.

## Decisions

### Compare the staged MCPB artifact, not two source files

The existing parity gate continues to stage the MCPB, read its staged manifest,
and enumerate middleware-applied tools from the staged runtime in a subprocess.
This proves what users install and catches staging as well as source drift.

### Keep two product contracts explicit

Shared seven-handle names do not make the products equivalent. Remote `/mcp`
is a hosted WorkOS/OAuth resource server. MCPB is a local stdio process with
local directory configuration and its observed local auth posture. Each
requires its own acceptance evidence.

Registry and hosted-chatbot artifacts are remote product metadata and bind only
to `/mcp`. Versioning occurs through artifact/package/registration versions,
not alternate endpoint paths.

### Make canonical status safe by construction

Public `read_graph(target=status)` and `get_status` return a typed allowlist
projection governed by exact `public-status-v1`. It emits only bounded enums,
booleans, counts, fixed action codes, and fixed error text; every object rejects
additional properties. A parse/projection failure returns the fixed safe
failure envelope and never falls back to raw text. Operator logs, sessions,
identities, paths, policy hashes, internal exceptions, and debug fields stay
outside the public MCP result. Authorized operator diagnostics use a separately
reviewed administrative surface rather than changing projection based on a
caller-controlled field. This change does not add an eighth public MCP tool or
a new admin endpoint; it reuses an existing internal operator surface, or a
separate OpenSpec/security-reviewed change must own any new administrative
boundary.

### Make instructions and metadata truthful

Server instructions describe when each tool is relevant without forcing a
call, impersonating a universe, or importing another prompt. `converse` occurs
only from explicit user intent.

Every advertised tool declares security schemes matching runtime behavior.
Public read tools advertise `noauth` plus OAuth; mutating, costly, and
first-contact `converse` handles advertise OAuth only. AuthKit schemes request
only `openid`, `profile`, `email`, and `offline_access`; internal
`tinyassets.*` capabilities remain Resource Server grants rather than OAuth
scopes. Bearer validation pins RS256, issuer, audience/resource, expiry, and a
non-anonymous subject. Founder grants/capabilities and visibility,
ownership, and action/object ACLs are enforced separately before effects.
`org_id` remains identity metadata, not an invented tenant authority boundary.

Router annotations are conservative across every advertised target/action. If
any path publishes externally or overwrites state, the router's open-world or
destructive hint reflects that. Descriptions disclose persistence, public
visibility, provider/data sharing, cost, confirmation, and reversibility.
Errors and results are bounded and secret-free.

### Migrate consumers before removing the route

The Registry manifest is version-bumped and republished for `/mcp`. OpenAI and
Claude submissions are rebuilt for seven tools and OAuth. Maintained Codex,
Cursor, Open WebUI, LibreChat, and other supported client packs migrate and
are re-proven. Hosts unable to support OAuth retain anonymous read-only access
only where the canonical contract permits it; unsupported claims are removed.

Telemetry and proof establish that supported consumers have migrated. Then
`directory_server`, catalog constants, mounts, versioned paths, discovery
copy, and Worker routing are removed together. Requests to the removed path
receive the normal absent-route response; there is no redirect.

Removal additionally requires the Registry current version to be published,
every maintained OpenAI/Claude registration to point to `/mcp` or be explicitly
removed/reclassified, and each external review state to be recorded. Vendor
acceptance is launch evidence, not an unbounded route-retirement dependency.
For a pending or unavailable review, a predeclared decision date records the
registration as pending, unavailable, withdrawn, or unsupported and permits
cutover without an unbounded wait. A predeclared telemetry window records its
exact start, end, evidence source, and zero unexplained maintained callers.
The 2026-07-24 host directive is standing authorization to delete the route
once these objective gates pass. No second discretionary host approval is
required; only a concrete newly discovered supported caller or safety failure
recorded in `STATUS.md` may stop the cutover.

### Preserve history, supersede guidance

Dated proof and audits keep the endpoint they actually tested. Current
runbooks, matrices, submission packets, and registry files receive new
superseding truth. Historical files are not bulk-edited to simulate a migration
that had not happened at their evidence date.

### Fold PR #1522 without restoring stale product claims

Preserve useful TinyAssets naming/provenance corrections, but replace the
three-row and pre-cutover material with a two-row remote/local product matrix.
Never restore the archived five-handle change.

### Accept each product through its real path

Remote acceptance proves exact seven, safe status projection, neutral
instructions, metadata/runtime OAuth agreement, truthful annotations,
anonymous-read and authenticated-write behavior, Registry resolution,
rendered ChatGPT/Claude conversations, supported-client migration,
concurrency, and post-change clean use.

Local MCPB acceptance proves schema, install, stdio launch, exact-seven
enumeration, configuration wiring, observed auth behavior, and usable
provider-free operations from an isolated data directory. Neither proof
substitutes for the other.

## Risks / Trade-offs

- **Status fields leak when schemas grow** — allowlist projection and
  fail-closed parse behavior prevent new raw fields from appearing by default.
- **A seven-tool router understates its riskiest action** — aggregate
  annotations conservatively and split only when no truthful contract is
  possible.
- **Directory removal breaks cached clients** — version and republish metadata,
  collect supported-client migration proof, then remove; do not hide breakage
  with a redirect.
- **OAuth excludes no-login hosts** — preserve only canonical anonymous reads;
  mark unsupported mutation flows honestly.
- **Historical docs look inconsistent** — keep dated evidence immutable and
  add explicit superseding current guidance.
- **MCPB is mistaken for hosted parity** — retain separate configuration,
  identity, and acceptance requirements.
- **Acceptance consumes maintainer quota** — all catalog, auth, redaction, and
  migration checks remain provider-free unless requester authority exists.

## Migration Plan

1. Record the host directive and adapt this change from three products to two.
2. Preserve completed MCPB parity tasks and verify the staged package remains
   exact seven.
3. Add failing tests for safe status projection, neutral instructions,
   security metadata/challenges, truthful annotations/descriptions, and
   bounded failures on canonical `/mcp`.
4. Implement those canonical hardening requirements and finalize matching
   privacy disclosures.
5. Rebuild Registry and ChatGPT/Claude metadata for `/mcp`, exact seven, and
   OAuth; version and publish through reviewed host flows.
6. Migrate and re-prove maintained supported clients. Record unsupported hosts
   or read-only limitations rather than preserving anonymous mutation.
7. Obtain rendered ChatGPT/Claude, Registry, concurrency, and post-change
   evidence; record external review states and apply the predeclared dated
   disposition when a vendor is pending or unavailable; inspect old-route
   usage through a predeclared bounded telemetry window.
8. Remove directory runtime, mounts, constants, catalogs, discovery text,
   Worker routing, and current operational guidance in one reviewed slice as
   soon as the objective migration gates pass.
9. Prove `/mcp-directory*` is absent, `/mcp` remains healthy, and no supported
   registration points at the retired path.
10. Sync canonical specs and archive this change only after all completed
    tasks and evidence are truthful.

## Open Questions

- Which supported third-party hosts cannot complete canonical OAuth and should
  be documented as anonymous-read-only or unsupported?
- What observation window gives sufficient confidence that every maintained
  registration migrated without turning the old route into a permanent shim?
