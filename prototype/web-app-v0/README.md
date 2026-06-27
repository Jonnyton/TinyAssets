# Web App v0 — SvelteKit Shell Prototype

**Status:** Throwaway scaffold. Proves the structure from spec #35 composes as a real SvelteKit project.
**Purpose:** Demonstrate the 16-surface site map, dual-adapter deploy split, and Supabase client wiring before track B dispatches.
**Out of scope for v0:** real pages (just placeholders), real auth, real Realtime, real accessibility pass.

## Stack (per spec #35 §1)

- **SvelteKit 2.x** with `@sveltejs/adapter-static` (primary) + `@sveltejs/adapter-node` (dynamic routes).
- **TypeScript** throughout.
- **Supabase** via `@supabase/supabase-js` + `@supabase/ssr`.
- **Tailwind** for styling (cheap, small bundle).

## Structure

```
prototype/web-app-v0/
├── README.md
├── package.json
├── svelte.config.js              # dual-adapter config
├── tsconfig.json
├── vite.config.ts
├── src/
│   ├── app.html
│   ├── app.d.ts
│   ├── lib/
│   │   ├── supabase.ts           # Supabase client factory
│   │   └── i18n/
│   │       └── en.json           # English content per #35 §7.6
│   └── routes/
│       ├── +layout.svelte        # shared chrome
│       ├── +page.svelte          # / landing (SSG)
│       ├── catalog/
│       │   └── +page.svelte      # /catalog home (SSG)
│       ├── connect/
│       │   └── +page.svelte      # T1 onboarding (SSG)
│       ├── host/
│       │   └── +page.svelte      # T2 onboarding (SSR)
│       ├── contribute/
│       │   └── +page.svelte      # T3 onboarding (SSG)
│       ├── status/
│       │   └── +page.server.ts   # SSR /status
│       ├── legal/
│       │   └── +page.svelte      # /legal ToS + privacy + license
│       └── account/
│           └── +page.server.ts   # SSR /account (auth-gated)
```

## Running (when node deps install)

```bash
cd prototype/web-app-v0
npm install
npm run dev       # dev server at localhost:5173
npm run build     # dual-adapter build — static to build-static/, node to build-dynamic/
```

## What we're proving

1. **Dual-adapter config works** — `adapter-static` generates `/`, `/catalog/`, `/connect`, `/contribute`, `/legal` as pure static HTML; `adapter-node` bundles `/host`, `/status`, `/account`.
2. **Supabase SSR client wires in** — `@supabase/ssr` session cookie flow works.
3. **i18n scaffold present** — `src/lib/i18n/en.json` has content strings; `[lang]` route prefix reserved in file layout (not wired v0).
4. **Tailwind styles** — minimal CSS setup verified.

## OPEN flags

- Adapter-static vs Cloudflare Pages native adapter — spec #35 §9 Q1 unresolved. v0 uses adapter-static.
- OG image generation library — not included in v0 (spec #35 §9 Q2).
- Full `/catalog/nodes/<slug>` SSG from the `TinyAssets-catalog/` repo — out of scope for v0 scaffold; content source is real in the prod build.
