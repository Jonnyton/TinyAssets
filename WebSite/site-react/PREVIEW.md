# Previewing & approving the React site

Four ways to see changes before they go live. **The live site (tinyassets.io)
is unaffected by all of these** until the host runs the gated cutover
(`docs/runbooks/2026-06-24-site-react-cutover.md`).

## 1. Local hot-reload (fastest, like the old `vite dev`)

```bash
cd WebSite/site-react
npm install        # first time
npm run dev        # → http://localhost:3000
```

Live data (vital signs, goals, graph) works: dev proxies `/mcp` →
`https://tinyassets.io/mcp` server-side (no CORS), the same role the old Svelte
`/mcp-live` proxy played.

## 2. Production-shaped local static preview

```bash
cd WebSite/site-react
npm run preview    # next build + serves the real static export at http://localhost:4322
```

This builds the same static-export source locally; the deploy workflow artifact
is the authoritative production build. Live `/mcp` data does not load here
because localhost has no same-origin endpoint. Use #1 for live data. Hosted PR
previews intentionally block `/mcp` and render checked-in public evidence only.

## 3a. Optional manually maintained GitHub Pages snapshot

**https://jonnyton.github.io/tiny-site-react-preview/** is a manually maintained
snapshot in the separate public repo `Jonnyton/tiny-site-react-preview`, not the
live `tinyassets.io`. It may be stale; verify its published commit before using
it for review. Notes:
- It's a project-pages subpath build (`PAGES_BASE_PATH=/tiny-site-react-preview`),
  so all links are prefixed; nav + in-content links work.
- Live `/mcp` data may not load (cross-origin from github.io); widgets degrade to
  "reading…/asleep" — use `npm run dev` for live data.
- It's a **manual snapshot**, not auto-updating. To refresh after changes:
  ```bash
  cd WebSite/site-react
  MSYS_NO_PATHCONV=1 PAGES_BASE_PATH=/tiny-site-react-preview \
    NEXT_PUBLIC_MCP_PATH=https://tinyassets.io/mcp npm run build
  # re-apply the raw-link prefix fixup + rm out/CNAME, then push out/ to the
  # preview repo's gh-pages branch. For automated PR review, use the isolated
  # Cloudflare Worker version flow below.
  ```

## 3b. Isolated hosted PR preview (after activation)

After the bootstrap is on `main` and the dedicated preview account/environment
is provisioned, each eligible same-repository pull request can get an isolated
URL of the form:

`https://p<pr-base36>-r<run-base36>-a<attempt-base36>-tiny-site-react-preview.<preview-account-subdomain>.workers.dev`

Treat everything rendered at that URL as untrusted review input. The trusted
Worker runs before every asset lookup. It canonicalizes case, escapes, slash
forms, and dot segments, returns no-store `503` for every MCP-equivalent path
and the `/.well-known/oauth-*`, `/.well-known/openid-*`, and
`/.well-known/mcp*` discovery namespaces, and fails closed when a segment
becomes empty after normalization or a path cannot otherwise be safely
canonicalized. Only other canonical paths fall through to static assets.
Sanitized artifacts reject literal-percent path components so every accepted
path is serveable under the same decoding policy. Preview JavaScript therefore
cannot acquire a same-origin bridge to production data.

An independent `preview-security` workflow checks the trust-boundary contract
on every pull request and `main` push. The publication path then has four
isolated authorities:

1. `preview-worker.yml` runs pull-request-controlled installs, tests, and builds
   with a read-only repository token/permission, no deployment secrets, and no
   persisted checkout credential. It uploads only the static `out/` tree.
2. The trusted default-branch `preview-worker-deploy.yml` validates the exact
   workflow, repository, open pull request, current head, and exact artifact ID
   plus bounded metadata without loading an environment or secret. It copies
   only bounded regular static files into a clean tree, records a deterministic
   manifest, and transfers both without claiming an independently verified
   archive digest.
3. A fresh protected-environment job regenerates the manifest from its
   independently revalidated tree, requires a byte-identical match, then hashes
   those regenerated manifest bytes for the published provenance receipt. It
   supplies the Worker program and configuration from its exact trusted commit,
   installs lockfile-pinned deployment tooling without lifecycle scripts,
   rechecks the current pull-request head, and uploads an undeployed Worker
   version under a never-reused alias derived from the PR, run, and attempt IDs.
   A trusted parser rejects ambiguous or malformed Wrangler receipts.
