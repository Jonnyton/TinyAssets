## Context

`harden-hosted-preview-trust-boundary` supplies a trusted default-branch source
pipeline but deliberately lands with no preview credential. Cloudflare Preview
URLs are public when enabled, aliases can be created only during version
upload, and the fixed `workers.dev` route and Preview URLs must both be placed
behind Access. The external activation receipt is therefore a prerequisite,
not evidence that can be inferred from repository source.

Primary provider references:

- https://developers.cloudflare.com/workers/versions-and-deployments/preview-urls/
- https://developers.cloudflare.com/workers/configuration/routing/workers-dev/
- https://developers.cloudflare.com/cloudflare-one/access-controls/applications/choose-application-type/

## Goals / Non-Goals

**Goals:**

- Prove the dedicated account contains no production resource or credential.
- Prove Access denies anonymous requests and permits an authorized reviewer on
  the base, alias, and immutable version hostname classes.
- Break the alias-proof ordering cycle without exposing pull-request bytes or a
  credential to GitHub.
- Enable the GitHub credential only after independent acceptance of redacted
  infrastructure evidence.
- Verify the first real current-head preview from artifact provenance through
  rendered use and post-fix observation.

**Non-Goals:**

- Reusing a production account, token, route, data binding, or custom domain.
- Deploying a preview version to shared traffic.
- Redesigning the trusted source pipeline.
- Adding a privileged TinyAssets cleanup or preview-management subsystem.
- Recording a token, Access assertion, session cookie, or other reusable
  credential in evidence.

## Decisions

### 1. Source bootstrap is a hard dependency

Activation starts only from the merged trusted default-branch consumer. A
branch copy is not an authority boundary because `workflow_run` trust depends
on the default-branch workflow definition.

### 2. The preview account is structurally separate

The account contains only the fixed preview Worker and no production Worker,
route, custom domain, data store, binding, token, or credential. Before GitHub
activation it may have one least-privilege, preview-only Workers Scripts
credential held by the host solely for the inert bootstrap upload. A fixed
Worker name inside the production account was rejected because Workers Scripts
write permission is account-scoped.

### 3. Provider-edge Access is proven for both route families

The fixed Worker's base `workers.dev` route and its Preview URLs are protected
with named-reviewer or approved-organization allow rules. `Everyone`,
`Bypass`, and public-path exceptions are forbidden. Evidence covers anonymous
denial and authorized loading on every hostname class rather than treating one
successful hostname as proof for the others.

### 4. An inert host upload breaks the proof-order cycle

Aliases exist only during `wrangler versions upload`, so a host-held
preview-account credential creates the fixed Worker and uploads one inert,
trusted bootstrap version under a unique bootstrap alias. This upload contains
no pull-request artifact, executes no pull-request code, and does not place the
credential in GitHub. It exists only to expose the real alias and version
hostnames needed for Access proof.

### 5. GitHub credentials follow accepted Access proof

After independent security review accepts the redacted base/alias/version
receipt, the host configures a main-restricted, reviewed `react-preview`
environment with administrator bypass disabled where supported. It receives
only the dedicated account ID and least-privilege Workers Scripts token.

### 6. First publication proves the whole user path

PR #1812 is rebased after the bootstrap merge. The first accepted publication
binds the current head, exact source artifact ID, regenerated-manifest digest,
Cloudflare version ID, immutable version URL, and never-reused alias. Live
testing covers canonical and adversarial `/mcp`, `/.well-known/oauth-*`, and
`/.well-known/mcp*` paths, a shadow asset, and ordinary assets on the base,
alias, and version hosts. A rendered reviewer session and post-fix clean-use
evidence complete acceptance; absent organic use remains a dated monitoring
item rather than a success claim.

### 7. Retention and revocation remain truthful

Removing the GitHub credential stops future publication but does not delete
versions. Disabling Preview URLs or deleting the fixed Worker/account revokes
retained version evidence. Any later retention automation is an ordinary
user-owned and remixable composition, never a privileged platform loop.

## Risks / Trade-offs

- **[Evidence leaks credentials]** → Store only redacted identifiers,
  timestamps, tested hostnames, policy outcomes, and response classes; never
  store tokens, cookies, or Access assertions.
- **[Access protects only one hostname class]** → Require separate
  base/alias/version anonymous and authorized probes.
- **[Bootstrap content is confused with a PR preview]** → Mark its receipt
  inert and host-owned; never use a PR artifact or advertise it as review
  evidence.
- **[A head changes during publication]** → Keep never-reused aliases,
  immutable version URLs, the pre-credential recheck, and the independent
  comment recheck.
- **[Retained URLs outlive the PR]** → Keep Access active and document
  credential removal versus URL revocation as distinct controls.

## Migration Plan

1. Confirm the source bootstrap is merged and the activation change remains
   open and unsynced.
2. Provision and inventory the preview-only Cloudflare account.
3. Configure Access for the fixed `workers.dev` route and Preview URLs.
4. Create the fixed Worker and inert version/alias with a host-held credential.
5. Capture and independently review base/alias/version Access proof.
6. Configure the protected GitHub environment only after proof acceptance.
7. Rebase PR #1812 and capture the first real current-head publication,
   routing matrix, rendered review, and post-fix evidence.
8. Sync and archive this change only after every activation fact is true.

Rollback removes the GitHub credential to stop future publication. Incident
revocation additionally disables Preview URLs or deletes the fixed
Worker/account.

## Open Questions

- Whether the repository plan exposes mandatory reviewers and administrator
  bypass controls for this environment. If not, credential provisioning stays
  blocked until an equivalent control is approved.
