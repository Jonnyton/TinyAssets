# Runbook — deploy the current React/Next production site

**Status (2026-07-26):** the cutover is complete. `WebSite/site-react/` is the
current production source for `tinyassets.io`. It is published manually through
`.github/workflows/deploy-site-react.yml`. `WebSite/site/` is retained only as
the dispatch-only Svelte rollback source through
`.github/workflows/deploy-site.yml`.

Both workflows deploy to the same `github-pages` environment and share the
`pages` concurrency group. Never run them concurrently, and never add an
automatic push or schedule trigger to the Svelte rollback workflow.

## Production change order

1. Make every production website edit in `WebSite/site-react/` first.
2. Build the React/Next site locally:

   ```powershell
   cd WebSite/site-react
   npm ci
   npm run build
   ```

3. Mirror the intended user-visible behavior into `WebSite/site/` so the
   rollback remains credible, then run its focused checks:

   ```powershell
   cd WebSite/site
   npm ci
   npm run check
   npm run build
   ```

4. Review both previews. React is the production candidate; Svelte parity is
   rollback readiness, not an alternate production lane.
5. Merge the approved source. A merge does not publish the website.

## Manual production deployment

1. In GitHub Actions, run `deploy-site-react`.
2. Enter `deploy` in the confirmation input.
3. Confirm the workflow builds `WebSite/design-system/`, builds the Next static
   export in `WebSite/site-react/out`, and deploys it to `github-pages`.
4. Verify the public surface:

   ```powershell
   python scripts/mcp_public_canary.py --url https://tinyassets.io/mcp
   ```

5. Load `https://tinyassets.io/` in a browser and verify the production routes
   affected by the change. Record the deployed source identity before claiming
   the change shipped; merged is not deployed.

## Rollback to Svelte

Use rollback only for a production regression that requires restoring the
retained Svelte build.

1. Confirm the Svelte source at the selected revision contains the required
   parity and passes `npm run check` plus `npm run build`.
2. Run the dispatch-only `deploy-site` workflow. Set
   `refresh_snapshot=true` only when the rollback specifically requires a fresh
   Svelte MCP snapshot.
3. Re-run the public MCP canary and browser checks.
4. Repair the production React source first, restore parity in Svelte, and
   manually redeploy React through `deploy-site-react`.

Do not re-enable Svelte push or cron triggers. Svelte is a rollback artifact,
not a competing deployment owner.

## Evidence boundary

Deployment proof comes from the React workflow result, the deployed source
identity, the public MCP canary, and rendered browser checks. Platform uptime
evidence must be labeled separately from user-workflow activity. There is no
community-watch fallback for deployment truth.