4. A separate least-privilege job rechecks the head before posting the
   provider-generated immutable version URL, alias URL, full SHA, run/attempt,
   exact source artifact ID, verified sanitized-manifest SHA-256, and Cloudflare
   version ID. An API-reported artifact digest is not treated as verified byte
   provenance.

The credentialed upload targets the GitHub environment `react-preview`. It must
not receive credentials until the following isolated infrastructure exists:

- a dedicated Cloudflare **preview account** with no production Workers, routes,
  domains, data, or credentials; enable its `workers.dev` subdomain and create
  the fixed `tiny-site-react-preview` Worker as a one-time host action because
  the workflow deliberately cannot provision or auto-create targets;
- enable Cloudflare Access for this Worker's base `workers.dev` hostname and
  its alias/version Preview URL hostnames, and allow only named reviewers or
  the approved organization; do not configure `Everyone`, `Bypass`, or
  public-path exceptions. These URLs are otherwise public, and arbitrary
  pull-request JavaScript is not an acceptable public hosting surface;
- with a host-held preview-account credential, upload one inert trusted
  bootstrap version under a unique alias without pull-request bytes or a
  GitHub credential, then prove anonymous denial and authorized-reviewer
  loading on the real base, bootstrap alias, and version hostnames;
- environment secret `CLOUDFLARE_PREVIEW_API_TOKEN`, containing a new token with
  only Workers Scripts write permission in that preview account, configured
  only after the Access proof is independently accepted;
- environment variable `CLOUDFLARE_PREVIEW_ACCOUNT_ID`, containing that preview
  account's ID.

Cloudflare Workers write permission is account-scoped, so a token in the
production account is not sufficiently isolated even when the workflow fixes
the Worker name. Never copy or reuse the production token. Restrict the
environment to `main`, require review, and disallow administrator bypass where
the repository plan supports those controls.

Before activation, a qualifying pull request may cause GitHub to materialize an
empty, unprotected `react-preview` environment record. The upload still fails
closed because both preview credential values must be non-empty. Activation
must create or harden that environment record and accept Access proof before
adding either credential.

`workflow_run` uses the workflow definition already present on the default
branch. The trusted workflow therefore must land through this narrow bootstrap
before it can publish previews for a later pull request. Fork pull requests may
build and test without secrets, but they never enter credentialed publication.
Same-repository pull requests are rechecked immediately before credential use
to confirm their current head still matches the validated build.

Each successfully published eligible build uses a never-reused alias and a
provider-generated immutable version URL, so a stale upload cannot change the
bytes behind earlier review evidence.
PR close/merge and one-day GitHub artifact expiry do **not** delete Cloudflare
versions or their version URLs. Cloudflare ages out only alias mappings after
the 1,000 most recently deployed aliases; underlying version URLs remain
Access-controlled retained evidence. Before enabling the GitHub credential,
prove unauthenticated denial and authorized-reviewer loading separately on the
fixed Worker's base `workers.dev` hostname, one inert host-created bootstrap
alias hostname, and its provider-generated version hostname. For incident
response, remove the GitHub environment secret and disable Preview URLs or
delete the dedicated Worker/account. If policy later requires shorter
retention, build it as an ordinary user-owned/remixable maintenance workflow
rather than a privileged TinyAssets loop.

## The hosted approval loop (after activation)

1. A change lands on a branch / PR (made by you or by an agent).
2. When the hosted flow is activated, the trusted
   `preview-worker-deploy.yml` posts an isolated preview URL and exact head SHA
   only after that unprivileged preview build succeeds and the trusted
   provenance, sanitization, upload, and current-head checks complete, provided
   the separately proven Access/environment controls remain active. Other
   repository checks remain independent merge gates. Until then, use local
   preview; the GitHub Pages snapshot is a manual fallback and may be stale.
3. You review the isolated URL as untrusted input; request tweaks or approve.
4. On approval → merge to `main`. **Merging does not auto-publish** — the React
   site only goes live when the host runs the cutover (`deploy-site-react.yml`,
   `confirm: deploy`). Until cutover, `main` just holds the approved React source
   while tinyassets.io stays on Svelte.
