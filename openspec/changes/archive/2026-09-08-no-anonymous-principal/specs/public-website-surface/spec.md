## MODIFIED Requirements

### Requirement: Public Views Distinguish Live Reads From The Checked-In Snapshot

The site SHALL carry a checked-in public snapshot (`lib/mcp-snapshot.json`: the
public universe list with `fetched_at`) and SHALL label it as a snapshot with
its date wherever it is shown. Public browser code SHALL NOT attempt a live MCP
read because it has no connector bearer. It SHALL state that live discovery
needs a signed-in connector and MUST NOT relabel snapshot data as live. The
snapshot SHALL be refreshed only by an authenticated `scripts/snapshot-public.mjs`
run, which reads the public projection and fails closed if completeness cannot
be proven.

#### Scenario: A visitor opens commons

- **WHEN** an unsigned browser renders `/commons`
- **THEN** it shows snapshot rows labelled with the snapshot date and the signed-in-connector requirement
- **AND** it makes no MCP request and offers no unauthenticated MCP refresh control

#### Scenario: No public universes exist

- **WHEN** the checked-in snapshot contains no discoverable universes
- **THEN** the page states that there are no public universes in this snapshot and that every universe starts private

#### Scenario: A snapshot record is not explicitly discoverable

- **WHEN** the checked-in snapshot holds a record whose `visibility` is missing, `private`, or any value other than `public`/`metadata_only`
- **THEN** it is dropped before render by `lib/discoverable.js`, rather than shown as public
- **AND** one bad record does not blank the list

#### Scenario: The public list is raw rather than curated

- **WHEN** the snapshot reports working or housekeeping universes as publicly discoverable
- **THEN** `/commons` shows them and says the list is what the endpoint reported rather than a curated gallery
- **AND** the site does not filter them out, which would make its own "what is public" claim false

### Requirement: Browser MCP Reads Use The Public Connector Contract And Only The Public Projection

The public browser SHALL NOT initialize an MCP session or issue any request to
`/mcp`. `lib/live.ts` SHALL expose only `fetchPublicUniverses`, which refuses
with a bounded signed-in-connector message, and `fetchVitals`, which returns an
explicit `authRequired` state without a network call. Live MCP reads SHALL be
performed only by an authenticated connector or account surface. The client
MUST NOT call `get_status`, request goals or runs, embed a bearer, default a
missing visibility to public, or surface untrusted endpoint detail.
`scripts/public-boundary.test.mjs` and `scripts/canonical-mcp-contract.test.mjs`
SHALL enforce this in `npm test`.

#### Scenario: A public browser loads the site

- **WHEN** any public route renders without an authenticated connector context
- **THEN** no MCP session or tool call is created
- **AND** no credential is embedded in or recovered by the static JavaScript

#### Scenario: Code attempts public universe refresh

- **WHEN** public browser code calls `fetchPublicUniverses`
- **THEN** it receives the bounded signed-in-connector refusal without a network request

### Requirement: Reachability And Activity Stay Distinct Operational Truths

The `/fine-print` reachability strip SHALL report that live readings require a
signed-in connector. It MUST NOT describe the protected endpoint as
unreachable, MUST NOT infer an executing run or public activity from snapshot
data, and SHALL NOT offer an unsigned `Refresh MCP` control.

#### Scenario: Public browser opens fine print

- **WHEN** the browser has no connector bearer
- **THEN** the strip reports "sign-in required" for live readings
- **AND** it makes no reachability request and asserts no activity state
