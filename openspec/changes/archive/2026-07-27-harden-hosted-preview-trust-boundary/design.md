## Context

`preview-worker.yml` previously ran pull-request-controlled package scripts,
built the candidate site, and then used a repository Cloudflare secret from the
same job and workspace. A pull request can change dependencies, lifecycle
scripts, build output, and the workflow itself, so that shape gave untrusted
code a direct path to a write credential.

GitHub loads a `workflow_run` workflow from the default branch. That creates a
usable privilege boundary only after the trusted consumer itself has landed on
`main`; this change is therefore a narrow bootstrap that must precede the
larger cheat-loop retirement PR.

## Goals / Non-Goals

**Goals:**

- Keep pull-request installation, testing, and build fully unprivileged.
- Authenticate one same-repository, open, current pull request and its exact
  successful build artifact ID without loading a deployment secret.
- Convert the untrusted archive into a bounded, normalized static tree and bind
  both trusted jobs to one deterministic manifest; after independent
  revalidation, hash the protected job's regenerated matching manifest for the
  published provenance receipt.
- Limit credential use to an exact trusted toolchain and configuration that
  uploads one undeployed per-run preview version.
- Prevent preview JavaScript from acquiring a same-origin bridge to production
  `/mcp`.
- Make the required external Cloudflare/GitHub custody boundary explicit.

**Non-Goals:**

- Supplying platform compute, model-provider quota, or production credentials.
- Treating hosted preview JavaScript as trusted product code.
- Deploying a preview version to shared traffic, a custom domain, or
  `tinyassets.io`.
- Solving repository-wide secret custody. Same-repository workflow authors can
  still request repository secrets in other workflows until those secrets are
  migrated to protected environments or removed.
- Restoring the retired cheat/community loop. Preview publication is ordinary
  CI composition over generic GitHub and Cloudflare primitives.

## Decisions

### 1. Separate build, intake, upload, and comment authorities

The `pull_request` workflow has read-only contents permission and no secret.
The trusted `workflow_run` consumer begins with a secretless intake job, then a
fresh `react-preview` environment job performs upload. A final job owns only
pull-request comment permission.

The artifact-producing workflow remains path-filtered, but a separate small
`preview-security` workflow runs the parsed workflow/config contract plus all
validator fixtures on every pull request and `main` push. That unfiltered check
can be required by branch protection without leaving unrelated pull requests in
an "Expected" state.

This uses more jobs than a single deploy workflow, but makes artifact handling,
credential use, and GitHub write authority independently reviewable. A shared
job or workspace was rejected because a compromised parser or untrusted build
residue could reach the deployment credential.

### 2. Fail closed on provenance before downloading by exact artifact ID

The intake validator compares the triggering run against the repository's
expected workflow ID/path, repository IDs/names, one open default-branch pull
request, same-repository current head, run attempt, and one non-expired bounded
artifact ID. The workflow then downloads that exact artifact ID from that exact
run. The artifact API's reported digest is metadata, not independent proof of
the downloaded bytes, and is not presented as verified provenance.

Names alone were rejected because retries and ambiguous artifacts can collide.
Current GitHub evidence shows the triggering `pull_request` workflow run's
`head_sha` is the source branch head while its associated-PR payload can drift
to the live PR head. The validator therefore requires run head, associated head,
current PR head, and artifact run head to agree. Historical reruns fail closed.

### 3. Normalize static bytes before entering the environment

The intake validator rejects symbolic and hard links, non-regular entries,
unsafe/colliding paths (including literal percent signs), files with executable
mode bits, package/deployment controls, archive-extension files, unexpected
extensions, missing static-export roots, and count/size excesses.
It copies accepted bytes without executing them and emits a sorted SHA-256
manifest. The upload job independently revalidates the copied tree, regenerates
the manifest, requires a byte-identical match, then computes the published
SHA-256 digest from its regenerated manifest bytes. Intake does not publish or
claim a separately verified content digest.

Trusting `upload-artifact` filtering alone was rejected because the protected
job must enforce its own allowlist and bounds.

### 4. Upload an undeployed version under a never-reused per-run alias

The trusted job uses a DNS-bounded base-36 alias derived from PR number, run ID,
and attempt:
`wrangler versions upload --preview-alias p<pr>-r<run>-a<attempt>`.
It does not call `wrangler deploy`, create a route, or mutate shared production
traffic. Every successfully published eligible build gets a new immutable URL,
so an upload that races a later pull-request push cannot mutate the bytes
behind an earlier review URL. The comment writer independently rechecks the
current head and therefore does not present the raced build as current. It
records the provider-generated immutable version URL plus never-reused alias
URL, full head SHA, run/attempt, exact source artifact ID, verified sanitized-
manifest SHA-256, and Cloudflare version ID.
Wrangler's stdout is treated as untrusted provider output: a dependency-free
trusted parser rejects ambiguous, malformed, control-bearing, cross-worker, or
cross-subdomain receipts before any value reaches a job output or pull-request
comment.

