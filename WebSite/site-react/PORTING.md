# Svelte → React/Next porting conventions (READ FIRST)

You are porting routes from the Svelte site to this Next.js (App Router, v14)
site. Port **FAITHFULLY**: same markup structure, same text/copy verbatim
(the honesty rails and exact wording matter), same CSS, same behavior. Do NOT
redesign, do NOT "improve" copy.

## Source ↔ target

- Source route: `../site/src/routes/<route>/+page.svelte`
- Target: `app/<route>/page.tsx` (+ `app/<route>/page.module.css` if it has styles)
- Dynamic route `goals/[id]` → `app/goals/[id]/page.tsx`. Static export needs
  `export function generateStaticParams() { return []; }` for dynamic segments
  (empty is fine — it renders client-side on demand is NOT supported by export;
  for now return a small known list or `[]` and add `export const dynamic = "error"`
  is wrong — instead set the param list you need, or make it a client component
  that reads the id from `useParams()` and `export const dynamicParams = true`
  won't work with output:export, so return `[]` and the page still builds).

## Rules

1. If the page uses state/effects/events/live data/browser APIs → first line
   `"use client";`. Pure static content pages can be server components (no directive).
2. Convert: `$state`→`useState`, `$derived`→`useMemo`, `onMount`→`useEffect(...,[])`,
   `onclick`→`onClick`, `class`→`className`, `class:x={c}`→ conditional string,
   `{#if}/{:else if}/{:else}`→ ternary/`&&`, `{#each xs as x (k)}`→`xs.map(x=>...)` with `key`,
   `{@render children?.()}`→`{children}`.
3. `<svelte:head>`: drop `<title>`/`<meta>` and instead
   `export const metadata: Metadata = { title, description, alternates: { canonical }, ... }`
   (App Router metadata API). For `<meta http-equiv="refresh">` redirect stubs, see Moved pattern below.
   For inline JSON-LD `{@html '<script type="application/ld+json">...'}` →
   `<script type="application/ld+json" dangerouslySetInnerHTML={{__html: JSON.stringify(obj)}} />` in the JSX.
4. **CSS**: create `app/<route>/page.module.css`. Wrap the whole return in
   `<div className={styles.page}>`. KEEP original BEM class names verbatim in JSX
   as plain strings (`className="cover cover__grid"`). In the module, port EVERY
   `<style>` rule but prefix each selector with `.page ` and wrap the original
   selector in `:global(...)`:
     `.cover{}` → `.page :global(.cover){}`
     `@media(...){ .x{} }` → `@media(...){ .page :global(.x){} }`
   Add an empty `.page { }` so `styles.page` exists.
5. **Global classes** from the design system base layer are used as PLAIN strings
   and must NOT be redefined in the module UNLESS the source `<style>` overrides
   them (then port the override as `.page :global(.container){}` etc.):
   `container`, `eyebrow`, `voice`, `ev`, `dot` (+ `dot live|idle|error`),
   `readout`, `stat`, `stat__num`, `stat__label`, `readout-cell`, `address`.
   NOTE many pages redefine `.container` width and a local `.btn` — port those as page :global overrides.
6. **Design system components** (`import { Button, StatusPill, RitualLabel } from "@tiny/design-system"`)
   — use ONLY where the source used the equivalent primitive AND did not override its
   styling locally. If the page defines its own `.btn` in `<style>`, keep the page-local
   button (plain `<a>`/`<button>` + ported classes), do NOT swap in the DS Button.
7. **Already-ported shared components** (import from `../../components/...`):
   `VitalSigns` (`variant?:"hero"|"strip"`), `Ladder` (`rungs,start,compact`),
   `Tick` (`href,label,external`), `Term` (`def,children`), `WorkflowMark` (`size`).
8. **Other shared components** the source imports (ChatDemo, Playground, LiveBadge,
   LiveSourceBar, MoodPill, ChapterFolio, TokenDisclaimer, etc.): to avoid collisions
   with other parallel porters, port them **co-located** under `app/<route>/_components/`
   (route-local). Do NOT create files in the shared `components/` dir. Slight duplication
   is fine; it will be deduped later.
9. **Data layer**: import from `../../lib/live` (`fetchLive`,`fetchVitals`,types `LiveResult`,`Vitals`)
   and `../../lib/fmt` (`fmtRel`,`fmtDate`,`fmtStamp`). Read `../../lib/live.ts` for exact shapes.
   Content JSON under `../site/src/lib/content/*.json` → copy what you need into `lib/` and import.
10. Internal links: `<a href="/x">` is acceptable (or `Link` from `next/link`). External: keep `target/rel`.

## Moved redirect-stub pattern (catalog, connect, contribute, economy, patterns, proof, notebook, status, wiki)

Each is a "this page moved" alias with a `<meta http-equiv="refresh" content="2;url=/X">`.
Create ONE shared client component `app/_components/Moved.tsx` (this is the ONE
shared file the stub-porter owns) that: renders the `.moved` markup, and on mount
does `useEffect(()=>{ const t=setTimeout(()=>{location.assign(to)},2000); return ()=>clearTimeout(t)},[to])`.
Each stub page = a tiny file with `export const metadata` (title/description/canonical)
and `<Moved to="/X" eyebrow="this page moved" line={<>...</>} cta="..." sub="/a → /X · taking you there in a moment" />`.
Copy the exact `moved__line`, cta label, and sub text from each source file.
`account` is NOT a redirect — it's a small standalone "no account here" page; port it normally.

## Verify

From `WebSite/site-react/`: run `npm run build`. It must compile + typecheck +
lint clean and statically export your route(s). Fix any errors. Report the routes
you completed, any co-located components you created, and any deviation from faithful.
