// Per-goal detail is a dynamic client-side route. The static adapter can't
// prerender an open-ended :id set, so we opt this route OUT of the layout's
// prerender=true. adapter-static's fallback (404.html) hydrates this route
// client-side on GitHub Pages — the page paints from the baked snapshot, then
// upgrades live via goals action=get.
export const prerender = false;
export const ssr = false;