A singleton deployed Worker and a mutable per-PR alias were rejected because
concurrent or stale runs could overwrite an already-reviewed URL.

### 5. Source every executable control from one exact trusted commit

Both trusted jobs check out `${{ github.sha }}` with persisted credentials
disabled. External actions are pinned to exact commits. Wrangler is an exact
lockfile dependency installed with `npm ci --ignore-scripts`; the Worker
program, name, and configuration come only from that trusted checkout.

Dynamic `npx ...@latest`, pull-request configuration, and mutable branch
checkouts were rejected because they expand the credentialed code surface.

### 6. Block production MCP surfaces and hand off external activation

The trusted Wrangler configuration pins static-asset handling and runs the
Worker before every lookup. The Worker repeatedly decodes escapes within a
fixed bound, normalizes slash forms, dot segments, and case, returns a no-store
`503` for every path canonically equivalent to `/mcp` or a descendant and for
the `/.well-known/oauth-*`, `/.well-known/openid-*`, and
`/.well-known/mcp*` discovery namespaces. A segment that becomes empty after
trailing dot/space normalization also fails closed. Only another canonical path
falls through to `ASSETS`; the Worker contains no production origin.

External activation is owned by the successor
`activate-hosted-preview-publication` change. Access is the provider-edge
authority for this fixed Worker. Its base
`workers.dev` hostname is an explicit public origin alongside alias and version
hostnames; all three hostname classes require deny-by-default Access. There is
no custom domain or production route. The Worker does not perform a header-
presence imitation of JWT validation. If a future change adds any route around
Access, that change must first add cryptographic issuer/audience/JWK validation
and fail closed; merely checking for `Cf-Access-Jwt-Assertion` is insufficient.
This source-only bootstrap explicitly blocks credentialed publication until the
successor records live anonymous-deny and authorized-load proofs for the fixed
Worker's base `workers.dev` hostname, one inert host-created alias hostname, and
its version hostname. Repository tests cannot prove that external policy, and
this change does not claim it is provisioned.

A fixed Worker name inside the production account is insufficient because
Workers Scripts write permission is account-scoped. A same-origin production
proxy was rejected because untrusted preview JavaScript could read data that a
reviewer's browser is allowed to reach.

## Risks / Trade-offs

- **[External protection cannot be proved by repository source]** → Keep the
  successor change and STATUS host-action incomplete until the dedicated
  account, protected environment, live run, and rendered URL evidence exist.
- **[Same-repository contributors remain repository-secret trusted]** → This
  workflow references no repository secret; record the broader custody problem
  as a separate P0 rather than overclaiming total repository isolation.
- **[Strict file allowlists can reject a legitimate future asset type]** →
  Extend the allowlist through reviewed code plus hostile and positive tests.
- **[Cloudflare versions are retained after PR close]** → Treat them as
  Access-controlled retained evidence, not deleted/expired previews.
  Cloudflare ages out only alias mappings after the 1,000 newest aliases; the
  underlying version URLs persist. Add ordinary user-owned cleanup automation
  only if policy later requires shorter retention.
- **[Archive expansion occurs before repository validation]** → Cap the
  GitHub-reported archive at 25 MiB, keep intake secretless and time-bounded, and
  apply entry/directory/depth/path/expanded-byte limits immediately after the
  platform action extracts it. This is an ephemeral-runner availability limit,
  not a credential boundary.
- **[A preview can lag the newest failing PR head]** → Every comment includes
  the exact head SHA; successful uploads and comments recheck current head.

## Migration Plan

1. Land this source bootstrap on `main` with no Cloudflare credential
   configured.
2. Leave `activate-hosted-preview-publication` and its STATUS host-action open.
   That successor owns the dedicated account, inert host-created alias/version,
   Access proof, GitHub environment credential, first real PR preview, rendered
   review, post-fix evidence, and revocation procedure.
3. Roll back this source bootstrap by reverting the trusted consumer. The
   unprivileged build remains safe and production is untouched.

## Open Questions

- Whether the repository plan supports mandatory environment reviewers and
  disabling administrator bypass. The successor change owns that decision;
  lack of an equivalent control blocks activation, not this source bootstrap.
- Whether version-retention measurements justify a later user-buildable cleanup
  automation. No privileged TinyAssets cleanup loop is introduced here.
