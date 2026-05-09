---
title: Marketing Site Non-JS Baseline
date: 2026-05-09
author: codex-wiki-design
status: proposed
request_id: WIKI-DESIGN
github_issue: 731
wiki_source: pages/patch-requests/pr-089-marketing-site-at-has-empty-body-until-js-hydrates-ai-fetche.md
scope: design-only; no runtime code in this branch
builds_on:
  - PLAN.md#distribution-and-discoverability
  - PLAN.md#cross-cutting-principles
  - WebSite/site/svelte.config.js
  - WebSite/site/src/routes/+layout.ts
---

# Marketing Site Non-JS Baseline

## 1. Classification

Issue #731 is a project-design request. The reported failure is user-visible
like a bug, but the filing explicitly asks for an architectural/design response
at the marketing-site layer, sibling to MCP endpoint discovery affordance work.
This note defines the design contract for the later runtime change.

## 2. Current Evidence

Local source evidence on 2026-05-09:

- `WebSite/site/svelte.config.js` uses `adapter-static`.
- `WebSite/site/src/routes/+layout.ts` sets `prerender = true`.
- `npm run build` from `WebSite/site/` produced `build/index.html`.
- The generated root HTML body contained non-trivial homepage copy, including
  `Workflow`, `/connect`, `/wiki`, `/graph`, and `tinyassets.io/mcp`.

That means the current source tree can produce a non-empty static root. The
design gap remains worth recording because the project has no explicit release
contract or build gate preventing a future SPA-only regression, and the filed
issue may have observed a deployed artifact, stale build, or earlier site state.

## 3. Problem

The marketing root at `/` is part of the product's discoverability surface. It
is the page most likely to be fetched by AI crawlers, link unfurlers, search
indexers, accessibility tooling, terminal browsers, and security scanners before
any JavaScript runs.

If the HTML response only contains the Svelte shell and depends on hydration to
render meaningful copy, those clients see an empty product. That breaks the
same product promise the site is trying to communicate: Workflow should be
usable and inspectable through standard surfaces, not only through one hydrated
browser path.

The current source configuration is the right substrate. The missing contract
is a release gate that treats prerendered body content as a first-class
artifact, not an incidental build output.

## 4. Design Contract

The marketing root MUST ship a meaningful non-JS baseline.

For `/`, "meaningful" means the built `index.html` body contains enough plain
HTML text and links for a non-JS client to understand:

1. What Workflow is.
2. How to connect through the MCP endpoint.
3. Where to inspect live project/wiki/status surfaces.
4. That client-side refreshes enhance the page but are not required for the
   first explanation.

Hydration may improve freshness, controls, graphs, and live refresh behavior.
Hydration must not be the only path to the core marketing explanation.

This is a marketing-site invariant, not a new daemon primitive and not a new
MCP action.

## 5. Minimal Implementation Path

The smallest useful runtime change should stay inside `WebSite/site/`:

1. Keep static prerendering enabled for `/`.
2. Ensure the home route renders baseline copy from build-time data before
   `onMount` or browser-only fetches run.
3. Treat live MCP/GitHub refresh data as progressive enhancement over baked
   snapshots.
4. Add a build-time assertion that parses `build/index.html` and fails if the
   body lacks required phrases and links.

The likely target is the home route and its landing components:

- `WebSite/site/src/routes/+page.svelte`
- `WebSite/site/src/lib/components/LiveLensPanel.svelte`
- `WebSite/site/src/lib/live/project.ts`

Avoid introducing a parallel static homepage unless the existing Svelte route
cannot satisfy the invariant. Duplicating the page creates copy drift and would
make the marketing surface less trustworthy over time.

## 6. Acceptance Checks

A runtime implementation should pass these checks before merge:

1. `npm run build` from `WebSite/site/`.
2. A no-JS body assertion against `WebSite/site/build/index.html`:
   - body text length is non-trivial;
   - contains "Workflow";
   - contains "MCP" or the connector URL;
   - contains at least one crawlable internal link such as `/connect`,
     `/wiki`, `/status`, or `/graph`;
   - contains no "loading" placeholder as the primary body content.
3. A browser check with JavaScript disabled or a plain HTML fetch, proving the
   first viewport contains readable product copy.
4. A normal hydrated browser check, proving the live refresh controls still
   work and no layout regression was introduced.

For public-surface release, final acceptance still needs rendered chatbot or
site-path evidence per AGENTS.md if the deployed page or connector-facing copy
changes.

## 7. Fit With PLAN.md

This follows the Distribution And Discoverability principle because `/` is a
distribution wrapper around the same Workflow substrate. A crawler-readable
homepage helps standard discovery surfaces understand the product without
changing the portable core.

It follows the Cross-Cutting Principles because harness and tool surfaces are
part of the cognition stack. An AI fetcher cannot reason from content that only
exists after hydration. The page should expose its durable explanation as
ordinary HTML, then let JavaScript add live evidence.

It follows the minimal-primitives rule because the fix is a website release
invariant and build check over existing SvelteKit prerendering. No new MCP verb,
daemon route, scheduler behavior, or storage model is needed.

## 8. Non-Goals

- No redesign of the marketing site.
- No change to the MCP endpoint contract.
- No new wiki or daemon action.
- No migration away from SvelteKit solely for this issue.
- No duplicated hand-maintained static homepage unless the existing prerendered
  route cannot satisfy the baseline.

## 9. Open Questions

1. Should the no-JS assertion apply only to `/`, or to every top-level
   marketing route in `svelte.config.js` prerender entries?

   Recommendation: start with `/`, `/connect`, and `/wiki` after the root fix
   proves stable.

2. Should the assertion live as a standalone Node script or inside Playwright?

   Recommendation: standalone Node script for the HTML body contract, with
   Playwright reserved for rendered visual checks.

3. What exact phrase set should be required?

   Recommendation: require concepts, not brittle marketing copy. Use stable
   tokens such as `Workflow`, `/connect`, and `tinyassets.io/mcp` rather than
   complete sentences.

## References

- Issue #731
- `PLAN.md` Distribution And Discoverability
- `PLAN.md` Cross-Cutting Principles
- `WebSite/site/svelte.config.js`
- `WebSite/site/src/routes/+layout.ts`
