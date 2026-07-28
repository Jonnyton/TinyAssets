## ADDED Requirements

### Requirement: Hosted Preview Source Pipeline Preserves The Untrusted-Build Boundary

The hosted React preview source pipeline SHALL execute pull-request-controlled
install, test, and build commands only in an unprivileged workflow with
read-only repository permission, no persisted checkout credential, and no
deployment secret. A separate exact-trusted-default-branch workflow SHALL
perform secretless provenance validation and artifact sanitization before a
fresh protected-environment job can receive any Cloudflare credential. When
separately activated, the credentialed job MUST consume only the normalized
static tree and matching deterministic manifest, MUST independently regenerate
and byte-compare that manifest before computing the published SHA-256 from the
regenerated manifest bytes, MUST NOT execute artifact content, and SHALL use
fixed trusted Worker code, Worker name, Wrangler configuration, exact action
revisions, lockfile-pinned Wrangler, and a dedicated preview-only account
credential. Credentialed publication MUST remain disabled until
`activate-hosted-preview-publication` records accepted external isolation proof.

#### Scenario: Pull-request code builds a preview candidate

- **WHEN** a pull request changes site source, dependencies, package scripts, or the unprivileged build workflow
- **THEN** those changes execute without Cloudflare secrets, repository-write or deployment permission, persisted checkout credentials, a persisted/shared cache that crosses the trust boundary, or a shared credentialed runner workspace
- **AND** the workflow uploads only one short-lived attempt-specific static-export candidate

#### Scenario: Any pull request changes repository source

- **WHEN** any pull request is opened, reopened, or synchronized, including one that does not match the hosted-preview build paths
- **THEN** an unfiltered read-only check runs the parsed trust-boundary contract and all preview validator fixtures
- **AND** branch protection can require that check without waiting for a path-filtered workflow that never starts

#### Scenario: A successful same-repository build enters trusted intake

- **WHEN** the trusted-default-branch workflow observes a successful pull-request build
- **THEN** its secretless intake verifies the exact workflow ID/path, repository, one open default-branch pull request, current same-repository head, run attempt, and one non-expired artifact ID with reported size no larger than 25 MiB before retrieval
- **AND** it downloads only that artifact ID from that workflow run
- **AND** it does not present the artifact API's reported digest as independently verified byte provenance
- **AND** platform extraction remains in the secretless time-bounded job before repository entry/directory/depth/path/expanded-byte limits apply

#### Scenario: Intake receives a hostile or malformed artifact

- **WHEN** the artifact contains a symbolic link, hard link, special entry, unsafe or colliding path, literal percent in a path component, file with executable mode bits, package/deployment control, archive-extension file, unexpected extension, missing static-export root, or file/directory/entry/depth/path/expanded-size excess
- **THEN** intake rejects it before any protected environment or Cloudflare credential is loaded
- **AND** it does not execute or copy the rejected entry
- **AND** the exact limits are 10,000 files, 2,000 directories, 12,000 total entries, depth 32, 512 Unicode characters and 1,024 UTF-8 bytes per relative path, 25 MiB per file, and 250 MiB expanded total
- **AND** a valid root contains `index.html`, `404.html`, and `_next/static`

#### Scenario: Intake receives a valid static export

- **WHEN** every candidate entry satisfies the bounded static-file contract
- **THEN** intake copies only regular bytes into a clean tree without execution and emits a sorted SHA-256 manifest
- **AND** intake does not claim that an API-reported artifact digest independently verifies the copied bytes
- **AND** the fresh credentialed job independently revalidates the tree, regenerates the manifest, requires a byte-identical match, then computes the published SHA-256 from those regenerated manifest bytes before staging trusted deployment code

#### Scenario: A sanitized current preview is published

- **WHEN** a separately accepted activation receipt exists and the pull request remains open at the exact validated same-repository head
- **THEN** the protected job installs the exact lockfile-pinned toolchain without lifecycle scripts and uploads an undeployed Worker version under a DNS-bounded base-36 alias derived from PR number, run ID, and attempt
- **AND** it does not deploy that version to shared traffic, create a production route or domain, or use a production-account credential
- **AND** trusted code rejects missing, duplicated, malformed, control-bearing, cross-worker, or cross-subdomain upload receipts before exporting any provider identity
- **AND** a separate least-privilege job rechecks the head before posting the provider-generated immutable version URL, never-reused alias URL, full head SHA, run/attempt, exact source artifact ID, verified sanitized-manifest SHA-256, and Cloudflare version ID
- **AND** a later platform run cannot reuse the run/attempt alias, and the provider-generated version URL remains byte-immutable

#### Scenario: A pull-request head is stale at the pre-upload recheck

- **WHEN** the open pull request no longer has the exact head validated by secretless intake when the pre-upload recheck runs
- **THEN** the protected job fails before starting the credential-bearing upload step
- **AND** no stale preview URL is posted as current review evidence

#### Scenario: A pull-request head changes during publication

- **WHEN** the pull-request head changes after the pre-upload recheck races with an already-starting upload
- **THEN** any resulting upload uses a never-reused alias and immutable version URL, so it cannot repoint earlier evidence
- **AND** the independent comment job rechecks the current head and does not advertise the raced upload as current

#### Scenario: Preview JavaScript requests a blocked service path

- **WHEN** the isolated preview receives a path that canonically equals `/mcp` or a descendant, enters `/.well-known/oauth-*` or `/.well-known/mcp*`, or cannot be safely canonicalized after bounded escape decoding, slash normalization, dot-segment handling, and case folding
- **THEN** the exact trusted Worker runs before asset lookup and returns a no-store `503`
- **AND** a shadowing static `mcp` asset cannot bypass the Worker
- **AND** it neither proxies nor embeds the production MCP origin
- **AND** other canonical requests fall through to the static asset binding

#### Scenario: A fork build completes

- **WHEN** a preview build originates from a fork
- **THEN** build and test evidence may complete without secrets
- **AND** no credentialed public preview publication runs

#### Scenario: The source bootstrap lands before external activation

- **WHEN** this source bootstrap is merged without an accepted `activate-hosted-preview-publication` receipt
- **THEN** the GitHub preview environment holds no publication credential
- **AND** no credentialed hosted preview is accepted as active or proven
- **AND** the successor change and STATUS host-action remain open
