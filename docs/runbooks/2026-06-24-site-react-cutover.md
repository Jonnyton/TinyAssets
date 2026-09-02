# Runbook — deploy the production site

**Status (2026-09-02):** the React cutover (2026-06-24) is complete and the
Svelte rollback tree is retired. `WebSite/site-react/` is the only site source
for `tinyassets.io`, published manually through
`.github/workflows/deploy-site-react.yml`. `WebSite/site/` and
`deploy-site.yml` were deleted on 2026-09-02.

The operational procedure now lives in `WebSite/DEPLOY.md` (deploy and verify)
and `WebSite/PREVIEW.md` (the preview loop). This runbook keeps the dated
history and the rules that outlived the cutover.

## History

- **2026-06-24** — React (`WebSite/site-react/`, Next.js static export on
  `@tiny/design-system`) replaced the SvelteKit site as the production source.
  Both trees deployed to the same `github-pages` environment and shared the
  `pages` concurrency group, so `deploy-site.yml` was kept dispatch-only as a
  rollback path and every site change carried a Svelte parity step.
- **2026-07-26** — cutover confirmed complete; React had been production for a
  month with no rollback ever dispatched.
- **2026-09-02** — the Svelte tree, `deploy-site.yml`, and the parity step were
  deleted in the website rewrite. Its shared tooling (the public read-contract
  test and the hosted-preview trust boundary) moved to
  `WebSite/site-react/scripts/`, and `deploy-site-react.yml`,
  `preview-worker.yml`, `preview-security.yml` and `preview-worker-deploy.yml`
  were repointed there.

## Rules that still hold

- **Merged is not deployed.** A merge never publishes the site. A host runs
  `deploy-site-react` with `confirm: deploy`, then records the deployed
  revision (`python scripts/deployed_sha.py --assert-contains <sha>`).
- **Rollback is a redeploy.** With one tree, restoring a previous site means
  dispatching `deploy-site-react` on the last good revision of `main`, then
  re-running the canary and rendered checks. Fix forward on `main` afterwards.
- **Evidence boundary.** Deployment proof is the workflow result, the deployed
  revision, `python scripts/mcp_public_canary.py --url https://tinyassets.io/mcp`,
  and rendered browser checks. Platform uptime evidence is labelled separately
  from user-workflow activity, and a community-watch signal is never a
  deployment fallback.
