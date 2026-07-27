# Deploy `tinyassets.io`

**Current production:** `WebSite/site-react/` (React/Next static export),
published manually by `.github/workflows/deploy-site-react.yml`.

**Retained rollback:** `WebSite/site/` (SvelteKit static build), published only
by an explicit dispatch of `.github/workflows/deploy-site.yml`.

Both workflows deploy to the same `github-pages` environment and share the
`pages` concurrency group. Never run them concurrently. Neither source merge is
deployment proof.

## Before a production deployment

1. Make production edits in React first and build them:

   ```powershell
   cd WebSite/site-react
   npm ci
   npm run build
   ```

2. Review the React development and production-exact previews described in
   `WebSite/site-react/PREVIEW.md`.
3. Mirror the intended user-visible behavior into the retained Svelte rollback
   tree and verify it:

   ```powershell
   cd WebSite/site
   npm ci
   npm run check
   npm run build
   ```

4. Review the relevant Svelte rollback routes through `WebSite/preview.bat`.
5. Merge the approved source through the normal review path.

The Svelte parity check protects rollback quality. It does not replace the
React production build or authorize a Svelte deployment.

## Publish the React production site

1. Open GitHub Actions and select `deploy-site-react`.
2. Choose the merged production revision.
3. Run the workflow with `confirm` set to `deploy`.
4. Confirm the build job produces `WebSite/site-react/out` and the deploy job
   succeeds in the `github-pages` environment.
5. Record the deployed source identity. A green merge or local build alone is
   not a shipped result.

## Verify production

Run the public MCP canary after the deployment:

```powershell
python scripts/mcp_public_canary.py --url https://tinyassets.io/mcp
```

Then load `https://tinyassets.io/` in a browser and exercise the routes and
controls changed by the deployment. Verify rendered content, navigation,
console errors, and meaningful live-data or explicit empty states.

Deployment evidence is the workflow result, deployed source identity, public
canary, and rendered browser result. Platform uptime evidence must be labeled
separately from user-workflow activity. Do not substitute a community-watch
signal or workflow-activity card for deployment verification.

## Roll back to Svelte

Use the Svelte workflow only when an explicit production rollback is required.

1. Select a revision whose Svelte tree has the required parity.
2. Run `npm run check` and `npm run build` in `WebSite/site`.
3. Dispatch `deploy-site`. Set `refresh_snapshot=true` only if the rollback
   specifically requires a freshly baked Svelte MCP snapshot.
4. Re-run the public canary and rendered browser checks.
5. Fix the React production source first, restore Svelte parity, and manually
   redeploy React through `deploy-site-react`.

Do not add push or schedule triggers to `deploy-site.yml`. Svelte is a
dispatch-only rollback artifact, not the current deployment owner.

The dated operational history and workflow rationale remain in
`docs/runbooks/2026-06-24-site-react-cutover.md`, updated to reflect the
completed cutover.
