# Previewing & approving the React site

This is the current production source for `tinyassets.io`. These preview paths
do not change the live site; a host publishes the approved React build by
manually running `deploy-site-react.yml` with `confirm: deploy`. See
`docs/runbooks/2026-06-24-site-react-cutover.md`.

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

## 3b. Isolated hosted PR preview (Cloudflare Worker version)

Each eligible pull request gets an isolated URL of the form:

`https://pr-<number>-tiny-site-react-preview.<preview-account-subdomain>.workers.dev`

Treat everything rendered at that URL as untrusted review input. The trusted
Worker deliberately returns `503` for `/mcp` and `/mcp/*`; preview JavaScript
can use only checked-in public evidence and cannot acquire a same-origin bridge
to production data.

Preview publication has three isolated stages:

1. `preview-worker.yml` runs pull-request-controlled installs, tests, and builds
   with read-only repository permission, no deployment secrets, and no persisted
   checkout credential. It uploads only the static `out/` tree.
2. The trusted default-branch `preview-worker-deploy.yml` validates the exact
   workflow, repository, open pull request, current head, and immutable artifact
   identity without loading an environment or secret. It copies only bounded
   regular static files into a clean tree and records a deterministic manifest.
3. A fresh protected-environment job revalidates that manifest, supplies the
   Worker program and configuration from its exact trusted commit, installs
   lockfile-pinned deployment tooling without lifecycle scripts, rechecks the
   current pull-request head, and uploads an undeployed Worker version under the
   fixed `pr-<number>` preview alias. A separate least-privilege job rechecks the
   head before posting or updating the pull-request comment.

The credentialed upload uses the protected GitHub environment `react-preview`.
That environment is restricted to `main`, but it intentionally has no
credentials until the following isolated infrastructure exists:

- a dedicated Cloudflare **preview account** with no production Workers, routes,
  domains, data, or credentials;
- environment secret `CLOUDFLARE_PREVIEW_API_TOKEN`, containing a new token with
  only Workers Scripts write permission in that preview account;
- environment variable `CLOUDFLARE_PREVIEW_ACCOUNT_ID`, containing that preview
  account's ID.

Cloudflare Workers write permission is account-scoped, so a token in the
production account is not sufficiently isolated even when the workflow fixes
the Worker name. Never copy or reuse the production token. Require environment
review and disallow administrator bypass when the repository plan supports
those controls.

`workflow_run` uses the workflow definition already present on the default
branch. The trusted workflow therefore must land through its narrow bootstrap
change before it can publish previews for a later pull request. Fork pull
requests may build and test without secrets, but they never enter credentialed
publication. Same-repository pull requests are publishable only when their
current head still matches the validated build.

## The production approval loop

1. A change lands on a branch / PR (made by you or by an agent).
2. The trusted `preview-worker-deploy.yml` posts the isolated preview URL and
   exact head SHA after the unprivileged build succeeds and every trust-boundary
   check passes. The GitHub Pages snapshot remains the no-Cloudflare fallback.
3. You review the isolated URL as untrusted input; request tweaks or approve.
4. Mirror the intended user-visible behavior into the retained Svelte rollback
   tree and verify its focused build.
5. On approval, merge to `main`. **Merging does not auto-publish.**
6. The host manually runs `deploy-site-react.yml` with `confirm: deploy`, then
   completes the public canary and rendered-browser checks in `WebSite/DEPLOY.md`.

React is always edited and built first for production changes. Svelte parity is
rollback readiness; `deploy-site.yml` remains dispatch-only and is not an
alternate production pipeline.
