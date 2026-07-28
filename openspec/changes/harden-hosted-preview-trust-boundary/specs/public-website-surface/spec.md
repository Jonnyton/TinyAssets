## ADDED Requirements

### Requirement: Hosted Preview Publication Preserves The Untrusted-Build Boundary

The hosted React preview SHALL execute pull-request-controlled install, test,
and build commands only in an unprivileged workflow with read-only repository
permission, no persisted checkout credential, and no deployment secret. A
separate exact-trusted-default-branch workflow SHALL perform secretless
provenance validation and artifact sanitization before a fresh protected-
environment job receives any Cloudflare credential. The credentialed job MUST
consume only the normalized static tree and matching deterministic manifest,
MUST NOT execute artifact content, and SHALL use fixed trusted Worker code,
Worker name, Wrangler configuration, exact action revisions, lockfile-pinned
Wrangler, and a credential belonging to a dedicated preview-only Cloudflare
account.

#### Scenario: Pull-request code builds a preview candidate

- **WHEN** a pull request changes site source, dependencies, package scripts, or the unprivileged build workflow
- **THEN** those changes execute without Cloudflare secrets, write permission, persisted checkout credentials, cache writes, or a shared credentialed runner workspace
- **AND** the workflow uploads only one short-lived attempt-specific static-export candidate

#### Scenario: A successful same-repository build enters trusted intake

- **WHEN** the trusted-default-branch workflow observes a successful pull-request build
- **THEN** its secretless intake verifies the exact workflow ID/path, repository, one open default-branch pull request, current same-repository head, run attempt, and one immutable bounded artifact before retrieval
- **AND** it downloads only that artifact ID from that workflow run

#### Scenario: Intake receives a hostile or malformed artifact

- **WHEN** the artifact contains a symbolic link, hard link, special entry, unsafe or colliding path, executable file, package/deployment control, archive, unexpected extension, missing static-export root, or count/size excess
- **THEN** intake rejects it before any protected environment or Cloudflare credential is loaded
- **AND** it does not execute or copy the rejected entry

#### Scenario: Intake receives a valid static export

- **WHEN** every candidate entry satisfies the bounded static-file contract
- **THEN** intake copies only regular bytes into a clean tree without execution and emits a sorted SHA-256 manifest
- **AND** the fresh credentialed job independently revalidates the tree and requires an identical manifest before staging trusted deployment code

#### Scenario: A sanitized current preview is published

- **WHEN** the pull request remains open at the exact validated same-repository head
- **THEN** the protected job installs the exact lockfile-pinned toolchain without lifecycle scripts and uploads an undeployed Worker version under `pr-<number>`
- **AND** it does not deploy that version to shared traffic, create a production route or domain, or use a production-account credential
- **AND** a separate least-privilege job rechecks the head before posting the isolated URL and exact SHA

#### Scenario: A pull-request head changes before credential use

- **WHEN** the open pull request no longer has the exact head validated by secretless intake
- **THEN** the protected job fails before reading or using the Cloudflare credential
- **AND** no stale preview URL is posted as current review evidence

#### Scenario: Preview JavaScript requests MCP

- **WHEN** the isolated preview receives `/mcp` or any `/mcp/*` request
- **THEN** the exact trusted Worker returns a no-store `503`
- **AND** it neither proxies nor embeds the production MCP origin

#### Scenario: A fork build completes

- **WHEN** a preview build originates from a fork
- **THEN** build and test evidence may complete without secrets
- **AND** no credentialed public preview publication runs

#### Scenario: Preview infrastructure is provisioned

- **WHEN** an operator enables credentialed preview publication
- **THEN** the protected environment is default-branch restricted and holds only a Workers Scripts write token plus account ID for a dedicated Cloudflare preview account
- **AND** that account contains no production Workers, routes, domains, data, or credentials
