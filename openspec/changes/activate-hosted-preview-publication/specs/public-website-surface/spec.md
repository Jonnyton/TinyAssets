## ADDED Requirements

### Requirement: Hosted Preview Publication Activation Requires Proven External Isolation

Hosted preview publication SHALL remain disabled until a merged trusted source
pipeline and independently accepted external isolation receipt exist. The
activation MUST use a dedicated preview-only Cloudflare account, proven
provider-edge Access, and a restricted GitHub environment without production
credentials or TinyAssets-provided compute.

#### Scenario: Activation is attempted before the source bootstrap lands

- **WHEN** the trusted default-branch preview consumer is not merged
- **THEN** the host refuses to configure a GitHub preview credential
- **AND** no branch copy of the trusted consumer is treated as publication authority

#### Scenario: The dedicated preview account is provisioned

- **WHEN** the host inventories the account before activation
- **THEN** it contains the fixed preview Worker and no production Worker, route, custom domain, data store, binding, token, or credential
- **AND** before GitHub activation, its only permitted write credential is one least-privilege preview-only Workers Scripts credential held by the host for the inert bootstrap upload
- **AND** the account's `workers.dev` subdomain and Preview URLs are enabled only for isolated preview use

#### Scenario: The host creates proofable preview hostnames

- **WHEN** real alias and version hostnames are needed before the GitHub credential can be enabled
- **THEN** a host-held preview-account credential uploads one inert trusted bootstrap version under a unique alias
- **AND** the upload contains no pull-request artifact, executes no pull-request code, and does not place the credential in GitHub

#### Scenario: Provider-edge Access is proven

- **WHEN** the fixed base `workers.dev`, inert alias, and inert version hostnames exist
- **THEN** anonymous requests are proven denied and an authorized named or organization reviewer is proven able to load each hostname
- **AND** the policies contain no `Everyone`, `Bypass`, or public-path exception
- **AND** an independent security reviewer accepts a redacted receipt before GitHub environment credential provisioning

#### Scenario: The GitHub preview credential is enabled

- **WHEN** the external isolation receipt has been accepted
- **THEN** a default-branch-restricted, reviewed `react-preview` environment receives only the dedicated preview account ID and least-privilege Workers Scripts token
- **AND** administrator bypass is disabled where the repository plan supports it
- **AND** no production account credential is copied or reused

#### Scenario: The first real pull-request preview is published

- **WHEN** an eligible pull request remains open at its validated current same-repository head
- **THEN** its receipt binds the full head SHA, run and attempt, exact source artifact ID, regenerated-manifest SHA-256, Cloudflare version ID, immutable version URL, and never-reused alias URL
- **AND** a later head cannot repoint the recorded alias or version evidence

#### Scenario: Live blocked-service routing is exercised

- **WHEN** canonical, encoded, slash, backslash, case, dot-segment, trailing-dot or space, malformed, residual-percent, shadow-asset, `/mcp`, `/.well-known/oauth-*`, and `/.well-known/mcp*` requests are sent to the live preview
- **THEN** each blocked or uncanonicalizable path returns a no-store `503` before asset lookup
- **AND** unrelated canonical paths and an ordinary asset load through the static binding
- **AND** the matrix is exercised on the base, alias, and version hostnames

#### Scenario: User-surface acceptance is recorded

- **WHEN** live routing and provenance checks pass
- **THEN** a real browser-rendered reviewer session records the preview behavior
- **AND** post-fix clean-use evidence is recorded, or its absence is stated explicitly in a dated monitoring item

#### Scenario: Publication is stopped or retained evidence is revoked

- **WHEN** an operator removes the GitHub credential
- **THEN** future publication stops without claiming existing versions were deleted
- **AND** disabling Preview URLs or deleting the fixed Worker/account is the documented control for revoking retained version evidence
- **AND** any future retention automation remains an ordinary user-owned, buildable, and remixable composition
