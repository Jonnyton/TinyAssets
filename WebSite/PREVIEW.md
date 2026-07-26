# Website preview loop — read this first

`WebSite/site-react/` is the current React/Next production source for
`tinyassets.io`. `WebSite/site/` is the retained Svelte rollback source. Make
production edits and build React first, then mirror the intended user-visible
behavior into Svelte and verify rollback parity.

## The preview commands

| Purpose | Command | URL |
|---|---|---|
| Preview the production React source with hot reload | `cd WebSite/site-react; npm run dev` | `http://localhost:3000/` |
| Preview the production-exact React static export | `cd WebSite/site-react; npm run preview` | `http://localhost:4322/` |
| Preview the retained Svelte rollback with hot reload | Double-click `WebSite/preview.bat` | `http://localhost:5173/` |
| Stop the Svelte background preview | Double-click `WebSite/preview-stop.bat` | — |

Run `npm install` or `npm ci` in the applicable site directory before the first
preview. See `WebSite/site-react/PREVIEW.md` for the hosted React preview
options and live-data caveats.

## Edit order

1. Edit `WebSite/site-react/**`.
2. Review the React hot-reload preview at `http://localhost:3000/`.
3. Build the React static export and, when production-exact rendering matters,
   review `http://localhost:4322/`.
4. Apply the corresponding user-visible change to `WebSite/site/**`.
5. Review the Svelte rollback preview at `http://localhost:5173/`.
6. Build and test both trees before requesting deployment.

React is the production candidate. Svelte parity keeps rollback viable; it does
not make Svelte a second production owner.

## Hot reload

Both development servers push saved changes to their own connected browser
tabs. React uses the Next development server on port 3000. Svelte uses Vite on
the fixed port 5173. Every tab connected to the same development server sees
the update.

If a tab needs a manual refresh, treat that as a preview failure worth
investigating. Syntax and compilation failures should be fixed before relying
on the preview.

`preview.bat` is hidden, persistent, and idempotent. Running it again opens the
Svelte preview without starting a second server. It exists for rollback parity;
it is not the production preview.

## Build checks

Production React:

```powershell
cd WebSite/site-react
npm ci
npm run build
```

Retained Svelte rollback:

```powershell
cd WebSite/site
npm ci
npm run check
npm run build
```

Do not use a successful Svelte build to claim the production site is ready.
The React build and rendered React preview are the production evidence.

## Shipping

`WebSite/ship.ps1` transfers the prepared website bundle/branch to GitHub. It
does not build or deploy either site. Merging the branch also does not deploy
the website.

After review and merge, a host manually runs
`.github/workflows/deploy-site-react.yml` with `confirm: deploy`. The
dispatch-only `.github/workflows/deploy-site.yml` is reserved for a deliberate
Svelte rollback.

Follow `WebSite/DEPLOY.md` for the deployment and verification sequence. A
community-watch signal or user-workflow activity is never a deployment
fallback; platform uptime evidence is separate and explicitly labeled.

## Files involved

| File | Role |
|---|---|
| `WebSite/site-react/` | Current production React/Next source |
| `WebSite/site-react/PREVIEW.md` | React local and hosted preview details |
| `WebSite/site/` | Retained Svelte rollback source |
| `WebSite/preview.bat` | Svelte rollback preview launcher |
| `WebSite/preview-stop.bat` | Stops the Svelte preview server |
| `WebSite/ship.ps1` | Pushes the prepared bundle/branch; does not deploy |
| `.github/workflows/deploy-site-react.yml` | Manual current-production deployment |
| `.github/workflows/deploy-site.yml` | Dispatch-only Svelte rollback |
| `WebSite/DEPLOY.md` | Deployment and rollback playbook |
