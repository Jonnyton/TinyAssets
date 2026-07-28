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
  successful build artifact without loading a deployment secret.
- Convert the untrusted archive into a bounded, normalized static tree and bind
  both trusted jobs to one deterministic manifest.
- Limit credential use to an exact trusted toolchain and configuration that
  uploads one undeployed per-PR preview version.
- Prevent preview JavaScript from reaching production `/mcp`.
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

This uses more jobs than a single deploy workflow, but makes artifact handling,
credential use, and GitHub write authority independently reviewable. A shared
job or workspace was rejected because a compromised parser or untrusted build
residue could reach the deployment credential.

### 2. Fail closed on provenance before downloading by exact artifact ID

The intake validator compares the triggering run against the repository's
expected workflow ID/path, repository IDs/names, one open default-branch pull
request, same-repository current head, run attempt, and one non-expired bounded
artifact with a SHA-256 digest. The workflow then downloads that exact artifact
ID from that exact run.

Names alone were rejected because retries and ambiguous artifacts can collide.
The workflow run's synthetic merge SHA is allowed, while the associated PR head
must match the current PR head and the artifact must match the workflow-run SHA.

### 3. Normalize static bytes before entering the environment

The intake validator rejects symbolic and hard links, non-regular entries,
unsafe/colliding paths, executable files, package/deployment controls, archives,
unexpected extensions, missing static-export roots, and count/size excesses.
It copies accepted bytes without executing them and emits a sorted SHA-256
manifest. The upload job independently revalidates the copied tree and requires
an identical manifest.

Trusting `upload-artifact` filtering alone was rejected because the protected
job must enforce its own allowlist and bounds.

### 4. Upload an undeployed per-PR version alias

The trusted job uses `wrangler versions upload --preview-alias pr-<number>`.
It does not call `wrangler deploy`, create a route, or mutate shared production
traffic. Deploy runs serialize per pull request; queued stale runs fail the
current-head check instead of racing a newer alias update.

A singleton deployed preview Worker was rejected because concurrent pull
requests would overwrite one another and a stale run could become the shared
review surface.

### 5. Source every executable control from one exact trusted commit

Both trusted jobs check out `${{ github.sha }}` with persisted credentials
disabled. External actions are pinned to exact commits. Wrangler is an exact
lockfile dependency installed with `npm ci --ignore-scripts`; the Worker
program, name, and configuration come only from that trusted checkout.

Dynamic `npx ...@latest`, pull-request configuration, and mutable branch
checkouts were rejected because they expand the credentialed code surface.

### 6. Block production MCP and isolate the Cloudflare account

The trusted Wrangler configuration intercepts `/mcp` and `/mcp/*` before static
asset lookup. The trusted Worker returns a no-store `503` and contains no
production origin. The environment token must belong to a dedicated Cloudflare
preview account containing no production Workers, routes, domains, data, or
credentials.

A fixed Worker name inside the production account is insufficient because
Workers Scripts write permission is account-scoped. A same-origin production
proxy was rejected because untrusted preview JavaScript could read data that a
reviewer's browser is allowed to reach.

## Risks / Trade-offs

- **[External protection cannot be proved by repository source]** → Keep the
  task incomplete until the dedicated account, protected environment, live run,
  and rendered URL evidence are recorded.
- **[Same-repository contributors remain repository-secret trusted]** → This
  workflow references no repository secret; record the broader custody problem
  as a separate P0 rather than overclaiming total repository isolation.
- **[Strict file allowlists can reject a legitimate future asset type]** →
  Extend the allowlist through reviewed code plus hostile and positive tests.
- **[Per-PR aliases consume Cloudflare versions]** → Use one stable alias per PR,
  one-day GitHub artifacts, and a later generic cleanup automation if measured
  retention requires it.
- **[A preview can lag the newest failing PR head]** → Every comment includes
  the exact head SHA; successful uploads and comments recheck current head.

## Migration Plan

1. Land this bootstrap on `main` with no Cloudflare credential configured.
2. Create a dedicated Cloudflare preview account and least-privilege Workers
   Scripts token; enable its `workers.dev` subdomain and create the fixed
   `tiny-site-react-preview` Worker as a one-time host action. The workflow
   deliberately disables provisioning and target auto-creation.
3. Configure the `react-preview` GitHub environment for `main`, add the preview
   account ID/token, require review, and disable admin bypass where supported.
4. Rebase PR #1812 onto the bootstrap merge so its unprivileged build can
   trigger the trusted default-branch consumer.
5. Record the first real per-PR URL, blocked `/mcp` response, rendered browser
   review, and later post-fix use evidence.
6. Roll back by removing the environment credential or reverting the trusted
   consumer; the unprivileged build remains safe and production is untouched.

## Open Questions

- Whether the repository plan supports mandatory environment reviewers and
  disabling administrator bypass. Lack of those controls blocks credential
  provisioning, not the source-only bootstrap.
- Whether version-retention measurements justify a later user-buildable cleanup
  automation. No privileged TinyAssets cleanup loop is introduced here.
